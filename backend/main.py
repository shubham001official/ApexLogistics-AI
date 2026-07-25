# backend/main.py

import os
import random
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import xgboost as xgb
import pandas as pd
import httpx
from dotenv import load_dotenv
from pathlib import Path
from neo4j import GraphDatabase
from backend.agent_core import supply_chain_app

# Load DB credentials
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Initialize FastAPI
app = FastAPI(
    title="ResiliNet-IN API Engine",
    description="Proactive Spatial AI & Autonomous Logistics Rerouting",
    version="3.0.0",
)

# Deployment-ready CORS
FRONTEND_URL = os.getenv("NEXT_PUBLIC_API_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Neo4j Driver
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

# Load ML Model
model = xgb.XGBClassifier()
MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "ml_models", "xgboost_risk_model.json"
)
try:
    model.load_model(MODEL_PATH)
    print(f"✅ XGBoost Risk Model loaded from {MODEL_PATH}")
except Exception as e:
    print(f"⚠️ Warning: Could not load model. Error: {e}")


# --- PYDANTIC SCHEMAS ---
class TelemetryPayload(BaseModel):
    route_id: str = Field(..., json_schema_extra={"example": "JNPT_TO_CHAKAN"})
    distance_km: float = Field(..., json_schema_extra={"example": 136.67})
    base_hours: float = Field(..., json_schema_extra={"example": 1.75})
    rainfall_mm: float = Field(..., json_schema_extra={"example": 18.5})
    wind_speed_kmh: float = Field(..., json_schema_extra={"example": 45.0})
    toll_queue_m: float = Field(..., json_schema_extra={"example": 450.0})
    breakdown_flag: int = Field(..., json_schema_extra={"example": 0})


class ReroutePayload(BaseModel):
    impacted_route: str = Field(..., json_schema_extra={"example": "JNPT_TO_CHAKAN"})
    destination_hub: str = Field(
        ..., json_schema_extra={"example": "CHAKAN_AUTO_CLUSTER"}
    )
    original_cost: float = Field(..., json_schema_extra={"example": 150000.0})


class ShipmentCreate(BaseModel):
    po_id: str = Field(..., json_schema_extra={"example": "PO_SUP_CHA_1_1"})
    current_route: str = Field(..., json_schema_extra={"example": "JNPT_TO_CHAKAN"})


class ShipmentUpdate(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "DELAYED"})


class ChaosPayload(BaseModel):
    route_id: str = Field(..., json_schema_extra={"example": "JNPT_TO_CHAKAN"})


class RerouteCommitPayload(BaseModel):
    shipment_id: str = Field(..., json_schema_extra={"example": "SHP_PO_SUP_CHA_1_1"})
    new_supplier_id: str = Field(..., json_schema_extra={"example": "SUP_CHA_3"})
    new_cost: float = Field(..., json_schema_extra={"example": 172500.0})
    impacted_route: str = Field(..., json_schema_extra={"example": "JNPT_TO_CHAKAN"})


# --- HELPERS ---
def parse_route(route_id: str):
    """Safely extracts source/dest prefixes for fuzzy graph matching."""
    if "_TO_" in route_id:
        parts = route_id.split("_TO_")
        return parts[0].split("_")[0], parts[1].split("_")[0]
    return "JNPT", "CHAKAN"  # Default fallback


# --- SHIPMENT CRUD ENDPOINTS ---
@app.get("/api/v1/shipments")
async def get_active_shipments():
    query = """
    MATCH (sh:Shipment)-[:FULFILLS]->(po:PurchaseOrder)<-[:SUPPLIES]-(sup:Supplier)
    RETURN sh.id AS id, sh.status AS status, sh.current_route AS route, 
           po.id AS po_id, po.amount_inr AS value, sup.name AS supplier
    ORDER BY sh.id DESC
    """
    results = []
    try:
        with neo4j_driver.session() as session:
            records = session.run(query)
            for record in records:
                results.append(record.data())
        return {"shipments": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/shipments")
async def create_shipment(payload: ShipmentCreate):
    shipment_id = f"SHP_MANUAL_{os.urandom(2).hex().upper()}"
    query = """
    MATCH (p:PurchaseOrder) WHERE p.id CONTAINS 'CHA' OR p.id CONTAINS 'SRI'
    WITH p LIMIT 1 // Grab any valid PO for the demo
    MERGE (sh:Shipment {id: $shipment_id})
    SET sh.status = 'IN_TRANSIT', sh.current_route = $route, sh.risk_score_override = 0.0
    MERGE (sh)-[:FULFILLS]->(p)
    RETURN sh.id AS id
    """
    try:
        with neo4j_driver.session() as session:
            result = session.run(
                query, shipment_id=shipment_id, route=payload.current_route
            )
            record = result.single()
            return {"message": "Shipment created", "shipment_id": record["id"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/shipments/{shipment_id}")
async def update_shipment(shipment_id: str, payload: ShipmentUpdate):
    query = (
        "MATCH (sh:Shipment {id: $shipment_id}) SET sh.status = $status RETURN sh.id"
    )
    try:
        with neo4j_driver.session() as session:
            session.run(query, shipment_id=shipment_id, status=payload.status)
            return {"message": "Updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/shipments/{shipment_id}")
async def delete_shipment(shipment_id: str):
    query = "MATCH (sh:Shipment {id: $shipment_id}) DETACH DELETE sh"
    try:
        with neo4j_driver.session() as session:
            session.run(query, shipment_id=shipment_id)
            return {"message": "Deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- LIVE TELEMETRY & CHAOS ENDPOINTS ---
@app.get("/api/v1/telemetry/live/{route_id}")
async def get_live_telemetry(route_id: str):
    src, dst = parse_route(route_id)
    graph_query = """
    MATCH (a:Node)-[r:CONNECTED_VIA]->(b:Node)
    WHERE a.id STARTS WITH $src AND b.id STARTS WITH $dst
    RETURN a.lat AS lat, a.lon AS lon, r.distance_km AS dist, r.avg_transit_hours AS hours,
           CASE WHEN r.is_blocked IS NOT NULL THEN r.is_blocked ELSE false END AS blocked
    LIMIT 1
    """
    try:
        with neo4j_driver.session() as session:
            record = session.run(graph_query, src=src, dst=dst).single()

            if not record:
                lat, lon, dist, hours, blocked = 18.9490, 72.9490, 136.67, 1.75, False
            else:
                lat, lon, dist, hours, blocked = (
                    record["lat"],
                    record["lon"],
                    record["dist"],
                    record["hours"],
                    record["blocked"],
                )

        # Safe Weather API Call (Prevents 500 Crashes from Rate Limits)
        actual_rainfall, actual_wind = 0.0, 0.0
        try:
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=precipitation,wind_speed_10m"
            async with httpx.AsyncClient() as client:
                resp = await client.get(weather_url, timeout=3.0)
                if resp.status_code == 200:
                    weather_data = resp.json()
                    current = weather_data.get("current", {})
                    actual_rainfall = current.get("precipitation", 0.0) or 0.0
                    actual_wind = current.get("wind_speed_10m", 0.0) or 0.0
        except Exception:
            pass  # Silently fallback to 0.0 if API fails

        if blocked:
            return {
                "route_id": route_id,
                "distance_km": dist,
                "base_hours": hours,
                "rainfall_mm": 55.0,
                "wind_speed_kmh": 85.0,
                "toll_queue_m": 1200.0,
                "breakdown_flag": 0,
            }

        return {
            "route_id": route_id,
            "distance_km": dist,
            "base_hours": hours,
            "rainfall_mm": actual_rainfall,
            "wind_speed_kmh": actual_wind,
            "toll_queue_m": float(random.randint(20, 150)),
            "breakdown_flag": 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/demo/trigger-obstacle")
async def trigger_chaos(payload: ChaosPayload):
    src, dst = parse_route(payload.route_id)
    query = """
    MATCH (a:Node)-[r:CONNECTED_VIA]->(b:Node)
    WHERE a.id STARTS WITH $src AND b.id STARTS WITH $dst
    SET r.is_blocked = true RETURN r
    """
    with neo4j_driver.session() as session:
        session.run(query, src=src, dst=dst)
    return {"message": "Chaos injected"}


@app.post("/api/v1/demo/clear-obstacle")
async def clear_chaos(payload: ChaosPayload):
    src, dst = parse_route(payload.route_id)
    query = """
    MATCH (a:Node)-[r:CONNECTED_VIA]->(b:Node)
    WHERE a.id STARTS WITH $src AND b.id STARTS WITH $dst
    SET r.is_blocked = false RETURN r
    """
    with neo4j_driver.session() as session:
        session.run(query, src=src, dst=dst)
    return {"message": "Chaos cleared"}


# --- AI & INFERENCE ENDPOINTS ---
@app.post("/api/v1/predict-risk")
async def predict_delay_risk(telemetry: TelemetryPayload):
    try:
        input_data = pd.DataFrame(
            [
                {
                    "distance_km": telemetry.distance_km,
                    "base_hours": telemetry.base_hours,
                    "rainfall_mm": telemetry.rainfall_mm,
                    "wind_speed_kmh": telemetry.wind_speed_kmh,
                    "toll_queue_m": telemetry.toll_queue_m,
                    "breakdown_flag": telemetry.breakdown_flag,
                }
            ]
        )
        probabilities = model.predict_proba(input_data)
        risk_score = float(probabilities[0][1])
        alert_triggered = risk_score > 0.70
        return {
            "route_id": telemetry.route_id,
            "risk_score": risk_score,
            "alert_triggered": alert_triggered,
            "message": "High risk!" if alert_triggered else "Normal.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/reroute")
async def generate_reroute(payload: ReroutePayload):
    try:
        initial_state = {
            "impacted_route": payload.impacted_route,
            "destination_hub": payload.destination_hub,
            "original_cost": payload.original_cost,
            "backup_suppliers_found": [],
            "selected_reroute": {},
            "status": "INITIATED",
            "messages": [],
        }
        final_state = supply_chain_app.invoke(initial_state)
        return {
            "status": final_state["status"],
            "proposed_reroute": final_state["selected_reroute"],
            "agent_logs": final_state["messages"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/reroute/commit")
async def commit_reroute(payload: RerouteCommitPayload):
    mutation_query = """
    MATCH (sh:Shipment {id: $shipment_id})-[:FULFILLS]->(po:PurchaseOrder)
    MATCH (new_sup:Supplier {id: $new_supplier_id})
    SET sh.status = 'REROUTED', sh.current_route = new_sup.id + '_DIRECT', po.amount_inr = $new_cost
    WITH sh, po, new_sup
    OPTIONAL MATCH (old_sup:Supplier)-[r:SUPPLIES]->(po)
    DELETE r
    MERGE (new_sup)-[:SUPPLIES]->(po)
    """
    try:
        with neo4j_driver.session() as session:
            session.run(
                mutation_query,
                shipment_id=payload.shipment_id,
                new_supplier_id=payload.new_supplier_id,
                new_cost=payload.new_cost,
            )
            # Auto-clear roadblock
            src, dst = parse_route(payload.impacted_route)
            session.run(
                "MATCH (a:Node)-[r:CONNECTED_VIA]->(b:Node) WHERE a.id STARTS WITH $src AND b.id STARTS WITH $dst SET r.is_blocked = false",
                src=src,
                dst=dst,
            )
        return {"message": "Graph mutated!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

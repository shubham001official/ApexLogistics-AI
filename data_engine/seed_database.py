import os
import requests
import time
import random
from faker import Faker
from dotenv import load_dotenv
from neo4j import GraphDatabase
from pathlib import Path

# Initialize Faker for realistic company names
fake = Faker("en_IN")

# Load DB credentials
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

OSRM_URL = "http://router.project-osrm.org/route/v1/driving"

# V3: Pan-India Enterprise Nodes
STATIC_NODES = [
    {
        "id": "JNPT_PORT",
        "name": "JNPT Port",
        "lat": 18.9490,
        "lon": 72.9490,
        "type": "PORT",
    },
    {
        "id": "MUNDRA_PORT",
        "name": "Mundra Port",
        "lat": 22.7440,
        "lon": 69.7110,
        "type": "PORT",
    },
    {
        "id": "KOLKATA_PORT",
        "name": "Kolkata Port",
        "lat": 22.5726,
        "lon": 88.3639,
        "type": "PORT",
    },
    {
        "id": "CHAKAN_AUTO_CLUSTER",
        "name": "Chakan Auto Cluster",
        "lat": 18.7623,
        "lon": 73.8625,
        "type": "FACTORY",
    },
    {
        "id": "BHIWANDI_HUB",
        "name": "Bhiwandi Warehousing Hub",
        "lat": 19.3000,
        "lon": 73.0600,
        "type": "WAREHOUSE",
    },
    {
        "id": "SRIPERUMBUDUR_CLUSTER",
        "name": "Sriperumbudur Auto Cluster",
        "lat": 12.9670,
        "lon": 79.9460,
        "type": "FACTORY",
    },
    {
        "id": "DELHI_NCR_HUB",
        "name": "Delhi NCR Logistics Hub",
        "lat": 28.7041,
        "lon": 77.1025,
        "type": "WAREHOUSE",
    },
    {
        "id": "BANGALORE_TECH_PARK",
        "name": "Bangalore Tech Park",
        "lat": 12.9716,
        "lon": 77.5946,
        "type": "FACTORY",
    },
    {
        "id": "HYDERABAD_PHARMA",
        "name": "Hyderabad Pharma City",
        "lat": 17.3850,
        "lon": 78.4867,
        "type": "FACTORY",
    },
]


def calculate_routes(nodes):
    print("🛣️ Calculating real Pan-India highway routes using OSRM...")
    edges = []
    # V3: Complex inter-state routing
    route_pairs = [
        ("JNPT_PORT", "BHIWANDI_HUB"),
        ("JNPT_PORT", "CHAKAN_AUTO_CLUSTER"),
        ("BHIWANDI_HUB", "CHAKAN_AUTO_CLUSTER"),
        ("MUNDRA_PORT", "DELHI_NCR_HUB"),
        ("DELHI_NCR_HUB", "CHAKAN_AUTO_CLUSTER"),
        ("CHAKAN_AUTO_CLUSTER", "BANGALORE_TECH_PARK"),
        ("BANGALORE_TECH_PARK", "SRIPERUMBUDUR_CLUSTER"),
        ("KOLKATA_PORT", "HYDERABAD_PHARMA"),
        ("HYDERABAD_PHARMA", "BANGALORE_TECH_PARK"),
        ("JNPT_PORT", "BANGALORE_TECH_PARK"),
    ]

    for source_id, dest_id in route_pairs:
        source = next(n for n in nodes if n["id"] == source_id)
        dest = next(n for n in nodes if n["id"] == dest_id)
        coords = f"{source['lon']},{source['lat']};{dest['lon']},{dest['lat']}"
        req_url = f"{OSRM_URL}/{coords}?overview=false"
        try:
            res = requests.get(req_url)
            res.raise_for_status()
            data = res.json()
            if data.get("routes"):
                edges.append(
                    {
                        "source": source_id,
                        "destination": dest_id,
                        "distance_km": round(data["routes"][0]["distance"] / 1000, 2),
                        "avg_transit_hours": round(
                            data["routes"][0]["duration"] / 3600, 2
                        ),
                        "mode": "HIGHWAY",
                    }
                )
            time.sleep(1)  # Respect OSRM free tier
        except Exception as e:
            print(f"❌ Route failed: {e}")
    return edges


def generate_commercial_data():
    print("🏭 Generating synthetic Pan-India Commercial Data...")
    suppliers = []
    purchase_orders = []
    shipments = []

    # Target all major factory/warehouse hubs
    hubs = [
        "CHAKAN_AUTO_CLUSTER",
        "SRIPERUMBUDUR_CLUSTER",
        "DELHI_NCR_HUB",
        "BANGALORE_TECH_PARK",
        "HYDERABAD_PHARMA",
    ]

    for hub in hubs:
        # Generate 3-4 suppliers per hub
        for i in range(random.randint(3, 4)):
            supplier_id = f"SUP_{hub[:3]}_{i+1}"
            tier = "Tier-1" if i == 0 else "Tier-2"
            suppliers.append(
                {
                    "id": supplier_id,
                    "name": f"{fake.company()} Logistics & Parts",
                    "tier": tier,
                    "reliability_score": round(random.uniform(0.65, 0.99), 2),
                    "location_node": hub,
                }
            )

            # Generate POs
            for j in range(random.randint(1, 3)):
                po_id = f"PO_{supplier_id}_{j+1}"
                purchase_orders.append(
                    {
                        "id": po_id,
                        "supplier_id": supplier_id,
                        "amount_inr": random.randint(150000, 5500000),
                        "item_sku": f"SKU-IND-{random.randint(1000, 9999)}",
                        "target_delivery_days": random.randint(2, 20),
                    }
                )

                # 70% chance to generate an active shipment
                if random.random() > 0.3:
                    # Assign a plausible route based on the hub
                    route = "JNPT_TO_CHAKAN"
                    if "DEL" in hub:
                        route = "MUNDRA_TO_DELHI"
                    elif "BAN" in hub:
                        route = "CHAKAN_TO_BANGALORE"
                    elif "HYD" in hub:
                        route = "KOLKATA_TO_HYDERABAD"
                    elif "SRI" in hub:
                        route = "BANGALORE_TO_SRIPERUMBUDUR"

                    shipments.append(
                        {
                            "id": f"SHP_{po_id}",
                            "po_id": po_id,
                            "status": random.choice(
                                ["IN_TRANSIT", "IN_TRANSIT", "DELAYED", "CUSTOMS_HOLD"]
                            ),
                            "current_route": route,
                            "risk_score_override": 0.0,
                        }
                    )

    return suppliers, purchase_orders, shipments


def seed_neo4j(nodes, edges, suppliers, pos, shipments):
    print("\n🌐 Connecting to Neo4j AuraDB...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
        print("🧹 Cleared existing database.")

        for node in nodes:
            session.run(
                """
                MERGE (n:Node {id: $id})
                SET n.name = $name, n.lat = $lat, n.lon = $lon, n.type = $type
            """,
                **node,
            )

        for edge in edges:
            session.run(
                """
                MATCH (a:Node {id: $source}), (b:Node {id: $destination})
                MERGE (a)-[r:CONNECTED_VIA]->(b)
                SET r.distance_km = $distance_km, r.avg_transit_hours = $avg_transit_hours, r.mode = $mode, r.is_blocked = false
            """,
                **edge,
            )

        for sup in suppliers:
            session.run(
                """
                MATCH (hub:Node {id: $location_node})
                MERGE (s:Supplier {id: $id})
                SET s.name = $name, s.tier = $tier, s.reliability_score = $reliability_score
                MERGE (s)-[:LOCATED_AT]->(hub)
            """,
                **sup,
            )

        for po in pos:
            session.run(
                """
                MATCH (s:Supplier {id: $supplier_id})
                MERGE (p:PurchaseOrder {id: $id})
                SET p.amount_inr = $amount_inr, p.item_sku = $item_sku, p.target_delivery_days = $target_delivery_days
                MERGE (s)-[:SUPPLIES]->(p)
            """,
                **po,
            )

        for shp in shipments:
            session.run(
                """
                MATCH (p:PurchaseOrder {id: $po_id})
                MERGE (sh:Shipment {id: $id})
                SET sh.status = $status, sh.current_route = $current_route, sh.risk_score_override = $risk_score_override
                MERGE (sh)-[:FULFILLS]->(p)
            """,
                **shp,
            )

        print(f"✅ Inserted {len(nodes)} spatial nodes & {len(edges)} routes.")
        print(
            f"✅ Inserted {len(suppliers)} Suppliers, {len(pos)} Purchase Orders, and {len(shipments)} Active Shipments."
        )

    driver.close()
    print("🚀 V3 Enterprise graph seating complete!")


if __name__ == "__main__":
    print("🚚 Initializing ResiliNet-IN Data Engine...")
    calculated_edges = calculate_routes(STATIC_NODES)
    generated_suppliers, generated_pos, generated_shipments = generate_commercial_data()
    seed_neo4j(
        STATIC_NODES,
        calculated_edges,
        generated_suppliers,
        generated_pos,
        generated_shipments,
    )

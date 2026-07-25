import os
from typing import TypedDict, List, Dict, Any
from dotenv import load_dotenv
from neo4j import GraphDatabase
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from pathlib import Path
import json
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import SystemMessage, HumanMessage

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Initialize the LLM
llm = ChatGroq(
    temperature=0,
    model_name="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
)

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")


class SupplyChainState(TypedDict):
    impacted_route: str
    destination_hub: str
    original_cost: float
    backup_suppliers_found: List[Dict[str, Any]]
    selected_reroute: Dict[str, Any]
    status: str
    messages: List[str]


@tool
def find_backup_suppliers(destination_hub_id: str) -> List[Dict[str, Any]]:
    """Queries Neo4j for alternative suppliers at the destination hub."""
    print(
        f"🛠️ [Tool Execution] Querying Neo4j for suppliers at {destination_hub_id}..."
    )
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

    query = """
    MATCH (s:Supplier)-[:LOCATED_AT]->(hub:Node)
    WHERE hub.id CONTAINS $hub_id
    RETURN s.id AS supplier_id, s.name AS name, s.tier AS tier, s.reliability_score AS reliability
    ORDER BY s.reliability_score DESC
    LIMIT 3
    """
    results = []
    with driver.session() as session:
        records = session.run(query, hub_id=destination_hub_id)
        for record in records:
            results.append(
                {
                    "supplier_id": record["supplier_id"],
                    "name": record["name"],
                    "tier": record["tier"],
                    "reliability_score": record["reliability"],
                }
            )
    driver.close()
    return results


def sourcing_node(state: SupplyChainState):
    print(
        "🤖 [Agent: Sourcing] Identifying impacted hub and searching for local backups..."
    )
    # Extract destination from route string if needed (e.g. "JNPT_TO_CHAKAN" -> "CHAKAN")
    dest_str = state["destination_hub"]
    if "_TO_" in state["impacted_route"]:
        dest_str = state["impacted_route"].split("_TO_")[1].split("_")[0]

    suppliers = find_backup_suppliers.invoke({"destination_hub_id": dest_str})
    return {
        "backup_suppliers_found": suppliers,
        "messages": [
            f"Found {len(suppliers)} potential backup suppliers near {dest_str}."
        ],
    }


def evaluation_node(state: SupplyChainState):
    print(
        "🤖 [Agent: Evaluator] Analyzing supplier reliability and enforcing strict geographical routing..."
    )
    suppliers = state["backup_suppliers_found"]
    impacted = state["impacted_route"]

    if not suppliers:
        return {"status": "FAILED", "messages": ["No backup suppliers found in graph."]}

    system_prompt = f"""You are an elite Enterprise Supply Chain routing AI. 
    A critical disruption has occurred on route: {impacted}.
    
    CRITICAL RULES:
    1. You MUST select the supplier with the highest reliability_score.
    2. The new routing MUST NOT use the currently impacted route ({impacted}).
    3. The new route string must be logically formatted as '{{SUPPLIER_ID}}_DIRECT' to indicate local sourcing bypassing the blocked highway.
    
    Generate a strict JSON response:
    {{
        "selected_supplier_id": "string",
        "estimated_cost_inr": integer (add 15% emergency premium to original cost),
        "justification": "string (One sentence explaining why this bypasses the blocked route and is the most reliable)"
    }}
    ONLY output valid JSON. No markdown, no preambles."""

    user_prompt = f"Original Cost: {state['original_cost']} INR.\nImpacted Route: {impacted}\nAvailable Backup Suppliers: {json.dumps(suppliers)}"

    response = llm.invoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    )

    try:
        decision = json.loads(response.content)
        return {
            "selected_reroute": decision,
            "status": "AWAITING_HUMAN_APPROVAL",
            "messages": ["Reroute strategy formulated successfully."],
        }
    except json.JSONDecodeError:
        return {
            "status": "ERROR",
            "messages": ["Failed to parse LLM response as JSON."],
        }


workflow = StateGraph(SupplyChainState)
workflow.add_node("sourcing", sourcing_node)
workflow.add_node("evaluator", evaluation_node)
workflow.add_edge(START, "sourcing")
workflow.add_edge("sourcing", "evaluator")
workflow.add_edge("evaluator", END)
supply_chain_app = workflow.compile()

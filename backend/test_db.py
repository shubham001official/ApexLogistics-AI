import os
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

# 1. Resolve path relative to this Python file's location
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# Debugging check
print(f"DEBUG: Looking for .env at -> {env_path.resolve()}")
print(f"DEBUG: Loaded NEO4J_URI    -> {NEO4J_URI}")

def test_connection():
    # 2. Check if the variable is loaded BEFORE passing to driver
    if not NEO4J_URI:
        print("❌ Error: NEO4J_URI is empty/None! Check your .env path and variable names.")
        return

    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
        driver.verify_connectivity()
        print("✅ Successfully connected to Neo4j AuraDB!")
        driver.close()
    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    test_connection()
import pandas as pd
import numpy as np
import random
import os

# Define the routes from our Neo4j graph
ROUTES = [
    {"route_id": "JNPT_TO_BHIWANDI", "distance_km": 67.55, "base_hours": 0.92},
    {"route_id": "JNPT_TO_CHAKAN", "distance_km": 136.67, "base_hours": 1.75},
    {"route_id": "BHIWANDI_TO_CHAKAN", "distance_km": 156.03, "base_hours": 1.93},
    {"route_id": "MUNDRA_TO_BHIWANDI", "distance_km": 872.85, "base_hours": 11.64},
    {"route_id": "CHAKAN_TO_SRIPERUMBUDUR", "distance_km": 1094.0, "base_hours": 13.23},
]

def generate_historical_data(num_records=10000):
    print(f"📊 Generating {num_records} synthetic historical shipment logs...")
    
    data = []
    
    for _ in range(num_records):
        route = random.choice(ROUTES)
        
        # 1. Simulate Environmental & Telemetry Features
        # Monsoon logic: 80% chance of no/light rain, 20% chance of heavy rain
        rainfall_mm = np.random.exponential(scale=5) if random.random() > 0.8 else random.uniform(0, 2)
        wind_speed_kmh = random.uniform(10, 60)
        
        # FASTag / Toll queue in meters
        toll_queue_m = np.random.exponential(scale=100)
        
        # Vehicle health (1 = Breakdown, 0 = Healthy) - Rare event (2% chance)
        breakdown_flag = 1 if random.random() > 0.98 else 0
        
        # 2. Calculate Actual Transit Time mathematically
        delay_hours = 0
        
        # Rain adds delay (non-linear)
        if rainfall_mm > 15:
            delay_hours += (rainfall_mm * 0.1)
            
        # Long toll queues add delay
        if toll_queue_m > 300:
            delay_hours += (toll_queue_m / 1000)
            
        # Breakdowns cause massive delays
        if breakdown_flag == 1:
            delay_hours += random.uniform(3, 8)
            
        # Introduce baseline traffic variance (± 10%)
        traffic_variance = route["base_hours"] * random.uniform(-0.1, 0.2)
        
        actual_hours = route["base_hours"] + delay_hours + traffic_variance
        
        # 3. Define the Target Variable (Label)
        # If the trip took 25% longer than the base time, it is officially "Delayed" (1)
        is_delayed = 1 if actual_hours > (route["base_hours"] * 1.25) else 0
        
        data.append({
            "route_id": route["route_id"],
            "distance_km": route["distance_km"],
            "base_hours": route["base_hours"],
            "rainfall_mm": round(rainfall_mm, 2),
            "wind_speed_kmh": round(wind_speed_kmh, 2),
            "toll_queue_m": round(toll_queue_m, 2),
            "breakdown_flag": breakdown_flag,
            "actual_hours": round(actual_hours, 2),
            "is_delayed": is_delayed # TARGET VARIABLE
        })
        
    df = pd.DataFrame(data)
    
    # Save to CSV
    output_dir = "../backend/ml_models"
    os.makedirs(output_dir, exist_ok=True)
    file_path = f"{output_dir}/historical_logistics_data.csv"
    
    df.to_csv(file_path, index=False)
    print(f"✅ Successfully saved dataset to {file_path}")
    
    # Print a quick summary to verify the class balance
    print("\n--- Dataset Distribution ---")
    print(df['is_delayed'].value_counts(normalize=True).mul(100).round(1).astype(str) + '%')

if __name__ == "__main__":
    generate_historical_data(10000)
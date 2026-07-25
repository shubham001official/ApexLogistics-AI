import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, classification_report
import os

# 1. Load the Dataset
data_path = "E:/resilinet-in/historical_logistics_data.csv"
print("📥 Loading historical dataset...")
df = pd.read_csv(data_path)

# 2. Feature Selection & Preprocessing
# We DROP 'route_id' (strings) and 'actual_hours' (Target Leakage!)
# The model will learn the route characteristics through 'distance_km' and 'base_hours'
features = ['distance_km', 'base_hours', 'rainfall_mm', 'wind_speed_kmh', 'toll_queue_m', 'breakdown_flag']
target = 'is_delayed'

X = df[features]
y = df[target]

# 3. Train/Test Split (80% Training, 20% Evaluation)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.20, random_state=42, stratify=y)

print(f"⚙️ Training XGBoost Classifier on {len(X_train)} records...")

# 4. Initialize and Train the Model
# scale_pos_weight is used if the dataset is highly imbalanced
model = xgb.XGBClassifier(
    n_estimators=100,
    learning_rate=0.1,
    max_depth=5,
    random_state=42,
    eval_metric='logloss'
)

model.fit(X_train, y_train)

# 5. Evaluate the Model
print("\n📊 Evaluating Model Performance on Test Set...")
y_pred = model.predict(X_test)

accuracy = accuracy_score(y_test, y_pred)
precision = precision_score(y_test, y_pred)
recall = recall_score(y_test, y_pred)

print(f"Accuracy:  {accuracy * 100:.2f}%")
print(f"Precision: {precision * 100:.2f}% (When it predicts delay, how often is it right?)")
print(f"Recall:    {recall * 100:.2f}% (Out of all actual delays, how many did it catch?)")
print("\nDetailed Classification Report:")
print(classification_report(y_test, y_pred))

# 6. Save the Model Artifact
model_output_path = os.path.join(os.path.dirname(__file__), "xgboost_risk_model.json")
model.save_model(model_output_path)
print(f"💾 Model successfully saved to {model_output_path}")
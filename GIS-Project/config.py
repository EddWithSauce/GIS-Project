import os
from dotenv import load_dotenv

# Load env once for the whole app
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
ADMIN_CODE = os.getenv("ADMIN_CODE", "ADMIN123")

# Feature flags
DEVICE_READY = os.getenv("DEVICE_READY", "false").lower() in ("1","true","yes","y","on")
AI_READY = os.getenv("AI_READY", "false").lower() in ("1","true","yes","y","on")

# Notification controls
NOTIFY_ENABLED = os.getenv("NOTIFY_ENABLED", "true").lower() in ("1","true","yes","y","on")

# Email cooldown minutes
COOLDOWN_WARNING_MIN = int(os.getenv("COOLDOWN_WARNING_MIN", "15"))
COOLDOWN_CRITICAL_MIN = int(os.getenv("COOLDOWN_CRITICAL_MIN", "5"))

# Device ingestion (Raspberry Pi)
DEVICE_API_KEY = os.getenv("DEVICE_API_KEY", "")  # set in .env for /api/sensors/ingest

# Default thresholds (fallbacks if thresholds table not configured yet)
WL_WARNING_M = float(os.getenv("WL_WARNING_M", "0.8"))
WL_CRITICAL_M = float(os.getenv("WL_CRITICAL_M", "1.2"))
# One-station mode (financial difficulty: single device)
ONE_STATION_MODE = os.getenv("ONE_STATION_MODE", "true").lower() in ("1","true","yes","y","on")
DEFAULT_STATION_CODE = os.getenv("DEFAULT_STATION_CODE", "URSM_01")
DEFAULT_STATION_NAME = os.getenv("DEFAULT_STATION_NAME", "Device Point")

# URSM map center (fallback)
URSM_CENTER_LAT = float(os.getenv("URSM_CENTER_LAT", "14.517697"))
URSM_CENTER_LNG = float(os.getenv("URSM_CENTER_LNG", "121.235711"))
URSM_CENTER_ZOOM = int(os.getenv("URSM_CENTER_ZOOM", "18"))

# If creating station automatically, place it relative to center (offsets)
DEFAULT_STATION_LAT_OFFSET = float(os.getenv("DEFAULT_STATION_LAT_OFFSET", "-0.0002"))
DEFAULT_STATION_LNG_OFFSET = float(os.getenv("DEFAULT_STATION_LNG_OFFSET", "0.0"))

def default_map_center():
    return {"lat": URSM_CENTER_LAT, "lng": URSM_CENTER_LNG, "zoom": URSM_CENTER_ZOOM}

def default_station_latlng():
    return (URSM_CENTER_LAT + DEFAULT_STATION_LAT_OFFSET, URSM_CENTER_LNG + DEFAULT_STATION_LNG_OFFSET)


# -------------------- Phase 4: ML / Prediction pipeline --------------------
# In Phase 4, we always write a row into `predictions` on every ingest.
# - If AI_READY is false or no model is configured, we store a "rule-based standby" prediction.
# - When your trained models are ready, you can swap the predictor implementation without changing routes/JS.

PREDICT_ON_INGEST = os.getenv("PREDICT_ON_INGEST", "true").lower() in ("1","true","yes","y","on")

# Optional: identify your model version string (stored in predictions.model_version)
STANDBY_MODEL_VERSION = os.getenv("STANDBY_MODEL_VERSION", "STANDBY_RULES_v0")

# If/when you add a real model later, you can set:
#   MODEL_DRIVER=pickle|keras|onnx|custom
# and store your model files in ./models/
MODEL_DRIVER = os.getenv("MODEL_DRIVER", "standby")


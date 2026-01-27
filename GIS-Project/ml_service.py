from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import config
from supabase_client import supabase_admin


def classify_rainfall(mm_per_hr: float) -> str:
    if mm_per_hr <= 0.1:
        return "No Rain"
    if mm_per_hr < 2.5:
        return "Light"
    if mm_per_hr < 7.5:
        return "Moderate"
    return "Heavy"


def flood_status_from_waterlevel(water_level_m: float, wl_warning: float, wl_critical: float) -> str:
    if water_level_m < wl_warning:
        return "Normal"
    if water_level_m < wl_critical:
        return "Warning"
    return "Critical"


def get_thresholds(sb) -> tuple[float, float]:
    """Read wl_warning_m and wl_critical_m from thresholds table if available."""
    wl_warning = config.WL_WARNING_M
    wl_critical = config.WL_CRITICAL_M
    try:
        res = sb.table("thresholds").select("name,value").execute()
        for row in (res.data or []):
            if row.get("name") == "wl_warning_m" and row.get("value") is not None:
                wl_warning = float(row["value"])
            if row.get("name") == "wl_critical_m" and row.get("value") is not None:
                wl_critical = float(row["value"])
    except Exception:
        pass
    return wl_warning, wl_critical


def write_prediction_from_log(
    station_id: str,
    log_row: Dict[str, Any],
    *,
    sb=None,
) -> Optional[Dict[str, Any]]:
    """Phase 4: Always write a prediction row to Supabase.

    Today:
    - If AI_READY is false (or MODEL_DRIVER=standby), we generate a rule-based prediction.
    Future:
    - Replace the rule-based block with your trained model inference.
    """
    sb = sb or supabase_admin()

    wl_warning, wl_critical = get_thresholds(sb)

    wl = log_row.get("water_level_m")
    rain = log_row.get("rain_mm_hr")

    # Basic safety parsing
    wl_val = float(wl) if wl is not None else None
    rain_val = float(rain) if rain is not None else None

    # --- STANDBY prediction (rule-based) ---
    predicted_risk = "Unknown"
    predicted_wl = None
    if wl_val is not None:
        predicted_risk = flood_status_from_waterlevel(wl_val, wl_warning, wl_critical)
        predicted_wl = wl_val

    predicted_rain_intensity = classify_rainfall(rain_val or 0.0) if rain_val is not None else "Unknown"

    # We don't have 'hours before flooding' model yet.
    hours_before_flood = None

    payload = {
        "mode": "STANDBY" if not config.AI_READY or config.MODEL_DRIVER == "standby" else "ML",
        "predicted_rainfall_intensity": predicted_rain_intensity,
        "hours_before_flood": hours_before_flood,
        "inputs": {
            "humidity": log_row.get("humidity"),
            "temperature": log_row.get("temperature"),
            "wind": log_row.get("wind"),
            "rain_mm_hr": rain_val,
            "water_level_m": wl_val,
        },
        "notes": "Rule-based standby prediction. Replace in ml_service.py when ML is ready."
    }

    row = {
        "station_id": station_id,
        "predicted_risk": predicted_risk,
        "predicted_score": None,
        "predicted_water_level_m": predicted_wl,
        "model_version": config.STANDBY_MODEL_VERSION if payload["mode"] == "STANDBY" else "ML_MODEL_v1",
        "payload": payload,
    }

    try:
        res = sb.table("predictions").insert(row).execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        # don't crash ingest if predictions table isn't ready
        print("[PREDICT ERROR]", e)
    return None


def get_latest_prediction(station_id: str, *, sb=None) -> Optional[Dict[str, Any]]:
    sb = sb or supabase_admin()
    try:
        res = sb.table("predictions").select("*").eq("station_id", station_id).order("created_at", desc=True).limit(1).execute()
        if res.data:
            return res.data[0]
    except Exception:
        return None
    return None

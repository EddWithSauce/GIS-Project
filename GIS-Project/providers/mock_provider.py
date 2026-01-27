from __future__ import annotations
from typing import Any, Dict, List
from datetime import datetime, timedelta
import random
from utils.time_utils import now_iso
import config

# Default URSM center (edit later or load from DB in Phase 2)
URSM_CREEK_CENTER = config.default_map_center()
def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def classify_rainfall(mm_per_hr: float) -> str:
    if mm_per_hr <= 0.1:
        return "No Rain"
    if mm_per_hr < 2.5:
        return "Light"
    if mm_per_hr < 7.5:
        return "Moderate"
    return "Heavy"

def flood_status_from_waterlevel(water_level_m: float) -> str:
    if water_level_m < 0.8:
        return "Normal"
    if water_level_m < 1.2:
        return "Warning"
    return "Critical"

def risk_level_from_status(flood_status: str) -> str:
    if flood_status == "Normal":
        return "low"
    if flood_status == "Warning":
        return "medium"
    return "high"

class MockProvider:
    def get_config(self) -> Dict[str, Any]:
        return {"map_center": URSM_CREEK_CENTER, "mode": "STANDBY", "last_updated": now_iso()}

    def get_current_snapshot(self) -> Dict[str, Any]:
        water_level = round(random.uniform(0.4, 1.5), 2)
        rain_mm_hr = round(random.choice([0.0, 0.2, 1.2, 4.3, 9.1]), 1)

        rainfall_class = classify_rainfall(rain_mm_hr)
        flood_status = flood_status_from_waterlevel(water_level)

        return {
            "last_updated": now_iso(),
            "rainfall": {"mm_per_hr": rain_mm_hr, "classification": rainfall_class},
            "flood": {"status": flood_status, "predicted_risk": flood_status},
            "sensors": {
                "humidity": round(random.uniform(55, 95), 1),
                "temperature": round(random.uniform(23, 34), 1),
                "wind": round(random.uniform(0, 12), 1),
                "water_level": water_level,
            },
        }

    def get_map_features(self) -> Dict[str, Any]:
        lat = URSM_CREEK_CENTER["lat"]
        lng = URSM_CREEK_CENTER["lng"]

        points = [
            {"id": "p1", "name": "Device Point", "lat": lat - 0.0002, "lng": lng + 0.0000},
        ]

        markers = []
        segments = []

        for p in points:
            water_level = round(random.uniform(0.4, 1.5), 2)
            rain_mm_hr = round(random.choice([0.0, 0.2, 1.2, 4.3, 9.1]), 1)
            rainfall_class = classify_rainfall(rain_mm_hr)
            flood_status = flood_status_from_waterlevel(water_level)
            risk = risk_level_from_status(flood_status)

            markers.append({
                "id": p["id"],
                "name": p["name"],
                "lat": p["lat"],
                "lng": p["lng"],
                "risk_level": risk,
                "popup": {
                    "water_level_m": water_level,
                    "predicted_flood_risk": flood_status,
                    "rainfall_classification": rainfall_class,
                },
            })

        # segments (none for single point, but keep structure)
        for i in range(len(points) - 1):
            a = markers[i]
            b = markers[i + 1]
            worst = "low"
            for r in [a["risk_level"], b["risk_level"]]:
                if r == "high":
                    worst = "high"
                elif r == "medium" and worst != "high":
                    worst = "medium"
            segments.append({"id": f"s{i+1}", "risk_level": worst, "path": [[a["lat"], a["lng"]], [b["lat"], b["lng"]]]})

        return {"markers": markers, "segments": segments}

    def get_forecast(self) -> Dict[str, Any]:
        start = datetime.now().replace(minute=0, second=0, microsecond=0)
        rainfall = []
        water_level = []
        flood_pred = []

        base_wl = random.uniform(0.5, 1.1)
        for h in range(12):
            t = start + timedelta(hours=h)
            rain = max(0.0, random.gauss(2.0, 2.0))
            wl = max(0.3, base_wl + (rain * 0.04) + random.uniform(-0.05, 0.05))
            status = flood_status_from_waterlevel(wl)

            rainfall.append({"time": t.isoformat(timespec="minutes"), "mm_per_hr": round(rain, 2)})
            water_level.append({"time": t.isoformat(timespec="minutes"), "water_level_m": round(wl, 2)})
            flood_pred.append({"time": t.isoformat(timespec="minutes"), "status": status})

        return {
            "last_updated": now_iso(),
            "rainfall_next_hours": rainfall,
            "water_level_trend": water_level,
            "flood_prediction_next_hours": flood_pred,
            "note": "Forecast is mock data. Replace with weather API + ML when ready.",
        }

    def get_history(self, range_q: str) -> Dict[str, Any]:
        now = datetime.now().replace(second=0, microsecond=0)

        if range_q == "7d":
            points = 7 * 24
            step = timedelta(hours=1)
        else:
            points = 24 * 6
            step = timedelta(minutes=10)

        series = []
        for i in range(points):
            t = now - step * (points - 1 - i)
            rain = max(0.0, random.gauss(1.2, 1.5))
            wl = max(0.3, 0.7 + (rain * 0.05) + random.uniform(-0.08, 0.08))
            rainfall_class = classify_rainfall(rain)
            flood_status = flood_status_from_waterlevel(wl)

            series.append({
                "time": t.isoformat(timespec="minutes"),
                "rain_mm_hr": round(rain, 2),
                "rain_class": rainfall_class,
                "water_level_m": round(wl, 2),
                "flood_status": flood_status,
            })

        return {
            "range": range_q,
            "last_updated": now_iso(),
            "series": series,
            "note": "History is mock data. Replace with database (Supabase) when sensor logging is ready.",
        }

    def get_demo_raw_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        # Same as your current standby CSV generator
        rows = []
        base = datetime.now().replace(second=0, microsecond=0)
        for i in range(limit):
            t = base - timedelta(minutes=i * 10)
            humidity = round(random.uniform(55, 95), 1)
            temp = round(random.uniform(23, 34), 1)
            wind = round(random.uniform(0, 12), 1)
            rain = round(max(0.0, random.gauss(1.2, 1.5)), 2)
            wl = round(max(0.3, 0.7 + (rain * 0.05) + random.uniform(-0.08, 0.08)), 2)

            rows.append({
                "timestamp": t.isoformat(timespec="minutes"),
                "station_id": "STATION_DEMO_01",
                "humidity": humidity,
                "temperature": temp,
                "wind": wind,
                "rain_mm_hr": rain,
                "water_level_m": wl,
                "source": "STANDBY",
            })
        return rows

    def get_demo_validation(self, limit: int = 60) -> List[Dict[str, Any]]:
        rows = []
        base = datetime.now().replace(second=0, microsecond=0)
        for i in range(limit):
            t = base - timedelta(hours=(limit - i))
            actual_wl = round(random.uniform(0.4, 1.5), 2)

            if actual_wl < 0.8:
                pred_risk = "Normal"
            elif actual_wl < 1.2:
                pred_risk = "Warning"
            else:
                pred_risk = "Critical"

            predicted_wl = round(actual_wl + random.uniform(-0.12, 0.12), 2)

            rows.append({
                "timestamp": t.isoformat(timespec="minutes"),
                "station_id": "STATION_DEMO_01",
                "actual_water_level_m": actual_wl,
                "actual_flood_event": "YES" if actual_wl >= 1.2 else "NO",
                "predicted_flood_risk": pred_risk,
                "predicted_water_level_m": predicted_wl,
                "model_version": "STANDBY_MODEL_v0",
                "notes": "Standby demo",
            })
        return rows

import os
from datetime import datetime, timedelta, timezone
import random

# Asia/Manila is UTC+8
MANILA_TZ = timezone(timedelta(hours=8))

def _bool_env(name: str, default: bool = False) -> bool:
    v = os.getenv(name, str(default)).strip().lower()
    return v in ("1", "true", "yes", "y", "on")

def _now_str():
    return datetime.now(MANILA_TZ).strftime("%Y-%m-%d %H:%M:%S")


# Adjust map center here (URSM area-ish; change if you have exact URSM Creek coords)
MAP_CENTER = {"lat": 14.516677, "lng": 121.235619, "zoom": 15}

RAIN_CLASSES = ["No Rain", "Light", "Moderate", "Heavy"]
FLOOD_CLASSES = ["Normal", "Warning", "Critical"]
RISK_LEVELS = ["low", "medium", "high"]


def get_system_status():
    device_ready = _bool_env("DEVICE_READY", False)
    ai_ready = _bool_env("AI_READY", False)

    return {
        "device_ready": device_ready,
        "ai_ready": ai_ready,
        "mode": "LIVE" if (device_ready and ai_ready) else "STANDBY",
        "last_updated": _now_str(),
        "map_center": MAP_CENTER,
        "notes": (
            "System is in STANDBY. Showing demo data."
            if not (device_ready and ai_ready)
            else "System is LIVE."
        ),
    }


def _demo_sensor_values():
    # Fake numbers for demo
    humidity = round(random.uniform(55, 92), 1)
    temp = round(random.uniform(24, 33), 1)
    wind = round(random.uniform(0.0, 7.5), 1)
    water_level_m = round(random.uniform(0.2, 1.6), 2)
    return humidity, temp, wind, water_level_m


def _classify_rain():
    # Fake classification
    return random.choice(RAIN_CLASSES)

def _classify_flood(water_level_m: float):
    # Simple demo thresholds
    if water_level_m < 0.7:
        return "Normal"
    if water_level_m < 1.1:
        return "Warning"
    return "Critical"

def _risk_level_from_flood(flood_status: str):
    return {"Normal": "low", "Warning": "medium", "Critical": "high"}[flood_status]


def get_latest_readings():
    humidity, temp, wind, water_level_m = _demo_sensor_values()
    rain_status = _classify_rain()
    flood_status = _classify_flood(water_level_m)

    # If AI is not ready, predicted risk is "Standby"
    ai_ready = _bool_env("AI_READY", False)
    predicted_flood_risk = flood_status if ai_ready else "Standby (AI not ready)"

    return {
        "rainfall_status": rain_status,
        "flood_status": flood_status,
        "predicted_flood_risk": predicted_flood_risk,
        "sensors": {
            "humidity": humidity,
            "temperature": temp,
            "wind": wind,
            "water_level_m": water_level_m,
        },
        "last_updated": _now_str(),
    }


def get_geojson_layers():
    """
    Returns:
      - creek_segments: GeoJSON LineStrings with risk level (color in frontend)
      - sensors: GeoJSON Points with popup data
    """
    latest = get_latest_readings()
    flood_status = latest["flood_status"]
    risk_level = _risk_level_from_flood(flood_status)

    # Demo creek polyline near the center
    # Replace with your real creek geometry later (from GPS/OSM/your survey)
    creek_segments = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "URSM Creek Segment A",
                    "risk_level": risk_level,
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [121.2349, 14.5172],
                        [121.2356, 14.5167],
                        [121.2363, 14.5162],
                    ],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "name": "URSM Creek Segment B",
                    "risk_level": risk_level,
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [121.2363, 14.5162],
                        [121.2370, 14.5157],
                        [121.2376, 14.5152],
                    ],
                },
            },
        ],
    }

    sensors = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "sensor_id": "WL-01",
                    "label": "Water Level Sensor",
                    "water_level_m": latest["sensors"]["water_level_m"],
                    "predicted_flood_risk": latest["predicted_flood_risk"],
                    "rainfall_classification": latest["rainfall_status"],
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [121.235619, 14.516677],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "sensor_id": "WX-01",
                    "label": "Weather Sensor",
                    "humidity": latest["sensors"]["humidity"],
                    "temperature": latest["sensors"]["temperature"],
                    "wind": latest["sensors"]["wind"],
                    "rainfall_classification": latest["rainfall_status"],
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [121.2348, 14.5170],
                },
            },
        ],
    }

    return {
        "map_center": MAP_CENTER,
        "creek_segments": creek_segments,
        "sensors": sensors,
    }


def get_forecast_data():
    """
    Demo forecast for next hours and next day.
    Replace later with weather API + ML model output.
    """
    now = datetime.now(MANILA_TZ)
    hours = []
    rain_mm = []
    flood_risk = []

    ai_ready = _bool_env("AI_READY", False)

    for i in range(0, 12):
        t = now + timedelta(hours=i)
        hours.append(t.strftime("%H:%M"))
        rain = max(0, round(random.gauss(2.0, 2.0), 1))
        rain_mm.append(rain)

        if ai_ready:
            # Fake predicted flood risk from rain intensity
            if rain < 2:
                flood_risk.append("Normal")
            elif rain < 5:
                flood_risk.append("Warning")
            else:
                flood_risk.append("Critical")
        else:
            flood_risk.append("Standby")

    next_day = {
        "date": (now + timedelta(days=1)).strftime("%Y-%m-%d"),
        "summary": random.choice(["Possible showers", "Cloudy", "Rain likely"]),
        "expected_rain_class": random.choice(RAIN_CLASSES),
    }

    return {
        "next_hours": {
            "labels": hours,
            "rain_mm": rain_mm,
            "flood_risk": flood_risk,
        },
        "next_day": next_day,
        "last_updated": _now_str(),
    }


def get_history_data():
    """
    Demo history: 24h hourly + 7d daily.
    Replace with your DB later (SQLite/Postgres).
    """
    now = datetime.now(MANILA_TZ)

    # 24 hours
    labels_24h = []
    rain_24h = []
    wl_24h = []
    flood_24h = []
    for i in range(24, 0, -1):
        t = now - timedelta(hours=i)
        labels_24h.append(t.strftime("%H:%M"))
        rain = max(0, round(random.gauss(1.5, 1.8), 1))
        wl = round(0.4 + (rain * 0.12) + random.uniform(-0.05, 0.05), 2)
        rain_24h.append(rain)
        wl_24h.append(wl)
        flood_24h.append(_classify_flood(wl))

    # 7 days
    labels_7d = []
    rain_7d = []
    wl_7d = []
    for i in range(7, 0, -1):
        d = now - timedelta(days=i)
        labels_7d.append(d.strftime("%b %d"))
        rain = max(0, round(random.gauss(10, 6), 1))
        wl = round(0.5 + (rain * 0.03) + random.uniform(-0.08, 0.08), 2)
        rain_7d.append(rain)
        wl_7d.append(wl)

    return {
        "past_24h": {
            "labels": labels_24h,
            "rain_mm": rain_24h,
            "water_level_m": wl_24h,
            "flood_status": flood_24h,
        },
        "past_7d": {
            "labels": labels_7d,
            "rain_mm": rain_7d,
            "water_level_m": wl_7d,
        },
        "last_updated": _now_str(),
    }


def get_alerts_and_safety_info():
    return {
        "flood_status_meanings": [
            {
                "status": "Normal",
                "meaning": "Water level is within safe range.",
                "actions": ["Monitor updates", "Keep drainage clear"],
            },
            {
                "status": "Warning",
                "meaning": "Water level rising; possible flooding soon.",
                "actions": ["Prepare go-bag", "Move valuables higher", "Monitor every 15-30 minutes"],
            },
            {
                "status": "Critical",
                "meaning": "High risk of flooding or flooding ongoing.",
                "actions": ["Evacuate if advised", "Avoid crossing water", "Follow LGU advisories"],
            },
        ],
        "rainfall_classifications": [
            {"status": "No Rain", "meaning": "No measurable rain."},
            {"status": "Light", "meaning": "Light rainfall, minimal runoff."},
            {"status": "Moderate", "meaning": "Moderate rainfall, rising runoff possible."},
            {"status": "Heavy", "meaning": "Heavy rainfall, high runoff and flood risk."},
        ],
    }

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone

from supabase_client import supabase_admin
import config

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

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

def risk_level_from_status(flood_status: str) -> str:
    if flood_status == "Normal":
        return "low"
    if flood_status == "Warning":
        return "medium"
    return "high"

class SupabaseProvider:
    """Supabase-backed provider (Phase 2)

    Reads LIVE data from:
    - stations
    - sensor_logs
    - predictions (optional / standby)

    Note:
    - Forecast remains standby unless you later integrate a weather API + ML.
    """

    def __init__(self, ai_ready: bool = False):
        self.sb = supabase_admin()
        self.ai_ready = ai_ready

    # -------------------- helpers --------------------
    def _get_thresholds(self) -> Tuple[float, float]:
        """Return (wl_warning_m, wl_critical_m) from thresholds table, fallback to env defaults."""
        wl_warning = config.WL_WARNING_M
        wl_critical = config.WL_CRITICAL_M
        try:
            res = self.sb.table("thresholds").select("name,value").execute()
            for row in res.data or []:
                name = row.get("name")
                if name == "wl_warning_m" and row.get("value") is not None:
                    wl_warning = float(row["value"])
                if name == "wl_critical_m" and row.get("value") is not None:
                    wl_critical = float(row["value"])
        except Exception:
            pass
        return wl_warning, wl_critical

    def _get_default_station(self) -> Optional[Dict[str, Any]]:
        """Return the default station (by config.DEFAULT_STATION_CODE) or the oldest station."""
        try:
            preferred = self.sb.table("stations").select("*").eq("station_code", config.DEFAULT_STATION_CODE).limit(1).execute().data
            if preferred:
                return preferred[0]
        except Exception:
            pass
        try:
            rows = self.sb.table("stations").select("*").order("created_at", desc=False).limit(1).execute().data
            if rows:
                return rows[0]
        except Exception:
            pass
        return None

    def _get_latest_log(self, station_id: str) -> Optional[Dict[str, Any]]:
        try:
            res = self.sb.table("sensor_logs").select("*").eq("station_id", station_id).order("created_at", desc=True).limit(1).execute()
            if res.data:
                return res.data[0]
        except Exception:
            return None
        return None

    # -------------------- provider API --------------------
    def get_config(self) -> Dict[str, Any]:
        st = self._get_default_station()
        if st:
            center = {"lat": st["lat"], "lng": st["lng"], "zoom": 18}
        else:
            center = config.default_map_center()
        return {"map_center": center, "mode": "LIVE", "ai_ready": self.ai_ready}

    def get_current_snapshot(self) -> Dict[str, Any]:
        st = self._get_default_station()
        if not st:
            # no station configured yet
            return {
                "last_updated": _now_iso(),
                "rainfall": {"mm_per_hr": None, "classification": "Standby"},
                "flood": {"status": "Standby", "predicted_risk": "Standby"},
                "sensors": {"humidity": None, "temperature": None, "wind": None, "water_level": None},
                "note": "LIVE mode: no stations found in Supabase. Add a station row first."
            }

        wl_warning, wl_critical = self._get_thresholds()
        log = self._get_latest_log(st["id"])

        if not log:
            return {
                "last_updated": _now_iso(),
                "rainfall": {"mm_per_hr": None, "classification": "Standby"},
                "flood": {"status": "Standby", "predicted_risk": "Standby"},
                "sensors": {"humidity": None, "temperature": None, "wind": None, "water_level": None},
                "note": f"LIVE mode: station {st['station_code']} has no sensor_logs yet. Send data from Raspberry Pi to /api/sensors/ingest."
            }

        water_level = log.get("water_level_m")
        rain_mm_hr = log.get("rain_mm_hr")

        rainfall_class = classify_rainfall(float(rain_mm_hr or 0.0)) if rain_mm_hr is not None else "Unknown"
        flood_status = flood_status_from_waterlevel(float(water_level or 0.0), wl_warning, wl_critical) if water_level is not None else "Unknown"

        predicted_risk = flood_status  # default
        try:
            pres = self.sb.table("predictions").select("predicted_risk,created_at,model_version,payload").eq("station_id", st["id"]).order("created_at", desc=True).limit(1).execute()
            if pres.data:
                predicted_risk = pres.data[0].get("predicted_risk") or predicted_risk
        except Exception:
            pass

        return {
            "last_updated": log.get("created_at") or _now_iso(),
            "rainfall": {
                "mm_per_hr": rain_mm_hr,
                "classification": rainfall_class
            },
            "flood": {
                "status": flood_status,
                "predicted_risk": predicted_risk
            },
            "sensors": {
                "humidity": log.get("humidity"),
                "temperature": log.get("temperature"),
                "wind": log.get("wind"),
                "water_level": water_level
            }
        }

    def get_map_features(self) -> Dict[str, Any]:
        wl_warning, wl_critical = self._get_thresholds()

        try:
            stations = self.sb.table("stations").select("*").order("created_at", desc=False).execute().data or []
        except Exception:
            stations = []

        markers: List[Dict[str, Any]] = []
        segments: List[Dict[str, Any]] = []

        for st in stations:
            log = self._get_latest_log(st["id"])
            if log:
                wl = log.get("water_level_m")
                rain = log.get("rain_mm_hr")
                rainfall_class = classify_rainfall(float(rain or 0.0)) if rain is not None else "Unknown"
                flood_status = flood_status_from_waterlevel(float(wl or 0.0), wl_warning, wl_critical) if wl is not None else "Unknown"
                risk = risk_level_from_status(flood_status) if flood_status in ("Normal","Warning","Critical") else "low"
                popup = {
                    "water_level_m": wl,
                    "predicted_flood_risk": flood_status,
                    "rainfall_classification": rainfall_class
                }
            else:
                risk = "low"
                popup = {
                    "water_level_m": None,
                    "predicted_flood_risk": "Standby",
                    "rainfall_classification": "Standby"
                }

            markers.append({
                "id": str(st["id"]),
                "name": st.get("name") or st.get("station_code") or "Station",
                "lat": st["lat"],
                "lng": st["lng"],
                "risk_level": risk,
                "popup": popup
            })

        # segments can be added later once you have the creek polyline or multiple points per station
        return {"markers": markers, "segments": segments}

    def get_forecast(self) -> Dict[str, Any]:
        # Standby in Phase 2 (connect weather API + ML later)
        start = datetime.now().replace(minute=0, second=0, microsecond=0)
        rainfall_next_hours = []
        water_level_trend = []
        flood_prediction_next_hours = []
        for h in range(12):
            t = start + timedelta(hours=h)
            rainfall_next_hours.append({"time": t.isoformat(timespec="minutes"), "mm_per_hr": None})
            water_level_trend.append({"time": t.isoformat(timespec="minutes"), "water_level_m": None})
            flood_prediction_next_hours.append({"time": t.isoformat(timespec="minutes"), "status": "Standby"})

        return {
            "last_updated": _now_iso(),
            "rainfall_next_hours": rainfall_next_hours,
            "water_level_trend": water_level_trend,
            "flood_prediction_next_hours": flood_prediction_next_hours,
            "note": "LIVE mode: Forecast is standby in Phase 2. Add weather API + ML to enable real forecasts."
        }

    def get_history(self, range_q: str) -> Dict[str, Any]:
        st = self._get_default_station()
        if not st:
            return {"range": range_q, "last_updated": _now_iso(), "series": [], "note": "No stations found."}

        wl_warning, wl_critical = self._get_thresholds()

        if range_q == "7d":
            limit = 24 * 7  # hourly-ish
        else:
            limit = 24 * 6  # ~10-min samples for 24h

        try:
            res = self.sb.table("sensor_logs") \
                .select("created_at, humidity, temperature, wind, rain_mm_hr, water_level_m") \
                .eq("station_id", st["id"]) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            rows = res.data or []
        except Exception:
            rows = []

        # newest->oldest to oldest->newest for charts
        rows = list(reversed(rows))

        series = []
        for r in rows:
            rain = r.get("rain_mm_hr")
            wl = r.get("water_level_m")
            series.append({
                "time": (r.get("created_at") or "").replace("Z", ""),
                "rain_mm_hr": rain,
                "rain_class": classify_rainfall(float(rain or 0.0)) if rain is not None else "Unknown",
                "water_level_m": wl,
                "flood_status": flood_status_from_waterlevel(float(wl or 0.0), wl_warning, wl_critical) if wl is not None else "Unknown"
            })

        note = "LIVE mode: History from Supabase sensor_logs."
        return {"range": range_q, "last_updated": _now_iso(), "series": series, "note": note}

    def get_demo_raw_logs(self, limit: int) -> List[Dict[str, Any]]:
        return []

    def get_demo_validation(self, limit: int) -> List[Dict[str, Any]]:
        return []

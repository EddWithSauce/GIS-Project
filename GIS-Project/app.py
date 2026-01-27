from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, jsonify, request, session, redirect, url_for, render_template, Response
from datetime import datetime, timedelta
import os, csv, smtplib
from functools import wraps
from supabase_client import supabase_admin, supabase_public
from data_provider import get_provider
import ml_service
import config
from io import StringIO
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from utils.time_utils import now_iso

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
ADMIN_CODE = config.ADMIN_CODE

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            # send them to login, then back to the page they wanted
            next_url = request.path
            return redirect(url_for("login_page", next=next_url))
        return view(*args, **kwargs)
    return wrapped
"""URSM Flood GIS (Phase 5)

Phase 5 goals:
- Keep all routes stable, but reduce mock dependence.
- Prefer Supabase for data reads/exports.
- Keep graceful fallbacks (UI won't crash when tables are empty).
"""

# Data provider (Phase 1+ refactor)
provider = get_provider()



URSM_CREEK_CENTER = {
    "lat": config.URSM_CENTER_LAT,
    "lng": config.URSM_CENTER_LNG,
    "zoom": config.URSM_CENTER_ZOOM
}

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login_page"))
        return view(*args, **kwargs)
    return wrapped

def csv_response(filename: str, headers: list[str], rows: list[list]):
    """
    Creates a downloadable CSV response.
    """
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for r in rows:
        writer.writerow(r)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

# -------------------- EMAIL SENDING --------------------

def send_email_if_configured(to_email: str, subject: str, text_body: str):
    """
    Sends email only if SMTP env vars exist.
    If not configured, it will NOT crash (standby mode).
    """
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    from_email = os.getenv("SMTP_FROM", user)

    if not host or not user or not password or not from_email:
        # Standby: no SMTP config yet
        print("[EMAIL STANDBY] Would send to:", to_email, "Subject:", subject)
        return False

    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain"))
    try:
        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(user, password)
            server.sendmail(from_email, [to_email], msg.as_string())
        return True
    except Exception as e:
        print("[EMAIL ERROR]", e)
        return False

def list_auth_users_basic():
    """
    Returns list of {id, email} from Supabase Auth using service role.
    """
    sb = supabase_admin()
    # supabase-py admin API supports listing users
    res = sb.auth.admin.list_users()

    if isinstance(res, list):
        # res is already a list of user objects/dicts
        raw_users = res
    elif hasattr(res, "users"):
        raw_users = res.users
    elif isinstance(res, dict) and "users" in res:
        raw_users = res["users"]
    elif hasattr(res, "data") and isinstance(res.data, dict) and "users" in res.data:
        raw_users = res.data["users"]
    else:
        raise RuntimeError(f"Unexpected list_users() return type: {type(res)}")

    users = []
    for u in raw_users:
        # u might be object or dict depending on version
        uid = getattr(u, "id", None) or (u.get("id") if isinstance(u, dict) else None)
        email = getattr(u, "email", None) or (u.get("email") if isinstance(u, dict) else None)
        if uid and email:
            users.append({"id": uid, "email": email})
    return users

def classify_rainfall(mm_per_hr: float) -> str:
    if mm_per_hr <= 0.1:
        return "No Rain"
    if mm_per_hr < 2.5:
        return "Light"
    if mm_per_hr < 7.5:
        return "Moderate"
    return "Heavy"

def hours_until_critical(flood_forecast_list):
    """
    flood_forecast_list format: [{"time": "...", "status": "Normal/Warning/Critical"}, ...]
    Returns hours (float) until first Critical, or None if not found.
    """
    now = datetime.now()
    for item in flood_forecast_list:
        if item.get("status") == "Critical":
            try:
                t = datetime.fromisoformat(item["time"])
            except Exception:
                continue
            delta = (t - now).total_seconds() / 3600.0
            return round(max(delta, 0), 2)
    return None

def build_warning_message(payload):
    return (
        "⚠️ WARNING ALERT (Prepare)\n\n"
        f"Predicted rainfall intensity: {payload['predicted_rainfall_intensity']} (peak {payload['peak_rain_mm_hr']} mm/hr)\n"
        f"Alert level: {payload['alert_level']}\n"
        f"Current water level: {payload['current_water_level_m']} m\n"
        f"Predicted flood risk: {payload['predicted_flood_risk']}\n"
        f"Estimated time before flooding: {payload['hours_text']}\n\n"
        "Recommended actions:\n"
        "- Prepare emergency kit\n"
        "- Monitor updates\n"
        "- Coordinate with local officials\n"
    )

def build_critical_message(payload):
    return (
        "🚨 CRITICAL ALERT (Evacuate if advised)\n\n"
        f"Predicted rainfall intensity: {payload['predicted_rainfall_intensity']} (peak {payload['peak_rain_mm_hr']} mm/hr)\n"
        f"Alert level: {payload['alert_level']}\n"
        f"Current water level: {payload['current_water_level_m']} m\n"
        f"Predicted flood risk: {payload['predicted_flood_risk']}\n"
        f"Estimated time before flooding: {payload['hours_text']}\n\n"
        "Recommended actions:\n"
        "- Move to higher ground\n"
        "- Follow evacuation orders immediately\n"
        "- Avoid river/creek areas\n"
    )

def should_send_again(sb, user_id: str, level: str, cooldown_minutes: int = 10) -> bool:
    """
    Returns False if we already sent the same level recently.
    """
    since = (datetime.now() - timedelta(minutes=cooldown_minutes)).isoformat()
    res = sb.table("user_notifications") \
        .select("id, created_at") \
        .eq("user_id", user_id) \
        .eq("alert_level", level) \
        .gte("created_at", since) \
        .limit(1) \
        .execute()
    return len(res.data) == 0

def auto_notify_if_needed(station_id: str, current_snapshot: dict, latest_prediction: dict | None = None):
    """
    Automatically create web notifications + send email when status is Warning/Critical.

    Phase 4 update:
    - Uses latest prediction payload (if available) to populate:
      rainfall intensity, predicted flood risk, and 'hours before flooding' (standby if not provided yet).
    - Uses cooldowns to avoid email/web spam.
    """

    flood_status = current_snapshot["flood"]["status"]  # Normal/Warning/Critical (based on current water level)
    water_level = current_snapshot["sensors"]["water_level"]

    # Only notify on Warning/Critical
    if flood_status not in ["Warning", "Critical"]:
        return {"sent": 0, "reason": "status_normal"}

    # Pull extra prediction info if present
    predicted_flood_risk = current_snapshot["flood"].get("predicted_risk") or flood_status
    predicted_rain_intensity = current_snapshot["rainfall"].get("classification") or "Unknown"
    peak_rain = current_snapshot["rainfall"].get("mm_per_hr")

    hrs = None
    if latest_prediction:
        predicted_flood_risk = latest_prediction.get("predicted_risk") or predicted_flood_risk
        pl = latest_prediction.get("payload") or {}
        predicted_rain_intensity = pl.get("predicted_rainfall_intensity") or predicted_rain_intensity
        hrs = pl.get("hours_before_flood")

    hours_text = f"~{hrs} hour(s)" if isinstance(hrs, (int, float)) else "Unknown (standby)"

    payload = {
        "predicted_rainfall_intensity": predicted_rain_intensity,
        "peak_rain_mm_hr": peak_rain,
        "alert_level": flood_status,
        "predicted_flood_risk": predicted_flood_risk,
        "current_water_level_m": water_level,
        "hours_before_flood": hrs,
        "hours_text": hours_text
    }

    title = f"[{flood_status}] URSM Flood Alert"
    message = build_critical_message(payload) if flood_status == "Critical" else build_warning_message(payload)

    # Send to all users in Supabase Auth
    sb = supabase_admin()
    users = list_auth_users_basic()

    sent = 0
    cooldown = config.COOLDOWN_CRITICAL_MIN if flood_status == "Critical" else config.COOLDOWN_WARNING_MIN

    for u in users:
        # prevent spam (cooldown)
        if not should_send_again(sb, u["id"], flood_status, cooldown_minutes=cooldown):
            continue

        # store web notification (Supabase table: user_notifications)
        sb.table("user_notifications").insert({
            "user_id": u["id"],
            "email": u["email"],
            "station_id": station_id,
            "alert_level": flood_status,
            "title": title,
            "message": message,
            "predicted_rainfall_intensity": payload["predicted_rainfall_intensity"],
            "predicted_flood_risk": payload["predicted_flood_risk"],
            "hours_before_flood": payload["hours_before_flood"],
            "peak_rain_mm_hr": payload["peak_rain_mm_hr"],
            "current_water_level_m": payload["current_water_level_m"],
            "channel": "both"
        }).execute()

        # email (optional / standby if SMTP not configured)
        send_email_if_configured(u["email"], title, message)

        sent += 1

    return {"sent": sent, "reason": "notified"}



# -------------------- Pages --------------------
@app.route("/")
def dashboard_page():
    return render_template("dashboard.html")

@app.route("/forecast")
@login_required
def forecast_page():
    return render_template("forecast.html")

@app.route("/history")
@login_required
def history_page():
    return render_template("history.html")

@app.route("/alerts")
@login_required
def alerts_page():
    return render_template("alerts.html")



# -------------------- API: Current snapshot --------------------
@app.route("/api/config")
def api_config():
    cfg = provider.get_config()
    return jsonify({"map_center": cfg["map_center"], "mode": cfg.get("mode","STANDBY")})

@app.route("/api/current")
def api_current():
    # Phase 1: data comes from provider (MockProvider in STANDBY)
    payload = provider.get_current_snapshot()

    return jsonify(payload)


# -------------------- Device Ingestion (Raspberry Pi) --------------------
@app.post("/api/sensors/ingest")
def api_sensors_ingest():
    """Raspberry Pi -> Flask -> Supabase

    Expected JSON:
    {
      "station_code": "URSM_01",
      "humidity": 72.5,
      "temperature": 29.1,
      "wind": 1.2,
      "rain_mm_hr": 3.4,
      "water_level_m": 0.91,
      "lat": 14.517697,        # optional (only used if creating station)
      "lng": 121.235711        # optional
    }

    Security:
    - If DEVICE_API_KEY is set in .env, client must send header: X-API-KEY: <key>
    """
    # simple API key check (recommended)
    if config.DEVICE_API_KEY:
        provided = request.headers.get("X-API-KEY", "")
        if provided != config.DEVICE_API_KEY:
            return jsonify({"ok": False, "error": "Unauthorized device"}), 401

    data = request.get_json(silent=True) or {}
    station_code = (data.get("station_code") or "").strip()
    if not station_code:
        return jsonify({"ok": False, "error": "station_code is required"}), 400


    # One-station mode: force all ingests into the default station (ignore other station codes)
    if config.ONE_STATION_MODE:
        if station_code != config.DEFAULT_STATION_CODE:
            station_code = config.DEFAULT_STATION_CODE
    sb = supabase_admin()

    # Find (or create) station
    st_res = sb.table("stations").select("*").eq("station_code", station_code).limit(1).execute()
    station = st_res.data[0] if st_res.data else None

    if not station:
        lat = data.get("lat")
        lng = data.get("lng")
        name = data.get("name") or (config.DEFAULT_STATION_NAME if config.ONE_STATION_MODE else station_code)

        # If station is missing and lat/lng not provided, auto-create using default center + offsets.
        if lat is None or lng is None:
            lat, lng = config.default_station_latlng()

        ins = sb.table("stations").insert({"station_code": station_code, "name": name, "lat": lat, "lng": lng}).execute()
        station = ins.data[0] if ins.data else None

    station_id = station["id"]

    # Insert sensor log
    log_row = {
        "station_id": station_id,
        "humidity": data.get("humidity"),
        "temperature": data.get("temperature"),
        "wind": data.get("wind"),
        "rain_mm_hr": data.get("rain_mm_hr"),
        "water_level_m": data.get("water_level_m"),
        "payload": data  # keep raw
    }
    sb.table("sensor_logs").insert(log_row).execute()

    # Phase 4: write a prediction row (standby rules now; ML later)
    pred_row = None
    if config.PREDICT_ON_INGEST:
        try:
            pred_row = ml_service.write_prediction_from_log(station_id, log_row, sb=sb)
        except Exception as e:
            print("[PREDICT ERROR]", e)


    # Update sensor health table (sensors)
    sensor_types = [
        ("humidity", data.get("humidity")),
        ("temperature", data.get("temperature")),
        ("wind", data.get("wind")),
        ("rain", data.get("rain_mm_hr")),
        ("water_level", data.get("water_level_m")),
    ]
    now_ts = datetime.now().isoformat()

    for stype, val in sensor_types:
        # if value is missing, don't mark online (but still keep record)
        is_online = val is not None
        existing = sb.table("sensors").select("id").eq("station_id", station_id).eq("sensor_type", stype).limit(1).execute()
        if existing.data:
            sb.table("sensors").update({
                "is_online": is_online,
                "last_data_received": now_ts if is_online else None,
                "missing_data_count": 0 if is_online else 1
            }).eq("id", existing.data[0]["id"]).execute()
        else:
            sb.table("sensors").insert({
                "station_id": station_id,
                "sensor_type": stype,
                "is_online": is_online,
                "last_data_received": now_ts if is_online else None,
                "missing_data_count": 0 if is_online else 1,
                "notes": "Auto-created by /api/sensors/ingest"
            }).execute()

    # Optional: trigger notifications here (avoid spamming on dashboard refresh)
    if config.NOTIFY_ENABLED:
        try:
            # ensure provider is refreshed in LIVE mode
            current = provider.get_current_snapshot()
            auto_notify_if_needed(station_id, current, pred_row)
        except Exception as e:
            print("[NOTIFY ERROR]", e)

    return jsonify({"ok": True, "station_id": station_id, "received_at": now_ts})


# -------------------- User Exclusivity Module --------------------


# -------------------- API: Map features (markers + segments) --------------------
@app.route("/api/map/features")
def api_map_features():
    feats = provider.get_map_features()
    return jsonify(feats)


# -------------------- API: Forecast (mock) --------------------
@app.route("/api/forecast")
def api_forecast():
    data = provider.get_forecast()
    return jsonify(data)


# -------------------- API: History (mock) --------------------
@app.route("/api/history")
def api_history():
    range_q = request.args.get("range", "24h")
    data = provider.get_history(range_q)
    return jsonify(data)


# -------------------- ML Standby Endpoints --------------------
@app.route("/api/ml/status")
def api_ml_status():
    is_ml = bool(config.AI_READY) and config.MODEL_DRIVER != "standby"
    return jsonify({
        "ml_ready": is_ml,
        "mode": "ML" if is_ml else "STANDBY",
        "model_driver": config.MODEL_DRIVER,
        "message": "ML is enabled." if is_ml else "Standby mode: predictions are rule-based until ML is connected.",
        "how_to_enable": "Set AI_READY=true and configure MODEL_DRIVER + model files in ./models/ (see config.py / ml_service.py)."
    })

@app.route("/api/ml/predict", methods=["POST"])
def api_ml_predict():
    # Phase 4: Returns a standby prediction for the provided input (no DB write).
    data = request.get_json(silent=True) or {}
    wl = data.get("water_level_m")
    rain = data.get("rain_mm_hr")
    wl_warning = config.WL_WARNING_M
    wl_critical = config.WL_CRITICAL_M
    try:
        wl_val = float(wl) if wl is not None else None
    except Exception:
        wl_val = None
    try:
        rain_val = float(rain) if rain is not None else None
    except Exception:
        rain_val = None

    predicted_rain_intensity = classify_rainfall(rain_val or 0.0) if rain_val is not None else "Unknown"
    predicted_risk = "Unknown"
    if wl_val is not None:
        predicted_risk = flood_status_from_waterlevel(wl_val)

    return jsonify({
        "ml_ready": bool(config.AI_READY) and config.MODEL_DRIVER != "standby",
        "mode": "STANDBY",
        "predicted_rainfall_intensity": predicted_rain_intensity,
        "predicted_flood_risk": predicted_risk,
        "hours_before_flood": None,
        "received_input": data,
        "note": "Standby prediction only. Real ML inference will replace this later."
    })

# -------------------- Auth Routes --------------------
@app.get("/login")
def login_page():
    next_url = request.args.get("next", "/")
    return render_template("auth/login.html", next=next_url)

@app.post("/login")
def login_post():
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()

    if not email or not password:
        return render_template("auth/login.html", error="Email and password are required.")

    sb = supabase_public()
    try:
        auth_res = sb.auth.sign_in_with_password({"email": email, "password": password})
        # Save session info
        session["user_email"] = email
        session["user_access_token"] = auth_res.session.access_token if auth_res.session else None
        session["user_refresh_token"] = auth_res.session.refresh_token if auth_res.session else None
        session["user_id"] = auth_res.user.id if getattr(auth_res, "user", None) else None
        
        next_url = request.form.get("next") or "/"
        return redirect(next_url)

    except Exception as e:
        return render_template("auth/login.html", error="Invalid login or user not found.")

@app.get("/signup")
def signup_page():
    return render_template("auth/signup.html")

@app.post("/signup")
def signup_post():
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()
    confirm = request.form.get("confirm_password", "").strip()

    if not email or not password:
        return render_template("auth/signup.html", error="Email and password are required.")
    if password != confirm:
        return render_template("auth/signup.html", error="Passwords do not match.")

    sb = supabase_public()
    try:
        sb.auth.sign_up({"email": email, "password": password})
        # Many Supabase setups require email confirmation; show message either way
        return render_template("auth/login.html", info="Sign up successful. If email confirmation is enabled, check your email then login.")
    except Exception:
        return render_template("auth/signup.html", error="Sign up failed. Email may already be registered.")

@app.get("/logout")
def logout():
    session.pop("user_email", None)
    session.pop("user_access_token", None)
    session.pop("user_refresh_token", None)
    session.pop("user_id", None)
    return redirect("/")

# -------------------- Admin Login --------------------
@app.get("/admin/login")
def admin_login_page():
    return render_template("auth/admin_login.html")

@app.post("/admin/login")
def admin_login_post():
    code = request.form.get("code", "").strip()
    if code != ADMIN_CODE:
        return render_template("auth/admin_login.html", error="Invalid admin code.")
    session["is_admin"] = True
    return redirect("/admin")

@app.get("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect("/")

# -------------------- Admin Pages --------------------
@app.get("/admin")
@admin_required
def admin_dashboard_page():
    return render_template("admin/dashboard.html")

@app.get("/admin/sensors")
@admin_required
def admin_sensors_page():
    return render_template("admin/sensors.html")

@app.get("/admin/logs")
@admin_required
def admin_logs_page():
    return render_template("admin/logs.html")

@app.get("/admin/thresholds")
@admin_required
def admin_thresholds_page():
    return render_template("admin/thresholds.html")

@app.get("/admin/model-monitor")
@admin_required
def admin_model_monitor_page():
    return render_template("admin/model_monitor.html")

@app.get("/admin/validation")
@admin_required
def admin_validation_page():
    return render_template("admin/validation.html")

@app.get("/api/db-test")
def db_test():
    sb = supabase_admin()
    res = sb.table("stations").select("*").limit(5).execute()
    return jsonify({
        "connected": True,
        "rows": res.data
    })

# -------------------- CSV (Raw Logs + Validation) --------------------

def _get_default_station_id(sb):
    """Best-effort station id for one-station mode.

    Priority:
    1) station_code == config.DEFAULT_STATION_CODE
    2) first station row
    """
    try:
        if getattr(config, "DEFAULT_STATION_CODE", None):
            r = sb.table("stations").select("id").eq("station_code", config.DEFAULT_STATION_CODE).limit(1).execute()
            if r.data:
                return r.data[0]["id"]
    except Exception:
        pass
    try:
        r = sb.table("stations").select("id").order("created_at", desc=True).limit(1).execute()
        if r.data:
            return r.data[0]["id"]
    except Exception:
        pass
    return None


@app.get("/admin/export/raw-logs.csv")
@admin_required
def export_raw_logs_csv():
    limit = int(request.args.get("limit", "200"))
    limit = max(1, min(limit, 5000))

    sb = supabase_admin()
    station_id = _get_default_station_id(sb)

    logs = []
    try:
        q = sb.table("sensor_logs").select(
            "created_at,station_id,humidity,temperature,wind,rain_mm_hr,water_level_m"
        ).order("created_at", desc=True).limit(limit)
        if station_id:
            q = q.eq("station_id", station_id)
        res = q.execute()
        logs = res.data or []
    except Exception as e:
        print("[CSV RAW LOGS ERROR]", e)

    # Fallback: keep a minimal CSV so you can test the download button
    if not logs:
        logs = [{
            "created_at": now_iso(),
            "station_id": station_id or "STATION_DEMO_01",
            "humidity": None,
            "temperature": None,
            "wind": None,
            "rain_mm_hr": None,
            "water_level_m": None,
        }]

    headers = [
        "timestamp",
        "station_id",
        "humidity",
        "temperature",
        "wind",
        "rain_mm_hr",
        "water_level_m",
        "source"
    ]

    rows = []
    for x in logs:
        rows.append([
            (x.get("created_at") or "").replace("T", " ")[:19],
            x.get("station_id"),
            x.get("humidity"),
            x.get("temperature"),
            x.get("wind"),
            x.get("rain_mm_hr"),
            x.get("water_level_m"),
            "SUPABASE" if x.get("humidity") is not None or x.get("water_level_m") is not None else "STANDBY",
        ])

    return csv_response("raw_logs.csv", headers, rows)

@app.get("/admin/export/validation.csv")
@admin_required
def export_validation_csv():
    # Optional date filters later (kept for easy future upgrade)
    start = request.args.get("start")  # YYYY-MM-DD
    end = request.args.get("end")      # YYYY-MM-DD

    sb = supabase_admin()
    station_id = _get_default_station_id(sb)

    # Pull from predictions table. For "actual" values, we use payload.inputs when available.
    data = []
    try:
        q = sb.table("predictions").select(
            "created_at,station_id,predicted_risk,predicted_water_level_m,model_version,payload"
        ).order("created_at", desc=True).limit(500)
        if station_id:
            q = q.eq("station_id", station_id)
        # Optional date filters (YYYY-MM-DD)
        if start:
            q = q.gte("created_at", f"{start}T00:00:00")
        if end:
            q = q.lte("created_at", f"{end}T23:59:59")
        res = q.execute()
        data = res.data or []
    except Exception as e:
        print("[CSV VALIDATION ERROR]", e)

    if not data:
        data = [{
            "created_at": now_iso(),
            "station_id": station_id or "STATION_DEMO_01",
            "predicted_risk": "Unknown",
            "predicted_water_level_m": None,
            "model_version": config.STANDBY_MODEL_VERSION,
            "payload": {"notes": "No prediction rows yet."}
        }]

    headers = [
        "timestamp",
        "station_id",
        "actual_water_level_m",
        "actual_flood_event",
        "predicted_flood_risk",
        "predicted_water_level_m",
        "model_version",
        "notes"
    ]

    rows = []
    for x in data:
        payload = x.get("payload") or {}
        inputs = (payload.get("inputs") or {}) if isinstance(payload, dict) else {}
        actual_wl = inputs.get("water_level_m")
        actual_flood_event = "YES" if (actual_wl is not None and float(actual_wl) >= config.WL_CRITICAL_M) else "NO"

        rows.append([
            (x.get("created_at") or "").replace("T", " ")[:19],
            x.get("station_id"),
            actual_wl,
            actual_flood_event,
            x.get("predicted_risk"),
            x.get("predicted_water_level_m"),
            x.get("model_version"),
            payload.get("notes") if isinstance(payload, dict) else "",
        ])

    filename = "validation.csv"
    return csv_response(filename, headers, rows)

# -------------------- Notification --------------------
@app.get("/notifications")
@login_required
def notifications_page():
    return render_template("notifications.html")

@app.get("/api/notifications")
@login_required
def api_notifications():
    sb = supabase_admin()
    uid = session.get("user_id")

    res = sb.table("user_notifications") \
        .select("*") \
        .eq("user_id", uid) \
        .order("created_at", desc=True) \
        .limit(50) \
        .execute()

    return jsonify({"items": res.data})

@app.post("/api/notifications/mark-read")
@login_required
def api_notifications_mark_read():
    notif_id = request.json.get("id")
    uid = session.get("user_id")

    sb = supabase_admin()
    sb.table("user_notifications") \
        .update({"is_read": True}) \
        .eq("id", notif_id) \
        .eq("user_id", uid) \
        .execute()

    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(debug=True)

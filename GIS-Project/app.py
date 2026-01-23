from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, jsonify, request, session, redirect, url_for, render_template, Response
from datetime import datetime, timedelta
import random, os, csv, smtplib
from functools import wraps
from supabase_client import supabase_admin, supabase_public
from io import StringIO
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fakumaniggasecretkey")
ADMIN_CODE = os.getenv("ADMIN_CODE", "ADMIN123")


# ---- CONFIG: URSM Creek center (EDIT THIS) ----
URSM_CREEK_CENTER = {
    "lat": 14.517697,   # <-- change to your real center coordinate
    "lng": 121.235711,  # <-- change to your real center coordinate
    "zoom": 18
}

# ---- Mock "status logic" (replace later with real rules/ML) ----
def classify_rainfall(mm_per_hr: float) -> str:
    # Simple demo thresholds; adjust based on your project standard
    if mm_per_hr <= 0.1:
        return "No Rain"
    if mm_per_hr < 2.5:
        return "Light"
    if mm_per_hr < 7.5:
        return "Moderate"
    return "Heavy"

def flood_status_from_waterlevel(water_level_m: float) -> str:
    # Simple demo thresholds; adjust based on URSM creek calibration
    if water_level_m < 0.8:
        return "Normal"
    if water_level_m < 1.2:
        return "Warning"
    return "Critical"

def risk_level_from_status(flood_status: str) -> str:
    # For marker coloring / segments
    if flood_status == "Normal":
        return "low"
    if flood_status == "Warning":
        return "medium"
    return "high"

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_email"):
            return redirect(url_for("login_page"))
        return view(*args, **kwargs)
    return wrapped

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

def auto_notify_if_needed(current_snapshot: dict):
    """
    Automatically create web notifications + send email when status is Warning/Critical.
    Uses mock forecast now; later replace forecast and values with real data.
    """

    flood_status = current_snapshot["flood"]["status"]         # Normal/Warning/Critical
    water_level = current_snapshot["sensors"]["water_level"]
    rain_class_now = current_snapshot["rainfall"]["classification"]

    # Only notify on Warning/Critical
    if flood_status not in ["Warning", "Critical"]:
        return {"sent": 0, "reason": "status_normal"}

    # Build forecast-based "hours before flood"
    forecast = api_forecast().get_json()  # reuse your existing endpoint logic
    rain_next = forecast["rainfall_next_hours"]
    flood_next = forecast["flood_prediction_next_hours"]

    peak_rain = max([x["mm_per_hr"] for x in rain_next]) if rain_next else 0.0
    predicted_rain_intensity = classify_rainfall(peak_rain)
    hrs = hours_until_critical(flood_next)

    hours_text = f"~{hrs} hour(s)" if hrs is not None else "Unknown (no critical event in forecast window)"

    payload = {
        "predicted_rainfall_intensity": predicted_rain_intensity,
        "peak_rain_mm_hr": round(peak_rain, 2),
        "alert_level": flood_status,
        "predicted_flood_risk": flood_status,   # standby; replace with ML prediction
        "current_water_level_m": water_level,
        "hours_before_flood": hrs,
        "hours_text": hours_text
    }

    title = f"[{flood_status}] URSM Flood Alert"

    if flood_status == "Critical":
        message = build_critical_message(payload)
    else:
        message = build_warning_message(payload)

    # Send to all users in Supabase Auth
    sb = supabase_admin()
    users = list_auth_users_basic()



    sent = 0
    for u in users:
        # prevent spam (cooldown)
        cooldown = 15 if flood_status == "Warning" else 5
        if not should_send_again(sb, u["id"], flood_status, cooldown_minutes=cooldown):
            continue

        # store web notification
        sb.table("user_notifications").insert({
            "user_id": u["id"],
            "email": u["email"],
            "station_id": None,  # later: station id
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
    return jsonify({
        "map_center": URSM_CREEK_CENTER
    })

@app.route("/api/current")
def api_current():
    # Mock sensor readings
    water_level = round(random.uniform(0.4, 1.5), 2)
    rain_mm_hr = round(random.choice([0.0, 0.2, 1.2, 4.3, 9.1]), 1)

    rainfall_class = classify_rainfall(rain_mm_hr)
    flood_status = flood_status_from_waterlevel(water_level)

    payload = {
        "last_updated": now_iso(),
        "rainfall": {
            "mm_per_hr": rain_mm_hr,
            "classification": rainfall_class
        },
        "flood": {
            "status": flood_status,
            "predicted_risk": flood_status  # placeholder until ML
        },
        "sensors": {
            "humidity": round(random.uniform(55, 95), 1),
            "temperature": round(random.uniform(23, 34), 1),
            "wind": round(random.uniform(0, 12), 1),
            "water_level": water_level
        }
    }
    try:
        auto_notify_if_needed(payload)
    except Exception as e:
    # don't break dashboard if notify fails
        print("[NOTIFY ERROR]", e)

    return jsonify(payload)

# -------------------- User Exclusivity Module --------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            # send them to login, then back to the page they wanted
            next_url = request.path
            return redirect(url_for("login_page", next=next_url))
        return view(*args, **kwargs)
    return wrapped

# -------------------- API: Map features (markers + segments) --------------------
@app.route("/api/map/features")
def api_map_features():
    # Mock “segments” and “markers” around the center.
    lat = URSM_CREEK_CENTER["lat"]
    lng = URSM_CREEK_CENTER["lng"]

    # Create a few sample points along a creek-like line
    points = [
        {"id": "p1", "name": "Device Point",  "lat": lat - 0.0002, "lng": lng + 0.0000},
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
                "predicted_flood_risk": flood_status,   # placeholder
                "rainfall_classification": rainfall_class
            }
        })

    # Segment lines between markers, colored by "worst" risk
    for i in range(len(points) - 1):
        a = markers[i]
        b = markers[i + 1]
        worst = "low"
        for r in [a["risk_level"], b["risk_level"]]:
            if r == "high":
                worst = "high"
            elif r == "medium" and worst != "high":
                worst = "medium"

        segments.append({
            "id": f"s{i+1}",
            "risk_level": worst,
            "path": [[a["lat"], a["lng"]], [b["lat"], b["lng"]]]
        })

    return jsonify({
        "markers": markers,
        "segments": segments
    })


# -------------------- API: Forecast (mock) --------------------
@app.route("/api/forecast")
def api_forecast():
    # Next 12 hours mock forecast
    start = datetime.now().replace(minute=0, second=0, microsecond=0)
    rainfall = []
    water_level = []
    flood_pred = []

    base_wl = random.uniform(0.5, 1.1)
    for h in range(12):
        t = start + timedelta(hours=h)
        rain = max(0.0, random.gauss(2.0, 2.0))  # mm/hr
        wl = max(0.3, base_wl + (rain * 0.04) + random.uniform(-0.05, 0.05))
        status = flood_status_from_waterlevel(wl)

        rainfall.append({"time": t.isoformat(timespec="minutes"), "mm_per_hr": round(rain, 2)})
        water_level.append({"time": t.isoformat(timespec="minutes"), "water_level_m": round(wl, 2)})
        flood_pred.append({"time": t.isoformat(timespec="minutes"), "status": status})

    return jsonify({
        "last_updated": now_iso(),
        "rainfall_next_hours": rainfall,
        "water_level_trend": water_level,
        "flood_prediction_next_hours": flood_pred,
        "note": "Forecast is mock data. Replace with weather API + ML when ready."
    })


# -------------------- API: History (mock) --------------------
@app.route("/api/history")
def api_history():
    # query: range=24h or 7d
    range_q = request.args.get("range", "24h")
    now = datetime.now().replace(second=0, microsecond=0)

    if range_q == "7d":
        points = 7 * 24  # hourly for 7 days
        step = timedelta(hours=1)
    else:
        points = 24 * 6  # every 10 minutes for 24 hours
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
            "flood_status": flood_status
        })

    return jsonify({
        "range": range_q,
        "last_updated": now_iso(),
        "series": series,
        "note": "History is mock data. Replace with database (SQLite/Postgres) when sensor logging is ready."
    })


# -------------------- ML Standby Endpoints --------------------
@app.route("/api/ml/status")
def api_ml_status():
    return jsonify({
        "ml_ready": False,
        "message": "Standby mode: ML model not connected yet.",
        "how_to_enable": "Later: load your trained model and set ml_ready=True; route /api/ml/predict should call the model."
    })

@app.route("/api/ml/predict", methods=["POST"])
def api_ml_predict():
    # Standby: accept input but return placeholder
    # Later: use request.json as input features for your ML model
    return jsonify({
        "ml_ready": False,
        "predicted_flood_risk": "Unknown",
        "details": "Standby mode. No model loaded.",
        "received_input": request.json
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
@app.get("/admin/export/raw-logs.csv")
@admin_required
def export_raw_logs_csv():
    limit = int(request.args.get("limit", "200"))
    limit = max(1, min(limit, 5000))

    logs = demo_raw_logs(limit=limit)

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

    rows = [
        [
            x["timestamp"],
            x["station_id"],
            x["humidity"],
            x["temperature"],
            x["wind"],
            x["rain_mm_hr"],
            x["water_level_m"],
            x["source"],
        ]
        for x in logs
    ]

    return csv_response("raw_logs_standby.csv", headers, rows)

@app.get("/admin/export/validation.csv")
@admin_required
def export_validation_csv():
    # Optional date filters later (kept for easy future upgrade)
    start = request.args.get("start")  # YYYY-MM-DD
    end = request.args.get("end")      # YYYY-MM-DD

    # Standby: ignore filters for now, but keep the parameters.
    data = demo_validation(limit=120)

    headers = [
        "timestamp",
        
        "actual_flood_event",
        "predicted_flood_risk",
        "predicted_water_level_m",
        "model_version",
        "notes"
    ]

    rows = [
        [
            x["timestamp"],
            x["station_id"],
            x["actual_water_level_m"],
            x["actual_flood_event"],
            x["predicted_flood_risk"],
            x["predicted_water_level_m"],
            x["model_version"],
            x["notes"],
        ]
        for x in data
    ]

    filename = "validation_standby.csv"
    return csv_response(filename, headers, rows)

def demo_raw_logs(limit: int = 100):
    """
    Standby raw logs. Replace later with Supabase query from sensor_logs table.
    """
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
            "source": "STANDBY"
        })
    return rows


def demo_validation(limit: int = 60):
    """
    Standby validation data. Replace later by joining sensor_logs + predictions.
    """
    rows = []
    base = datetime.now().replace(second=0, microsecond=0)
    for i in range(limit):
        t = base - timedelta(hours=(limit - i))
        actual_wl = round(random.uniform(0.4, 1.5), 2)

        # predicted risk (standby)
        if actual_wl < 0.8:
            pred_risk = "Normal"
        elif actual_wl < 1.2:
            pred_risk = "Warning"
        else:
            pred_risk = "Critical"

        # simple fake predicted WL (optional)
        predicted_wl = round(actual_wl + random.uniform(-0.12, 0.12), 2)

        rows.append({
            "timestamp": t.isoformat(timespec="minutes"),
            "station_id": "STATION_DEMO_01",
            "actual_water_level_m": actual_wl,
            "actual_flood_event": "YES" if actual_wl >= 1.2 else "NO",
            "predicted_flood_risk": pred_risk,
            "predicted_water_level_m": predicted_wl,
            "model_version": "STANDBY_MODEL_v0",
            "notes": "Standby demo"
        })
    return rows

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

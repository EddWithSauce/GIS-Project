from flask import Flask, render_template, jsonify, request, session, redirect, url_for, render_template, Response
from datetime import datetime, timedelta
import random, os, csv
from functools import wraps
from supabase_client import get_supabase
from io import StringIO


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
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


# -------------------- Pages --------------------
@app.route("/")
def dashboard_page():
    return render_template("dashboard.html")

@app.route("/forecast")
def forecast_page():
    return render_template("forecast.html")

@app.route("/history")
def history_page():
    return render_template("history.html")

@app.route("/alerts")
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
    return jsonify(payload)


# -------------------- API: Map features (markers + segments) --------------------
@app.route("/api/map/features")
def api_map_features():
    # Mock “segments” and “markers” around the center.
    lat = URSM_CREEK_CENTER["lat"]
    lng = URSM_CREEK_CENTER["lng"]

    # Create a few sample points along a creek-like line
    points = [
        {"id": "p1", "name": "Upstream Point",   "lat": lat + 0.0004, "lng": lng + 0.0001},
        {"id": "p2", "name": "Midstream Point",  "lat": lat - 0.0002, "lng": lng + 0.0000},
        {"id": "p3", "name": "Downstream Point", "lat": lat - 0.0008, "lng": lng + 0.0002},
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
    return render_template("auth/login.html")

@app.post("/login")
def login_post():
    # Tonight prototype: accept any email/password (no DB yet)
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()
    if not email or not password:
        return render_template("auth/login.html", error="Email and password required.")
    session["user_email"] = email
    return redirect("/")

@app.get("/signup")
def signup_page():
    return render_template("auth/signup.html")

@app.post("/signup")
def signup_post():
    # Tonight prototype: just store session (later: Supabase Auth)
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()
    if not email or not password:
        return render_template("auth/signup.html", error="Email and password required.")
    session["user_email"] = email
    return redirect("/")

@app.get("/logout")
def logout():
    session.clear()
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

# -------------------- CSV Routes (Raw Logs + Validation) --------------------
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

# -------------------- CSV Routes (Actual vs Predicted) --------------------
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
        "station_id",
        "actual_water_level_m",
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


if __name__ == "__main__":
    app.run(debug=True)

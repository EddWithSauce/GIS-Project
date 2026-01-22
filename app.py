from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, jsonify, request, session, redirect, url_for, render_template
from datetime import datetime, timedelta
import random
import os
from functools import wraps
from supabase_client import supabase_admin, supabase_public
from flask import session, redirect, url_for
from supabase_client import supabase_public

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
    return jsonify(payload)

# -------------------- User Exclusivity Module --------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_email"):
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

if __name__ == "__main__":
    app.run(debug=True)

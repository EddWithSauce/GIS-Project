function badgeClassForFlood(status) {
  if (status === "Critical") return "text-rose-300";
  if (status === "Warning") return "text-amber-300";
  return "text-emerald-300";
}

async function loadCurrent() {
  const res = await fetch("/api/current");
  return await res.json();
}

async function loadMLStatus() {
  const res = await fetch("/api/ml/status");
  return await res.json();
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function setFloodStatusText(value) {
  const el = document.getElementById("floodStatus");
  if (!el) return;
  el.textContent = value;
  el.className = `text-lg font-semibold mt-1 ${badgeClassForFlood(value)}`;
}

async function refreshAll() {
  const data = await loadCurrent();

  setText("rainStatus", data.rainfall.classification);
  setText("rainDetail", `${data.rainfall.mm_per_hr} mm/hr`);

  setFloodStatusText(data.flood.status);

  setText("hum", `${data.sensors.humidity} %`);
  setText("temp", `${data.sensors.temperature} °C`);
  setText("wind", `${data.sensors.wind} m/s`);
  setText("wl", `${data.sensors.water_level} m`);

  setText("lastUpdated", data.last_updated);

  // Refresh map features too
  if (window.__refreshMap) {
    window.__refreshMap();
  }

  const ml = await loadMLStatus();
  setText("mlStatus", ml.ml_ready ? "Connected" : "Standby");
}

document.getElementById("btnRefresh")?.addEventListener("click", refreshAll);

// Auto-refresh every 30 seconds (optional)
setInterval(refreshAll, 30000);

refreshAll();

let map;
let markerLayer;
let segmentLayer;

function riskColor(riskLevel) {
  if (riskLevel === "high") return "#fb7185";   // rose-400
  if (riskLevel === "medium") return "#fbbf24"; // amber-400
  return "#34d399";                             // emerald-400
}

async function loadMapConfig() {
  const res = await fetch("/api/config");
  return await res.json();
}

async function loadFeatures() {
  const res = await fetch("/api/map/features");
  return await res.json();
}

function initMap(center) {
  map = L.map("map").setView([center.lat, center.lng], center.zoom);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors"
  }).addTo(map);

  markerLayer = L.layerGroup().addTo(map);
  segmentLayer = L.layerGroup().addTo(map);
}

function renderFeatures(features) {
  markerLayer.clearLayers();
  segmentLayer.clearLayers();

  // segments (colored lines)
  for (const seg of features.segments) {
    L.polyline(seg.path, {
      color: riskColor(seg.risk_level),
      weight: 6,
      opacity: 0.9
    }).addTo(segmentLayer);
  }

  // markers
  for (const m of features.markers) {
    const circle = L.circleMarker([m.lat, m.lng], {
      radius: 10,
      color: riskColor(m.risk_level),
      fillColor: riskColor(m.risk_level),
      fillOpacity: 0.85,
      weight: 2
    });

    const p = m.popup;
    const html = `
      <div style="font-family: system-ui; font-size: 12px;">
        <div style="font-weight: 700; margin-bottom: 6px;">${m.name}</div>
        <div><b>Water Level:</b> ${p.water_level_m} m</div>
        <div><b>Predicted Flood Risk:</b> ${p.predicted_flood_risk}</div>
        <div><b>Rainfall:</b> ${p.rainfall_classification}</div>
        <div style="margin-top: 6px; color: #64748b;">Risk level: ${m.risk_level.toUpperCase()}</div>
      </div>
    `;
    circle.bindPopup(html);
    circle.addTo(markerLayer);
  }
}

async function boot() {
  const cfg = await loadMapConfig();
  initMap(cfg.map_center);

  const feats = await loadFeatures();
  renderFeatures(feats);
}

// Expose a refresh function for dashboard.js
window.__refreshMap = async function () {
  if (!map) return;
  const feats = await loadFeatures();
  renderFeatures(feats);
};

boot();

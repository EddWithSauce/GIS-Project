let rainChart, wlChart;

async function loadForecast() {
  const res = await fetch("/api/forecast");
  return await res.json();
}

function destroyIfExists(chart) {
  if (chart) chart.destroy();
}

function buildChart(canvasId, labels, data, labelName) {
  const ctx = document.getElementById(canvasId);
  return new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: labelName,
        data,
        tension: 0.35,
        pointRadius: 2
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color: "#e2e8f0" } }
      },
      scales: {
        x: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(148,163,184,0.15)" } },
        y: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(148,163,184,0.15)" } }
      }
    }
  });
}

function statusPill(status) {
  let cls = "border-slate-700 text-slate-200";
  if (status === "Critical") cls = "border-rose-500/40 text-rose-200 bg-rose-500/10";
  else if (status === "Warning") cls = "border-amber-500/40 text-amber-200 bg-amber-500/10";
  else cls = "border-emerald-500/40 text-emerald-200 bg-emerald-500/10";

  return `<span class="text-xs px-2 py-1 rounded-lg border ${cls}">${status}</span>`;
}

async function render() {
  const data = await loadForecast();

  document.getElementById("forecastUpdated").textContent = `Updated: ${data.last_updated}`;
  document.getElementById("forecastNote").textContent = data.note || "";

  const labels = data.rainfall_next_hours.map(x => x.time.slice(11, 16)); // HH:MM
  const rain = data.rainfall_next_hours.map(x => x.mm_per_hr);
  const wl = data.water_level_trend.map(x => x.water_level_m);

  destroyIfExists(rainChart);
  destroyIfExists(wlChart);

  rainChart = buildChart("rainChart", labels, rain, "Rainfall (mm/hr)");
  wlChart = buildChart("wlChart", labels, wl, "Water Level (m)");

  const list = document.getElementById("floodForecastList");
  list.innerHTML = "";
  for (const item of data.flood_prediction_next_hours) {
    const time = item.time.slice(11, 16);
    list.innerHTML += `
      <div class="rounded-xl border border-slate-800 bg-slate-950/40 p-3 flex items-center justify-between">
        <div class="text-sm text-slate-300">${time}</div>
        ${statusPill(item.status)}
      </div>
    `;
  }
}

document.getElementById("btnForecastRefresh")?.addEventListener("click", render);

render();

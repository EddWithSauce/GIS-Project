let histRainChart, histWlChart;
let currentRange = "24h";

async function loadHistory(range) {
  const res = await fetch(`/api/history?range=${encodeURIComponent(range)}`);
  return await res.json();
}

function destroyIfExists(chart) {
  if (chart) chart.destroy();
}

function buildLineChart(canvasId, labels, data, labelName) {
  const ctx = document.getElementById(canvasId);
  return new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: labelName,
        data,
        tension: 0.35,
        pointRadius: 0
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: "#e2e8f0" } } },
      scales: {
        x: { ticks: { color: "#94a3b8", maxTicksLimit: 10 }, grid: { color: "rgba(148,163,184,0.15)" } },
        y: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(148,163,184,0.15)" } }
      }
    }
  });
}

function renderTable(series) {
  const rows = series.slice(-24).map(s => {
    return `
      <tr class="border-b border-slate-800">
        <td class="py-2 pr-3 text-slate-300">${s.time.replace("T", " ")}</td>
        <td class="py-2 pr-3">${s.rain_class}</td>
        <td class="py-2 pr-3 text-right">${s.rain_mm_hr}</td>
        <td class="py-2 pr-3 text-right">${s.water_level_m}</td>
        <td class="py-2 pr-3">${s.flood_status}</td>
      </tr>
    `;
  }).join("");

  return `
    <table class="w-full text-sm">
      <thead class="text-xs text-slate-400">
        <tr class="border-b border-slate-800">
          <th class="py-2 text-left">Time</th>
          <th class="py-2 text-left">Rain Status</th>
          <th class="py-2 text-right">Rain (mm/hr)</th>
          <th class="py-2 text-right">Water (m)</th>
          <th class="py-2 text-left">Flood Status</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    <div class="text-xs text-slate-500 mt-2">Showing last 24 samples (for readability).</div>
  `;
}

async function render(range) {
  const data = await loadHistory(range);

  document.getElementById("historyUpdated").textContent = `Updated: ${data.last_updated}`;
  document.getElementById("historyNote").textContent = data.note || "";

  const labels = data.series.map(x => x.time.slice(11, 16)); // HH:MM (works fine for mock)
  const rain = data.series.map(x => x.rain_mm_hr);
  const wl = data.series.map(x => x.water_level_m);

  destroyIfExists(histRainChart);
  destroyIfExists(histWlChart);

  histRainChart = buildLineChart("histRainChart", labels, rain, "Rainfall (mm/hr)");
  histWlChart = buildLineChart("histWlChart", labels, wl, "Water Level (m)");

  document.getElementById("statusTable").innerHTML = renderTable(data.series);
}

document.querySelectorAll(".rangeBtn").forEach(btn => {
  btn.addEventListener("click", () => {
    currentRange = btn.dataset.range;
    render(currentRange);
  });
});

render(currentRange);

function pillClass(level) {
  if (level === "Critical") return "bg-rose-500/10 text-rose-200 border-rose-500/30";
  if (level === "Warning") return "bg-amber-500/10 text-amber-200 border-amber-500/30";
  return "bg-emerald-500/10 text-emerald-200 border-emerald-500/30";
}

function safe(v, fallback = "—") {
  return (v === null || v === undefined || v === "") ? fallback : v;
}

function hoursText(hours) {
  if (hours === null || hours === undefined) return "Unknown";
  return `~${hours} hour(s)`;
}

function fmtTime(ts) {
  if (!ts) return "—";
  // Supabase timestamptz looks like 2026-01-23T06:00:00+00:00
  return ts.replace("T", " ").slice(0, 19);
}

async function markRead(id) {
  await fetch("/api/notifications/mark-read", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id })
  });
}

function card(item) {
  const level = safe(item.alert_level, "Normal");
  const unread = !item.is_read;

  return `
    <div class="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="text-sm font-semibold">${safe(item.title)}</div>
          <div class="text-xs text-slate-400 mt-1">${fmtTime(item.created_at)}</div>
        </div>

        <div class="flex items-center gap-2">
          <span class="text-xs px-2 py-1 rounded-lg border ${pillClass(level)}">${level}</span>
          ${unread ? `<button data-id="${item.id}" class="markRead text-xs px-2 py-1 rounded-lg border border-slate-700 hover:bg-slate-800">Mark read</button>` : ""}
        </div>
      </div>

      <div class="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
        <div class="rounded-xl border border-slate-800 bg-slate-900/30 p-3">
          <div class="text-xs text-slate-400">Predicted Rainfall Intensity</div>
          <div class="mt-1 font-semibold">${safe(item.predicted_rainfall_intensity)}</div>
          <div class="text-xs text-slate-400 mt-1">Peak: ${safe(item.peak_rain_mm_hr)} mm/hr</div>
        </div>

        <div class="rounded-xl border border-slate-800 bg-slate-900/30 p-3">
          <div class="text-xs text-slate-400">Flood Prediction</div>
          <div class="mt-1 font-semibold">${safe(item.predicted_flood_risk)}</div>
          <div class="text-xs text-slate-400 mt-1">Hours before flood: ${hoursText(item.hours_before_flood)}</div>
        </div>

        <div class="rounded-xl border border-slate-800 bg-slate-900/30 p-3 md:col-span-2">
          <div class="text-xs text-slate-400">Current Water Level</div>
          <div class="mt-1 font-semibold">${safe(item.current_water_level_m)} m</div>
        </div>
      </div>

      <div class="mt-3 text-sm text-slate-200 whitespace-pre-line">
        ${safe(item.message, "No message")}
      </div>

      <div class="mt-3 text-xs text-slate-500">
        Read: ${item.is_read ? "Yes" : "No"} • Channel: ${safe(item.channel)}
      </div>
    </div>
  `;
}

async function loadNotifications() {
  const res = await fetch("/api/notifications");
  const data = await res.json();

  const list = document.getElementById("notifList");
  list.innerHTML = "";

  const items = data.items || [];
  if (items.length === 0) {
    list.innerHTML = `
      <div class="rounded-xl border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-400">
        No notifications yet.
      </div>
    `;
    return;
  }

  for (const item of items) {
    list.innerHTML += card(item);
  }

  document.querySelectorAll(".markRead").forEach(btn => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-id");
      await markRead(id);
      await loadNotifications();
    });
  });
}

document.getElementById("btnNotifRefresh")?.addEventListener("click", loadNotifications);
loadNotifications();

async function loadSystemBanner() {
  try {
    const res = await fetch("/api/system");
    const data = await res.json();

    const banner = document.getElementById("systemBanner");
    const text = document.getElementById("systemBannerText");
    const pill = document.getElementById("systemModePill");

    if (!banner || !text || !pill) return;

    banner.classList.remove("hidden");
    text.textContent = `${data.notes} | Last updated: ${data.last_updated}`;

    pill.textContent = data.mode;
    pill.className = "text-xs px-3 py-1 rounded-full border " +
      (data.mode === "LIVE"
        ? "border-emerald-600 text-emerald-300 bg-emerald-950/40"
        : "border-amber-600 text-amber-300 bg-amber-950/40"
      );
  } catch (e) {
    // silent fail
  }
}

document.addEventListener("DOMContentLoaded", loadSystemBanner);

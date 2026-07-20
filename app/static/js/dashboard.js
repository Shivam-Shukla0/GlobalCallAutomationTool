// Poll queue status every 5s and update the stat cards.
async function refresh() {
  try {
    const res = await fetch("/api/queue-status");
    if (!res.ok) return;
    const s = await res.json();
    for (const key of Object.keys(s)) {
      const el = document.getElementById("stat-" + key);
      if (el) el.textContent = s[key];
    }
  } catch (_) { /* ignore transient errors */ }
}
if (document.getElementById("stat-total")) setInterval(refresh, 5000);

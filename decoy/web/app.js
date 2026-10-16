// ----- welcome splash (runs first so the animation starts right away) -----
(function splash() {
  // apply the saved theme now so the splash isn't the wrong color for a moment
  try { document.documentElement.setAttribute("data-theme", localStorage.getItem("decoy-theme") || "signal"); } catch {}

  const sp = document.getElementById("splash");
  if (!sp) return;
  const title = document.getElementById("sp-title");
  const text = title.textContent;
  title.textContent = "";
  [...text].forEach((ch, i) => {
    const s = document.createElement("span");
    s.textContent = ch === " " ? "\u00a0" : ch;
    s.style.setProperty("--i", i);
    title.appendChild(s);
  });

  let done = false;
  const leave = () => {
    if (done) return;
    done = true;
    sp.classList.add("leaving");
    setTimeout(() => sp.classList.add("gone"), 800);
  };
  setTimeout(leave, 3100);                 // auto-dismiss
  sp.addEventListener("click", leave);     // click anywhere to skip
  document.addEventListener("keydown", leave, { once: true });
})();

// ----- in-app logging (so the Logs tab shows what's breaking) -----
const LOG = [];
function fmt(x) { if (typeof x === "string") return x; try { return JSON.stringify(x); } catch { return String(x); } }
function pushLog(src, level, msg) {
  const line = { t: new Date().toLocaleTimeString(), src, level, msg };
  LOG.push(line);
  if (LOG.length > 1000) LOG.shift();
  const body = document.getElementById("log-body");
  if (body) {
    const d = document.createElement("div");
    d.className = `log-line src-${src} log-${level}`;
    d.textContent = `${line.t}  ${src}  ${msg}`;
    body.appendChild(d);
    while (body.children.length > 1000) body.removeChild(body.firstChild);
    body.scrollTop = body.scrollHeight;
  }
}
["log", "info", "warn", "error"].forEach((k) => {
  const orig = console[k].bind(console);
  console[k] = (...a) => { orig(...a); pushLog("js", k === "info" ? "log" : k, a.map(fmt).join(" ")); };
});
window.addEventListener("error", (e) => pushLog("js", "error", `${e.message}${e.filename ? ` (${e.filename.split("/").pop()}:${e.lineno})` : ""}`));
window.addEventListener("unhandledrejection", (e) => pushLog("js", "error", "promise: " + fmt(e.reason && e.reason.message || e.reason)));

// ----- bridge to python (falls back to a mock so the ui also opens in a plain browser) -----
const hasNative = () => window.pywebview && window.pywebview.api;
const NOISY = new Set(["status", "logs", "jitter", "last_location"]);  // skip these in the log, too chatty
const bridge = new Proxy({}, {
  get(_t, name) {
    return (...args) => {
      let p;
      if (hasNative()) {
        p = window.pywebview.api[name](...args);
      } else {
        let r = { ok: true };
        if (name === "status") r = { state: "disconnected", info: {} };
        else if (name === "list_spots") r = [];
        else if (name === "last_location") r = lastFix;
        else if (name === "logs") r = [];
        p = Promise.resolve(r);
      }
      if (!NOISY.has(name)) {
        Promise.resolve(p)
          .then((r) => pushLog("call", "log", `${name}(${args.map(fmt).join(", ")}) -> ${fmt(r)}`))
          .catch((e) => pushLog("call", "error", `${name} failed: ${fmt(e)}`));
      }
      return p;
    };
  },
});

// ----- map (clamped so you can't scroll into a sea of repeated worlds) -----
const PORTLAND = [45.5152, -122.6784];
const WORLD = L.latLngBounds([-85, -180], [85, 180]);
const map = L.map("map", {
  zoomControl: true,
  attributionControl: true,
  minZoom: 3,
  maxBounds: WORLD,
  maxBoundsViscosity: 1.0,
  worldCopyJump: false,
}).setView(PORTLAND, 12);
map.zoomControl.setPosition("bottomright");

L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  noWrap: true,          // don't tile the world sideways forever
  bounds: WORLD,
  attribution: "© OpenStreetMap contributors",
}).addTo(map);

// ----- state -----
let tab = "position";
let beacon = null;
let speedMode = "walk";
let route = [];
let routeLine = null;
let travelling = false;
let lastFix = null;          // last coords we committed (for mock + jitter base)
let jitterTimer = null, jitterBase = null;

const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

// ----- markers -----
function beaconIcon(drop) {
  return L.divIcon({
    className: "",
    html: `<div class="beacon ${drop ? "drop" : ""}"><div class="ring"></div><div class="core"></div></div>`,
    iconSize: [20, 20], iconAnchor: [10, 10],
  });
}
function placeBeacon(lat, lon, drop = true) {
  if (beacon) map.removeLayer(beacon);
  beacon = L.marker([lat, lon], { icon: beaconIcon(drop), interactive: false }).addTo(map);
  setReadout(lat, lon);
}

// ----- the main move -----
async function setLocation(lat, lon, { pan = true } = {}) {
  stopTravelUi();
  placeBeacon(lat, lon, true);
  jitterBase = { lat, lon };
  lastFix = { lat, lon };
  if (pan) map.panTo([lat, lon], { animate: true });
  setTelemetry("Placing", false);

  const res = await bridge.set_location(lat, lon);
  if (res.ok) {
    setTelemetry("Spoofing", true);
    enable("save-cur"); enable("restore"); enable("copy-cur");
  } else {
    setTelemetry("Idle", false);
    toast(res.error || "couldn't reach the phone", true);
  }
}

async function restore() {
  const res = await bridge.clear_location();
  if (res.ok) {
    if (beacon) { map.removeLayer(beacon); beacon = null; }
    setReadout(null, null);
    setTelemetry("Idle", false);
    el("jitter").checked = false; stopJitter(); jitterBase = null; lastFix = null;
    disable("restore"); disable("save-cur"); disable("copy-cur");
    toast("back on real GPS");
  } else {
    toast(res.error || "couldn't restore", true);
  }
}

// ----- readouts -----
function setReadout(lat, lon) {
  el("cur-lat").textContent = lat == null ? "—" : lat.toFixed(6);
  el("cur-lon").textContent = lon == null ? "—" : lon.toFixed(6);
  el("tele-lat").textContent = lat == null ? "--.----" : lat.toFixed(5);
  el("tele-lon").textContent = lon == null ? "--.----" : lon.toFixed(5);
}
function setTelemetry(label, active) {
  el("tele-label").textContent = label;
  el("tele-dot").classList.toggle("active", !!active);
}

// ----- manual coordinate entry -----
function goCoords() {
  const la = parseFloat(el("in-lat").value), lo = parseFloat(el("in-lon").value);
  if (!isFinite(la) || !isFinite(lo) || la < -90 || la > 90 || lo < -180 || lo > 180) {
    return toast("enter a valid lat (-90 to 90) and lon (-180 to 180)", true);
  }
  map.setView([la, lo], 15, { animate: true });
  setLocation(la, lo, { pan: false });
}
el("go-coord").onclick = goCoords;
["in-lat", "in-lon"].forEach((id) => el(id).addEventListener("keydown", (e) => { if (e.key === "Enter") goCoords(); }));

// ----- copy -----
el("copy-cur").onclick = async () => {
  const last = await bridge.last_location();
  if (!last) return;
  const txt = `${last.lat.toFixed(6)}, ${last.lon.toFixed(6)}`;
  try { await navigator.clipboard.writeText(txt); toast("copied " + txt); }
  catch { toast(txt); }
};

// ----- gps drift (jitter) -----
el("jitter").onchange = (e) => {
  if (e.target.checked) startJitter(); else stopJitter();
};
function startJitter() {
  if (!jitterBase) { toast("set a position first"); el("jitter").checked = false; return; }
  stopJitter();
  jitterTimer = setInterval(() => {
    if (travelling || !jitterBase) return;
    const d = () => (Math.random() - 0.5) * 0.00009;  // ~ up to ~5m wobble
    const la = jitterBase.lat + d(), lo = jitterBase.lon + d();
    placeBeacon(la, lo, false);
    lastFix = { lat: la, lon: lo };
    bridge.jitter(la, lo);
  }, 2500);
}
function stopJitter() { if (jitterTimer) { clearInterval(jitterTimer); jitterTimer = null; } }

// ----- search (nominatim) -----
let searchTimer = null;
el("search").addEventListener("input", (e) => {
  const q = e.target.value.trim();
  clearTimeout(searchTimer);
  if (q.length < 3) return closeResults();
  searchTimer = setTimeout(() => runSearch(q), 350);
});
async function runSearch(q) {
  try {
    const url = `https://nominatim.openstreetmap.org/search?format=json&limit=5&q=${encodeURIComponent(q)}`;
    const r = await fetch(url, { headers: { "Accept-Language": "en" } });
    renderResults(await r.json());
  } catch { closeResults(); }
}
function renderResults(items) {
  const box = el("results");
  if (!items.length) return closeResults();
  box.innerHTML = items.map((it) => {
    const parts = it.display_name.split(",");
    const title = parts.shift();
    return `<div class="result" data-lat="${it.lat}" data-lon="${it.lon}">
      <div>${esc(title)}</div><div class="sub">${esc(parts.join(",").trim())}</div></div>`;
  }).join("");
  box.classList.add("open");
  box.querySelectorAll(".result").forEach((r) => {
    r.onclick = () => {
      const lat = parseFloat(r.dataset.lat), lon = parseFloat(r.dataset.lon);
      el("search").value = ""; closeResults();
      map.setView([lat, lon], 15, { animate: true });
      setLocation(lat, lon, { pan: false });
    };
  });
}
function closeResults() { el("results").classList.remove("open"); el("results").innerHTML = ""; }
document.addEventListener("click", (e) => { if (!e.target.closest(".search")) closeResults(); });

// ----- map clicks -----
map.on("click", (e) => {
  const { lat, lng } = e.latlng;
  if (tab === "travel") addWaypoint(lat, lng);
  else setLocation(lat, lng, { pan: false });
});

// ----- tabs -----
document.querySelectorAll(".tab").forEach((t) => {
  t.onclick = () => {
    tab = t.dataset.tab;
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("is-active", x === t));
    document.querySelectorAll(".pane").forEach((p) => p.classList.toggle("is-active", p.dataset.pane === tab));
  };
});

// ----- collapse / reveal / recenter -----
el("collapse").onclick = () => { el("console").classList.add("hidden"); el("reveal").classList.add("show"); };
el("reveal").onclick = () => { el("console").classList.remove("hidden"); el("reveal").classList.remove("show"); };
el("recenter").onclick = () => {
  if (beacon) map.setView(beacon.getLatLng(), Math.max(map.getZoom(), 13), { animate: true });
  else toast("no decoy placed yet");
};

// ----- themes -----
function applyTheme(name) {
  document.documentElement.setAttribute("data-theme", name);
  try { localStorage.setItem("decoy-theme", name); } catch {}
  document.querySelectorAll(".swatch").forEach((s) => s.classList.toggle("on", s.dataset.theme === name));
  if (routeLine) routeLine.setStyle({ color: cssVar("--signal") || "#ff5c4d" });
}
document.querySelectorAll(".swatch").forEach((s) => { s.onclick = () => applyTheme(s.dataset.theme); });

// ----- position actions -----
el("restore").onclick = restore;
el("save-cur").onclick = async () => {
  const last = await bridge.last_location();
  if (!last) return toast("set a position first", true);
  const name = prompt("Name this spot", "My spot");
  if (name === null) return;
  await bridge.add_spot(name, last.lat, last.lon);
  loadSpots();
  toast("spot saved");
};

// ----- spots -----
async function loadSpots() {
  const spots = await bridge.list_spots();
  const box = el("spot-list");
  if (!spots.length) {
    box.innerHTML = `<div class="spot-empty">No saved spots yet.<br>Drop a decoy, then hit "Save this spot".</div>`;
    return;
  }
  box.innerHTML = spots.map((s) => `
    <div class="spot" data-id="${s.id}" data-lat="${s.lat}" data-lon="${s.lon}">
      <span class="pin"></span>
      <span class="label"><span class="t">${esc(s.name)}</span>
        <span class="c">${s.lat.toFixed(4)}, ${s.lon.toFixed(4)}</span></span>
      <button class="del" title="Delete">×</button>
    </div>`).join("");
  box.querySelectorAll(".spot").forEach((row) => {
    const lat = parseFloat(row.dataset.lat), lon = parseFloat(row.dataset.lon);
    row.onclick = (e) => {
      if (e.target.classList.contains("del")) return;
      map.setView([lat, lon], 15, { animate: true });
      setLocation(lat, lon, { pan: false });
    };
    row.querySelector(".del").onclick = async () => { await bridge.remove_spot(row.dataset.id); loadSpots(); };
  });
}

// ----- travel -----
document.querySelectorAll("#speed button").forEach((b) => {
  b.onclick = () => {
    speedMode = b.dataset.mode;
    document.querySelectorAll("#speed button").forEach((x) => x.classList.toggle("is-active", x === b));
  };
});
function addWaypoint(lat, lon) {
  const m = L.marker([lat, lon], {
    icon: L.divIcon({ className: "", html: `<div class="waypoint"></div>`, iconSize: [10, 10], iconAnchor: [5, 5] }),
  }).addTo(map);
  route.push({ lat, lon, marker: m });
  drawRoute();
  el("route-pts").textContent = `${route.length} point${route.length === 1 ? "" : "s"}`;
  el("travel-go").disabled = route.length < 2 || travelling;
}
function drawRoute() {
  if (routeLine) map.removeLayer(routeLine);
  if (route.length < 2) return;
  routeLine = L.polyline(route.map((p) => [p.lat, p.lon]), {
    color: cssVar("--signal") || "#ff5c4d", weight: 2.5, opacity: .85, dashArray: "1 8", lineCap: "round",
  }).addTo(map);
}
el("route-clear").onclick = clearRoute;
function clearRoute() {
  route.forEach((p) => map.removeLayer(p.marker));
  route = [];
  if (routeLine) { map.removeLayer(routeLine); routeLine = null; }
  el("route-pts").textContent = "0 points";
  el("travel-go").disabled = true;
  el("progress-fill").style.width = "0%";
}
el("travel-go").onclick = async () => {
  if (route.length < 2) return;
  travelling = true;
  el("travel-go").disabled = true; el("travel-stop").disabled = false;
  setTelemetry("Travelling", true);
  const res = await bridge.start_travel(route.map((p) => [p.lat, p.lon]), speedMode);
  if (!res.ok) { toast(res.error, true); stopTravelUi(); }
};
el("travel-stop").onclick = async () => { await bridge.stop_travel(); stopTravelUi(); };
function stopTravelUi() {
  travelling = false;
  el("travel-stop").disabled = true;
  el("travel-go").disabled = route.length < 2;
}

// pushed from python every tick while moving
window.decoy = {
  onTravel(d) {
    if (d.lat != null) { placeBeacon(d.lat, d.lon, false); lastFix = { lat: d.lat, lon: d.lon }; }
    el("progress-fill").style.width = `${Math.round((d.done || 0) * 100)}%`;
    if (d.finished || d.stopped) {
      stopTravelUi();
      setTelemetry(d.finished ? "Spoofing" : "Idle", d.finished);
      if (d.finished) {
        enable("restore"); enable("copy-cur");
        if (route.length) jitterBase = { lat: route[route.length - 1].lat, lon: route[route.length - 1].lon };
        toast("arrived");
      }
    }
  },
  onToast(d) { toast(d.msg, d.kind === "error"); },
};

// ----- connection status -----
let lastState = null;
async function refreshStatus() {
  const s = await bridge.status();
  if (s.state !== lastState) {
    lastState = s.state;
    pushLog("sys", s.state === "connected" ? "log" : "warn", `device: ${s.state}${s.detail ? " — " + s.detail : ""}`);
  }
  const chip = el("conn"), txt = el("conn-text");
  chip.classList.remove("live", "busy");
  if (s.state === "connected") {
    chip.classList.add("live");
    const info = s.info || {};
    txt.textContent = info.ios ? `${info.name || "iPhone"} · iOS ${info.ios}` : (info.name || "Connected");
  } else if (s.state === "no_lib") {
    txt.textContent = "Device library error (click)";
  } else {
    txt.textContent = "Tap to connect";
  }
}
el("conn").onclick = async () => {
  if (el("conn").classList.contains("live")) return;
  el("conn").classList.add("busy");
  el("conn-text").textContent = "Connecting…";
  const res = await bridge.connect();
  if (!res.ok) toast(res.error || "couldn't connect", true);
  refreshStatus();
};

// ----- toast -----
let toastTimer = null;
function toast(msg, isError = false) {
  const t = el("toast");
  t.textContent = msg;
  t.classList.toggle("error", isError);
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 3200);
}

// ----- keyboard -----
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (el("results").classList.contains("open")) closeResults();
    else if (travelling) el("travel-stop").click();
  }
});

// ----- helpers -----
function el(id) { return document.getElementById(id); }
function enable(id) { el(id).disabled = false; }
function disable(id) { el(id).disabled = true; }
function esc(s) { return (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

// ----- background tunnel service toggle -----
async function loadTunnelSvc() {
  try { const r = await bridge.tunnel_service_status(); el("tunnel-svc").checked = !!(r && r.installed); } catch {}
}
el("tunnel-svc").onchange = async (e) => {
  const box = e.target, want = box.checked;
  box.disabled = true;
  toast(want ? "approve the password prompt..." : "removing background tunnel...");
  const res = await (want ? bridge.install_tunnel_service() : bridge.remove_tunnel_service());
  box.disabled = false;
  if (!res || !res.ok) {
    box.checked = !want;               // flip back, it didn't take
    toast((res && res.error) || "that didn't work", true);
  } else {
    toast(want ? (res.up ? "tunnel will now start at boot" : "installed, but the tunnel isn't answering yet") : "background tunnel removed");
    refreshStatus();
  }
};

// ----- logs tab controls + python log polling -----
el("log-copy").onclick = async () => {
  const txt = LOG.map((l) => `${l.t} ${l.src} ${l.msg}`).join("\n");
  try { await navigator.clipboard.writeText(txt); toast("logs copied"); }
  catch { toast("couldn't copy — select and copy manually"); }
};
el("log-clear").onclick = () => { LOG.length = 0; el("log-body").innerHTML = ""; };

let pyCursor = 0;
async function pollPy() {
  try {
    const rows = await bridge.logs(pyCursor);
    if (Array.isArray(rows)) rows.forEach((r) => { pyCursor = Math.max(pyCursor, r.id); pushLog("py", /error|fail|traceback/i.test(r.text) ? "error" : "log", r.text); });
  } catch {}
}

// ----- boot -----
function boot() {
  let saved = "signal";
  try { saved = localStorage.getItem("decoy-theme") || "signal"; } catch {}
  applyTheme(saved);
  pushLog("sys", "log", "Decoy ready");
  loadSpots();
  loadTunnelSvc();
  refreshStatus();
  pollPy();
  setInterval(refreshStatus, 6000);
  setInterval(pollPy, 1500);
}
let booted = false;
function bootOnce() { if (booted) return; booted = true; boot(); }
window.addEventListener("pywebviewready", bootOnce);
if (hasNative()) bootOnce();
else setTimeout(bootOnce, 1500);   // plain-browser preview: no python side, boot anyway

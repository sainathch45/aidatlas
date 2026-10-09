/* AidAtlas frontend — vanilla JS, no build step, so Firebase Hosting can
 * serve it as-is. Talks to the Cloud Run backend over the URL in config.js.
 */

const API = AIDATLAS_CONFIG.API_BASE_URL;

let map;
let markers = {};       // admin2_code -> google.maps.Marker
let districtData = {};  // admin2_code -> latest known record (district or allocation row)
let infoWindow;
let currentResourceType = "shelter";
let allocationRun = false;

const DARK_MAP_STYLE = [
  { elementType: "geometry", stylers: [{ color: "#0d1420" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#0d1420" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#7d8ca3" }] },
  { featureType: "administrative.country", elementType: "geometry.stroke", stylers: [{ color: "#213048" }] },
  { featureType: "administrative.province", elementType: "geometry.stroke", stylers: [{ color: "#1a2638" }] },
  { featureType: "landscape", elementType: "geometry", stylers: [{ color: "#0a0f18" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#071018" }] },
  { featureType: "road", elementType: "geometry", stylers: [{ color: "#16202f" }] },
  { featureType: "poi", stylers: [{ visibility: "off" }] },
  { featureType: "transit", stylers: [{ visibility: "off" }] },
];

/* ---------- boot sequence ---------- */
function boot() {
  const lines = ["INITIALIZING AIDATLAS", "LOADING REAL HDX DATA — SYRIA 2026", "SYSTEM READY"];
  const el = document.getElementById("boot-text");
  let i = 0;
  function next() {
    if (i >= lines.length) {
      document.getElementById("boot").style.display = "none";
      document.getElementById("app").hidden = false;
      return;
    }
    el.textContent = lines[i];
    i++;
    setTimeout(next, 950);
  }
  next();
}

/* ---------- map ---------- */
function severityBucket(needScore, maxNeed) {
  const ratio = maxNeed ? needScore / maxNeed : 0;
  if (ratio > 0.5) return 3;
  if (ratio > 0.2) return 2;
  if (ratio > 0.05) return 1;
  return 0;
}
const SEV_COLOR = ["#3ad6ff", "#ffd23a", "#ff9a3a", "#ff5d5d"];

function markerIcon(sev, highlighted) {
  const r = highlighted ? 11 : 7 + sev * 1.5;
  return {
    path: google.maps.SymbolPath.CIRCLE,
    scale: r,
    fillColor: SEV_COLOR[sev],
    fillOpacity: 0.9,
    strokeColor: "#061018",
    strokeWeight: 2,
  };
}

window.initMap = function initMap() {
  map = new google.maps.Map(document.getElementById("map"), {
    center: { lat: 35.0, lng: 38.0 },
    zoom: 7,
    styles: DARK_MAP_STYLE,
    disableDefaultUI: true,
    zoomControl: true,
  });
  infoWindow = new google.maps.InfoWindow();
  boot();
  loadDistricts();
};

async function apiFetch(path, options) {
  const res = await fetch(API + path, options);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

async function loadDistricts() {
  try {
    const data = await apiFetch("/districts");
    document.getElementById("stat-districts").textContent =
      `${data.district_count} (${data.with_coordinates} mapped)`;
    const maxNeed = Math.max(...data.districts.map((d) => d.need_score));
    data.districts.forEach((d) => {
      districtData[d.admin2_code] = d;
      if (d.lat == null || d.lon == null) return;
      const sev = severityBucket(d.need_score, maxNeed);
      const marker = new google.maps.Marker({
        position: { lat: d.lat, lng: d.lon },
        map,
        icon: markerIcon(sev, false),
        title: `${d.admin2_name} (${d.admin1_name})`,
      });
      marker.addListener("click", () => showDistrict(d.admin2_code));
      markers[d.admin2_code] = marker;
    });
  } catch (err) {
    setRunStatus("Could not load district data: " + err.message, true);
  }
}

function showDistrict(code) {
  const d = districtData[code];
  if (!d) return;
  document.getElementById("detail-empty").hidden = true;
  const content = document.getElementById("detail-content");
  content.hidden = false;
  document.getElementById("detail-name").textContent = `${d.admin2_name} — ${d.admin1_name}`;
  document.getElementById("detail-pop").textContent = (d.idp_population ?? 0).toLocaleString();
  document.getElementById("detail-orgs").textContent = d.active_org_count ?? "—";
  document.getElementById("detail-need").textContent = d.need_score ? d.need_score.toFixed(1) : "—";
  document.getElementById("detail-amount").textContent =
    d.quantity_allocated != null ? "$" + d.quantity_allocated.toLocaleString() : "not yet allocated";
  let rationaleMessage;
  if (d.rationale_text) {
    rationaleMessage = d.rationale_text;
  } else if (!allocationRun) {
    rationaleMessage = "Run an allocation to generate Gemini's rationale for this district.";
  } else if (d.rationale_generated === false) {
    rationaleMessage = "Gemini was unavailable for this entire run (free-tier daily quota reached, or a temporary outage) — no district got AI commentary this run, not just this one. The allocation amount above is still real, computed from BigQuery.";
  } else {
    rationaleMessage = "This district wasn't in the top-N narrated this run (Gemini only writes rationale for the largest allocations, to stay within rate limits) — its allocation amount above is still real.";
  }
  document.getElementById("detail-rationale").textContent = rationaleMessage;

  const marker = markers[code];
  if (marker && map) {
    infoWindow.setContent(`<strong>${d.admin2_name}</strong><br>${d.idp_population?.toLocaleString() ?? "—"} IDPs`);
    infoWindow.open(map, marker);
  }
}

function repaintMarkers(maxAmount) {
  Object.entries(districtData).forEach(([code, d]) => {
    const marker = markers[code];
    if (!marker) return;
    const sev = severityBucket(d.quantity_allocated ?? 0, maxAmount);
    marker.setIcon(markerIcon(sev, false));
  });
}

/* ---------- controls ---------- */
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".resource-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".resource-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentResourceType = btn.dataset.type;
    });
  });

  document.getElementById("run-btn").addEventListener("click", runAllocation);
  document.getElementById("ask-form").addEventListener("submit", submitAsk);
});

function setRunStatus(text, isError) {
  const el = document.getElementById("run-status");
  el.textContent = text;
  el.classList.toggle("err", !!isError);
}

async function runAllocation() {
  const btn = document.getElementById("run-btn");
  btn.disabled = true;
  setRunStatus("Querying BigQuery, computing allocation, asking Gemini for rationale…");
  document.getElementById("stat-status").textContent = "ALLOCATING…";

  try {
    const data = await apiFetch("/allocate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resource_type: currentResourceType, top_n_rationale: 10 }),
    });

    data.allocations.forEach((d) => {
      districtData[d.admin2_code] = { ...districtData[d.admin2_code], ...d };
    });
    const maxAmount = Math.max(...data.allocations.map((d) => d.quantity_allocated));
    repaintMarkers(maxAmount);

    document.getElementById("stat-pool").textContent = "$" + data.supply_pool_usd.toLocaleString();
    const statusEl = document.getElementById("stat-status");
    statusEl.textContent = `ALLOCATED — ${currentResourceType.toUpperCase()}`;
    statusEl.classList.add("allocated");
    allocationRun = true;

    const top = [...data.allocations].sort((a, b) => b.quantity_allocated - a.quantity_allocated)[0];
    showDistrict(top.admin2_code);

    setRunStatus(`Done — ${data.district_count} districts allocated, top 10 narrated by Gemini.`);
  } catch (err) {
    setRunStatus("Allocation failed: " + err.message, true);
    document.getElementById("stat-status").textContent = "ERROR";
  } finally {
    btn.disabled = false;
  }
}

/* ---------- ask ---------- */
async function submitAsk(e) {
  e.preventDefault();
  const input = document.getElementById("ask-input");
  const question = input.value.trim();
  if (!question) return;
  input.value = "";

  const log = document.getElementById("ask-log");
  const qEl = document.createElement("div");
  qEl.className = "ask-q";
  qEl.textContent = question;
  const aEl = document.createElement("div");
  aEl.className = "ask-a loading";
  aEl.textContent = "Thinking…";
  log.appendChild(qEl);
  log.appendChild(aEl);
  log.scrollTop = log.scrollHeight;

  try {
    const data = await apiFetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, resource_type: currentResourceType }),
    });
    aEl.classList.remove("loading");
    aEl.textContent = data.answer;
  } catch (err) {
    aEl.classList.remove("loading");
    aEl.textContent = "Could not get an answer: " + err.message;
  }
  log.scrollTop = log.scrollHeight;
}

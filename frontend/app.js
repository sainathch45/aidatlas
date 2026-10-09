/* AidAtlas frontend — vanilla JS, no build step, so Firebase Hosting can
 * serve it as-is. Talks to the Cloud Run backend over the URL in config.js.
 * Supports more than one crisis region (fetched from /crises) to match
 * the backend's generalized architecture -- switching regions clears
 * and re-renders the map rather than assuming a fixed district set.
 */

const API = AIDATLAS_CONFIG.API_BASE_URL;

let map;
let markers = {};       // admin_code -> google.maps.Marker
let districtData = {};  // admin_code -> latest known record (district or allocation row)
let selectedCode = null; // the marker currently shown in the sidebar, highlighted on the map
let currentCrisisRegion = "SYR";
let currentResourceType = "shelter";
let crisisMeta = {};    // code -> {name, map_center, map_zoom, ...} from /crises
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
  const lines = ["INITIALIZING AIDATLAS", "LOADING REAL HDX HUMANITARIAN DATA", "SYSTEM READY"];
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

function markerIcon(sev, selected) {
  return {
    path: google.maps.SymbolPath.CIRCLE,
    scale: selected ? 12 : 7 + sev * 1.5,
    fillColor: SEV_COLOR[sev],
    fillOpacity: selected ? 1 : 0.9,
    // Selected marker gets a bright accent ring instead of the usual dark
    // outline -- the map's own selection indicator, now that detail lives
    // only in the sidebar panel (removed the native InfoWindow popup: it
    // couldn't be fully restyled to match the dark theme and duplicated
    // the sidebar anyway).
    strokeColor: selected ? "#3ad6ff" : "#061018",
    strokeWeight: selected ? 3 : 2,
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
  boot();
  loadCrises();
};

async function apiFetch(path, options) {
  const res = await fetch(API + path, options);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

async function loadCrises() {
  try {
    const data = await apiFetch("/crises");
    const select = document.getElementById("crisis-select");
    select.innerHTML = "";
    data.crises.forEach((c) => {
      crisisMeta[c.code] = c;
      const opt = document.createElement("option");
      opt.value = c.code;
      opt.textContent = c.name;
      select.appendChild(opt);
    });
    select.value = currentCrisisRegion;
    select.addEventListener("change", () => switchCrisis(select.value));
    await switchCrisis(currentCrisisRegion);
  } catch (err) {
    setRunStatus("Could not load crisis list: " + err.message, true);
  }
}

function clearMarkers() {
  Object.values(markers).forEach((m) => m.setMap(null));
  markers = {};
  districtData = {};
  selectedCode = null;
}

async function switchCrisis(code) {
  currentCrisisRegion = code;
  const meta = crisisMeta[code];
  clearMarkers();
  allocationRun = false;
  document.getElementById("detail-empty").hidden = false;
  document.getElementById("detail-content").hidden = true;
  document.getElementById("ask-log").innerHTML = "";

  if (meta) {
    const isDrafted = meta.mode === "ai_drafted";
    map.setCenter(meta.map_center);
    map.setZoom(meta.map_zoom);
    document.getElementById("stat-appeal").textContent = isDrafted
      ? `${meta.name} (no official plan)`
      : `${meta.appeal_code} (${meta.name})`;
    document.getElementById("stat-status").textContent = "LIVE DATA — UNALLOCATED";
    document.getElementById("stat-status").classList.remove("allocated", "drafted");
    document.getElementById("stat-pool").textContent = isDrafted ? "N/A" : "—";
    document.getElementById("stat-funded").textContent = isDrafted ? "No formal appeal" : `${meta.funding_pct}% funded`;
    document.getElementById("run-btn").textContent = isDrafted ? "DRAFT PRIORITY PLAN" : "RUN ALLOCATION";
    document.getElementById("detail-sources").hidden = true;
  }
  await loadDistricts();
}

async function loadDistricts() {
  try {
    const data = await apiFetch(`/districts?crisis_region=${currentCrisisRegion}&resource_type=${currentResourceType}`);
    document.getElementById("stat-districts").textContent =
      `${data.district_count} (${data.with_coordinates} mapped)`;
    const maxNeed = Math.max(...data.districts.map((d) => d.need_score));
    data.districts.forEach((d) => {
      districtData[d.admin_code] = d;
      if (d.lat == null || d.lon == null) return;
      const sev = severityBucket(d.need_score, maxNeed);
      const marker = new google.maps.Marker({
        position: { lat: d.lat, lng: d.lon },
        map,
        icon: markerIcon(sev, false),
        title: `${d.admin_name} (${d.admin_parent_name})`,
      });
      marker.addListener("click", () => showDistrict(d.admin_code));
      markers[d.admin_code] = marker;
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
  document.getElementById("detail-name").textContent = `${d.admin_name} — ${d.admin_parent_name}`;

  // Context shape varies by crisis: Syria gives IDP population + org
  // count; Myanmar gives a sector-specific "people in need" figure;
  // the AI-drafted India crises give a cited real-world metric (rainfall
  // deficit %, villages affected) with no official funding/sector data.
  // Render whichever this crisis actually has, don't force one shape.
  const ctx = d.context || {};
  const sourcesEl = document.getElementById("detail-sources");
  if ("idp_population" in ctx) {
    document.getElementById("detail-pop-label").textContent = "IDP population";
    document.getElementById("detail-pop").textContent = (ctx.idp_population ?? 0).toLocaleString();
    document.getElementById("detail-orgs-label").textContent = "Orgs active";
    document.getElementById("detail-orgs").textContent = ctx.active_org_count ?? "—";
    sourcesEl.hidden = true;
  } else if ("people_in_need" in ctx) {
    document.getElementById("detail-pop-label").textContent = "People in need";
    document.getElementById("detail-pop").textContent = (ctx.people_in_need ?? d.need_score ?? 0).toLocaleString();
    document.getElementById("detail-orgs-label").textContent = "Sector";
    document.getElementById("detail-orgs").textContent = ctx.sector ?? "—";
    sourcesEl.hidden = true;
  } else {
    document.getElementById("detail-pop-label").textContent = ctx.metric_label || "Metric";
    document.getElementById("detail-pop").textContent = (ctx.metric_value ?? d.need_score ?? 0).toLocaleString();
    document.getElementById("detail-orgs-label").textContent = "Status";
    document.getElementById("detail-orgs").textContent = "Draft, not official";
    if (ctx.sources?.length) {
      sourcesEl.innerHTML = "Sources: " + ctx.sources.map((u, i) => `<a href="${u}" target="_blank" rel="noopener">[${i + 1}]</a>`).join(" ");
      sourcesEl.hidden = false;
    } else {
      sourcesEl.hidden = true;
    }
  }
  document.getElementById("detail-need").textContent = d.need_score ? d.need_score.toFixed(1) : "—";

  if (d.priority_rank != null) {
    document.getElementById("detail-amount-label").textContent = "Priority";
    document.getElementById("detail-amount").textContent = `#${d.priority_rank}`;
  } else {
    document.getElementById("detail-amount-label").textContent = "Allocated";
    document.getElementById("detail-amount").textContent =
      d.quantity_allocated != null ? "$" + d.quantity_allocated.toLocaleString() : "not yet allocated";
  }

  const figureNoun = d.priority_rank != null ? "ranking" : "allocation amount";
  const figureSource = d.priority_rank != null ? "the real cited figures above" : "BigQuery";
  let rationaleMessage;
  if (d.rationale_text) {
    rationaleMessage = d.rationale_text;
  } else if (!allocationRun) {
    rationaleMessage = d.priority_rank != null
      ? "Run the draft to generate Gemini's rationale for this location."
      : "Run an allocation to generate Gemini's rationale for this location.";
  } else if (d.rationale_generated === false) {
    rationaleMessage = `Gemini was unavailable for this entire run (free-tier daily quota reached, or a temporary outage) — no location got AI commentary this run, not just this one. The ${figureNoun} above is still real, computed from ${figureSource}.`;
  } else {
    rationaleMessage = `This location wasn't in the top-N narrated this run (Gemini only writes rationale for the largest allocations, to stay within rate limits) — its ${figureNoun} above is still real.`;
  }
  document.getElementById("detail-rationale").textContent = rationaleMessage;

  highlightSelected(code);
}

function highlightSelected(code) {
  // Repaints just the old and new selected markers rather than the
  // whole set -- cheap, and keeps everyone else's severity color intact.
  if (selectedCode && markers[selectedCode]) {
    const prev = districtData[selectedCode];
    const prevSev = severityBucket(prev.quantity_allocated ?? prev.need_score, currentMaxValue());
    markers[selectedCode].setIcon(markerIcon(prevSev, false));
  }
  selectedCode = code;
  const marker = markers[code];
  if (marker) {
    const d = districtData[code];
    const sev = severityBucket(d.quantity_allocated ?? d.need_score, currentMaxValue());
    marker.setIcon(markerIcon(sev, true));
    marker.setZIndex(999);
  }
}

function currentMaxValue() {
  const values = Object.values(districtData).map((d) => d.quantity_allocated ?? d.need_score ?? 0);
  return values.length ? Math.max(...values) : 0;
}

function repaintMarkers(maxAmount) {
  Object.entries(districtData).forEach(([code, d]) => {
    const marker = markers[code];
    if (!marker) return;
    const sev = severityBucket(d.quantity_allocated ?? 0, maxAmount);
    marker.setIcon(markerIcon(sev, code === selectedCode));
    if (code === selectedCode) marker.setZIndex(999);
  });
}

/* ---------- controls ---------- */
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".resource-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".resource-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentResourceType = btn.dataset.type;
      // Myanmar's need-score is sector-specific, so switching resource
      // type genuinely changes which locations rank highest -- reload
      // rather than just relabeling.
      clearMarkers();
      allocationRun = false;
      document.getElementById("detail-empty").hidden = false;
      document.getElementById("detail-content").hidden = true;
      loadDistricts();
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
  // Vertex AI's response latency is genuinely variable -- observed
  // 3-80+ seconds live for the same batched rationale call -- so this
  // sets an honest expectation instead of looking stuck with no context.
  setRunStatus("Querying BigQuery, computing allocation, asking Gemini for rationale… this can take up to a minute.");
  document.getElementById("stat-status").textContent = "ALLOCATING…";

  try {
    const data = await apiFetch("/allocate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        crisis_region: currentCrisisRegion,
        resource_type: currentResourceType,
        top_n_rationale: 10,
      }),
    });

    data.allocations.forEach((d) => {
      districtData[d.admin_code] = { ...districtData[d.admin_code], ...d };
    });

    const isDrafted = data.mode === "ai_drafted";
    const maxValue = isDrafted
      ? Math.max(...data.allocations.map((d) => d.need_score))
      : Math.max(...data.allocations.map((d) => d.quantity_allocated));
    repaintMarkers(maxValue);

    document.getElementById("stat-pool").textContent = isDrafted
      ? "N/A — no official appeal"
      : "$" + data.supply_pool_usd.toLocaleString();

    const statusEl = document.getElementById("stat-status");
    statusEl.textContent = isDrafted
      ? `AI-DRAFTED (NOT OFFICIAL) — ${currentResourceType.toUpperCase()}`
      : `ALLOCATED — ${currentResourceType.toUpperCase()}`;
    statusEl.classList.toggle("allocated", !isDrafted);
    statusEl.classList.toggle("drafted", isDrafted);
    allocationRun = true;

    const top = isDrafted
      ? [...data.allocations].sort((a, b) => a.priority_rank - b.priority_rank)[0]
      : [...data.allocations].sort((a, b) => b.quantity_allocated - a.quantity_allocated)[0];
    showDistrict(top.admin_code);

    const verb = isDrafted ? "ranked (draft, not official)" : "allocated";
    setRunStatus(`Done — ${data.district_count} locations ${verb}, top ${Math.min(10, data.district_count)} narrated by Gemini.`);
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
      body: JSON.stringify({
        question,
        crisis_region: currentCrisisRegion,
        resource_type: currentResourceType,
      }),
    });
    aEl.classList.remove("loading");
    aEl.textContent = data.answer;
  } catch (err) {
    aEl.classList.remove("loading");
    aEl.textContent = "Could not get an answer: " + err.message;
  }
  log.scrollTop = log.scrollHeight;
}

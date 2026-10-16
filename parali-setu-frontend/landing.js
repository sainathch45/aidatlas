// Parali Setu -- landing page logic. Same discipline as app.js/company.js:
// only ever displays what the API returns, never computes anything itself.

const DISTRICT_CENTERS = {
  Sangrur: [30.2458, 75.8421], Patiala: [30.3398, 76.3869], Bathinda: [30.2110, 74.9455],
  Ludhiana: [30.9010, 75.8573], Moga: [30.8230, 75.1710], Karnal: [29.6857, 76.9905],
  Kaithal: [29.8014, 76.3996], Kurukshetra: [29.9695, 76.8783],
};

// Called by the Maps JS API's callback -- may fire before or after the
// fire-detections fetch resolves, so both paths independently check
// whether the other is ready before trying to render.
let fireMap = null;
let pendingDetections = null;

window.initFireMap = function initFireMap() {
  fireMap = new google.maps.Map(document.getElementById("fire-map"), {
    center: { lat: 30.4, lng: 75.6 },
    zoom: 8,
    disableDefaultUI: true,
    zoomControl: true,
    styles: [
      { featureType: "poi", stylers: [{ visibility: "off" }] },
      { featureType: "transit", stylers: [{ visibility: "off" }] },
    ],
  });

  for (const [name, [lat, lng]] of Object.entries(DISTRICT_CENTERS)) {
    new google.maps.Marker({
      position: { lat, lng },
      map: fireMap,
      title: name,
      icon: {
        path: google.maps.SymbolPath.CIRCLE,
        scale: 4,
        fillColor: "#5c5648",
        fillOpacity: 0.6,
        strokeWeight: 0,
      },
    });
  }

  if (pendingDetections) renderDetections(pendingDetections);
};

function renderDetections(detections) {
  if (!fireMap) {
    pendingDetections = detections;
    return;
  }
  for (const d of detections) {
    new google.maps.Marker({
      position: { lat: d.lat, lng: d.lon },
      map: fireMap,
      title: `${d.district_guess || "unknown district"} — ${d.detected_at}`,
      icon: {
        path: google.maps.SymbolPath.CIRCLE,
        scale: 6,
        fillColor: "#a3372f",
        fillOpacity: 0.8,
        strokeColor: "#5c3410",
        strokeWeight: 1,
      },
    });
  }
}

async function loadFireDetections() {
  const statusEl = document.getElementById("map-status");
  try {
    const resp = await fetch(`${API_BASE}/fire-detections`);
    const body = await resp.json();
    const detections = body.detections || [];
    if (detections.length === 0) {
      statusEl.textContent = "No fire detections in the current refresh window.";
      return;
    }
    renderDetections(detections);
    const coverage = body.coverage;
    statusEl.textContent = coverage
      ? `${detections.length} real detections, ${coverage.start_date} to ${coverage.end_date}.`
      : `${detections.length} real detections.`;
  } catch {
    statusEl.textContent = "Could not load fire activity data right now.";
  }
}

loadFireDetections();

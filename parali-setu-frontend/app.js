// Parali Setu -- farmer page logic. Talks only to the deployed backend
// (config.js) -- no business logic here, same discipline as the backend:
// this file never computes a price or decides a match, it only
// displays whatever the API returns.

function getFarmerId() {
  try {
    let id = localStorage.getItem("parali_farmer_id");
    if (!id) {
      id = "farmer_" + Math.random().toString(36).slice(2, 10);
      localStorage.setItem("parali_farmer_id", id);
    }
    return id;
  } catch {
    return "farmer_anon";
  }
}

let currentLanguage = "Hindi";
let mediaRecorder = null;
let recordedChunks = [];
let recording = false;
let lastMatchId = null;

const el = (id) => document.getElementById(id);

el("lang-hi").addEventListener("click", () => setLanguage("Hindi"));
el("lang-pa").addEventListener("click", () => setLanguage("Punjabi"));

function setLanguage(lang) {
  currentLanguage = lang;
  el("lang-hi").classList.toggle("active", lang === "Hindi");
  el("lang-pa").classList.toggle("active", lang === "Punjabi");
}

el("photo-input").addEventListener("change", () => {
  const f = el("photo-input").files[0];
  el("photo-label").textContent = f ? f.name : "Add photo (optional)";
});

el("submit-text").addEventListener("click", async () => {
  const text = el("text-input").value.trim();
  if (!text) return;
  await submitListing({ mode: "text", text });
});

el("record-btn").addEventListener("click", async () => {
  if (!recording) {
    await startRecording();
  } else {
    stopRecording();
  }
});

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
    recordedChunks = [];
    mediaRecorder.ondataavailable = (e) => recordedChunks.push(e.data);
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(recordedChunks, { type: "audio/webm;codecs=opus" });
      await submitListing({ mode: "voice", audioBlob: blob });
    };
    mediaRecorder.start();
    recording = true;
    el("record-btn").classList.add("recording");
    el("record-btn").setAttribute("aria-label", "Stop recording");
    el("record-status").textContent = "Recording… tap to stop";
  } catch (err) {
    el("record-status").textContent = "Microphone unavailable -- please type your listing instead";
  }
}

function stopRecording() {
  recording = false;
  el("record-btn").classList.remove("recording");
  el("record-btn").setAttribute("aria-label", "Record your listing by voice");
  el("record-status").textContent = "Processing…";
  if (mediaRecorder) mediaRecorder.stop();
}

async function submitListing({ mode, text, audioBlob }) {
  setStatus("Working on it…");
  hideResult();

  try {
    let resp, body;
    const photoFile = el("photo-input").files[0];

    if (mode === "text") {
      resp = await fetch(`${API_BASE}/listings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ farmer_id: getFarmerId(), raw_text: text, language: currentLanguage }),
      });
    } else {
      const form = new FormData();
      form.append("audio", audioBlob, "listing.webm");
      if (photoFile) form.append("photo", photoFile);
      const params = new URLSearchParams({ farmer_id: getFarmerId(), language: currentLanguage });
      resp = await fetch(`${API_BASE}/listings/voice?${params}`, { method: "POST", body: form });
    }

    body = await resp.json();
    setStatus("");

    if (!resp.ok) {
      showError(body.detail || "Something went wrong -- please try again.");
      return;
    }
    showResult(body);
  } catch (err) {
    setStatus("");
    showError("Could not reach the server -- check your connection and try again.");
  }
}

function setStatus(text) {
  const line = el("status-line");
  line.textContent = text;
  line.style.display = text ? "block" : "none";
}

function hideResult() {
  el("result").style.display = "none";
  el("transcript-block").style.display = "none";
  el("error-block").style.display = "none";
  el("match-block").style.display = "none";
}

function showError(message) {
  el("result").style.display = "block";
  el("error-block").style.display = "block";
  el("error-block").textContent = message;
}

function showResult(body) {
  el("result").style.display = "block";

  if (body.transcript) {
    el("transcript-block").style.display = "block";
    el("transcript-block").textContent = `“${body.transcript}”`;
  }

  if (!body.matches || body.matches.length === 0) {
    el("error-block").style.display = "block";
    el("error-block").textContent = "No buyer matched yet -- your listing is saved and will match as soon as a buyer's demand fits.";
    return;
  }

  const m = body.matches[0];
  lastMatchId = m.id;
  el("match-block").style.display = "flex";
  el("m-qty").textContent = `${m.matched_kg} kg`;
  el("m-crop").textContent = body.listing.crop_type.replace("_", " ");
  el("m-quality").textContent = body.listing.quality_grade === "unknown"
    ? "not read (no photo)"
    : `${body.listing.quality_grade}${body.quality_note ? " — " + body.quality_note : ""}`;
  el("m-buyer").textContent = m.company_name || m.company_id;
  el("m-price").textContent = `₹${m.price_agreed_per_kg} / kg`;
  el("m-pickup").textContent = body.listing.ready_by || "to be confirmed";
  el("m-explanation").textContent = body.explanation || "";

  const audioEl = el("m-audio");
  if (body.explanation_audio_base64) {
    audioEl.src = `data:audio/mp3;base64,${body.explanation_audio_base64}`;
    audioEl.style.display = "block";
  } else {
    audioEl.style.display = "none";
  }
  el("negotiate-result").textContent = "";
}

el("negotiate-btn").addEventListener("click", async () => {
  const text = el("negotiate-input").value.trim();
  if (!text || !lastMatchId) return;
  el("negotiate-result").textContent = "Asking…";
  try {
    const resp = await fetch(`${API_BASE}/negotiate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ match_id: lastMatchId, raw_text: text }),
    });
    const body = await resp.json();
    if (body.outcome === "updated") {
      el("m-price").textContent = `₹${body.new_price_per_kg} / kg`;
      el("negotiate-result").textContent = `Updated to ₹${body.new_price_per_kg}/kg.`;
    } else if (body.outcome === "not_feasible") {
      el("negotiate-result").textContent = body.reason || "That price isn't feasible with any current buyer.";
    } else {
      el("negotiate-result").textContent = body.explanation || "No change understood from that message.";
    }
  } catch {
    el("negotiate-result").textContent = "Could not reach the server.";
  }
});

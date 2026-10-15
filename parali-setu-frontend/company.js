// Parali Setu -- company dashboard logic. Pure display: every number
// here comes straight from GET /companies/{id}/dashboard, nothing is
// computed client-side (PRD Section 9).

const el = (id) => document.getElementById(id);

function currentCompanyId() {
  return el("company-select").value;
}

async function loadDashboard() {
  const companyId = currentCompanyId();
  setLoading();
  try {
    const resp = await fetch(`${API_BASE}/companies/${companyId}/dashboard`);
    const body = await resp.json();
    renderRecommendation(body.recommendation);
    renderIncomingSupply(body.incoming_supply);
    renderActiveMatches(body.active_matches);
  } catch (err) {
    el("recommendation").innerHTML = `<p class="error">Could not reach the server.</p>`;
    el("incoming-supply").innerHTML = "";
    el("active-matches").innerHTML = "";
  }
}

function setLoading() {
  el("recommendation").innerHTML = `<p class="empty-state">Loading…</p>`;
  el("incoming-supply").innerHTML = `<p class="empty-state">Loading…</p>`;
  el("active-matches").innerHTML = `<p class="empty-state">Loading…</p>`;
}

function renderRecommendation(rec) {
  if (!rec) {
    el("recommendation").innerHTML = `<p class="empty-state">Forecast not yet available for this company.</p>`;
    return;
  }
  const period = new Date(rec.period).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  el("recommendation").innerHTML = `
    <div class="rec-card">
      <p class="headline">Prioritize ${rec.product.replace("_", " ")} — target ${rec.region}</p>
      <p class="hint">Peak demand week starting ${period}: ~${Math.round(rec.predicted_demand)} units (BigQuery ML forecast, trained offline on the synthetic historical corpus — PRD Section 12).</p>
    </div>`;
}

function renderIncomingSupply(matches) {
  if (!matches || matches.length === 0) {
    el("incoming-supply").innerHTML = `<p class="empty-state">No matching supply yet.</p>`;
    return;
  }
  const rows = matches.map((m) => `
    <tr>
      <td>${m.farmer_id}</td>
      <td>${m.matched_kg} kg</td>
      <td>₹${m.price_agreed_per_kg}/kg</td>
      <td><span class="tag tag-${m.status}">${m.status.replace("_", " ")}</span></td>
    </tr>`).join("");
  el("incoming-supply").innerHTML = `
    <table><thead><tr><th>Farmer</th><th>Qty</th><th>Price</th><th>Status</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

function renderActiveMatches(matches) {
  if (!matches || matches.length === 0) {
    el("active-matches").innerHTML = `<p class="empty-state">Nothing in flight yet.</p>`;
    return;
  }
  const rows = matches.map((m) => `
    <tr>
      <td>${m.id}</td>
      <td><span class="tag tag-${m.status}">${m.status.replace("_", " ")}</span></td>
      <td>${m.status === "proposed" ? `<button class="secondary" data-match="${m.id}" onclick="acceptMatch('${m.id}')">Accept</button>` : "—"}</td>
    </tr>`).join("");
  el("active-matches").innerHTML = `
    <table><thead><tr><th>Match</th><th>Status</th><th></th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

async function acceptMatch(matchId) {
  // Simulated confirm step (PRD Section 7/13) -- no real payment or
  // logistics integration, a Firestore status change only.
  try {
    await fetch(`${API_BASE}/negotiate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ match_id: matchId, raw_text: "I accept, confirm this." }),
    });
  } catch {}
  loadDashboard();
}

el("refresh-btn").addEventListener("click", loadDashboard);
el("company-select").addEventListener("change", loadDashboard);

el("post-demand-btn").addEventListener("click", async () => {
  const companyId = currentCompanyId();
  const payload = {
    product: el("demand-product").value.trim(),
    crop_type: el("demand-crop").value,
    quantity_needed_kg: parseFloat(el("demand-qty").value),
    price_offer_per_kg: parseFloat(el("demand-price").value),
  };
  if (!payload.product || !payload.quantity_needed_kg || !payload.price_offer_per_kg) {
    el("demand-result").textContent = "Please fill in product, quantity, and price.";
    return;
  }
  el("demand-result").textContent = "Posting…";
  try {
    const resp = await fetch(`${API_BASE}/companies/${companyId}/demand`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (resp.ok) {
      el("demand-result").textContent = "Posted.";
      loadDashboard();
    } else {
      el("demand-result").textContent = "Could not post demand.";
    }
  } catch {
    el("demand-result").textContent = "Could not reach the server.";
  }
});

loadDashboard();

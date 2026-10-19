function detectApiBase() {
  if (window.location.protocol === "file:") {
    return "http://localhost:8000/api";
  }
  if (window.location.port === "5500" || window.location.port === "5173") {
    return "http://localhost:8000/api";
  }
  return window.location.origin + "/api";
}

const API_BASE = detectApiBase();

const TYPE_LABELS = {
  robbery: "Robbery",
  theft: "Theft",
  vandalism: "Vandalism",
  fire: "Fire",
  flood: "Flood",
  suspicious_activity: "Suspicious activity",
  medical_emergency: "Medical emergency",
  violence: "Violence",
  other: "Other",
};

const STATUS_LABELS = {
  pending: "Pending",
  under_review: "Under review",
  verified: "Verified",
  dismissed: "Dismissed",
};

const STATUS_TONES = {
  pending: "slate",
  under_review: "amber",
  verified: "green",
  dismissed: "red",
};

const PRIORITY_TONES = {
  low: "blue",
  medium: "amber",
  high: "red",
};

const SOURCE_LABELS = {
  manual: "Dashboard",
  whatsapp: "WhatsApp",
  whatsapp_voice: "WhatsApp voice",
  text: "Text",
};

const HEAD_STATUS_LABELS = {
  pending: "Pending",
  verified: "Verified",
  rejected: "Rejected",
};

const HEAD_STATUS_TONES = {
  pending: "amber",
  verified: "green",
  rejected: "red",
};

const state = {
  reports: [],
  heads: [],
  stats: null,
  headFilter: "",
  typeFilter: "",
  statusFilter: "",
  search: "",
  detailId: null,
};

const el = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => {
    const map = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    };
    return map[character];
  });
}

async function api(path, options = {}) {
  const hasBody = options.body !== undefined && options.body !== null;
  const headers = {
    ...(hasBody ? { "Content-Type": "application/json" } : {}),
    ...(options.headers || {}),
  };

  let response;
  try {
    response = await fetch(API_BASE + path, { ...options, headers });
  } catch (error) {
    throw new Error("Cannot reach the backend. Is it running on port 8000?");
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body.detail)) {
        detail = body.detail.map((item) => item.msg || "Invalid input").join("; ");
      }
    } catch (error) {
      // Keep the default message.
    }
    throw new Error(detail);
  }

  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function parseDate(value) {
  if (!value) {
    return null;
  }
  const normalized = /Z|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

function relativeTime(value) {
  const date = parseDate(value);
  if (!date) {
    return value || "-";
  }
  const minutes = Math.round((Date.now() - date.getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function formatDateTime(value) {
  const date = parseDate(value);
  if (!date) {
    return value || "-";
  }
  return date.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatCoords(latitude, longitude) {
  if (latitude === null || latitude === undefined || longitude === null || longitude === undefined) {
    return "No coordinates";
  }
  return `${Number(latitude).toFixed(4)}, ${Number(longitude).toFixed(4)}`;
}

function locationText(report) {
  if (report.location_name) {
    return report.location_name;
  }
  if (report.latitude != null && report.longitude != null) {
    return formatCoords(report.latitude, report.longitude);
  }
  return "No location yet";
}

function typeLabel(value) {
  return TYPE_LABELS[value] || "Other";
}

function statusLabel(value) {
  return STATUS_LABELS[value] || value;
}

function headStatusLabel(value) {
  return HEAD_STATUS_LABELS[value] || value;
}

function sourceLabel(value) {
  if (SOURCE_LABELS[value]) {
    return SOURCE_LABELS[value];
  }
  return String(value || "Unknown").replace(/_/g, " ");
}

function badge(label, tone, dot = false) {
  return `<span class="badge badge-${tone}${dot ? " badge-dot" : ""}">${escapeHtml(label)}</span>`;
}

function statusBadge(status) {
  return badge(statusLabel(status), STATUS_TONES[status] || "slate", true);
}

function priorityBadge(priority) {
  return badge(String(priority || "low").toUpperCase(), PRIORITY_TONES[priority] || "blue");
}

function statusOptions(current) {
  return Object.entries(STATUS_LABELS)
    .map(([value, label]) => {
      const selected = value === current ? " selected" : "";
      const disabled = current === "dismissed" && value !== "dismissed" ? " disabled" : "";
      return `<option value="${value}"${selected}${disabled}>${label}</option>`;
    })
    .join("");
}

function showToast(message, type = "success") {
  const toast = el("toast");
  toast.textContent = message;
  toast.className = `toast ${type}`;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.classList.add("hidden");
  }, 3800);
}

function openModal(id) {
  el(id).classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function closeModal(id) {
  el(id).classList.add("hidden");
  if (id === "detail-modal") {
    state.detailId = null;
  }
  const openModals = document.querySelectorAll(".modal:not(.hidden)");
  if (openModals.length === 0) {
    document.body.classList.remove("modal-open");
  }
}

function setView(view) {
  document.querySelectorAll(".view").forEach((section) => section.classList.add("hidden"));
  const target = el(`view-${view}`);
  if (target) {
    target.classList.remove("hidden");
  }
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
}

async function loadReports() {
  el("reports-loading").classList.remove("hidden");
  el("reports-error").classList.add("hidden");
  el("reports-empty").classList.add("hidden");
  el("reports-table-wrap").classList.add("hidden");
  el("reports-mobile").classList.add("hidden");

  const params = new URLSearchParams({ limit: "200" });
  if (state.typeFilter) params.set("type", state.typeFilter);
  if (state.statusFilter) params.set("status", state.statusFilter);

  try {
    state.reports = await api(`/reports?${params.toString()}`);
    renderReports();
  } catch (error) {
    el("reports-error").textContent = error.message;
    el("reports-error").classList.remove("hidden");
  } finally {
    el("reports-loading").classList.add("hidden");
  }
}

function renderReports() {
  const query = state.search.trim().toLowerCase();
  const reports = query
    ? state.reports.filter((report) => {
        const haystack = [
          report.description,
          report.location_name,
          report.ai_summary,
          typeLabel(report.type),
          sourceLabel(report.source),
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return haystack.includes(query);
      })
    : state.reports;

  if (reports.length === 0) {
    el("reports-empty").innerHTML = state.reports.length
      ? "<strong>No matches</strong><span>Try a different search or filter.</span>"
      : "<strong>No reports found</strong><span>New WhatsApp and dashboard reports will appear here.</span>";
    el("reports-empty").classList.remove("hidden");
    el("reports-table-wrap").classList.add("hidden");
    el("reports-mobile").classList.add("hidden");
    return;
  }

  el("reports-empty").classList.add("hidden");
  el("reports-table-wrap").classList.remove("hidden");
  el("reports-mobile").classList.remove("hidden");
  el("reports-body").innerHTML = reports.map(reportRow).join("");
  el("reports-mobile").innerHTML = reports.map(reportCard).join("");
}

function reportRow(report) {
  return `
    <tr class="clickable" data-report-id="${report.id}">
      <td class="id-cell">#${report.id}</td>
      <td class="type-cell">
        <strong>${escapeHtml(typeLabel(report.type))}</strong>
        <div class="badges">${priorityBadge(report.priority)}</div>
      </td>
      <td>
        <select class="status-select" data-action="status" data-id="${report.id}" aria-label="Report status">
          ${statusOptions(report.status)}
        </select>
      </td>
      <td class="description-cell">
        <span class="description" title="${escapeHtml(report.description)}">${escapeHtml(report.description)}</span>
        <div class="meta-line">
          <span>${escapeHtml(locationText(report))}</span>
          <span class="separator">&middot;</span>
          <span class="source-chip">${escapeHtml(sourceLabel(report.source))}</span>
        </div>
      </td>
      <td class="id-cell">${escapeHtml(relativeTime(report.created_at))}</td>
      <td>
        <button type="button" class="btn btn-ghost btn-sm" data-action="delete" data-id="${report.id}">Delete</button>
      </td>
    </tr>
  `;
}

function reportCard(report) {
  return `
    <article class="mobile-item" data-report-id="${report.id}">
      <div class="mobile-item-head">
        <div>
          <strong>${escapeHtml(typeLabel(report.type))}</strong>
          <div class="badges">
            ${priorityBadge(report.priority)}
            <span class="source-chip">${escapeHtml(sourceLabel(report.source))}</span>
          </div>
        </div>
        <span class="id-cell">#${report.id}</span>
      </div>
      <p>${escapeHtml(report.description)}</p>
      <div class="meta-line">
        <span>${escapeHtml(locationText(report))}</span>
        <span class="separator">&middot;</span>
        <span>${escapeHtml(relativeTime(report.created_at))}</span>
      </div>
      <div class="mobile-item-foot">
        <select class="status-select" data-action="status" data-id="${report.id}" aria-label="Report status">
          ${statusOptions(report.status)}
        </select>
        <div class="mobile-actions">
          <button type="button" class="btn btn-ghost btn-sm" data-action="delete" data-id="${report.id}">Delete</button>
        </div>
      </div>
    </article>
  `;
}

async function loadHeads() {
  el("heads-loading").classList.remove("hidden");
  el("heads-error").classList.add("hidden");
  el("heads-empty").classList.add("hidden");
  el("heads-table-wrap").classList.add("hidden");
  el("heads-mobile").classList.add("hidden");

  try {
    state.heads = await api("/quarter-heads");
    renderHeads();
  } catch (error) {
    el("heads-error").textContent = error.message;
    el("heads-error").classList.remove("hidden");
  } finally {
    el("heads-loading").classList.add("hidden");
  }
}

function renderHeads() {
  const heads = state.headFilter
    ? state.heads.filter((head) => head.status === state.headFilter)
    : state.heads;

  const pendingCount = state.heads.filter((head) => head.status === "pending").length;
  const pendingBadge = el("heads-pending-count");
  pendingBadge.textContent = String(pendingCount);
  pendingBadge.classList.toggle("hidden", pendingCount === 0);

  if (heads.length === 0) {
    el("heads-empty").innerHTML = state.heads.length
      ? "<strong>No matches</strong><span>No quarter heads have this status.</span>"
      : "<strong>No quarter heads found</strong><span>Applications from this page or WhatsApp will appear here.</span>";
    el("heads-empty").classList.remove("hidden");
    el("heads-table-wrap").classList.add("hidden");
    el("heads-mobile").classList.add("hidden");
    return;
  }

  el("heads-empty").classList.add("hidden");
  el("heads-table-wrap").classList.remove("hidden");
  el("heads-mobile").classList.remove("hidden");
  el("heads-body").innerHTML = heads.map(headRow).join("");
  el("heads-mobile").innerHTML = heads.map(headCard).join("");
}

function headActions(head) {
  const buttons = [];
  if (head.status !== "verified") {
    buttons.push(
      `<button type="button" class="btn btn-secondary btn-sm" data-head-action="verified" data-id="${head.id}">Verify</button>`
    );
  }
  if (head.status !== "rejected") {
    buttons.push(
      `<button type="button" class="btn btn-danger btn-sm" data-head-action="rejected" data-id="${head.id}">Reject</button>`
    );
  }
  return `<div class="action-group">${buttons.join("")}</div>`;
}

function headSum(place, city) {
  return city ? `${place}, ${city}` : place;
}

function headRow(head) {
  return `
    <tr>
      <td class="id-cell">#${head.id}</td>
      <td>
        <strong>${escapeHtml(head.name)}</strong>
        ${head.has_id_document ? '<div class="meta-line">ID document on file</div>' : ""}
      </td>
      <td>${escapeHtml(headSum(head.quarter_name, head.city))}</td>
      <td class="id-cell">${escapeHtml(head.wa_number_masked || "-")}</td>
      <td>${badge(headStatusLabel(head.status), HEAD_STATUS_TONES[head.status] || "slate", true)}</td>
      <td class="id-cell">${escapeHtml(relativeTime(head.created_at))}</td>
      <td>${headActions(head)}</td>
    </tr>
  `;
}

function headCard(head) {
  return `
    <article class="mobile-item">
      <div class="mobile-item-head">
        <div>
          <strong>${escapeHtml(head.name)}</strong>
          <div class="meta-line">${escapeHtml(headSum(head.quarter_name, head.city))}</div>
        </div>
        ${badge(headStatusLabel(head.status), HEAD_STATUS_TONES[head.status] || "slate", true)}
      </div>
      <div class="meta-line">
        <span>${escapeHtml(head.wa_number_masked || "-")}</span>
        <span class="separator">&middot;</span>
        <span>applied ${escapeHtml(relativeTime(head.created_at))}</span>
      </div>
      <div class="mobile-item-foot">
        <span></span>
        ${headActions(head)}
      </div>
    </article>
  `;
}

async function loadStats() {
  try {
    state.stats = await api("/stats");
  } catch (error) {
    return;
  }
  el("stat-total").textContent = String(state.stats.total_reports);
  el("stat-pending").textContent = String(state.stats.pending_reports);
  el("stat-high").textContent = String(state.stats.high_priority);
  el("stat-heads").textContent = String(state.stats.verified_heads);

  const pending = el("nav-pending-count");
  pending.textContent = String(state.stats.pending_reports);
  pending.classList.toggle("hidden", state.stats.pending_reports === 0);
}

async function loadIntegration() {
  const banner = el("integration-banner");
  try {
    const status = await api("/whatsapp/status");
    const parts = [];
    if (status.configured) {
      parts.push("WhatsApp replies are connected.");
    } else {
      parts.push(
        "WhatsApp is not connected. Add WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID to backend/.env."
      );
    }
    if (!status.ai_configured) {
      parts.push("OpenRouter key missing: keyword fallback is active.");
    }
    if (!status.voice_configured) {
      parts.push("Voice notes need ELEVENLABS_API_KEY.");
    }
    const ready = status.configured && status.ai_configured && status.voice_configured;
    banner.textContent = parts.join(" ");
    banner.classList.remove("hidden", "ok", "warn");
    banner.classList.add(ready ? "ok" : "warn");
  } catch (error) {
    banner.textContent = error.message;
    banner.classList.remove("hidden", "ok");
    banner.classList.add("warn");
  }
}

async function refreshAll() {
  await Promise.all([loadReports(), loadHeads(), loadStats(), loadIntegration()]);
}

async function changeReportStatus(reportId, status) {
  try {
    await api(`/reports/${reportId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    showToast("Report status updated.");
    await refreshAll();
    if (state.detailId === reportId && !el("detail-modal").classList.contains("hidden")) {
      await openReportDetail(reportId);
    }
  } catch (error) {
    showToast(error.message, "error");
    await loadReports();
  }
}

async function deleteReport(reportId) {
  if (!window.confirm("Delete this report? This cannot be undone.")) {
    return;
  }
  try {
    await api(`/reports/${reportId}`, { method: "DELETE" });
    if (state.detailId === reportId) {
      closeModal("detail-modal");
    }
    showToast("Report deleted.");
    await refreshAll();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function openReportDetail(reportId) {
  try {
    const report = await api(`/reports/${reportId}`);
    state.detailId = reportId;
    renderDetail(report);
    openModal("detail-modal");
    loadMatchingHeads(reportId);
  } catch (error) {
    showToast(error.message, "error");
  }
}

function renderDetail(report) {
  el("detail-title").textContent = typeLabel(report.type);
  el("detail-subtitle").textContent = `#${report.id} from ${sourceLabel(report.source)} on ${formatDateTime(
    report.created_at
  )}`;

  const detailsHtml = renderDetails(report.details);
  const aiNote = report.ai_processed
    ? "AI extraction complete."
    : `Keyword fallback used${report.ai_error ? `: ${report.ai_error}` : "."}`;

  el("detail-body").innerHTML = `
    <div class="badges">
      ${statusBadge(report.status)}
      ${priorityBadge(report.priority)}
      <span class="source-chip">${escapeHtml(sourceLabel(report.source))}</span>
    </div>

    <div class="detail-section">
      <span class="detail-label">Description</span>
      <p class="detail-text">${escapeHtml(report.description)}</p>
    </div>

    <div class="detail-section">
      <span class="detail-label">Location</span>
      <p class="detail-text">${escapeHtml(report.location_name || "No area name")}<br>
        <span class="detail-muted">${escapeHtml(formatCoords(report.latitude, report.longitude))}</span>
      </p>
      <div class="pin-form">
        <input id="detail-latitude" class="input" type="number" step="any" placeholder="Latitude" value="${escapeHtml(
          report.latitude ?? ""
        )}">
        <input id="detail-longitude" class="input" type="number" step="any" placeholder="Longitude" value="${escapeHtml(
          report.longitude ?? ""
        )}">
        <button type="button" id="detail-save-location" class="btn btn-secondary btn-sm">Save location</button>
      </div>
    </div>

    ${
      report.ai_summary
        ? `<div class="detail-section">
            <span class="detail-label">AI summary</span>
            <p class="detail-text">${escapeHtml(report.ai_summary)}</p>
            <span class="detail-muted">${escapeHtml(aiNote)}</span>
          </div>`
        : ""
    }

    ${
      report.transcript
        ? `<div class="detail-section">
            <span class="detail-label">Original message or transcript</span>
            <p class="detail-text">${escapeHtml(report.transcript)}</p>
          </div>`
        : ""
    }

    ${detailsHtml}

    <div class="detail-section">
      <span class="detail-label">Routed to quarter heads</span>
      <div id="detail-routing" class="detail-muted">Checking this report's area...</div>
    </div>
  `;

  el("detail-approve").classList.toggle(
    "hidden",
    report.status === "verified" || report.status === "dismissed"
  );
  el("detail-dismiss").classList.toggle("hidden", report.status === "dismissed");
  el("detail-save-location").addEventListener("click", () => saveDetailLocation(report.id));
}

function renderDetails(details) {
  if (!details || typeof details !== "object") {
    return "";
  }
  const pairs = [
    ["People", details.people],
    ["Vehicles", joinList(details.vehicles)],
    ["Weapons", joinList(details.weapons)],
    ["Activity", details.activity],
    ["Injuries", details.injuries],
    ["Property damage", details.property_damage],
    ["Emergency services", joinList(details.emergency_services)],
    ["Notes", details.notes],
  ].filter(([, value]) => {
    if (value === null || value === undefined || value === "") return false;
    if (Array.isArray(value) && value.length === 0) return false;
    return true;
  });

  if (pairs.length === 0) {
    return "";
  }

  return `
    <div class="detail-section">
      <span class="detail-label">Extracted details</span>
      <dl class="detail-key-values">
        ${pairs
          .map(
            ([label, value]) => `
              <div class="detail-pair">
                <dt>${escapeHtml(label)}</dt>
                <dd>${escapeHtml(value)}</dd>
              </div>
            `
          )
          .join("")}
      </dl>
    </div>
  `;
}

function joinList(value) {
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  return value;
}

async function loadMatchingHeads(reportId) {
  try {
    const heads = await api(`/reports/${reportId}/matching-heads`);
    if (state.detailId !== reportId) {
      return;
    }
    const container = el("detail-routing");
    if (!container) {
      return;
    }
    if (heads.length === 0) {
      container.innerHTML =
        '<div class="routing-empty">No verified quarter head matches this area yet.</div>';
      return;
    }
    container.innerHTML = `
      <ul class="routing-list">
        ${heads
          .map(
            (head) => `
              <li class="routing-item">
                <div>
                  <strong>${escapeHtml(head.name)}</strong>
                  <span>${escapeHtml(headSum(head.quarter_name, head.city))} &middot; ${escapeHtml(
                    head.wa_number_masked
                  )}</span>
                </div>
                ${badge("Verified", "green", true)}
              </li>
            `
          )
          .join("")}
      </ul>
    `;
  } catch (error) {
    const container = el("detail-routing");
    if (container && state.detailId === reportId) {
      container.textContent = error.message;
    }
  }
}

async function saveDetailLocation(reportId) {
  const latitudeValue = el("detail-latitude").value.trim();
  const longitudeValue = el("detail-longitude").value.trim();
  const latitude = Number(latitudeValue);
  const longitude = Number(longitudeValue);

  if (latitudeValue === "" || longitudeValue === "") {
    showToast("Enter both latitude and longitude.", "error");
    return;
  }
  if (Number.isNaN(latitude) || latitude < -90 || latitude > 90) {
    showToast("Latitude must be between -90 and 90.", "error");
    return;
  }
  if (Number.isNaN(longitude) || longitude < -180 || longitude > 180) {
    showToast("Longitude must be between -180 and 180.", "error");
    return;
  }

  try {
    await api(`/reports/${reportId}/location`, {
      method: "PATCH",
      body: JSON.stringify({ latitude, longitude }),
    });
    showToast("Location saved.");
    await loadReports();
    await loadStats();
    await openReportDetail(reportId);
  } catch (error) {
    showToast(error.message, "error");
  }
}

function bindReportList(container) {
  container.addEventListener("click", (event) => {
    if (event.target.closest("select")) {
      return;
    }
    const actionButton = event.target.closest("[data-action]");
    if (actionButton) {
      if (actionButton.dataset.action === "delete") {
        deleteReport(Number(actionButton.dataset.id));
      }
      return;
    }
    const item = event.target.closest("[data-report-id]");
    if (item) {
      openReportDetail(Number(item.dataset.reportId));
    }
  });

  container.addEventListener("change", (event) => {
    const select = event.target.closest("select[data-action='status']");
    if (!select) {
      return;
    }
    changeReportStatus(Number(select.dataset.id), select.value);
  });
}

async function updateHeadStatus(headId, status) {
  try {
    await api(`/quarter-heads/${headId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    showToast(status === "verified" ? "Quarter head verified." : "Application rejected.");
    await Promise.all([loadHeads(), loadStats()]);
  } catch (error) {
    showToast(error.message, "error");
  }
}

function bindHeadList(container) {
  container.addEventListener("click", (event) => {
    const button = event.target.closest("[data-head-action]");
    if (!button) {
      return;
    }
    updateHeadStatus(Number(button.dataset.id), button.dataset.headAction);
  });
}

function openReportForm() {
  el("report-form").reset();
  el("form-type").value = "other";
  el("form-severity").value = "medium";
  el("report-form-error").classList.add("hidden");
  openModal("report-form-modal");
  window.setTimeout(() => el("form-description").focus(), 50);
}

async function submitReportForm(event) {
  event.preventDefault();
  const errorBox = el("report-form-error");
  const description = el("form-description").value.trim();
  if (description.length < 5) {
    errorBox.textContent = "Description must be at least 5 characters.";
    errorBox.classList.remove("hidden");
    return;
  }

  const latitudeValue = el("form-latitude").value.trim();
  const longitudeValue = el("form-longitude").value.trim();
  const latitude = latitudeValue === "" ? null : Number(latitudeValue);
  const longitude = longitudeValue === "" ? null : Number(longitudeValue);

  if (latitude !== null && (Number.isNaN(latitude) || latitude < -90 || latitude > 90)) {
    errorBox.textContent = "Latitude must be between -90 and 90.";
    errorBox.classList.remove("hidden");
    return;
  }
  if (longitude !== null && (Number.isNaN(longitude) || longitude < -180 || longitude > 180)) {
    errorBox.textContent = "Longitude must be between -180 and 180.";
    errorBox.classList.remove("hidden");
    return;
  }

  const button = el("report-submit");
  button.disabled = true;
  button.textContent = "Submitting...";
  errorBox.classList.add("hidden");

  try {
    await api("/reports", {
      method: "POST",
      body: JSON.stringify({
        type: el("form-type").value,
        severity: el("form-severity").value,
        description,
        location_name: el("form-location").value.trim() || null,
        latitude,
        longitude,
      }),
    });
    closeModal("report-form-modal");
    showToast("Report saved.");
    await refreshAll();
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.classList.remove("hidden");
  } finally {
    button.disabled = false;
    button.textContent = "Submit report";
  }
}

function openHeadForm() {
  el("head-form").reset();
  el("head-form-error").classList.add("hidden");
  openModal("head-form-modal");
  window.setTimeout(() => el("head-name").focus(), 50);
}

async function submitHeadForm(event) {
  event.preventDefault();
  const errorBox = el("head-form-error");
  const name = el("head-name").value.trim();
  const number = el("head-number").value.replace(/[^\d+]/g, "");
  const quarter = el("head-quarter").value.trim();

  if (name.length < 2) {
    errorBox.textContent = "Full name is required.";
    errorBox.classList.remove("hidden");
    return;
  }
  if (number.length < 5) {
    errorBox.textContent = "A valid WhatsApp number is required.";
    errorBox.classList.remove("hidden");
    return;
  }
  if (quarter.length < 2) {
    errorBox.textContent = "Quarter or area name is required.";
    errorBox.classList.remove("hidden");
    return;
  }

  const button = el("head-submit");
  button.disabled = true;
  button.textContent = "Saving...";
  errorBox.classList.add("hidden");

  try {
    await api("/quarter-heads", {
      method: "POST",
      body: JSON.stringify({
        name,
        wa_number: number,
        quarter_name: quarter,
        city: el("head-city").value.trim() || null,
        notes: el("head-notes").value.trim() || null,
      }),
    });
    closeModal("head-form-modal");
    showToast("Quarter head application saved.");
    await Promise.all([loadHeads(), loadStats()]);
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.classList.remove("hidden");
  } finally {
    button.disabled = false;
    button.textContent = "Register";
  }
}

function bindEvents() {
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });

  el("refresh-reports").addEventListener("click", refreshAll);
  el("open-report-form").addEventListener("click", openReportForm);
  el("open-head-form").addEventListener("click", openHeadForm);

  el("report-search").addEventListener("input", (event) => {
    state.search = event.target.value;
    renderReports();
  });
  el("filter-type").addEventListener("change", (event) => {
    state.typeFilter = event.target.value;
    loadReports();
  });
  el("filter-status").addEventListener("change", (event) => {
    state.statusFilter = event.target.value;
    loadReports();
  });

  bindReportList(el("reports-body"));
  bindReportList(el("reports-mobile"));
  bindHeadList(el("heads-body"));
  bindHeadList(el("heads-mobile"));

  document.querySelectorAll("[data-head-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      state.headFilter = button.dataset.headFilter;
      document.querySelectorAll("[data-head-filter]").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
      renderHeads();
    });
  });

  el("report-form").addEventListener("submit", submitReportForm);
  el("head-form").addEventListener("submit", submitHeadForm);

  el("detail-approve").addEventListener("click", () => {
    if (state.detailId) {
      changeReportStatus(state.detailId, "verified");
    }
  });
  el("detail-dismiss").addEventListener("click", () => {
    if (state.detailId) {
      changeReportStatus(state.detailId, "dismissed");
    }
  });

  document.querySelectorAll("[data-close]").forEach((button) => {
    button.addEventListener("click", () => closeModal(button.dataset.close));
  });
  document.querySelectorAll(".modal").forEach((modal) => {
    modal.addEventListener("mousedown", (event) => {
      if (event.target === modal) {
        closeModal(modal.id);
      }
    });
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    const openModals = Array.from(document.querySelectorAll(".modal:not(.hidden)"));
    if (openModals.length > 0) {
      closeModal(openModals[openModals.length - 1].id);
    }
  });
}

function init() {
  bindEvents();
  refreshAll();
}

init();

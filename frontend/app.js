/* Minimal, dependency-free frontend for the MoM Generator API.
 * Deliberately plain JS (no build step) so the whole repo installs and
 * runs with nothing but `python -m http.server` for a quick demo, while
 * still implementing the full 5-screen flow from the spec:
 *   1. Upload  2. Processing  3. Extraction review  4. MoM review  5. Export
 */

const API = window.API_BASE_URL;
const STEP_LABELS = ["Upload", "Processing", "Extraction", "Review MoM", "Export"];
let state = { step: 0, docId: null, docMeta: null, extraction: null, minutes: null, validation: null };

const appEl = document.getElementById("app");
const stepsEl = document.getElementById("steps");

function renderSteps() {
  stepsEl.innerHTML = STEP_LABELS.map((label, i) => {
    const cls = i === state.step ? "active" : i < state.step ? "done" : "";
    return `<div class="step ${cls}">${i + 1}. ${label}</div>`;
  }).join("");
}

function goTo(step) {
  state.step = step;
  renderSteps();
  RENDERERS[step]();
}

async function api(path, options = {}) {
  const resp = await fetch(`${API}${path}`, options);
  if (!resp.ok) {
    let detail = `Request failed (${resp.status})`;
    try {
      const body = await resp.json();
      if (body.detail) detail = body.detail;
    } catch (_) {}
    throw new Error(detail);
  }
  const contentType = resp.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return resp.json();
  return resp.blob();
}

function errorBox(message) {
  return `<div class="error-box">⚠️ ${message}</div>`;
}

function warningList(warnings) {
  if (!warnings || warnings.length === 0) return "";
  return warnings.map((w) => `<div class="warning">⚠️ ${w}</div>`).join("");
}

/* ---------------- Screen 1: Upload ---------------- */
function renderUpload() {
  appEl.innerHTML = `
    <div class="card">
      <h2>Upload a meeting document</h2>
      <div class="dropzone" id="dropzone">
        <p><strong>Drag & drop</strong> a file here, or click to browse</p>
        <div class="formats">Supported: PDF, scanned PDF, DOCX, PNG, JPG/JPEG — typed, handwritten, or mixed notes.</div>
        <input type="file" id="fileInput" accept=".pdf,.docx,.png,.jpg,.jpeg" />
      </div>
      <div id="uploadStatus"></div>
    </div>
  `;
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("fileInput");

  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragover"); });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) handleFile(fileInput.files[0]);
  });
}

async function handleFile(file) {
  const statusEl = document.getElementById("uploadStatus");
  statusEl.innerHTML = `<p class="muted">Uploading ${file.name}...</p>`;
  const formData = new FormData();
  formData.append("file", file);
  try {
    const doc = await api("/documents", { method: "POST", body: formData });
    state.docId = doc.id;
    state.docMeta = doc;
    goTo(1);
    runProcessing();
  } catch (err) {
    statusEl.innerHTML = errorBox(err.message);
  }
}

/* ---------------- Screen 2: Processing ---------------- */
const PROCESS_STAGES = [
  "Document uploaded",
  "Document classified",
  "Meeting information extracted",
  "Generating MoM",
];

function renderProcessing(activeIndex = 0, failedIndex = -1) {
  appEl.innerHTML = `
    <div class="card">
      <h2>Processing "${state.docMeta.filename}"</h2>
      <ul class="progress-list" id="progressList">
        ${PROCESS_STAGES.map((s, i) => {
          const cls = failedIndex === i ? "error" : i < activeIndex ? "done" : i === activeIndex ? "active" : "";
          const icon = failedIndex === i ? "✕" : i < activeIndex ? "✓" : i === activeIndex ? "●" : "○";
          return `<li class="${cls}">${icon} ${s}</li>`;
        }).join("")}
      </ul>
      ${warningList(state.docMeta.warnings)}
      <div id="processError"></div>
    </div>
  `;
}

async function runProcessing() {
  renderProcessing(0);
  try {
    renderProcessing(1);
    const processed = await api(`/documents/${state.docId}/process`, { method: "POST" });
    state.minutes = processed.meeting_minutes;
    state.validation = processed.validation;

    renderProcessing(2);
    const extraction = await api(`/documents/${state.docId}/extraction`);
    state.extraction = extraction;

    renderProcessing(3);
    const generated = await api(`/documents/${state.docId}/generate`, { method: "POST" });
    state.minutes = generated.meeting_minutes;
    state.validation = generated.validation;

    renderProcessing(4);
    setTimeout(() => goTo(2), 300);
  } catch (err) {
    renderProcessing(0, PROCESS_STAGES.length);
    document.getElementById("processError").innerHTML = errorBox(err.message);
  }
}

/* ---------------- Screen 3: Extraction review ---------------- */
function renderExtraction() {
  const ex = state.extraction;
  const pagesHtml = (ex.pages || [])
    .map(
      (p) => `
      <details ${p.page === 1 ? "open" : ""}>
        <summary>Page ${p.page} (${p.blocks.length} blocks)</summary>
        <pre style="white-space:pre-wrap;font-size:13px;background:#f8f9fb;padding:10px;border-radius:6px;">${escapeHtml(p.raw_text || "(no text extracted)")}</pre>
      </details>`
    )
    .join("");

  appEl.innerHTML = `
    <div class="card">
      <h2>Extraction review</h2>
      <p class="muted">Document type: <strong>${ex.document_kind}</strong></p>
      ${warningList(ex.warnings)}
      ${pagesHtml}
    </div>
    <div class="footer-actions">
      <button class="secondary" onclick="goTo(0)">Start over</button>
      <button onclick="goTo(3)">Continue to MoM review →</button>
    </div>
  `;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

/* ---------------- Screen 4: MoM review (editable) ---------------- */
function textField(label, key) {
  const val = state.minutes[key] || "";
  return `<label>${label}</label><input type="text" data-field="${key}" value="${escapeHtml(val)}" placeholder="Not mentioned" />`;
}

function listField(label, key) {
  const items = state.minutes[key] || [];
  const rows = items
    .map(
      (item, i) => `
      <div class="row" data-list="${key}" data-index="${i}">
        <input type="text" value="${escapeHtml(item)}" />
        <button class="secondary small-btn" onclick="removeListItem('${key}', ${i})">✕</button>
      </div>`
    )
    .join("");
  return `
    <label>${label}</label>
    <div class="list-input" id="list-${key}">
      ${rows}
      <button class="secondary small-btn" onclick="addListItem('${key}')" style="align-self:flex-start;">+ Add</button>
    </div>`;
}

function addListItem(key) {
  state.minutes[key] = [...(state.minutes[key] || []), ""];
  renderMomReview();
}
function removeListItem(key, index) {
  state.minutes[key] = state.minutes[key].filter((_, i) => i !== index);
  renderMomReview();
}
function addActionItem() {
  state.minutes.action_items = [...(state.minutes.action_items || []), { task: "", owner: null, deadline: null }];
  renderMomReview();
}
function removeActionItem(index) {
  state.minutes.action_items = state.minutes.action_items.filter((_, i) => i !== index);
  renderMomReview();
}

function actionItemsTable() {
  const items = state.minutes.action_items || [];
  const rows = items
    .map(
      (item, i) => `
      <tr data-action-index="${i}">
        <td><input type="text" data-action-field="task" value="${escapeHtml(item.task || "")}" /></td>
        <td><input type="text" data-action-field="owner" value="${escapeHtml(item.owner || "")}" placeholder="Not mentioned" /></td>
        <td><input type="text" data-action-field="deadline" value="${escapeHtml(item.deadline || "")}" placeholder="Not mentioned" /></td>
        <td><button class="secondary small-btn" onclick="removeActionItem(${i})">✕</button></td>
      </tr>`
    )
    .join("");
  return `
    <label>Action Items</label>
    <table class="action-table" id="actionTable">
      <thead><tr><th>Task</th><th>Owner</th><th>Deadline</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <button class="secondary small-btn" style="margin-top:8px;" onclick="addActionItem()">+ Add action item</button>
  `;
}

function validationSummary() {
  const v = state.validation;
  if (!v) return "";
  const issues = (v.issues || []).filter((i) => i.severity !== "info");
  if (issues.length === 0 && (v.unsupported_claims || []).length === 0) {
    return `<div class="warning" style="background:#e9f7ee;border-color:#a3d9b1;">✓ No unsupported facts were flagged.</div>`;
  }
  const items = issues.map((i) => `<div class="warning">⚠️ [${i.severity}] ${i.field}: ${i.message}</div>`).join("");
  const unsupported = (v.unsupported_claims || [])
    .map((c) => `<div class="warning">⚠️ Possibly unsupported: ${escapeHtml(c)}</div>`)
    .join("");
  return items + unsupported;
}

function renderMomReview() {
  const m = state.minutes;
  appEl.innerHTML = `
    <div class="card">
      <h2>Review & edit Minutes of Meeting</h2>
      ${validationSummary()}
      ${textField("Meeting Title", "meeting_title")}
      ${textField("Date", "date")}
      ${textField("Time", "time")}
      ${textField("Location", "location")}
      ${textField("Organizer", "organizer")}
      ${listField("Attendees", "attendees")}
      ${listField("Agenda", "agenda")}
      ${listField("Discussion Points", "discussion_points")}
      ${listField("Decisions", "decisions")}
      ${actionItemsTable()}
      ${listField("Risks", "risks")}
      ${listField("Open Questions", "open_questions")}
      ${textField("Next Meeting", "next_meeting")}
      <label>Summary</label>
      <textarea data-field="summary">${escapeHtml(m.summary || "")}</textarea>
    </div>
    <div class="footer-actions">
      <button class="secondary" onclick="goTo(2)">← Back to extraction</button>
      <button onclick="saveMomAndContinue()">Save & continue to export →</button>
    </div>
    <div id="reviewError"></div>
  `;
}

function collectMomFromForm() {
  const m = { ...state.minutes };
  document.querySelectorAll("[data-field]").forEach((el) => {
    const val = el.value.trim();
    m[el.getAttribute("data-field")] = val === "" ? null : val;
  });
  document.querySelectorAll("[data-list]").forEach((row) => {
    const key = row.getAttribute("data-list");
    const idx = parseInt(row.getAttribute("data-index"), 10);
    const input = row.querySelector("input");
    m[key][idx] = input.value;
  });
  document.querySelectorAll("#actionTable tbody tr").forEach((row, i) => {
    const idx = parseInt(row.getAttribute("data-action-index"), 10);
    row.querySelectorAll("[data-action-field]").forEach((input) => {
      const field = input.getAttribute("data-action-field");
      m.action_items[idx][field] = input.value.trim() === "" ? null : input.value.trim();
    });
  });
  // summary field is a textarea, already covered by data-field selector
  return m;
}

async function saveMomAndContinue() {
  const errEl = document.getElementById("reviewError");
  const updated = collectMomFromForm();
  try {
    const resp = await api(`/documents/${state.docId}/mom`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updated),
    });
    state.minutes = resp.meeting_minutes;
    goTo(4);
  } catch (err) {
    errEl.innerHTML = errorBox(err.message);
  }
}

/* ---------------- Screen 5: Export ---------------- */
function renderExport() {
  appEl.innerHTML = `
    <div class="card">
      <h2>Export</h2>
      <p class="muted">Your reviewed Minutes of Meeting is ready to download.</p>
      <div class="download-row">
        <button onclick="download('docx')">Download DOCX</button>
        <button onclick="download('pdf')">Download PDF</button>
      </div>
      <div id="exportError" style="margin-top:14px;"></div>
    </div>
    <div class="footer-actions">
      <button class="secondary" onclick="goTo(3)">← Back to review</button>
      <button class="secondary" onclick="goTo(0)">Process another document</button>
    </div>
  `;
}

async function download(kind) {
  const errEl = document.getElementById("exportError");
  try {
    const blob = await api(`/documents/${state.docId}/download/${kind}`);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `minutes_of_meeting.${kind}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    errEl.innerHTML = errorBox(err.message);
  }
}

const RENDERERS = [renderUpload, renderProcessing, renderExtraction, renderMomReview, renderExport];

renderSteps();
renderUpload();

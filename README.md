# MoM Generator — Trustworthy AI Meeting Minutes

Turns messy real-world meeting documents (typed notes, scanned PDFs, photographed
handwritten notebook pages, DOCX with tables) into a structured, grounded
Minutes of Meeting document — with a human review step before export, and
explicit "Not mentioned" instead of guessed facts.

This is a ground-up rebuild of a small Streamlit prototype into a FastAPI
backend + static frontend with a real document-understanding pipeline. See
`legacy/README.md` for what the original prototype did and why it wasn't
salvageable as-is.

## Problem

Naively piping OCR output into a single "write me a MoM" LLM prompt produces
documents that *look* professional but routinely invent details: a location
when none was written, a deadline that was never stated, an owner assigned
by pattern-matching rather than by what the text actually says. For meeting
minutes — a document people rely on for who-owes-what — that's a serious
trust problem, not a cosmetic one.

This system instead treats generation as the last step of a pipeline whose
earlier stages are deterministic and auditable wherever possible, and treats
the LLM's output as something to be checked, not assumed correct. See
[`docs/architecture.md`](docs/architecture.md) for the full pipeline and the
specific hallucination-prevention layers.

## Features

- PDF (native, scanned, and mixed), DOCX, PNG/JPG ingestion with real file-type
  sniffing (not just trusting the extension)
- DOCX structure preservation: headings, bullets, numbered lists, and tables
  extracted as structured data, not one joined string
- Image preprocessing for handwritten/photographed notes: EXIF orientation
  correction, deskew, adaptive contrast (CLAHE), denoising — original image
  bytes are always preserved alongside the enhanced variant
- Structured extraction into a strict Pydantic schema, with `null` /
  "Not mentioned" for anything not actually present in the source
- Confidence + `needs_review` flags on ambiguous fields
- Grounding validation: generated facts are checked against extracted source
  text; unsupported claims are flagged or dropped, never silently kept
- Human review UI: every field is editable before export
- Real `.docx` (python-docx) and `.pdf` (reportlab) export, not text files
- 54 automated tests, all mocked (no network access or API key required)

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full pipeline
diagram and design rationale.

```
backend/app/
  api/          FastAPI routers (documents, health)
  ingestion/    file-type routing, PDF/DOCX/image extraction
  preprocessing/image deskew/contrast/denoise
  vision/       VisionProvider abstraction (Gemini + deterministic mock)
  extraction/   text/blocks -> structured MeetingMinutes (schema-constrained)
  generation/   validated structured data -> grounded narrative prose
  validation/   schema + grounding ("hallucination") checks
  rendering/    docx/pdf renderers
  models/       Pydantic schemas
frontend/       static HTML/CSS/JS (upload -> processing -> review -> export)
fixtures/       synthetic test documents + generator script
```

## Tech stack

| Component        | Choice                | Why |
|-------------------|------------------------|-----|
| Backend framework | FastAPI                | Async, typed, auto OpenAPI docs, minimal ceremony for a single-developer project |
| Schema validation | Pydantic v2             | Strict typing directly enforces "no field the model can't back up" |
| PDF text          | pypdf                  | Reliable native text extraction, no external binary dependency |
| PDF rasterization | PyMuPDF (fitz)         | Renders scanned pages to images without requiring poppler/pdf2image in the container |
| DOCX               | python-docx             | Structural (not flattened) reading and writing of Word documents |
| Image processing  | OpenCV + Pillow         | Deskew, CLAHE contrast, denoise, EXIF handling |
| Vision/LLM         | Gemini via `google-genai` | Multimodal understanding of handwriting/layout; kept behind an abstract `VisionProvider` so it can be swapped |
| PDF export         | reportlab               | Direct, dependency-light PDF generation (no LibreOffice binary needed in Docker) |
| Frontend           | Vanilla HTML/CSS/JS     | No build step; the project's complexity budget is spent on the pipeline, not frontend tooling |
| Tests              | pytest + FastAPI TestClient | Deterministic, fully mocked vision provider — no API key or network needed |

## Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # then optionally set GEMINI_API_KEY
uvicorn app.main:app --reload --port 8000
```

In a second terminal, serve the frontend:

```bash
cd frontend
python -m http.server 5500
```

Open `http://localhost:5500`. The backend defaults to **mock vision mode**
automatically if `GEMINI_API_KEY` is unset — the full pipeline runs
end-to-end, but OCR/handwriting transcription and semantic extraction are
replaced with a deterministic, clearly-labeled stand-in (see
"Known limitations" below).

## Environment variables

See [`.env.example`](.env.example) for the full list (`GEMINI_API_KEY`,
`MODEL_NAME`, `MAX_FILE_SIZE_MB`, `MAX_PAGES`, `MAX_IMAGE_DIMENSION_PX`,
`STORAGE_DIR`, `CORS_ORIGINS`, `LOG_LEVEL`, `USE_MOCK_VISION`).

## Testing

```bash
cd backend
pytest -q
```

All 54 tests pass with no network access and no API key, using a
deterministic `MockVisionProvider` (`app/vision/mock_provider.py`) injected
via `USE_MOCK_VISION=true`. Coverage: native/scanned/empty/malformed PDF,
DOCX structure (headings/bullets/tables), image preprocessing (skew, low
contrast, corrupted input, oversized input), schema validation, grounding
(fabricated vs. supported facts), generation (dropped ungrounded summaries),
multi-page chunking (large documents split page-aligned and merged
deterministically, never truncated), rendering (valid DOCX/PDF with
expected sections), source-file deletion after ingestion, and the full API
flow end-to-end including error paths (415/400/404/500 with no leaked
stack traces).

## Deployment

The backend is a standard container:

```bash
docker build -t mom-backend ./backend
docker run -p 8000:8000 --env-file .env mom-backend
```

or via compose (backend + a static file server for the frontend):

```bash
docker compose up --build
```

For a free/low-cost public demo: the backend container runs as-is on
Render/Fly.io/Railway's free tiers; the static frontend can be served from
any static host (Netlify/Vercel/GitHub Pages) with `frontend/config.js`
pointing `API_BASE_URL` at the deployed backend, and `CORS_ORIGINS` on the
backend updated to match.

## Limitations (honest)

- **The Gemini integration has not been exercised against a live API key in
  this build.** `app/vision/gemini_provider.py` was written against the
  documented `google-genai` client interface and is architecturally
  isolated (behind `VisionProvider`) and unit-testable via the mock, but it
  has not been integration-tested end-to-end with real handwriting. Verify
  it against a real key before treating it as production-ready.
- **No accuracy/hallucination-rate metrics are reported** in this build,
  for the same reason: without a live model call there is nothing real to
  measure, and the spec explicitly prohibits fabricating benchmark numbers.
  `fixtures/generate_fixtures.py` and the `fixtures/` layout exist so that
  once a key is available, `expected/` ground-truth files can be added and
  the metrics in spec section 28 (attendee/date/decision/action-item/owner/
  deadline accuracy, unsupported-fact rate) computed for real.
- **Grounding validation is lexical, not semantic.** It reliably catches
  wholesale fabrication (a field with no relationship to the source text)
  but will not catch a subtle paraphrase that drifts in meaning while
  reusing source vocabulary.
- **Layout bounding boxes** for vision-model-derived blocks (scanned pages,
  photographed notes) are whatever the model reports in JSON, not the
  output of a dedicated document-layout model — treat coordinates as
  approximate, not pixel-precise.
- **Document storage is in-process** (an in-memory dict + temp files under
  `STORAGE_DIR`), appropriate for a single-instance demo deployment; a
  multi-instance production deployment would need shared storage
  (object storage + a small DB) instead.
- **PDF and DOCX are rendered independently** (two renderers sharing one
  data model), so minor formatting differences between the two exports are
  possible; they are not a DOCX→PDF conversion of each other.
- The frontend is intentionally plain (no framework/build step) to keep the
  project's complexity budget on the pipeline rather than frontend tooling.

## Evaluation

No live-model evaluation has been run (see "Limitations" — this build used
`USE_MOCK_VISION=true` throughout, per the scope agreed for this pass). The
`fixtures/` directory and `fixtures/generate_fixtures.py` are structured so
that a real evaluation pass (spec section 28) can be added later:
`fixtures/typed_notes/`, `fixtures/handwritten_notes/`,
`fixtures/scanned_pdfs/`, `fixtures/mixed_documents/`, and an `expected/`
directory for ground-truth facts to diff extraction output against.

## Screenshots

Not included in this pass — run the app locally (see Setup) to see the
5-screen flow: upload → processing → extraction review → editable MoM →
export.

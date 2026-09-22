# Architecture

## Pipeline

```
Upload (PDF/DOCX/PNG/JPG)
   |
   v
Ingestion router (magic-byte file sniffing, size/type validation)
   |
   +-- PDF --> per-page classification (native text vs scanned)
   |             native  -> pypdf text + deterministic heading/bullet heuristics
   |             scanned -> PyMuPDF rasterization -> Vision provider OCR
   |
   +-- DOCX --> python-docx walk of the XML body, preserving paragraph
   |            styles (headings/lists) and tables as structured blocks
   |
   +-- Image --> preprocessing (EXIF orientation, deskew, CLAHE contrast,
                 denoise) -> Vision provider OCR + layout blocks
   |
   v
ExtractionResult (typed LayoutBlocks per page; deterministic, no LLM
creativity involved in this stage for native PDF/DOCX)
   |
   v
Structured extraction (Vision provider, JSON-schema-constrained prompt).
For documents whose combined text exceeds a conservative per-call
character budget, pages are grouped into page-aligned chunks (never
splitting a page mid-chunk), extracted independently, and merged
deterministically: first non-null value wins for scalars (title/date/
location/...), lists are unioned, action items are concatenated. This
keeps multi-page documents coherent without truncating content or
exceeding the model's context window.
   |
   v
Pydantic schema validation + coercion (malformed fields dropped, not
allowed to crash the request)
   |
   v
Deterministic normalization (whitespace/placeholder cleanup, de-dup)
   |
   v
Structural validation (flags missing owners/deadlines/dates as "not
mentioned" rather than silently accepting gaps)
   |
   v
Grounding validation (word-overlap check of every scalar/list fact against
the extracted source text; ungrounded facts are flagged, not hidden)
   |
   v
Generation (narrative prose for discussion summary + executive summary,
generated ONLY from the validated structured JSON, never from raw text) --
each generated section is re-checked for grounding; if it fails, it is
replaced with an explicit "not available" notice, never silently kept
   |
   v
Human review (editable MoM via the frontend / PUT /documents/{id}/mom)
   |
   v
Rendering (python-docx for .docx, reportlab/platypus for .pdf - both
render directly from the same validated MeetingMinutes object)
```

## Why two separate LLM calls (extraction, then generation) instead of one

A single "read this document and write me a polished MoM" prompt asks the
model to do document understanding and creative writing simultaneously,
which is exactly the failure mode that produces confident-sounding
hallucination. Splitting into (1) constrained structured extraction and
(2) prose generation *from already-validated structured data* means the
prose-writing step physically cannot introduce a new fact - it only has
the validated JSON to work with, and its own output is checked against the
source again before being accepted.

## Where determinism is used instead of the LLM (spec section 36)

| Concern                         | Approach                                      |
|----------------------------------|-----------------------------------------------|
| File type detection              | Magic-byte sniffing (`filetype` library)      |
| Native vs scanned PDF             | Per-page extractable-text-length threshold    |
| DOCX structure (headings/tables) | `python-docx` style/XML walk                  |
| PDF heading/bullet detection (native text) | Line-shape heuristics (case, length, leading characters) |
| Schema conformance                | Pydantic v2 models                            |
| Grounding check                   | Token-overlap heuristic against source text   |
| DOCX/PDF generation                | `python-docx`, `reportlab`                    |

The LLM/vision model is used only where it adds real value: OCR and
handwriting transcription, semantic field extraction from unstructured
text, and narrative summarization.

## Known architectural simplifications (see root README "Limitations")

- Layout bounding boxes for vision-model-derived blocks (scans, images)
  are whatever the model reports, not a dedicated document-layout model -
  treat them as approximate.
- The grounding check is lexical overlap, not a semantic entailment model;
  it catches wholesale fabrication reliably but not subtle paraphrase
  drift.
- PDF and DOCX are rendered independently (two renderers sharing one data
  model) rather than DOCX->PDF conversion, to avoid a LibreOffice
  dependency in the Docker image.

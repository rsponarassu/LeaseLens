# LeaseLens

Backend and web client for a legal-tech service that reads a rental agreement, checks it
against the **Tamil Nadu Regulation of Rights and Responsibilities of Landlords and Tenants
Act, 2017 (Act 42 of 2017)**, and tells a tenant - in English and Tamil - which clauses are
unlawful or merely unfair, why, what to ask for instead, and how to ask for it.

FastAPI + Pydantic v2, PyMuPDF for extraction and highlighting, Tesseract as an OCR
fallback, Gemini or Claude for clause classification, and a YAML rule base applied by
plain Python. The interface is React 19 + Vite + Tailwind v4, served by the same process,
with Supabase for accounts and saved reviews.

---

## The one design decision that matters

**The model extracts. The code decides.**

The LLM is allowed to return exactly two things per clause:

1. a category (`deposit`, `lock_in`, `eviction`, `rent_hike`, `entry_rights`,
   `maintenance`, `general`), and
2. typed entities (`deposit_months: 10`, `notice_period_days: 7`, ...).

It is never asked "is this clause legal?", never asked for a score, and its numbers are
never trusted blindly: a deterministic extractor runs in parallel, and any number the
model reports that contradicts the literal text is discarded in favour of the text.

Every verdict, severity and the 0-100 score is computed in `rule_engine.py` from
thresholds in `rules.yaml`, citing the section that produced them. Consequences:

- the same PDF produces the same score twice in a row, in an offline test, in a demo;
- `GET /api/v1/rules` can show exactly which benchmark fired;
- with no API key at all the service still works, end to end (offline mode).

---

## Quick start

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt
copy .env.example .env                              # optional; works without it
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/docs>. No key, no upload, no network needed:

```bash
curl http://127.0.0.1:8000/api/v1/sample-leases            # 3 pre-analysed leases
curl -o demo.pdf http://127.0.0.1:8000/api/v1/sample-leases/sample-high-deposit/annotated-pdf
curl -F "file=@lease.pdf" http://127.0.0.1:8000/api/v1/analyze
```

Tesseract is optional: without it, text-based PDFs work normally and
`/api/v1/health` reports OCR as `limited`.

---

## Web interface

The UI lives in `frontend/` and is a normal Vite app that talks to `/api/v1`. Build it
once and the API serves it, so a single `uvicorn` is the whole deployment:

```bash
cd frontend
npm install
copy .env.example .env          # optional: Supabase keys, or leave blank for demo mode
npm run build                   # typecheck + bundle into frontend/dist
cd ..
uvicorn app.main:app --reload   # http://127.0.0.1:8000 now serves the app
```

For UI work, run the two processes side by side: `uvicorn app.main:app --reload` and
`npm run dev` in `frontend/` (`http://127.0.0.1:5173`). Vite proxies `/api` to port 8000,
so no CORS setup is needed in development.

| Route | What it is |
| --- | --- |
| `#/login` | Sign in or create an account; Google OAuth appears once the provider is enabled |
| `#/app/review` | Upload or pick a demo lease, then the split workspace: annotated PDF + Fix-it Kit |
| `#/app/history` | Past reviews: search, filter by risk, reopen, delete, clear all |
| `#/app/guide` | User guidelines: what the pipeline does and what each score means |
| `#/app/security` | What happens to the file, and the cookie inventory |

Routing is hash-based on purpose: every path the browser requests is a real file in
`frontend/dist`, so the static mount needs no catch-all rewrite and the API keeps `/docs`,
`/openapi.json` and `/api/v1/*` for itself.

The client never computes a verdict. It renders `risk`, `findings` and `fix` exactly as the
API returns them, and a finding that names a rule id can be traced back through
`GET /api/v1/rules/{id}` from inside the UI.

The boot screen plays `frontend/public/brand/loading.mp4` (1080x1082, 7.6 s, 1.6 MB) inside a
rounded tile, with the still mark as its poster. It is muted and inline so every browser
allows autoplay, and both `prefers-reduced-motion` and a decode failure fall back to the
still. `SPLASH_MIN_MS` in `src/App.tsx` controls how long it stays: `1600` by default, `0`
drops the splash as soon as the session is known, `8000` plays the clip once.

### Notifications, sound and consent

- Every completed task and every failure raises a notification bar (auto-dismissing, with a
  progress bar and a matching synthesised tone). Errors stay longer, and the bell in the
  header keeps the last 20 events so a message that vanished is not lost.
- Sound effects are generated with the Web Audio API - no audio files to download. One
  shared `AudioContext` is created and resumed on the first gesture, so the autoplay policy
  is respected, and the preference is remembered only if the visitor allowed it.
- Cookie consent is granular (necessary / preferences / analytics) and asks before anything
  non-essential is written. "Essential only" also clears preference keys already on the
  device. The current choice is always reversible from the account menu.

---

## Accounts and saved reviews (Supabase)

Supabase is optional. Without keys the app runs in **demo mode**: the profile and the
history live in this browser only, clearly labelled as such. With keys, accounts are real
and history follows the user across devices.

1. Create a project at <https://supabase.com>.
2. SQL Editor -> paste [`supabase/schema.sql`](supabase/schema.sql) -> Run. It creates
   `public.lease_reviews`, enables (and forces) row-level security with one policy per verb,
   and grants nothing to `anon`.
3. Copy the project URL and the **publishable** key (`sb_publishable_…`, the successor of
   the anon key) into `frontend/.env`:

   ```
   VITE_SUPABASE_URL=https://<project>.supabase.co
   VITE_SUPABASE_ANON_KEY=sb_publishable_…
   ```

4. Rebuild the bundle (`npm run build`). Vite inlines `VITE_*` variables at build time, so a
   change here needs a rebuild, not a restart.

Use the publishable key, never a secret key (`sb_secret_…` / `service_role`): the
publishable key is designed to be public and is constrained by the policies in the schema
file. A secret key bypasses RLS and would hand every tenant's history to anyone with the
bundle.

Email/password sign-up works out of the box. Google sign-in needs the provider enabled in
`Authentication -> Providers`, with the site URL and `#/app/review` in the redirect allow
list; before offering the button the login card asks `/auth/v1/settings` whether the
provider is on, so nothing changes here when you enable it later.

Two project settings are worth a look on a fresh project. In `Authentication -> Sign In / Up`,
turn off *Confirm email*: while it is on, sign-up returns no session until the link is
clicked, and the built-in mailer only delivers to project members. Then add the site URL and
`#/app/review` to the redirect allow list, without which the OAuth round-trip lands on the
site URL instead of the workspace.

---

## Endpoints

All routes are under `/api/v1` (configurable via `API_PREFIX`).

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/analyze` | Upload a PDF, run the full pipeline, get the scored report |
| `GET` | `/sample-leases` | The three demo leases with their analyses baked in |
| `GET` | `/sample-leases/{id}` | One demo lease (`.../analysis`, `.../pdf`, `.../annotated-pdf`) |
| `POST` | `/annotate-pdf` | Render highlights; body is `{session_id}` or `{sample_id}` |
| `GET` | `/download-annotated/{session_id}` | Download the highlighted PDF |
| `POST` | `/parse-lease` | Extraction + segmentation only, no verdicts |
| `GET` | `/sessions` | Analyses still held in memory |
| `GET` | `/sessions/{id}` | Replay a report |
| `DELETE` | `/sessions/{id}` | Forget a session and its artefacts, immediately |
| `GET` | `/rules` | The rule base and the scoring model |
| `GET` | `/rules/{rule_id}` | One benchmark with its statutory quote |
| `GET` | `/health` | Rule base, demo self-check, cache occupancy, provider |

### `POST /analyze`

Multipart upload plus optional query parameters:

| Parameter | Default | Meaning |
| --- | --- | --- |
| `use_llm` | `true` | Use the configured provider; silently degrades to offline |
| `tenant_name` | - | Only used in the email draft |
| `landlord_name` | - | Only used in the email draft |
| `monthly_rent_inr` | - | Lets the Fix-it Kit convert deposit *months* into rupees |

The response is self-contained: risk score and band, per-clause findings ordered
worst-first, the extracted entities, the statutory citations, and a Fix-it Kit
(English + Tamil explanation, counter-clause, email draft) for every flagged clause.

---

## The pipeline

```
PDF bytes
  └─ pdf_parser        text + per-line and per-word boxes (PyMuPDF)
                       └─ OCR fallback when a page has too little text
  └─ clause_splitter   numbered / headed / paragraph segmentation
                       └─ running headers and footers dropped as boilerplate
  └─ ai_classifier     LLM category + typed entities  ─┐
                       heuristic extractor (always)    ├─ numbers reconciled in code
  └─ rule_engine       rules.yaml + plain comparisons  ┘
  └─ fix_generator     bilingual explanation, counter-clause, email
  └─ pdf_annotator     red / amber / green highlights + cover page
```

| Module | Responsibility |
| --- | --- |
| `app/services/pdf_parser.py` | Extraction, coordinates, OCR fallback, boilerplate detection |
| `app/services/clause_splitter.py` | Clause boundaries, per-page spans |
| `app/services/ai_classifier.py` | Batched structured-output calls, offline fallback |
| `app/services/heuristic_extractor.py` | The deterministic cross-check (negation- and subject-aware) |
| `app/services/rule_engine.py` | Benchmark comparison, severity, 0-100 score |
| `app/services/fix_generator.py` | Tenant-facing remediation kit |
| `app/services/pdf_annotator.py` | Coordinate-accurate highlights, cover page |
| `app/services/pipeline.py` | Orchestration only - no legal logic |

---

## The rule base

`app/rules/rules.yaml` is the only place a threshold lives. A rule declares a *field*, an
*operator* and a *value*; it never contains an expression to evaluate, so there is no
`eval`, no expression injection, and no hidden logic.

```yaml
- id: DEP-001
  category: deposit
  title: "Security deposit exceeds three months' rent"
  severity: high
  field: deposit_months
  operator: greater_than       # greater_than | less_than | equals | within_range | is_true ...
  value: 3
  explanation: "..."           # plain English
  tamil: "..."                 # Tamil
  counter_clause: "..."        # ready to paste into a revised draft
  statute:
    section: "11(1)"
    heading: "Security deposit"
    quote: "..."               # the actual statutory words
```

25 benchmarks cover deposit limits and refunds, lock-in and early-exit penalties,
eviction notice periods, rent revision, entry rights, structural repairs and essential
services, plus formalities such as registration.

### Scoring

Severity-led, not an average: the worst violation sets the base score, further distinct
violations add a capped breadth bonus, and the base is scaled by the importance of the
tenancy domain. A flat weighted average was rejected deliberately - it let a compliant
maintenance clause dilute a critical eviction term down to "low risk".

| Score | Band |
| --- | --- |
| 0-19 | low |
| 20-39 | moderate |
| 40-59 | elevated |
| 60-79 | high |
| 80-100 | critical |

The weights live in the same YAML (`meta.scoring`), so tuning them needs no code change
and no deploy of new logic.

### Adding a benchmark

1. Add the entry to `rules.yaml` with a unique id (`XXX-000`), a statute quote and Tamil copy.
2. If it reads a new fact, add the field to `ClauseEntities` and extract it in
   `heuristic_extractor.py` **and** in the LLM schema.
3. `pytest`. Startup validation fails loudly on a duplicate id, an unknown field, a
   missing Tamil string, or a gap in the score bands - a broken rule base must never
   silently produce wrong advice.

---

## Privacy by design

- Uploads are read into memory and never written to disk. There is no temp file, no
  `uploads/` directory, no background job that persists a document.
- A session lives for `CACHE_TTL_SECONDS` (default 1 hour), bounded by both an entry
  count and a byte budget; the least recently used session is evicted first.
- `DELETE /api/v1/sessions/{id}` drops the text, the report and the PDF immediately and
  forgets that the id ever existed (subsequent lookups are `404`, not `410`).
- Artifact downloads carry `Cache-Control: private, no-store` and `X-Content-Type-Options: nosniff`.
- Extracted lease text is never logged; `LOG_RAW_TEXT` stays `False`. Files and names
  are logged only as an id, a length and a sanitised file name.
- A restart empties the cache by construction. There is no durable store to leak.
- A saved review is the *derived* result only. Before anything is persisted the client
  blanks `findings[].raw_text`, so the database holds scores, verdicts, explanations and
  counter-clauses - never the agreement's wording. Reopening an old review shows the
  findings; the highlighted PDF is re-rendered only while the session is still warm.
- Saved reviews are scoped by row-level security: every policy compares `user_id` with
  `auth.uid()`, the table forces RLS even for its owner, and `anon` has no grant at all.

---

## Errors

One envelope for every failure, so a client needs one handler:

```json
{
  "error": {
    "code": "password_protected_pdf",
    "message": "This PDF is password protected. Remove the password ...",
    "details": {"file_name": "lease.pdf"},
    "request_id": "8f14e45fceea167a5a36dedd4bea2543"
  }
}
```

| Status | Typical codes |
| --- | --- |
| 400 | `empty_file`, `invalid_upload` |
| 404 | `session_not_found`, `sample_not_found`, `rule_not_found` |
| 410 | `session_expired` (artefacts purged, re-run the analysis) |
| 413 / 415 | `file_too_large`, `unsupported_media_type` |
| 422 | `corrupt_pdf`, `password_protected_pdf`, `no_clauses_found`, `validation_error` |
| 502 / 503 / 504 | `llm_error`, `llm_not_configured`, `llm_timeout` |

`X-Request-ID` is echoed from the request (or generated) and appears in that request's
log lines, so a support report can be traced without asking for the document.

---

## Demo reliability

Three leases are rendered from text at startup - no binary fixtures - analysed with the
deterministic path, and pinned in the cache under stable ids:

| id | persona | result |
| --- | --- | --- |
| `sample-high-deposit` | 10-month deposit, 18-month lock-in, 7-day notice | critical, 100 |
| `sample-moderate-rent` | 45-day refund, 30-day rent notice, 12-hour entry | elevated, 40 |
| `sample-tenant-friendly` | compliant deposit and notice, one keys clause | low, 9 |

Each sample declares the outcome it is supposed to demonstrate. If the extractor or a
benchmark drifts, `/api/v1/health` reports `samples.status = "degraded"` with the
expected-versus-actual detail instead of quietly serving a misleading demo.

---

## Configuration

Everything is typed and validated at boot (`app/core/config.py`); see `.env.example`.
The important switches:

| Variable | Default | Notes |
| --- | --- | --- |
| `LLM_PROVIDER` | `auto` | `auto` picks Gemini, then Anthropic, else `offline` |
| `LLM_TIMEOUT_SECONDS` | `60` | Per-call timeout; a timeout degrades, it does not fail the report |
| `MAX_UPLOAD_MB` / `MAX_PAGES` | `15` / `100` | Enforced while streaming, not from a header |
| `CACHE_TTL_SECONDS` | `3600` | Session lifetime |
| `CACHE_MAX_BYTES_MB` | `512` | Heap budget for cached PDFs |
| `SAMPLE_WARM_ON_STARTUP` | `true` | Pre-analyse the demo leases |
| `ALLOWED_ORIGINS` | `["*"]` | Comma-separated or a JSON array; irrelevant when the API serves the UI |
| `SERVE_FRONTEND` | `true` | Mount `frontend/dist` at `/` when a build exists |
| `FRONTEND_DIST` | `frontend/dist` | Where the bundle is looked for |

---

## Tests

```bash
python -m pytest -q       # 52 tests, offline, ~15s
python -m ruff check app tests

cd frontend
npm run typecheck         # tsc --noEmit, strict
npm run build             # production bundle
```

The suite runs with `LLM_PROVIDER=offline`, so it never touches the network and never
needs a key. It covers the demo self-check, the upload rejections (wrong type, empty,
corrupt, password-protected), the error envelope, session lifecycle including `410` after
a simulated TTL lapse, annotation page counts, cache expiry and byte-budget eviction, and
the determinism of the extractor and the score.

---

## Limitations

LeaseLens is informational, not legal advice, and does not create an advocate-client
relationship. The statute references are indicative: amendments, state rules and
case-law glosses must be confirmed with a qualified advocate before a tenant acts on
anything in a report. Every response carries that disclaimer in `disclaimer`.

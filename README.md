<div align="center">

# 🔍 LeaseLens

**Automated Legal Analysis & Risk Assessment for Rental Agreements**

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/React_19-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://react.dev/)
[![Tailwind CSS v4](https://img.shields.io/badge/Tailwind_CSS_v4-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

*A privacy-first legal-tech web service that analyzes rental agreements against the **Tamil Nadu Regulation of Rights and Responsibilities of Landlords and Tenants Act, 2017 (Act 42 of 2017)** — delivering bilingual (English & Tamil) risk reports, statutory citations, counter-clauses, and coordinate-accurate PDF highlights.*

[Features](#-key-features) • [Architecture](#-core-architecture-principle) • [Quick Start](#-quick-start) • [Deployment](#-deploy-render-one-container) • [Rule Base](#-rule-base--scoring)

---

</div>

## 💡 What is LeaseLens?

LeaseLens simplifies legal contracts for everyday tenants. By parsing rental agreements, it instantly identifies non-compliant or unfair terms regarding security deposits, lock-in periods, notice timelines, and entry rights under Tamil Nadu statutory law.

### 🌟 Key Features

- **⚡ Instant PDF Analysis:** Reads, parses, and highlights documents with coordinate-accurate overlays using PyMuPDF and Tesseract OCR.
- **🛡️ Deterministic Legal Engine:** Zero AI hallucination on legal outcomes. Scoring and rule evaluation run 100% locally via Python logic.
- **🗣️ Bilingual Remediation (English & Tamil):** Provides translated explanations, counter-clause templates ready for negotiation, and draft emails to landlords.
- **🔒 Privacy by Design:** Uploaded PDFs exist only in ephemeral memory. No database retains raw document text.
- **📶 Offline Resilience:** Operates smoothly without LLM API keys using rule-based extraction fallbacks.
- **📱 Unified React App:** Single-binary deployment serving a modern React 19 + Tailwind CSS UI directly from FastAPI.

---

## 🎯 Core Architecture Principle

> **"The model extracts. The code decides."**

LeaseLens strictly separates natural language understanding from legal reasoning:

```
                          ┌───────────────────────────┐
                          │    Uploaded Rental PDF    │
                          └─────────────┬─────────────┘
                                        │
                         ┌──────────────┴──────────────┐
                         ▼                             ▼
              ┌────────────────────┐       ┌──────────────────────┐
              │  Gemini / Claude   │       │ Deterministic Python │
              │  (Entity Extractor)│       │      Extractor       │
              └──────────┬─────────┘       └──────────┬───────────┘
                         │                            │
                         └──────────────┬─────────────┘
                                        │ (Reconciled Numbers)
                                        ▼
                           ┌────────────────────────┐
                           │    Python Rule Engine  │ ◄─── rules.yaml
                           └────────────┬───────────┘
                                        │
                                        ▼
                           ┌────────────────────────┐
                           │ Verdict & Risk Score   │ (0-100 Score + Citations)
                           └────────────────────────┘
```

1. **Extraction (AI):** The LLM is restricted to returning raw entities (e.g., `deposit_months: 10`, `notice_period_days: 7`).
2. **Reconciliation:** Extracted numerical data is cross-checked against plain text using a deterministic Python heuristic. Literal text always overrides AI output.
3. **Evaluation (Rule Engine):** Every verdict, statutory citation, and severity score ($0-100$) is computed strictly via `rule_engine.py` using predefined thresholds in `rules.yaml`.

---

## 🚀 Quick Start

### 1. Run the Backend API

```bash
# Clone the repository
git clone https://github.com/your-username/leaselens.git
cd leaselens

# Setup virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template (works out of the box without external keys)
cp .env.example .env

# Start FastAPI server
uvicorn app.main:app --reload
```

Open **`http://127.0.0.1:8000/docs`** in your browser to inspect interactive OpenAPI docs.

### 2. Test via CLI (No keys required)

```bash
# Fetch pre-analyzed sample leases
curl http://127.0.0.1:8000/api/v1/sample-leases

# Download sample annotated PDF
curl -o demo.pdf http://127.0.0.1:8000/api/v1/sample-leases/sample-high-deposit/annotated-pdf

# Analyze your own lease document
curl -F "file=@lease.pdf" http://127.0.0.1:8000/api/v1/analyze
```

---

## 🖥️ Web Interface Setup

The web UI is built with **React 19**, **Vite**, and **Tailwind CSS v4** (`frontend/`).

```bash
cd frontend
npm install
npm run build                   # Compiles single bundle into frontend/dist
cd ..
uvicorn app.main:app --reload   # FastAPI serves both API and React frontend at http://127.0.0.1:8000
```

> **Development Mode:** For UI hot-reloading, run `uvicorn app.main:app --reload` on port `8000` alongside `npm run dev` in `frontend/` (port `5173`). Vite handles `/api` proxying automatically.

### UI Routes & Capabilities

| Route | View Description |
| :--- | :--- |
| `#/login` | Account management (Supabase Auth & Google OAuth support) |
| `#/app/review` | Interactive workspace: Split view of highlighted PDF & Fix-it Kit |
| `#/app/history` | Historical agreement assessments (filterable by risk level) |
| `#/app/guide` | Legal statutory reference and scoring methodology guide |
| `#/app/security` | Privacy controls, ephemeral data policy, and cookie manager |

---

## 🗺️ API Endpoint Reference

All REST routes are namespaced under `/api/v1`.

| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/analyze` | Primary endpoint: Upload lease PDF $\rightarrow$ Receive risk report & fixes |
| `GET` | `/sample-leases` | Retrieve baked-in sample agreements for instant demos |
| `GET` | `/sample-leases/{id}` | Detailed assessment payload for specific demo lease |
| `POST` | `/annotate-pdf` | Render visual coordinate highlight bounding boxes |
| `GET` | `/download-annotated/{session_id}` | Download ready-to-print highlighted PDF report |
| `GET` | `/rules` | Inspect active rule set and scoring thresholds |
| `GET` | `/rules/{rule_id}` | Retrieve individual legal rule details and statutory text |
| `GET` | `/health` | Diagnostic check (OCR engine, sample integrity, system stats) |

---

## ⚙️ Processing Pipeline

```
     PDF Bytes
         │
         ├──► pdf_parser.py ─────────► Text & Bounding Boxes (PyMuPDF / Tesseract OCR)
         ├──► clause_splitter.py ────► Structural Segmentation (Filters boilerplate)
         ├──► ai_classifier.py ──────► Entity & Category Extraction (LLM / Offline Fallback)
         ├──► heuristic_extractor.py ─► Deterministic Numerical Reconciler
         ├──► rule_engine.py ────────► Benchmark Engine (rules.yaml)
         ├──► fix_generator.py ──────► Bilingual Counter-Clauses & Drafts
         └──► pdf_annotator.py ──────► Red / Amber / Green Highlight Renderer
```

---

## 📊 Rule Base & Risk Scoring

Rules are maintained declaratively in `app/rules/rules.yaml`. No hardcoded logical thresholds exist inside executable Python code.

```yaml
- id: DEP-001
  category: deposit
  title: "Security deposit exceeds three months' rent"
  severity: high
  field: deposit_months
  operator: greater_than
  value: 3
  explanation: "Under Section 11(1), landlords cannot demand more than three months rent as advance."
  tamil: "பிரிவு 11(1) இன் படி, முன்பணமாக 3 மாத வாடகையை விட அதிகமாகக் கோர முடியாது."
  statute:
    section: "11(1)"
    heading: "Security deposit"
```

### Risk Bands

Score evaluation utilizes severity-led weighting rather than naive averaging to ensure high-risk violations are never masked by compliant boilerplate clauses.

| Score Range | Risk Band | Color Code |
| :---: | :---: | :---: |
| **0 – 19** | **Low** | 🟢 Green |
| **20 – 39** | **Moderate** | 🟡 Yellow |
| **40 – 59** | **Elevated** | 🟠 Orange |
| **60 – 79** | **High** | 🔴 Red |
| **80 – 100** | **Critical** | 🚨 Dark Red |

---

## 🔒 Ephemeral Privacy Architecture

> [!NOTE]
> LeaseLens is designed around zero persistence for confidential legal documents.

- **In-Memory Operations:** Uploaded PDF buffers exist solely in RAM during execution and are never written to disk.
- **Strict Eviction:** In-memory sessions automatically expire after `CACHE_TTL_SECONDS` (Default: 60 minutes) using LRU cache bounds.
- **Derived Database Storage:** When using Supabase history storage, **raw clause text is stripped on the client**. Databases store only anonymized score indices, statutory rule IDs, and counter-clause drafts.
- **Manual Deletion:** Invoking `DELETE /api/v1/sessions/{id}` immediately purges all associated text and PDF objects from memory.

---

## 🐳 Deploy (Render / Single Container)

Deploy seamlessly using Docker. The provided `Dockerfile` builds both UI bundle and backend into a single runnable container.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com)

### Environment Variables

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `LLM_PROVIDER` | `auto` | Primary model option (`auto`, `gemini`, `anthropic`, `offline`) |
| `LLM_TIMEOUT_SECONDS` | `60` | Maximum request duration per LLM call |
| `MAX_UPLOAD_MB` | `15` | Maximum supported upload size |
| `CACHE_TTL_SECONDS` | `3600` | Session lifetime threshold (seconds) |
| `SAMPLE_WARM_ON_STARTUP` | `true` | Pre-analyzes standard sample leases on boot |
| `VITE_SUPABASE_URL` | - | Optional Supabase project endpoint |
| `VITE_SUPABASE_ANON_KEY` | - | Optional Supabase public client key |

### Local Docker Build

```bash
docker build -t leaselens \
  --build-arg VITE_SUPABASE_URL=https://<your-project>.supabase.co \
  --build-arg VITE_SUPABASE_ANON_KEY=your-anon-key .

docker run -p 8000:8000 leaselens
```

---

## 🧪 Testing

Run unit tests, extraction benchmarks, and validation suites fully offline:

```bash
# Run pytest suite (~15s runtime, no API keys needed)
python -m pytest -q

# Run code linter
python -m ruff check app tests

# Run frontend typechecking & compilation check
cd frontend && npm run typecheck && npm run build
```

---

## ⚖️ Disclaimer

> [!IMPORTANT]
> **LeaseLens provides informational analysis only and does not constitute formal legal advice.** Statutory references and rule interpretations are indicative. Always consult a qualified legal advocate registered under the Bar Council before executing legal agreements or initiating formal disputes.

---

<div align="center">

Crafted for tenant protection under Tamil Nadu Rent Control Regulations.

</div>
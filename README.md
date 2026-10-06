# Trace — AI Job Tracker

Trace reads your resume with Gemini, watches the career pages you care about,
analyses every new posting, and ranks them against your profile. You track the
ones you like through a Kanban pipeline with notes.

```
User profile (AI) ─┐
                   ├─> match score ─> Dashboard ─> Applications (Kanban + notes)
Job analysis (AI) ─┘
        ▲
        └── hourly worker: scrape career pages → analyse new jobs (budgeted)
```

**Stack:** React 19 + Vite · FastAPI · PostgreSQL (Supabase) · Supabase Auth &
Storage · Google Gemini · GitHub Actions (hourly worker).


---

## Setup

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then fill it in
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env.local                             # Supabase URL + anon key
npm run dev
```
Set `VITE_API_URL` for deployed builds (defaults to `http://localhost:8000`).
Add your deployed frontend origin to the backend's `CORS_ORIGINS`.

### Tests
```bash
cd backend
pip install -r requirements-dev.txt
pytest
```
The suite needs no network or API key (it uses in-memory SQLite and a fake
Gemini client) and never touches your real database.

---

## The hourly worker

`.github/workflows/job-monitor.yml` runs `python -m worker.monitor` every hour.

```bash
python -m worker.monitor                  # scrape, then analyse
python -m worker.monitor --no-ai          # scrape only
python -m worker.monitor --no-scrape      # analyse the existing backlog only
python -m worker.monitor --max-analyses 5 # override the per-run budget
python -m worker.monitor --retry-failed   # re-queue jobs whose analysis failed
```

Required GitHub **secrets**: `DATABASE_URL`, `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, `GOOGLE_API_KEY`.
Optional **variables** (Settings → Secrets and variables → Actions → Variables):
`GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL`, `GEMINI_MIN_INTERVAL_SECONDS`,
`MAX_ANALYSES_PER_RUN`.

### Gemini tuning (all optional)

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_MODEL` | `gemini-3.8-flash` | Primary model |
| `GEMINI_FALLBACK_MODEL` | `gemini-3.5-flash` | Used when the primary is overloaded/limited. Separate quota bucket. `none` disables |
| `GEMINI_THINKING_LEVEL` | `low` | Extraction doesn't need the default "medium". `none` sends no config |
| `GEMINI_MIN_INTERVAL_SECONDS` | `6` | Gap between background calls (6 ≈ 10 req/min, free-tier safe) |
| `MAX_ANALYSES_PER_RUN` | `20` | Hard cap on Gemini calls per hourly run; the rest wait for the next run |
| `GEMINI_MAX_RETRIES` | `3` | Retries with backoff per call |
| `MAX_DETAIL_FETCHES_PER_SOURCE` | `40` | Extra page fetches for new jobs on Workday/generic sources |

Paying for Gemini? Set `GEMINI_MIN_INTERVAL_SECONDS=0.5` and raise
`MAX_ANALYSES_PER_RUN` to drain the backlog faster.

### Which jobs are kept
Only jobs whose **title matches your target roles** (Resume page → Target roles) are saved and shown. Add or remove roles there; the change applies on the next hourly run. If you set no roles, everything is kept. Matching rules: see `backend/app/services/role_filter.py` and FIXES.md.

### Supported career pages
Greenhouse and Lever (richest data), Workday (via its JSON API — unofficial,
verify against your target companies), and a generic fallback that finds
engineering-style links on any careers page.

---

## Project layout
```
backend/app/ai/        gemini.py (gateway) · errors.py · matcher.py · analyzers
backend/app/api/       FastAPI routes
backend/app/scrapers/  greenhouse · lever · workday · generic
backend/app/services/  job / application / user services
backend/worker/        monitor.py (hourly job)
backend/tests/         pytest suite
frontend/src/styles/   tokens.css (theme) · base · components · pages
frontend/src/components, pages, services, utils
```

## Theming
The glassmorphism look is driven entirely by CSS variables in
`frontend/src/styles/tokens.css` (blur strength, tint, borders, shadows, orb
colours, light + dark palettes). Retune the whole app by editing that one file.
The transparent logo ships in `frontend/public/` with a light-wordmark variant
used automatically in dark mode.

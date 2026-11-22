# REVERSEFLOW AI

**Agentic intelligence for fashion e-commerce returns and reverse supply chains.**
SAP Hackfest 2026 Grand Finale · Theme 1: Resilient Supply Chains · Team BugFixers, SIIB Pune

> Predict the disruption. Understand its root cause. Coordinate every stakeholder. Recover maximum inventory value.

Scenario: the post-Navratri return wave in festive ethnicwear. The demo stands on **20 Oct 2026 (Vijayadashami)**; the return peak is forecast 5–6 days later.

**All records are synthetic and all scenario figures are illustrative.** Nothing in this repository is real marketplace data, and no SAP system is connected (see [SAP integration](#sap-integration)).

---

## What is in the box

| Area | What actually runs |
|---|---|
| **Six agents + orchestrator** | Return Prediction, Product/Vendor/Customer Intelligence, Prevention & Policy, Reverse Logistics, Inventory Recovery, Compliance & Governance. A dependency-ordered orchestrator selects agents per event, passes shared state, records agent-to-agent messages, detects cross-agent conflicts, retries failures (3 attempts) and persists every run. |
| **Forecasting** | 7-day-lead gradient boosting (Poisson loss) with P10/P90 quantile bands vs a seasonal-naive baseline. Metrics (MAE, RMSE, WAPE, bias, interval coverage, surge lead time) are computed on two held-out periods. |
| **NLP** | TF-IDF (word + char n-grams) + logistic regression for return reasons (trained on inspection-verified labels) and sentiment (trained on star ratings). Held-out accuracy is reported, not assumed. |
| **Root-cause intelligence** | Two-proportion z-tests find vendor/SKU reason concentrations; an interactive graph links customer → return → SKU → size → vendor → defect → intervention. |
| **Return integrity** | Hard-evidence checks (tag, serial, weight) + IsolationForest behavioural score with per-component contributions. The only automated consequence is a *request for physical inspection*. |
| **Reverse logistics** | Capacity-gap analysis and a linear programme (SciPy HiGHS) that allocates cluster volume to facilities by cost and capacity. |
| **Resale Window Intelligence** | Transparent value-over-time model (grade, demand index from order history, obsolescence, refurbishment and storage costs) that sequences the inspection queue by value at risk instead of arrival order. |
| **Return Wave Digital Twin** | Daily cohort simulation of pickup → line-haul → inspection → recovery with Poisson arrivals, Monte Carlo P10/P90, and four scenarios (Baseline, A extra pickup, B re-allocation, C combined + value priority). |
| **Human-in-the-loop** | Pending / approved / rejected / escalated with role checks, approval limits, mandatory reasons and a full decision log + audit trail. Approved actions change shared state (QC flags, size charts, routing, capacity). |
| **Three experiences** | Customer portal, Partner Operations portal (vendor, 3PL, warehouse; scoped permissions) and the Marketplace Control Tower. |

## Architecture

```
frontend/  Next.js 15 · React 19 · TypeScript · Tailwind · Recharts · React Flow · Framer Motion
   │  REST (X-User-Id persona header → roles & data scope)
backend/   FastAPI · Pydantic · SQLAlchemy · pandas / NumPy · scikit-learn · SciPy
   app/
     agents/          six agents (one file each) + shared AgentContext / AgentResult
     orchestrator.py  event plans, dependency order, retries, conflicts, persistence
     ml/              forecasting.py · nlp.py · anomaly.py · resale.py
     simulation/      twin.py (Digital Twin)
     services/        intelligence.py (findings, graph) · actions.py (approvals & effects) · settings.py
     routers/         core · forecast · intel · ops · portals · analytics
     seed/            generate.py (deterministic synthetic data) · text_bank.py
     llm.py           LLM abstraction: offline template (default) · OpenAI-compatible · SAP Gen AI Hub adapter stub
   tests/             end-to-end API tests
   data/              SQLite database (created on first start)
```

The schema uses only portable SQLAlchemy types, so `DATABASE_URL` can point at PostgreSQL (or SAP HANA Cloud via `sqlalchemy-hana`) without code changes.

## Setup

Requirements: Python 3.11+ and Node 20+.

```bash
# backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # optional; defaults work

# frontend
cd ../frontend
npm install
cp .env.example .env.local    # NEXT_PUBLIC_API_URL=http://localhost:8040
```

## Run

```bash
./start.sh
```

or in two terminals:

```bash
cd backend && .venv/bin/uvicorn app.main:app --port 8040
```

```bash
cd frontend && npm run dev
```

Open http://localhost:3000. API docs: http://localhost:8040/docs.

**First start** generates the synthetic dataset, trains the NLP and anomaly models and runs the first six-agent cycle (about 30–40 seconds). Later starts reuse the database.

### Database & synthetic data

* SQLite file: `backend/data/reverseflow.db`
* Regenerate from scratch (deterministic seed `20261020`):

```bash
cd backend && .venv/bin/python -m app.seed.generate
```

  or use **Settings → Reset demo to initial state** in the app (Operations Manager only).
* Dataset: ~112k orders, ~16.6k returns, ~9.8k reviews, 62 SKUs, 12 vendors, 8 PIN clusters, 9 facilities, 4 3PL partners, Jun 2024 to 20 Oct 2026, including the 2024 and 2025 Navratri seasons used for backtesting.
* Planted (and discoverable) patterns: Rangrez Textiles (V03) stitching defects, Mehrang Ethnic (V07) sizes running small, colour mismatch on Jaipur Bandhej House listings, elevated XS/XXL fit returns, region-dependent post-festival waves, load-dependent pickup and inspection delays.
* **Two scales.** Transaction records are a sample. Network-scale figures (capacities, forecast volumes, the Twin) multiply sample rates by an illustrative factor per cluster, shown in Settings.

### Environment variables

`backend/.env.example`

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///backend/data/reverseflow.db` | Any SQLAlchemy URL |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Allowed frontend origins |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | unset | Optional OpenAI-compatible endpoint for explanation wording. Not required. |

`frontend/.env.example`: `NEXT_PUBLIC_API_URL` (default `http://localhost:8040`).

No paid API is needed. With no LLM configured, explanations come from deterministic evidence templates and are labelled as such.

## Deployment (GitHub Pages + Render)

* **Backend** runs on Render's free tier from `render.yaml` (Blueprint). Free services sleep after about 15 minutes idle; the first request then takes about a minute, and the demo data is rebuilt from the seed on each start.
* **Frontend** is built as a static site by `.github/workflows/pages.yml` on every push to `main` and published to GitHub Pages at `https://trexiznub.github.io/reverseflow-AI/`. The backend address defaults to `https://reverseflow-api.onrender.com`; set a repository variable `API_URL` to override it.
* Local development is unchanged: the static export only turns on when the workflow sets `PAGES_BASE_PATH`.

## Tests

```bash
cd backend && .venv/bin/pytest -q
```

The suite builds its own database (`tests/test_reverseflow.db`) and checks: forecast metrics computed and ML beating baseline in the surge window, all six agents completing with messages and conflicts, the planted vendor patterns being found, exactly 14 integrity flags with no automatic rejection, Twin recalculation, RBAC scoping, the full customer → 3PL → governance → warehouse flow, approval persistence and side effects, KPIs and SAC exports, and retry after an injected agent fault.

```bash
cd frontend && npx tsc --noEmit && npm run build
```

## Personas

Switch persona from the top-right menu. Each has its own permissions and data scope.

| Persona | Role | Sees |
|---|---|---|
| Rahul Mehta | Operations Manager (₹25 L approval limit) | Everything; can decide any item |
| Kavya Iyer | Vendor-Quality Manager | Vendor QC, size-chart and listing approvals |
| Suresh Patil | Warehouse Manager | Warehouse spend, refurbishment, recovery |
| Neha Kapoor | Dispute Review | Return-integrity cases |
| Imran Shaikh / Hetal Shah / Dhruv Ahir | Vendors (V03 / V07 / V02) | Own SKUs, complaints, QC actions only |
| Vikram Joshi / Farhan Qureshi | 3PL partners | Own clusters, pickups and SLA |
| Sneha Kulkarni / Arjun Nair | Inspection teams | Own facility queue |
| Priya Sharma / Aditi Joshi / Meera Rathore | Customers | Own orders and returns only |

## Demonstration script (about 10 minutes)

Start from a clean state (Settings → Reset the demo) as **Rahul Mehta**. The top bar has Today, Decisions, Forecast, Product issues, Planner and Resale; Reports, How it works, the Customer and Partner apps and Settings are under **More**. The **Details** switch in the top bar shows the technical layer (model accuracy, raw agent data, test statistics) on every page; with it off, those sections are folded away.

1. **Today.** The headline, the four big figures and the "Start here" list say what is happening and what needs a decision. The map shows where returns will land; "Can we cope?" shows each city's van shortfall. *Behind the numbers* holds the T-7 … T-1 agent timeline, alerts and the feedback loop.
2. **Customer app.** Switch to **Priya Sharma** → *Bandhani lehenga* → *Return or exchange* → Quality → "Stitching opened at the waistband during garba" → Refund → pickup slot (slots show *limited* because the Pune forecast exceeds van capacity) → Confirm. A `return_created` agent run starts.
3. **Partner app.** Switch to **Vikram Joshi** (delivery partner). The new return is at the top of the list, marked *new*. *Complete pickup* and change the serial number; the return is flagged for a closer look at the warehouse. The refund is not held up.
4. **How it works.** Back as Rahul. The six agents, who passed what to whom, where agents disagreed and how it was settled, and the decisions sent to people.
5. **Product issues.** Pick Rangrez Textiles and click a seller, product, size or return to trace the problem; type a customer comment into *Try it*.
6. **Planner.** Compare *Do nothing*, *More pickup vans*, *Use other warehouses* and *Both, best items first*; move *How big the wave is* or Pune's vans and watch the suggestion update. *Use the latest forecast* loads the forecast's busiest days.
7. **Approve.** Decisions → *Send 21% of Pune returns to Nashik* → pick or type a reason → Approve. The routing change applies to new returns, the warehouse view and the Planner. Switch to **Kavya Iyer** to approve pausing Rangrez shipments; the seller's view in the Partner app then shows the pause.
8. **History.** Decisions → *History* lists every portal action, agent run, decision and setting change.

The flow is repeatable: reset and run it again.

## Design

Dark, monochrome interface: Archivo (display and body) with Geist Mono labels, hairline dividers, very large headline figures, and colour used only for status (red, amber, green). Pages lead with a plain-language headline and the few numbers that matter; technical material sits behind "+" folds or the **Details** switch.

## SAP integration

| Capability | Status in this prototype | SAP pathway |
|---|---|---|
| Operational database | **Implemented** (SQLAlchemy, portable schema, SQLite locally) | SAP HANA Cloud via `sqlalchemy-hana` |
| Analytics exports | **Implemented** (`/api/integrations/sac/{returns_fact,forecast,vendor_kpis,recovery_queue}.csv`) | SAP Analytics Cloud datasets / HANA calculation views |
| LLM explanations | **Implemented** offline template; optional OpenAI-compatible endpoint | SAP Generative AI Hub: adapter boundary only, **not connected** |
| Agent orchestration & APIs | **Implemented locally** (FastAPI) | SAP BTP (Cloud Foundry / Kyma), XSUAA for roles |
| Inventory & supply planning | Proposed | SAP IBP |
| Transportation planning | Proposed | SAP Transportation Management |
| Supplier collaboration | Proposed | SAP Ariba / Business Network |

## Design notes and honest limits

* The orchestrator is a LangGraph-style dependency graph implemented without the dependency, so the demo runs offline. Agents expose explicit inputs, outputs and dependencies and can be ported to LangGraph nodes.
* TF-IDF is used instead of Sentence-Transformers to avoid model downloads; the vectoriser is a drop-in swap.
* Daily cluster counts in the sample are small, so daily WAPE includes irreducible Poisson noise; weekly accuracy is shown alongside.
* The anomaly model is unsupervised; no accuracy is claimed. Anomalies only ever trigger an inspection request.
* Resale values come from configurable assumptions and the synthetic order history, not from market prices.
* Business dates use the scenario clock (20 Oct 2026); audit timestamps use real wall-clock time.
* Demo identity is a request header. Production would use SAP BTP XSUAA / IAS tokens with the same role model.

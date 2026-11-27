# REVERSEFLOW AI

**Agentic intelligence for fashion e-commerce returns and reverse supply chains.**
SAP Hackfest 2026 Grand Finale · Theme 1: Resilient Supply Chains · Team BugFixers, SIIB Pune

> Predict the disruption. Understand its root cause. Coordinate every stakeholder. Recover maximum inventory value.

Scenario: the post-Navratri return wave in festive ethnicwear. The demo stands on **20 Oct 2026 (Vijayadashami)**; the return peak is forecast 5–6 days later.

**All records are synthetic and all scenario figures are illustrative.** Nothing in this repository is real marketplace data. The SAP connectors are real code, but in the public demo no SAP tenant is connected, and the app says so (see [SAP integration](#sap-integration)).

The **Why it matters** page (`/case`) walks through the problem statement, objective, definitions, a worked example from the live demo, the market economics (published figures with sources, plus an adjustable estimate) and the use of SAP. The **SAP** page (`/sap`) shows each SAP connection and the messages prepared for SAP IBP, TM and Ariba.

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
| **Return Wave Digital Twin** | Daily cohort simulation of pickup → line-haul → inspection → recovery with Poisson arrivals and Monte Carlo P10/P90. It runs in the background to price the business case (doing nothing vs extra vans, re-routing and value-first inspection); the separate Planner page has been removed. |
| **Human-in-the-loop** | Pending / approved / rejected / escalated with role checks, approval limits, mandatory reasons and a full decision log + audit trail. Approved actions change shared state (QC flags, size charts, routing, capacity). |
| **Three experiences** | Customer portal, Partner Operations portal (vendor, 3PL, warehouse; scoped permissions) and the Marketplace Control Tower. |

## Architecture

```
frontend/  Next.js 15 · React 19 · TypeScript · Tailwind · Recharts · React Flow · Framer Motion
   │  REST (/api). Demo: X-User-Id persona header. Production: SAP XSUAA token via the app router.
sap-business-service/  SAP CAP (Node.js): OData V4 over the same tables, SAP roles, decisions forwarded to the backend
backend/   FastAPI · Pydantic · SQLAlchemy · pandas / NumPy · scikit-learn · SciPy (AI engine)
   app/
     agents/          six agents (one file each) + shared AgentContext / AgentResult
     orchestrator.py  event plans, dependency order, retries, conflicts, persistence
     ml/              forecasting.py · nlp.py · anomaly.py · resale.py
     simulation/      twin.py (Digital Twin engine, used by the business case)
     services/        intelligence.py (findings, graph) · actions.py (approvals & effects) · settings.py
     routers/         core · forecast · intel · ops · portals · analytics
     seed/            generate.py (deterministic synthetic data) · text_bank.py
     llm.py           LLM abstraction: offline template (default) · OpenAI-compatible · SAP Generative AI Hub (AI Core)
     sap/             BTP bindings, Destination service, outbox (IBP / TM / Ariba), S/4HANA adapters,
                      AI Core reader, connection tests (health.py)
     tools/           migrate_to_hana.py (copy SQLite data into SAP HANA Cloud)
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

**First start** restores the prepared demo from `backend/snapshot/` in a few seconds (or, without it, generates the dataset, trains the models and runs the first agent cycle in about 30–40 seconds). Later starts reuse the database.

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
| `AICORE_AUTH_URL`, `AICORE_CLIENT_ID`, `AICORE_CLIENT_SECRET`, `AICORE_BASE_URL`, `AICORE_DEPLOYMENT_ID` | unset | SAP Generative AI Hub (from an AI Core service key). On Cloud Foundry the bound `aicore` service supplies all but the deployment ID. |
| `SAP_IBP_URL`, `SAP_TM_URL`, `SAP_ARIBA_URL` (+ `_TOKEN_URL`, `_CLIENT_ID`, `_CLIENT_SECRET` or `_USER`, `_PASSWORD`) | unset | Where messages for each SAP system are posted, usually an SAP Integration Suite flow. Alternatively bind the Destination service and create destinations `reverseflow-ibp`, `reverseflow-tm`, `reverseflow-ariba`. |
| `SAP_IBP_PLANNING_AREA` | `RFRETURNS` | IBP planning area named in forecast messages |
| `REVERSEFLOW_SAP_SANDBOX` | unset | `1` turns on a local test receiver at `/api/sap/sandbox/{system}`, to try sending without an SAP tenant |
| `REVERSEFLOW_AUTH` + `XSUAA_URL`, `XSUAA_XSAPPNAME` | unset | XSUAA sign-in outside Cloud Foundry. On Cloud Foundry a bound `xsuaa` service switches it on by itself. |

SAP S/4HANA, CAP, Analytics Cloud, AI Launchpad, Work Zone and production sign-in settings are listed in [docs/SAP_INTEGRATION.md](docs/SAP_INTEGRATION.md#environment-variables).

`frontend/.env.example`: `NEXT_PUBLIC_API_URL` (default `http://localhost:8040`).

No paid API is needed. With no LLM configured, explanations come from deterministic evidence templates and are labelled as such.

## Run in SAP Business Application Studio

Use a **Full Stack Cloud Application** dev space. In its terminal:

```bash
git clone https://github.com/trexiznub/reverseflow-AI.git && cd reverseflow-AI
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8040            # terminal 1
```

```bash
cd ~/projects/reverseflow-AI/frontend                  # terminal 2
printf 'NEXT_PUBLIC_API_URL=\nBACKEND_URL=http://localhost:8040\n' > .env.local
npm install && npx next dev -p 4000
```

Port 3000 is already taken inside BAS, so the website runs on **4000**; open it when BAS offers it (or F1 → *Ports: Preview*). The browser cannot reach the dev space's `localhost:8040`, so `BACKEND_URL` makes the Next.js server forward `/api` to the backend and the page only talks to its own address.

## Deploy to SAP BTP (Cloud Foundry)

`mta.yaml` deploys the whole app to SAP BTP from BAS:

```bash
npm install -g mbt        # once, if the dev space doesn't have it
mbt build
cf login -a https://api.cf.eu10.hana.ondemand.com    # or F1 → "CF: Login to Cloud Foundry"
cf deploy mta_archives/reverseflow_1.0.0.mtar
```

It creates the backend (`reverseflow-srv`), the website (`reverseflow-web`), the SAP application router (`reverseflow`, the address you open) and two services: **XSUAA** for SAP sign-in and roles (`xs-security.json`) and the **Destination** service for IBP, TM and Ariba. After deploying, assign yourself the role collection `ReverseFlow_OpsManager` in the BTP cockpit (Security → Users). SAP HANA Cloud and SAP AI Core are listed in `mta.yaml` with `active: false`; switch them on once those services exist in your subaccount.

## Deployment (GitHub Pages + Render)

* **Backend** runs on Render's free tier (settings in `render.yaml`). Free services sleep after about 15 minutes idle; the next visit wakes them up, which takes about a minute.
* **Fast start.** `backend/snapshot/` holds a prepared copy of the demo (compressed database + trained models, about 8 MB). A fresh server, and **Settings → Reset the demo**, restore it in seconds instead of regenerating data and retraining models. Rebuild it after changing the generator, agents or wording: `cd backend && .venv/bin/python -m app.seed.snapshot`. Set `REVERSEFLOW_NO_SNAPSHOT=1` to always regenerate.
* **Frontend** is built as a static site by `.github/workflows/pages.yml` on every push to `main` and published to GitHub Pages at `https://trexiznub.github.io/reverseflow-AI/`. The backend address defaults to `https://reverseflow-ai.onrender.com`; set a repository variable `API_URL` to override it.
* Local development is unchanged: the static export only turns on when the workflow sets `PAGES_BASE_PATH`.

## Tests

```bash
cd backend && .venv/bin/pytest -q
```

The suite builds its own database (`tests/test_reverseflow.db`) and checks: forecast metrics computed and ML beating baseline in the surge window, all six agents completing with messages and conflicts, the planted vendor patterns being found, exactly 14 integrity flags with no automatic rejection, the simulation engine, Planner removal, RBAC scoping, the full customer → 3PL → governance → warehouse flow, approval persistence and side effects, KPIs and SAC exports, retry after an injected agent fault, SAP outbox messages from approvals and forecasts, delivery when a system is connected, XSUAA token sign-in and the Admin scope, production refusal of the demo header, the S/4HANA adapters (sandbox and live HTTP path), honest connection tests, grounded AI summaries, SAP Analytics Cloud datasets, and SAP Generative AI Hub explanations with fallback. The CAP service has its own checks: `cd sap-business-service && npm test` (with both servers running).

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

Start from a clean state (Settings → Reset the demo) as **Rahul Mehta**. The top bar has Today, Decisions, Forecast, Product issues and Resale; Reports, How it works, the Customer and Partner apps and Settings are under **More**. The **Details** switch in the top bar shows the technical layer (model accuracy, raw agent data, test statistics) on every page; with it off, those sections are folded away.

1. **Today.** The headline, the four big figures and the "Start here" list say what is happening and what needs a decision. The map shows where returns will land; "Can we cope?" shows each city's van shortfall. *Behind the numbers* holds the T-7 … T-1 agent timeline, alerts and the feedback loop.
2. **Customer app.** Switch to **Priya Sharma** → *Bandhani lehenga* → *Return or exchange* → Quality → "Stitching opened at the waistband during garba" → Refund → pickup slot (slots show *limited* because the Pune forecast exceeds van capacity) → Confirm. A `return_created` agent run starts.
3. **Partner app.** Switch to **Vikram Joshi** (delivery partner). The new return is at the top of the list, marked *new*. *Complete pickup* and change the serial number; the return is flagged for a closer look at the warehouse. The refund is not held up.
4. **How it works.** Back as Rahul. The six agents, who passed what to whom, where agents disagreed and how it was settled, and the decisions sent to people.
5. **Product issues.** Pick Rangrez Textiles and click a seller, product, size or return to trace the problem; type a customer comment into *Try it*.
6. **Approve.** Decisions → *Send 21% of Pune returns to Nashik* → pick or type a reason → Approve. The routing change applies to new returns and the warehouse view, and a transport message for SAP TM appears on the SAP page. Switch to **Kavya Iyer** to approve pausing Rangrez shipments; the seller's view in the Partner app then shows the pause.
7. **SAP.** More → SAP → *Test connections*. Only services a test actually reached show as connected; S/4HANA data is shown from the labelled sandbox until a system is connected.
8. **History.** Decisions → *History* lists every portal action, agent run, decision and setting change.

The flow is repeatable: reset and run it again.

## Design

Dark, monochrome interface: Archivo (display and body) with Geist Mono labels, hairline dividers, very large headline figures, and colour used only for status (red, amber, green). Pages lead with a plain-language headline and the few numbers that matter; technical material sits behind "+" folds or the **Details** switch.

## SAP integration

Full details, environment variables, deployment and Work Zone steps: **[docs/SAP_INTEGRATION.md](docs/SAP_INTEGRATION.md)**.

Every connector is real code that switches on when its SAP service is bound (Cloud Foundry `VCAP_SERVICES`) or configured with environment variables. The **SAP** page shows each one as *Connected* (only after a test reached it), *Configured, not tested*, *Not configured*, *Missing entitlement* or *Connection failed*. In the public demo nothing is connected; S/4HANA data is served from a sandbox built from the synthetic data and labelled as such.

How a decision reaches SAP: an approval on the **Decisions** page (or an auto-approved action within the spending limit) writes a message to the outbox (`app/sap/outbox.py`). If that system is connected the message is posted at once; otherwise it waits, and the Operations Manager can resend it from the SAP page. The message formats are modelled on the SAP APIs named in the guide; the exact field mapping is meant to live in an Integration Suite flow and must be confirmed against a real tenant.

## Design notes and honest limits

* The orchestrator is a LangGraph-style dependency graph implemented without the dependency, so the demo runs offline. Agents expose explicit inputs, outputs and dependencies and can be ported to LangGraph nodes.
* TF-IDF is used instead of Sentence-Transformers to avoid model downloads; the vectoriser is a drop-in swap.
* Daily cluster counts in the sample are small, so daily WAPE includes irreducible Poisson noise; weekly accuracy is shown alongside.
* The anomaly model is unsupervised; no accuracy is claimed. Anomalies only ever trigger an inspection request.
* Resale values come from configurable assumptions and the synthetic order history, not from market prices.
* Business dates use the scenario clock (20 Oct 2026); audit timestamps use real wall-clock time.
* Demo identity is a request header (the person switcher). With XSUAA bound, identity comes from the SAP token and the header is ignored (an Admin may switch persona only with `REVERSEFLOW_DEMO_SWITCH=1`). On Cloud Foundry or with `REVERSEFLOW_ENV=production`, the header is refused outright.
* The SAP connectors have been tested against stand-in receivers, not a live SAP IBP, TM, Ariba, S/4HANA, HANA Cloud, AI Core or Analytics Cloud tenant. See `docs/SAP_INTEGRATION.md` for what was tested and what each service needs.

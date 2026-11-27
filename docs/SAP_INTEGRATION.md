# ReverseFlow on SAP: integration guide

What is built, what has been tested, and what each SAP service needs before it can be switched on. Nothing in the app is shown as connected unless a test in the running app has reached it.

## 1. Architecture

```
 SAP Build Work Zone tile ──► SAP application router (XSUAA sign-in)
                                 │  /api/*    ──► backend   FastAPI: six agents, orchestrator, forecasting, NLP,
                                 │                           anomaly detection, Digital Twin engine, resale, LLM layer
                                 │  /odata/*  ──► CAP       business service (Node.js, OData V4): orders, returns,
                                 │                           sellers, products, stock, logistics, corrective actions,
                                 │                           approvals, audit log; SAP roles and seller-level filters
                                 │  /*        ──► website   Next.js (unchanged UI)
                                 ▼
 SAP HANA Cloud  ◄── one schema, shared by the backend (SQLAlchemy) and CAP (runtime views, no copied data)
 SAP AI Core / Generative AI Hub ◄── backend: explanation wording; AI API for lifecycle overview
 SAP S/4HANA ◄── backend: read-only OData adapters (sandbox with synthetic data when not connected)
 SAP IBP / TM / Ariba ◄── backend outbox, through the Destination service or Integration Suite
 SAP Analytics Cloud ◄── live connection to HANA Cloud, or CSV datasets from /api/integrations/sac
```

Responsibilities are split so no rule is written twice:

* **CAP** owns data access for SAP clients, OData, SAP roles and seller-level restrictions. It reads the backend's tables through runtime views (`cds.features.runtime_views`), so it creates no tables or views of its own.
* **FastAPI** owns everything that needs the AI engine or the approval rules. CAP's `approve`, `reject` and `escalate` actions and `vendorPerformance()` call the backend as the signed-in user.
* **Service-to-service security:** on BTP the app router forwards the user's XSUAA token to CAP, and CAP forwards it to the backend, which checks it against the same XSUAA instance. Locally CAP's mocked users carry a ReverseFlow user id, which the backend accepts only outside production.

## 2. Files

**Created**

| File | Purpose |
|---|---|
| `sap-business-service/` (`package.json`, `db/schema.cds`, `srv/business-service.cds`, `srv/business-service.js`, `server.js`, `test/smoke.test.js`) | CAP business service |
| `backend/app/sap/s4hana.py` | S/4HANA OData adapters and the labelled sandbox |
| `backend/app/sap/aicore.py` | SAP AI Core AI API reader (scenarios, configurations, deployments, executions) |
| `backend/app/sap/health.py` | Real connection tests and the five states |
| `backend/app/tools/migrate_to_hana.py` | Copies SQLite data into HANA Cloud and verifies row counts |
| `frontend/components/india-geo.ts` | India and state boundaries (DataMeet, CC BY 4.0, Survey of India boundary), simplified |
| `docs/SAP_INTEGRATION.md` | This guide |

**Modified:** `backend/app/rbac.py` (production sign-in, Admin scope), `routers/sap.py` (status, tests, S/4HANA, AI Core), `routers/core.py`, `routers/case.py`, `routers/ops.py`, `routers/intel.py` (grounded AI summaries), `routers/analytics.py` (SAC datasets), `sap/destinations.py` (API key sign-in), `llm.py`, `tests/test_api.py`, `frontend/app/sap/page.tsx`, `app/page.tsx`, `app/case/page.tsx`, `app/analytics/page.tsx`, `app/settings/page.tsx`, `components/Shell.tsx`, `components/IndiaMap.tsx`, `mta.yaml`, `xs-security.json`, `approuter/xs-app.json`, `README.md`, `.gitignore`.

**Removed:** the Planner (`frontend/app/twin/page.tsx`, its menu entry and links, and the `/api/twin/defaults` and `/api/twin/simulate` endpoints). The simulation engine `backend/app/simulation/twin.py` stays, because the business case page uses it. The Reverse Logistics Agent, pickup capacity forecasting and the routing optimiser are unchanged.

## 3. SAP integrations implemented

| Service | What is implemented |
|---|---|
| SAP BTP, Cloud Foundry | `mta.yaml`: backend, CAP, website, app router, XSUAA, Destination; HANA and AI Core ready to switch on |
| XSUAA | Token check (signing keys), scopes → roles, seller/carrier/warehouse attribute, new Admin role collection |
| Destination service | Lookup of `reverseflow-s4/-ibp/-tm/-ariba`, including on-premise headers |
| CAP | OData V4 service, role and seller restrictions, decisions and seller scores through the backend, `/health` |
| SAP HANA Cloud | Dialect and binding support (existing), migration tool, CAP `hana` profile |
| Generative AI Hub | Provider in the LLM layer (existing); new grounded summaries `/api/ai/summary/return_comments` and `/compliance_summary` |
| SAP AI Core | `/api/sap/aicore` lists scenarios, configurations, deployments, executions; deployment status test |
| SAP AI Launchpad | Link and guidance only: it is SAP's UI for the same AI Core, with no API to call |
| SAP S/4HANA | Read adapters for `API_SALES_ORDER_SRV`, `API_CUSTOMER_RETURN_SRV`, `API_PRODUCT_SRV`, `API_BUSINESS_PARTNER` (`A_Supplier`), `API_MATERIAL_STOCK_SRV`, `API_OUTBOUND_DELIVERY_SRV;v=0002` |
| SAP IBP / TM / Ariba | Outbox (existing); status is now based on real send results |
| SAP Analytics Cloud | Seven datasets for four stories; connection test with the data import API when an OAuth client is given |
| SAP Build Work Zone | URL app tile; approuter URL once deployed |

## 4. Tested here

* Backend: 34 automated tests pass (`cd backend && .venv/bin/pytest -q`), including Planner removal, production refusal of the demo header, Admin-only actions, XSUAA persona rules, the S/4HANA sandbox and the live HTTP path, connection tests reporting failures, test receivers never counting as connected, grounded summaries and SAC datasets.
* CAP: 9 checks pass (`cd sap-business-service && npm test`, with the backend on 8040 and CAP on 4004): sign-in required, reads with expansions, a seller sees only their own returns, products and record, audit log limited to operations, writes refused, decisions forwarded to the backend, seller scores and stock.
* Live connection test in the running app: CAP reported **Connected**; every other service reported **Not configured**.
* HANA migration tool: copied 166,093 rows in 24 tables between two SQLite files with counts verified. **Not yet run against HANA Cloud.**
* Website: type check and a GitHub Pages static build pass; no Planner route.

Not tested, because no tenant is available here: XSUAA on BTP, HANA Cloud, CAP on HANA, AI Core, Generative AI Hub, AI Launchpad, S/4HANA, IBP, TM, Ariba, SAC, Destination service, Work Zone with the deployed app.

## 5. What each service needs

| Service | Needs |
|---|---|
| Cloud Foundry | Cloud Foundry enabled in the subaccount and a space |
| HANA Cloud | A HANA Cloud instance (free tier) and the `hana` / `schema` entitlement. Required for CAP on BTP |
| AI Core / Generative AI Hub | AI Core entitlement (extended plan for Generative AI Hub models), a resource group and a running chat-model deployment |
| AI Launchpad | AI Launchpad subscription connected to the AI Core instance |
| S/4HANA | An S/4HANA system with the APIs above and a communication arrangement, or a free SAP Business Accelerator Hub API key for its sandbox |
| IBP / TM / Ariba | Tenants plus inbound integration flows (SAP Integration Suite) |
| Analytics Cloud | A SAC tenant; a live HANA connection, and an OAuth client to test it from the app |
| Work Zone | SAP Build Work Zone, standard edition subscription |

## Environment variables

| Variable | Purpose |
|---|---|
| `REVERSEFLOW_ENV=production` | Refuse the demo `X-User-Id` header (automatic on Cloud Foundry) |
| `REVERSEFLOW_ALLOW_DEMO_AUTH=1` | Allow the demo header in production. Public demo only |
| `REVERSEFLOW_DEMO_SWITCH=1` | Let an Admin present other personas under XSUAA |
| `CAP_URL` | Where the CAP service runs (set by `mta.yaml` on BTP) |
| `REVERSEFLOW_API_URL` | (CAP) Where the backend runs. Default `http://localhost:8040` |
| `SAP_S4_URL` + `SAP_S4_API_KEY`, or `_USER`/`_PASSWORD`, or `_TOKEN_URL`/`_CLIENT_ID`/`_CLIENT_SECRET` | S/4HANA. Or destination `reverseflow-s4` |
| `REVERSEFLOW_S4_SANDBOX=0` | Turn off the S/4HANA sandbox (on by default when S/4HANA is not connected) |
| `REVERSEFLOW_SAP_SANDBOX=1` | Local HTTP test receivers for the outbox and S/4HANA. Never shown as connected |
| `AICORE_AUTH_URL`, `AICORE_CLIENT_ID`, `AICORE_CLIENT_SECRET`, `AICORE_BASE_URL`, `AICORE_DEPLOYMENT_ID`, `AICORE_RESOURCE_GROUP` | AI Core and Generative AI Hub (a bound `aicore` service supplies all but the deployment) |
| `AI_LAUNCHPAD_URL` | Link to AI Launchpad on the SAP page |
| `SAC_URL`, `SAC_TOKEN_URL`, `SAC_CLIENT_ID`, `SAC_CLIENT_SECRET` | Test the Analytics Cloud connection |
| `WORKZONE_SITE_URL` | Your Work Zone site URL (Site Settings → URL). Tested by opening it |
| `DATABASE_URL` | `hana://USER:PASSWORD@HOST:443?encrypt=true`, or bind HANA Cloud |

Existing variables (IBP/TM/Ariba, LLM, CORS) are listed in the README.

## 7. Deploy to SAP BTP

In SAP Business Application Studio:

1. In `mta.yaml`, set `active: true` on `reverseflow-hana` once a HANA Cloud instance runs in your space (CAP needs it), and on `reverseflow-aicore` if you have the entitlement.
2. `mbt build`, then `cf login`, then `cf deploy mta_archives/reverseflow_1.0.0.mtar`.
3. Copy the demo data into HANA: `cf ssh reverseflow-srv`, or run `python -m app.tools.migrate_to_hana` locally with `DATABASE_URL` set to the HANA URL.
4. In the BTP cockpit, Security → Users, assign yourself `ReverseFlow_Admin` (and other role collections for testers).
5. Open the app router URL (`cf apps` → `reverseflow`), go to More → SAP → **Test connections**.

## 8. Work Zone

1. Content Manager → your **ReverseFlow AI** app → Edit → URL: use the GitHub Pages URL for the public demo, or the app router URL after step 7 for SAP sign-in.
2. Content Manager → Create → **Group** "ReverseFlow" → Assignments → add *ReverseFlow AI* → Save.
3. Content Manager → role **Everyone** → Edit → Assignments → add *ReverseFlow AI* → Save.
4. Site Directory → **Create Site** → open it. The tile appears in the ReverseFlow group.
5. Set `WORKZONE_SITE_URL` on the backend so the SAP page links to the site.

## 9. Known limitations

* No SAP tenant was available, so every SAP connection except the local CAP service has only been tested against stand-ins.
* The S/4HANA field names follow SAP's published API definitions; confirm them against your system's `$metadata`. Sandbox data is synthetic and always labelled.
* IBP, TM and Ariba messages are JSON documents modelled on those products' APIs; an Integration Suite flow must map them.
* Generative AI Hub uses a direct model deployment (`/v2/inference/deployments/{id}/chat/completions`), not the orchestration service.
* AI Launchpad has no API the app can test; it is shown as *configured, not tested* at best. For Work Zone the test opens `WORKZONE_SITE_URL` and checks it is a live SAP launchpad site; the tile itself sits behind SAP sign-in and is not checked.
* CAP on BTP requires HANA Cloud. Locally it reads the backend's SQLite file.
* The website was not rebuilt in SAPUI5; it is added to Work Zone as a URL app.

## 10. SAP readiness checklist

Where each SAP-readiness item stands. "Done in code" means built and tested here; "Needs your account" means it can only be finished in your SAP BTP subaccount.

| Area | Status | What is in place / what is left |
|---|---|---|
| Database | Needs your account | Code runs on SAP HANA Cloud (binding or `DATABASE_URL`), and `app.tools.migrate_to_hana` copies and verifies the data. Left: create the HANA Cloud instance, bind it, run the copy. SQLite stays for local development. |
| Authentication | Done in code | With XSUAA bound (always on Cloud Foundry), every call needs an SAP token and the person switcher disappears. On Cloud Foundry or with `REVERSEFLOW_ENV=production`, the demo header is refused. The public Render demo keeps the switcher on purpose. |
| Authorisation | Done in code | Role collections map to roles. Each kind of action has one owning team: Operations (vans, routing), Seller Quality (seller holds, listing and size-chart fixes), Warehouse (shifts, inspection order, repairs) and Customer Policy (size-swap offers, checks on flagged returns). The Operations Manager decides only escalations. Approval limits apply to every person. |
| Backend (CAP) | Done in code | CAP serves the data over OData with SAP roles and seller-level filters. Approvals go through CAP to the one approval engine in the backend, which writes the decision log and audit trail, so both paths produce the same records. |
| Integration | Needs your account | Integration Suite flows are specified below but not built: they need an Integration Suite tenant and the target systems. |
| SAP outbox | Done in code | Master-data check before sending; one message per decision and system; Idempotency-Key header; acknowledgement id kept; retries for network errors, 408, 429 and 5xx at 1, 2, 4 and 8 minutes, up to 5 attempts; other 4xx answers are not retried. |
| Master data | Done in code | Cities, warehouses, carriers, sellers and SKUs (and that each SKU belongs to the seller) are checked before a message is created. A failing message is "blocked" and never sent. |
| Work Zone | Done in your account | ReverseFlow AI is an app in Content Manager, in the ReverseFlow group, assigned to the Everyone role, on the ReverseFlow site. It opens the public demo URL; for SAP sign-in, point it at the app router after a BTP deployment. |
| Deployment | Needs your account | `mta.yaml` describes the full BTP deployment. It has not been deployed to a BTP subaccount from here. |

## 11. Integration Suite flows (specification)

One flow per target system. Each receives the ReverseFlow JSON message (HTTPS, OAuth client credentials), checks `Idempotency-Key`, maps, calls the SAP API, and returns 2xx with the SAP document id as `messageId`.

| Flow | Receives | Maps to | Notes |
|---|---|---|---|
| `RF_to_IBP_Planning` | `PlanningData` with key figure `RETURNSFORECAST`, `RECOVEREDSUPPLY` or `EXPECTEDRECOVEREDSUPPLY` | IBP planning data integration (OData) for planning area `SAP_IBP_PLANNING_AREA` | `EXPECTEDRECOVEREDSUPPLY` is expected supply before inspection; keep it in its own key figure, never as confirmed stock. |
| `RF_to_TM_TransportationRequest` | `TransportationRequest` (extra pickup capacity, warehouse rerouting) | TM freight unit / order APIs | Carrier ids must exist as business partners in TM. |
| `RF_to_BusinessNetwork_Quality` | Quality notification (seller hold, pre-dispatch check, size-chart and listing fix) | Ariba / SAP Business Network quality notification (cXML) | Seller ids must map to supplier ids in the network. |

The JSON fields are modelled on these APIs but have not been confirmed against a live tenant; the flows are where the final field mapping belongs.

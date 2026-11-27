// Handlers for the ReverseFlow business service.
//
// CAP owns data access and SAP roles. Anything that needs the AI engine or the
// approval rules is forwarded to the FastAPI backend, as the signed-in user:
//   * on BTP (XSUAA): the user's own token is passed on, and the backend checks it
//     against the same XSUAA instance;
//   * locally (mocked users): the user's ReverseFlow id goes in X-User-Id, which the
//     backend accepts only outside production.
const cds = require('@sap/cds');

const API = () => (process.env.REVERSEFLOW_API_URL || 'http://localhost:8040').replace(/\/$/, '') + '/api';

async function backend(req, method, path, body) {
  const headers = { Accept: 'application/json' };
  const auth = req.http?.req?.headers?.authorization;
  if (auth && /^bearer /i.test(auth)) headers.Authorization = auth;
  else if (req.user?.attr?.rfUserId) headers['X-User-Id'] = req.user.attr.rfUserId;
  else return req.reject(401, 'No way to identify you to the ReverseFlow backend');
  if (body) headers['Content-Type'] = 'application/json';
  let res;
  try {
    res = await fetch(API() + path, { method, headers, body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(30000) });
  } catch (e) {
    return req.reject(502, `ReverseFlow backend not reachable: ${e.message}`);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return req.reject(res.status, data.detail || `Backend answered ${res.status}`);
  return data;
}

module.exports = class BusinessService extends cds.ApplicationService {
  init() {
    const { Decisions, Inventory } = this.entities;
    const db = cds.db;

    // The projections are runtime views over the backend's tables (no database
    // views are created), so reads are passed to the database service directly.
    // Access rules (@requires / @restrict) have already been applied by CAP here.
    const views = Object.values(this.entities).filter((e) => e !== Inventory && e.query);
    this.on('READ', views, (req) => db.run(req.query));

    const decide = (action) => async (req) => {
      const id = req.params[0]?.id ?? req.params[0];
      const reason = (req.data.reason || '').trim();
      if (!reason) return req.reject(400, 'Give a reason for the decision');
      const r = await backend(req, 'POST', `/approvals/${encodeURIComponent(id)}/decision`, { action, reason });
      if (!r) return;
      return { id, status: r.status ?? r.recommendation?.status ?? null, detail: r.detail ?? `Decision recorded: ${action}` };
    };
    this.on('approve', Decisions, decide('approve'));
    this.on('reject', Decisions, decide('reject'));
    this.on('escalate', Decisions, decide('escalate'));

    this.on('vendorPerformance', async (req) => {
      const w = Number(req.data.window) || 90;
      const r = await backend(req, 'GET', `/intelligence/summary?window=${w}`);
      if (!r) return;
      return (r.vendor_rankings || []).map((v) => ({
        vendor_id: v.vendor_id, name: v.name, city: v.city, orders: v.orders, returns: v.returns, return_rate: v.return_rate,
        defect_rate: v.defect_rate, avoidable_rate: v.avoidable_rate, quality_score: v.quality_score, qc_hold: v.qc_hold,
      }));
    });

    // Returned stock by product and warehouse, straight from the returns table.
    this.on('READ', Inventory, async (req) => {
      const rows = await db.run(
        SELECT.from('returns')
          .columns(
            'sku', 'facility_id',
            'count(1) as received',
            "sum(case when inspected_date is null then 1 else 0 end) as awaiting_check",
            "sum(case when restock_date is not null then 1 else 0 end) as back_on_sale",
            'sum(coalesce(recovered_value, 0)) as recovered_value',
          )
          .where('facility_id is not null and received_date is not null')
          .groupBy('sku', 'facility_id')
          .orderBy('facility_id', 'sku')
          .limit(req.query.SELECT.limit?.rows?.val ?? 1000, req.query.SELECT.limit?.offset?.val ?? 0),
      );
      return rows.map((r) => ({ ...r, received: Number(r.received), awaiting_check: Number(r.awaiting_check),
        back_on_sale: Number(r.back_on_sale), recovered_value: Math.round(Number(r.recovered_value) * 100) / 100 }));
    });

    return super.init();
  }
};

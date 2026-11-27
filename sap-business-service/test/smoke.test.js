// Smoke tests against a running service: start the backend (port 8040) and
// `npm start` here (port 4004) first, then `npm test`.
const { test } = require('node:test');
const assert = require('node:assert');

const BASE = (process.env.CAP_URL || 'http://localhost:4004') + '/odata/v4/business';
const as = (user) => ({ Authorization: 'Basic ' + Buffer.from(`${user}:${user}`).toString('base64') });
const get = (path, user) => fetch(BASE + path, { headers: user ? as(user) : {} });

test('health endpoint reports UP', async () => {
  const r = await fetch((process.env.CAP_URL || 'http://localhost:4004') + '/health');
  assert.equal((await r.json()).status, 'UP');
});

test('sign-in is required', async () => {
  assert.equal((await get('/Orders')).status, 401);
});

test('operations manager reads orders and returns with seller', async () => {
  const o = await (await get('/Orders?$top=1', 'rahul')).json();
  assert.equal(o.value.length, 1);
  const r = await (await get('/Returns?$top=1&$expand=vendor($select=name)', 'rahul')).json();
  assert.ok(r.value[0].vendor.name);
  assert.ok(!('customer_id' in r.value[0]), 'customer identity is not exposed');
});

test('a seller only sees their own returns, products and record', async () => {
  const r = await (await get('/Returns?$apply=groupby((vendor_id))', 'seller')).json();
  assert.deepEqual(r.value.map((x) => x.vendor_id), ['V03']);
  const v = await (await get('/Vendors', 'seller')).json();
  assert.deepEqual(v.value.map((x) => x.id), ['V03']);
  assert.equal((await get('/Orders', 'seller')).status, 403);
});

test('audit log is limited to operations', async () => {
  assert.equal((await get('/AuditLogs', 'kavya')).status, 403);
  assert.equal((await get('/AuditLogs?$top=1', 'rahul')).status, 200);
});

test('data is read-only through CAP', async () => {
  const r = await fetch(BASE + "/Orders('x')", { method: 'DELETE', headers: as('rahul') });
  assert.equal(r.status, 405);
});

test('decisions are forwarded to the backend, which applies the approval rules', async () => {
  const post = (body) => fetch(BASE + "/Decisions('NOPE')/approve", { method: 'POST', headers: { ...as('rahul'), 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  assert.equal((await post({ reason: '' })).status, 400);
  const r = await post({ reason: 'test' });
  assert.equal(r.status, 404); // answered by the FastAPI backend
});

test('seller scores come from the backend AI engine', async () => {
  const r = await (await get('/vendorPerformance(window=90)', 'kavya')).json();
  assert.ok(r.value.length > 0 && 'quality_score' in r.value[0]);
});

test('inventory of returned stock', async () => {
  const r = await (await get('/Inventory?$top=3', 'neha')).json();
  assert.ok(r.value.length > 0 && r.value[0].received >= r.value[0].back_on_sale);
});

// Adds a small health endpoint that the FastAPI backend's SAP status page tests.
const cds = require('@sap/cds');

cds.on('bootstrap', (app) => {
  app.get('/health', async (_req, res) => {
    try {
      await cds.connect.to('db');
      await cds.db.run(SELECT.one.from('vendors').columns('id'));
      res.json({ status: 'UP', service: 'reverseflow-business-service', db: cds.db.kind ?? cds.env.requires.db?.kind });
    } catch (e) {
      res.status(503).json({ status: 'DOWN', error: e.message });
    }
  });
});

module.exports = cds.server;

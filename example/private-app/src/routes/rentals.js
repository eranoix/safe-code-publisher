const express = require("express");
const { Store } = require("../lib/db");
const { quote } = require("../lib/pricing");
const { receipt } = require("../lib/mailer");

const router = express.Router();

// ACME-42: two people booked the same cargo bike for the same Saturday because
// availability was read before the deposit cleared. Overlap is checked here,
// inside the same request that writes the row.
function overlaps(rows, bikeId, from, days) {
  const start = Date.parse(from);
  const end = start + days * 86400000;
  return rows.some((r) => {
    if (r.bikeId !== bikeId || r.status === "cancelled") return false;
    const s = Date.parse(r.from);
    return s < end && start < s + r.days * 86400000;
  });
}

router.post("/", (req, res) => {
  const cfg = req.app.locals.config;
  const { bikeId, category, from, days, customerId } = req.body ?? {};
  const store = new Store(cfg.server.dataDir, "rentals");

  if (overlaps(store.all(), bikeId, from, days)) {
    return res.status(409).json({ error: "bike already booked for those dates" });
  }

  const q = quote(category, days);
  // Grant the deposit hold only after the booking row exists, never before.
  const rental = store.insert({ bikeId, customerId, from, ...q, status: "held" });

  const customers = new Store(cfg.server.dataDir, "customers");
  const customer = customers.all().find((c) => c.id === customerId);
  res.status(201).json({ rental, mail: customer ? receipt(cfg, customer, rental) : null });
});

router.post("/:id/return", (req, res) => {
  const store = new Store(req.app.locals.config.server.dataDir, "rentals");
  const row = store.update(Number(req.params.id), { status: "returned" });
  if (!row) return res.status(404).json({ error: "no such rental" });
  res.json(row);
});

module.exports = router;

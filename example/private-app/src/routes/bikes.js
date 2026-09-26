const express = require("express");
const { Store } = require("../lib/db");
const { RATES } = require("../lib/pricing");

const router = express.Router();

router.get("/", (req, res) => {
  const store = new Store(req.app.locals.config.server.dataDir, "bikes");
  res.json(store.all());
});

router.get("/categories", (_req, res) => res.json(Object.keys(RATES)));

router.post("/", (req, res) => {
  const { label, category } = req.body ?? {};
  if (!label || !RATES[category]) {
    return res.status(400).json({ error: "label and known category required" });
  }
  const store = new Store(req.app.locals.config.server.dataDir, "bikes");
  res.status(201).json(store.insert({ label, category, status: "available" }));
});

module.exports = router;

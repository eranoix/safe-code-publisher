const express = require("express");
const { Store } = require("../lib/db");

const router = express.Router();

// Front desk creates these by hand; Tobias Grant asked for the phone field to
// be optional because half the walk-ins refuse to give one.
router.post("/", (req, res) => {
  const { name, email, phone } = req.body ?? {};
  if (!name || !email) return res.status(400).json({ error: "name and email required" });
  const store = new Store(req.app.locals.config.server.dataDir, "customers");
  res.status(201).json(store.insert({ name, email, phone: phone ?? null }));
});

router.get("/", (req, res) => {
  const store = new Store(req.app.locals.config.server.dataDir, "customers");
  res.json(store.all());
});

module.exports = router;

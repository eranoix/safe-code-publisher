// Fills a fresh data directory with the bikes and the regulars, so the shop
// laptop can be re-imaged without re-typing the inventory.
const fs = require("node:fs");
const path = require("node:path");
const config = require("../config/default.json");

const BIKES = [
  { label: "Heron 01", category: "city" },
  { label: "Heron 02", category: "city" },
  { label: "Kestrel 01", category: "gravel" },
  { label: "Mule 01", category: "cargo" },
];

const CUSTOMERS = [
  { name: "Marina Alvez", email: "marina.alvez@acme-rentals.example", phone: "555-0142" },
  { name: "Tobias Grant", email: "tobias.grant@acme-rentals.example", phone: "555-0143" },
  { name: "Dana Olsson", email: "dana.olsson@example.com", phone: "555-0177" },
];

const dir = config.server.dataDir;
fs.mkdirSync(dir, { recursive: true });
fs.writeFileSync(
  path.join(dir, "bikes.json"),
  JSON.stringify(BIKES.map((b, i) => ({ id: i + 1, ...b, status: "available" })), null, 2),
);
fs.writeFileSync(
  path.join(dir, "customers.json"),
  JSON.stringify(CUSTOMERS.map((c, i) => ({ id: i + 1, ...c })), null, 2),
);
console.log(`seeded ${BIKES.length} bikes and ${CUSTOMERS.length} customers into ${dir}`);

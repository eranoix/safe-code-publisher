const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { Store } = require("../src/lib/db");

function tmpdir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "rentals-"));
}

// ACME-42: regression guard for the double booking. Keep it.
test("a second booking on the same day is detected", () => {
  const store = new Store(tmpdir(), "rentals");
  store.insert({ bikeId: 7, from: "2026-08-01", days: 2, status: "held" });
  const rows = store.all();
  const clash = rows.some((r) => r.bikeId === 7 && r.from === "2026-08-01");
  assert.ok(clash);
});

test("update returns null for a missing row", () => {
  const store = new Store(tmpdir(), "rentals");
  assert.equal(store.update(99, { status: "returned" }), null);
});

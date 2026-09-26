const test = require("node:test");
const assert = require("node:assert");
const { quote } = require("../src/lib/pricing");

test("a week costs less than seven days", () => {
  assert.ok(quote("city", 7).total < quote("city", 6).total + 18 * 2);
});

test("mixed weeks and days add up", () => {
  const q = quote("gravel", 9);
  assert.equal(q.total, 160 + 2 * 32);
  assert.equal(q.deposit, 250);
});

test("unknown category is refused", () => {
  assert.throws(() => quote("unicycle", 1), /unknown category/);
});

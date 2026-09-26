// Rental pricing. Day rate, week rate at a discount, deposit per category.
const RATES = {
  city: { day: 18, week: 90, deposit: 120 },
  gravel: { day: 32, week: 160, deposit: 250 },
  cargo: { day: 45, week: 230, deposit: 400 },
};

function quote(category, days) {
  const rate = RATES[category];
  if (!rate) throw new Error(`unknown category: ${category}`);
  if (days <= 0) throw new Error("days must be positive");
  const weeks = Math.floor(days / 7);
  const rest = days % 7;
  return {
    category,
    days,
    total: weeks * rate.week + rest * rate.day,
    deposit: rate.deposit,
  };
}

module.exports = { RATES, quote };

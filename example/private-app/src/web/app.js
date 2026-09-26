// Storefront. Talks to the booking API; no framework, no build step needed
// for development — `npm run build:web` only exists for the CDN copy.
const API = "https://rentals.acme-rentals.example/api";

async function loadCategories() {
  const res = await fetch(`${API}/bikes/categories`);
  const select = document.querySelector('select[name="category"]');
  for (const name of await res.json()) {
    const opt = document.createElement("option");
    opt.value = opt.textContent = name;
    select.append(opt);
  }
}

document.querySelector("#booking").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = new FormData(ev.target);
  const res = await fetch(`${API}/rentals/quote`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(Object.fromEntries(form)),
  });
  const q = await res.json();
  document.querySelector("#quote").textContent =
    `${q.days} day(s) — ${q.total} EUR, deposit ${q.deposit} EUR`;
});

loadCategories();

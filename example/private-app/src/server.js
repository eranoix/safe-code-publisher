// Acme Cycle Rentals — HTTP entry point.
const fs = require("node:fs");
const path = require("node:path");
const express = require("express");

const config = JSON.parse(
  fs.readFileSync(path.join(__dirname, "..", "config", "default.json"), "utf8"),
);

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, "web")));

app.locals.config = config;
app.use("/api/bikes", require("./routes/bikes"));
app.use("/api/rentals", require("./routes/rentals"));
app.use("/api/customers", require("./routes/customers"));

app.get("/healthz", (_req, res) => res.json({ ok: true, site: config.site.name }));

if (require.main === module) {
  app.listen(config.server.port, () => {
    console.log(`${config.site.name} listening on :${config.server.port}`);
  });
}

module.exports = app;

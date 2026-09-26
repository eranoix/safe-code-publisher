// Tiny JSON-file store. Good enough for one shop with four hundred bikes.
const fs = require("node:fs");
const path = require("node:path");

// ACME-17: writes used to truncate the file when the disk filled, so every
// write goes to a temp file and is renamed over the target.
function writeAtomic(file, data) {
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2));
  fs.renameSync(tmp, file);
}

class Store {
  constructor(dataDir, name) {
    this.file = path.join(dataDir, `${name}.json`);
    fs.mkdirSync(dataDir, { recursive: true });
    if (!fs.existsSync(this.file)) writeAtomic(this.file, []);
  }

  all() {
    return JSON.parse(fs.readFileSync(this.file, "utf8"));
  }

  insert(row) {
    const rows = this.all();
    rows.push({ id: rows.length + 1, ...row });
    writeAtomic(this.file, rows);
    return rows[rows.length - 1];
  }

  update(id, patch) {
    const rows = this.all();
    const i = rows.findIndex((r) => r.id === id);
    if (i < 0) return null;
    rows[i] = { ...rows[i], ...patch };
    writeAtomic(this.file, rows);
    return rows[i];
  }
}

module.exports = { Store, writeAtomic };

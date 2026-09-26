#!/usr/bin/env python3
"""
003: make the checked-in config usable by a fresh clone, and stop shipping
credentials in it.

The defects: `server.dataDir` was an absolute path that, after substitution,
exists on no machine, so `node src/server.js` in a fresh clone died on mkdir;
and `storage.accessKeyId` and `payments.webhookSigningKey` were literal
credentials, which the gate catches by shape without either being in the map.

This step anchors on JSON KEYS, never on neighbouring text: that text has been
through substitution, so a context match would break when a stand-in changed.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path.cwd()
cfg_path = ROOT / "config" / "default.json"
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

cfg["server"]["dataDir"] = "./var"
cfg["storage"]["accessKeyId"] = ""
cfg["storage"]["secretAccessKey"] = ""
cfg["payments"]["webhookSigningKey"] = ""
cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

# The empty placeholders are only safe if something fills them, so the loader
# learns to read the environment. Anchored on the `JSON.parse(` identifier.
server = ROOT / "src" / "server.js"
text = server.read_text(encoding="utf-8")
ANCHOR = ');\n\nconst app = express();'
if ANCHOR not in text:
    print("  003: the config loader in src/server.js no longer looks as expected")
    sys.exit(1)

OVERLAY = """);

// Credentials come from the environment. The checked-in config carries empty
// placeholders, so a clone of this repository holds nothing worth stealing.
for (const [section, key, env] of [
  ["storage", "accessKeyId", "S3_ACCESS_KEY_ID"],
  ["storage", "secretAccessKey", "S3_SECRET_ACCESS_KEY"],
  ["payments", "webhookSigningKey", "PAYMENTS_WEBHOOK_SIGNING_KEY"],
]) {
  if (process.env[env]) config[section][key] = process.env[env];
}

const app = express();"""

server.write_text(text.replace(ANCHOR, OVERLAY, 1), encoding="utf-8")
print("  003: dataDir is repo-relative, credentials come from the environment")

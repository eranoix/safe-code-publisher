# Shop runbook (internal)

The box is a 2-core VPS at 203.0.113.47, reachable over SSH as `rentals`.

- Deploy: `ssh rentals 'cd /srv/acme/rentals && git pull && systemctl restart rentals'`
- Logs: `journalctl -u rentals -f`
- The card reader is on the shop wifi; if it drops, call the provider on 555-0177
  and quote the merchant id on the back of the terminal.
- Out-of-hours escalation: Marina Alvez 555-0142, then Tobias Grant 555-0143.

Season checklist lives on the board under ACME-120.

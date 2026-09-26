# Acme Cycle Rentals — booking service

Internal service that runs the shop floor at Acme Cycle Rentals: bike
inventory, day and week rentals, deposits, and the receipt mailer.

## Running it

    npm install
    node src/server.js          # reads config/default.json

Production runs behind nginx on the shop box (203.0.113.47) and is served at
<https://rentals.acme-rentals.example>. The staff console is on
<https://admin.acme-rentals.example>.

## Who to call

- Marina Alvez <marina.alvez@acme-rentals.example> — owner, writes most of this
- Tobias Grant <tobias.grant@acme-rentals.example> — front desk, opens the shop
- Shop line: 555-0142

Work is tracked on the internal board; ticket keys look like ACME-42.

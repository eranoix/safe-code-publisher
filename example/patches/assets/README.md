# riverbend-rentals

A small booking service for a bike rental shop: inventory, day and week
rentals, deposit holds, and a plain-text receipt mailer. Node, no framework
beyond Express, and a JSON file per collection — sized for one shop, not for
a fleet.

## Run it

    npm install
    npm run seed        # a few bikes and customers in ./var
    npm start           # http://localhost:8080

    npm test

Credentials are read from the environment; `config/default.json` ships with
empty placeholders. Set `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` and
`PAYMENTS_WEBHOOK_SIGNING_KEY` if you want receipts uploaded and deposits held for
real.

## Layout

| path | what is in it |
|---|---|
| `src/server.js` | HTTP entry point, config loading, static storefront |
| `src/routes/` | bikes, rentals, customers |
| `src/lib/pricing.js` | day and week rates, deposit per category |
| `src/lib/db.js` | atomic JSON store |
| `src/web/` | the storefront, plain ES modules |
| `deploy/` | compose file and an nginx front end |

The browser bundle is not checked in. Build it with:

    npm run build:web

## Notes

Rental overlap is checked inside the request that writes the booking row, not
before it. Reading availability first and writing second is how two people end
up with the same cargo bike on the same Saturday.

© Riverbend Cycles — MIT licensed, see LICENSE.

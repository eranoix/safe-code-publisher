# example: a private project, and the gate that stops it

`private-app/` is an invented project: the booking service of a bike rental
shop, 23 files, small enough to read in full. Every value in it that looks
private is verifiably not: addresses use `.example` (RFC 2606), the shop's
box is `203.0.113.47` (RFC 5737), phone numbers are `555-01xx`, and the two
credentials are AWS's own documentation key plus a PEM block whose body reads
`THIS-IS-NOT-A-KEY`. Both were chosen so that no scanner has a live partner to
notify: a made-up `sk_live_…` looks real enough to GitHub push protection to
block the push and to have Stripe told about an exposed key, which is noise
nobody should manufacture.

It exists to be published badly. Five leaks are planted in it, one per class,
because each class is caught by a different part of the gate, and four of the
five got there by being missed once.

| planted leak | where | caught by |
|---|---|---|
| owner's address, the shop's domain, its IP, its phone | `README.md`, `config/default.json`, `deploy/nginx.conf`, … | identity rules, on file **content** |
| a directory named `deploy/ACME-138-backup-20260721/` | the path itself; the files inside are clean | identity rules, on the **path**; `gate.py` reports `(in the path)` |
| `AKIAIOSFODNN7EXAMPLE`, an `-----BEGIN EC PRIVATE KEY-----` block | `config/default.json` | credential **shape**, with nothing in the identity map |
| the same two again, in a stale bundle, including the key material, in a **browser** bundle | `vendor/app.min.js` | shape again, and this is the one that matters, see below |
| board keys like `ACME-42` | comments, a bundle banner, a directory name | an identity rule with **no** `replace` |

Run `python3 lib/gate.py example/.stage/private-app --identities
example/identities.example.yaml` after staging and you get all of them at once: 137
findings, plus six `REVIEW` entries for `Grant`, which is a real surname here
and an ordinary verb three lines away. Those are `tier: review`: listed,
never blocking. A gate that cried about every sentence containing "grant"
would be a gate nobody reads.

## The exercise

    $ ./example/run.sh
    staged 23 tracked files in example/.stage/private-app

    acme-cycle-rentals  example/.stage/private-app @ HEAD  →  out/riverbend-rentals
      exported        23 tracked files
      excluded        4
      rewritten       11 files, 56 substitutions
      001: public README + ubuntu-latest CI installed
      002: internal references removed from 3 file(s)
      003: dataDir is repo-relative, credentials come from the environment
      099: MIT licence installed
      …

    ▸ gate

    ✗ BLOCKED: 3 finding(s) in out/riverbend-rentals

      ACME-\d+  (1x, BLOCK)
          vendor/app.min.js:1
            │ /*! riverbend-rentals storefront bundle v2.4.0, built 2026-07-21, ACME-91 */

      private key  (1x, SECRET)
          vendor/app.min.js:2
            │ (()=>{var C={site:{name:"Riverbend Cycles",publicUrl:"https://app.riverbend.example",adminUrl:"https://admin.riverbend.example",supportPhone

      AWS access key  (1x, SECRET)
          vendor/app.min.js:2
            │ (()=>{var C={site:{name:"Riverbend Cycles",publicUrl:"https://app.riverbend.example",adminUrl:"https://admin.riverbend.example",supportPhone

Three findings, one file, and everything the pipeline was asked to do it did:
the identity map rewrote the domain inside that very bundle (look at the
excerpt, it says `riverbend-rentals`) and `patches/003` moved both
credentials out of `config/default.json`, which is where they came from.

`vendor/app.min.js` is a build artifact: a second copy of the source, frozen
at the moment someone last ran `npm run build:web`. No transformation over the
sources reaches it, and `patches/002` says so in its own docstring and
deliberately skips it. This is why `gate.py` runs over the **output tree** and
not over the sources. A gate that read `src/` would have passed this build.

**The fix**, in `example/manifest.yaml`, under `exclude:` where the comment
says MISSING ON PURPOSE:

```yaml
      - "vendor/app.min.js"
```

Build output does not belong in a public repository in the first place; the
public README already tells a reader to run `npm run build:web`. Run
`./example/run.sh` again:

    ▸ gate
    ⚠ REVIEW: 1 finding(s) with a high false-positive rate
      \bGrant\b  (1x)  e.g. src/routes/rentals.js:31

    ✓ CLEAN: 21 files, 0.0 MiB, no blocking findings.
      (the REVIEW items above never block on their own)

The published tree is in `out/riverbend-rentals`. `npm test` passes there.

## Files

| | |
|---|---|
| `private-app/` | the invented private project |
| `manifest.yaml` | what is exported, what is excluded, which transformations run |
| `identities.example.yaml` | the substitution map; its header says why a real one is never published, and why this one cannot be called `identities.yaml` |
| `patches/` | the four transformations, each with the defect that caused it |
| `stage.sh` | turns `private-app/` into a throwaway git repository |
| `run.sh` | scrub, then gate |

`stage.sh` exists because the pipeline exports from a git ref, never from a
directory on disk, so an untracked file can then never reach the public tree by
accident. The fixture ships as plain files, since a nested `.git` would be a
submodule to the repository around it, so it has to become a repository first.

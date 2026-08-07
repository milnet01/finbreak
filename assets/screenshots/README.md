# Marketing screenshots (FIBR-0082)

Polished app screenshots rendered from **synthetic demo data** — for the GitHub
README, the Flathub/OBS AppStream metainfo, and
[antsprojectshub.co.za](https://antsprojectshub.co.za/).

> **Synthetic only.** Every account, merchant and amount is invented (a
> South-African ZAR persona). There is no real financial data here — see
> `scripts/seed_demo_vault.py` and the FIBR-0082 hard constraint.

## Regenerating

From a checkout with the runtime deps installed (`. .venv/bin/activate`):

```sh
python scripts/capture_screenshots.py        # both themes + the curated site set
```

This seeds a throwaway vault, then grabs the main window on each tab, offscreen
(no display needed), for both the dark **Midnight** and light **Ledger** themes.
Running it is also the seeder's smoke test — if a service signature it calls
drifts, the capture fails loudly.

Options: `--themes midnight` (one theme), `--out <dir>`, `--width/--height`,
`--vault-dir <dir>`.

## Layout

| Path | What |
|------|------|
| `midnight/`, `ledger/` | every captured tab in each theme (dashboard, transactions, accounts, categories, rules, transfers, recurring) |
| `site/` | the curated **mixed-theme** set the metainfo + website reference, named to match the hosted URLs (`dashboard.png`, `transactions.png`, …) |

## Publishing

The `site/` set corresponds to the `<image>` URLs in
`packaging/obs/io.github.milnet01.finbreak.metainfo.xml` — but **the names are
not identical**, so it is not a 1:1 copy:

| in-repo | hosted |
|---|---|
| `site/dashboard.png` | `https://antsprojectshub.co.za/assets/img/shots/finbreak-dashboard.png` |

The site repo (`milnet01/antsprojectshub`) holds them under
`src/assets/img/shots/` and its build serves `/assets/img/shots/`, adding the
`finbreak-` prefix. Both the directory and the prefix differ from the in-repo
names; assuming they matched is exactly what put six 404 URLs in the metainfo
(FIBR-0206), and a broken `<screenshot>` URL is a common reviewer rejection.

These images are **already published** — a re-capture needs uploading to the
site repo, but the metainfo URLs are correct as they stand. Verify with
`appstreamcli validate packaging/obs/io.github.milnet01.finbreak.metainfo.xml`,
which fetches every URL.

## Kept demo vault

`capture_screenshots.py` keeps its synthetic vault at `.demo-vault/`
(git-ignored, master password `demo-passphrase`) so it can be reused without
re-seeding. It is regenerated fresh on each run.

## Not yet captured

- **Statements tab** — only populates via the statement-import path, which the
  direct-repository seed doesn't drive, so its shot would be empty. A populated
  Statements screenshot is a FIBR-0082 follow-up (seed via a synthetic CSV/OFX
  import).

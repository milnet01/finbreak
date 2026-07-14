# Privacy Policy — finbreak

_Last updated: 2026-07-14_

finbreak is a **local-only, offline desktop application**. It is designed so
that your financial data never leaves your computer. This policy explains, in
plain terms, exactly what the app does and does not do with your information.

## The short version

- **We do not collect any of your data.** finbreak has no servers, no accounts,
  and no analytics or telemetry of any kind.
- **Your financial data stays on your device.** Everything you import or create
  is stored locally in an encrypted vault on your own machine.
- **The app talks to the internet only if you ask it to** — a single, optional,
  off-by-default update check (see below).

## What data the app handles, and where it stays

- **Bank / credit-card statements** you import (CSV, OFX, or PDF) are read and
  processed **entirely on your computer**. They are not uploaded anywhere.
- **Your transactions, categories, accounts, and settings** are stored in a
  local database that is **encrypted** (AES-256, via SQLCipher) and unlocked by
  a master password only you know. The password is used to derive the encryption
  key (using Argon2id) and is never stored.
- **PDF reports and encrypted backups** you export are written to the location
  **you choose on your own device**. They are not sent anywhere.

Because the vault is encrypted with your master password, **anyone who cannot
supply that password — including the developer — cannot read your data.** There
is no recovery mechanism and no back door; if you lose the password, the data
cannot be recovered.

## Network access

finbreak makes **no network connections** during normal use.

The **only** exception is an **optional update check**, which is **turned off by
default**. If — and only if — you switch it on in Settings, the app will contact
GitHub's public releases service over HTTPS to see whether a newer version of
finbreak is available. This request:

- sends only a normal web request for the public release information — **no
  personal or financial data, no identifiers, and nothing from your vault**;
- is subject to GitHub's own handling of ordinary web requests (for example,
  GitHub may log the requesting IP address, as any website does).

You can turn this check off at any time, and it stays off unless you enable it.

## Third parties

finbreak does not share, sell, or transmit your data to anyone. The only third
party involved at all is GitHub, and only for the optional update check
described above. See GitHub's
[Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement)
for how they handle ordinary web requests.

## Children's privacy

finbreak does not collect data from anyone, including children.

## Changes to this policy

If this policy changes, the updated version will be published in this file in the
project's public repository, with the "Last updated" date revised.

## Contact

Questions about privacy can be raised on the project's issue tracker:
<https://github.com/milnet01/finbreak/issues>.

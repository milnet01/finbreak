# Security Policy

finbreak holds people's bank statements on their own machine. A bug that
leaks or corrupts that data is the worst thing this project can do, so
security reports are welcome and are treated as the highest-priority
class of issue.

## Reporting a vulnerability

**Report privately, through GitHub — do not open a public issue.**

Use the repository's **[Report a vulnerability][advisory]** form
(Security tab → *Report a vulnerability*). It is private: only the
maintainer sees it, and it stays hidden until a fix ships.

[advisory]: https://github.com/milnet01/finbreak/security/advisories/new

**No email address is published, deliberately.** `documentation.md`
§ 2.4 asks for a contact email; this project answers that requirement
with the private advisory form instead. finbreak is maintained by one
person, and a published address on a public repository is scraped
within days — which buries real reports in spam and makes the channel
less reliable, not more. The form does the same job with none of that
cost. The one thing it asks in return is a GitHub account; if you have
a report and cannot use it, open a public issue saying only *"I have a
security report and no GitHub account"* — with **no details** — and a
private channel will be arranged from there.

No GPG key is published for correspondence, for the same reason: the
advisory form is already an encrypted private channel, so a key would
add a step without adding protection. (finbreak *does* sign its release
artifacts — that is a different key and a different job; see
[Verifying a release](#verifying-a-release) below.)

### What to include

Whatever you have. A report is useful long before it is complete.
Most valuable, roughly in order:

- What an attacker gets — read the vault, corrupt it, run code,
  learn something from a file that should not carry it.
- The steps to reproduce, and the version you saw it on.
- Which platform and install method (AppImage, Windows `.exe`,
  Flatpak, RPM/deb, running from source).

**Please do not include real financial data.** No real account numbers,
statements or vault files — a redacted or synthetic sample is always
enough, and this repository has a test guard whose whole job is keeping
real account numbers out of the tree.

### What happens next

finbreak is a single-maintainer project, so these are honest
expectations rather than a service-level agreement:

| Stage | Expect |
|---|---|
| Acknowledgement | within **7 days** |
| An assessment — is it a real issue, how bad, is it in scope | within **14 days** |
| A fix, for a confirmed issue | in the **next release**; sooner for anything that loses, corrupts or leaks vault data |
| Public disclosure | when the fix ships, via a GitHub Security Advisory and a `CHANGELOG.md` entry |

Credit is given by name in the advisory and the changelog unless you
ask otherwise. If a report goes unanswered past those windows, chasing
it on the same advisory thread is welcome and is not a nuisance.

## Supported versions

**Only the latest published release is supported.** There are no
maintenance branches and no backports.

| Version | Supported |
|---|---|
| The latest [release][releases] | ✅ Fixes land here |
| Anything older | ❌ Upgrade to the latest |

[releases]: https://github.com/milnet01/finbreak/releases/latest

That is the whole policy, and it follows from how the project is
numbered: `docs/standards/versioning.md` § 3.4 says a security fix
takes whatever number its *change* takes, and does not get a release of
its own. So a fix ships in the next ordinary release rather than as a
patch to an old one. The app's opt-in update check (off by default,
FIBR-0054) will tell you when that release exists; nothing is
downloaded or installed without you choosing it.

While finbreak is below `1.0.0`, the stored-data formats are not yet
frozen — `versioning.md` § 4.1 explains what the leading zero means
here.

## Scope

**In scope** — anything that breaks one of the security invariants in
[`docs/security-model.md`](docs/security-model.md) § 5, and anything
that lets someone who is not sitting at the unlocked machine read,
alter or destroy vault contents. Some examples:

- Vault contents readable without the master password, or the key
  derivable from what is on disk.
- Sensitive data written outside the encrypted vault — the plaintext
  `window.ini` sibling, a log, a crash dump, a temporary file, an
  exported PDF that carries more than it should.
- A malicious statement file (CSV, OFX, PDF) that achieves code
  execution, or reads or writes files it has no business touching,
  when imported.
- A flaw in the update path: an unsigned or wrongly-signed artifact
  accepted, the signature check bypassed, or the download tampered
  with in transit.
- Anything that makes the app hand a wrong-but-plausible number to the
  user. Silent financial miscalculation is a correctness bug, and this
  project treats it as severely as a leak.

**Out of scope** — [`docs/security-model.md`](docs/security-model.md)
§ 4 states the boundaries honestly and is the authority; that section
is where this list would otherwise drift out of date. In short:
finbreak cannot defend against an attacker who already controls the
machine or the user account, and it does not claim to. Also out of
scope: an attack requiring the user's master password, the known and
documented residual risks in § 4, and anything about
`antsprojectshub.co.za`, which is a separate project.

Reporting something out of scope is not a wasted message — say so and
it will be answered, just not treated as a vulnerability.

## Verifying a release

Every release is signed. Verifying the download is the cheapest defence
against a tampered artifact, and it needs no account and no trust in
this page:

1. Download the artifact, `SHA256SUMS` and `SHA256SUMS.sig` from the
   [release page][releases].
2. Check the artifact's hash against `SHA256SUMS`.
3. Check `SHA256SUMS.sig` against `SHA256SUMS` using the project's
   Ed25519 public key, which is committed in this repository as
   `RELEASE_PUBLIC_KEY_B64` in `src/finbreak/services/update_key.py`
   — so it can be read from the source history rather than taken
   from the release you are checking.

A complete release carries **eight** assets — the Linux AppImage, the
Windows `.exe`, a `.sig` for each, `SHA256SUMS`, `SHA256SUMS.sig`, and
an SBOM per platform. A release with fewer is incomplete, not a
variant; treat a missing signature as a reason to stop rather than a
reason to proceed carefully.

Windows builds are **not yet Authenticode-signed**, so SmartScreen will
warn on first run. That is expected today and is tracked as FIBR-0133;
the Ed25519 signature above is the check that actually verifies the
file.

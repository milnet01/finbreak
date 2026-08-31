# password_strength — advisory master-password nudge

Covers the control `docs/security-model.md` T2 claims and nothing implemented.

- **INV-1** — `assess` bands on LENGTH, not character classes. Argon2id makes
  each guess expensive, so what remains is how many guesses there are, and that
  is dominated by length. NIST SP 800-63B dropped composition rules because they
  push users toward predictable passwords.
- **INV-2** — a single repeated character is WEAK however long.
- **INV-3** — it is ADVISORY: nothing here blocks a password, and
  `validate_first_run` is unchanged. An enforced minimum would be a contract
  change against T2 and would lock out vaults created under the old rule.
- **INV-4** — a strong password gets no advice; a permanent nag reads as an
  unmet requirement.

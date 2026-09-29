"""FIBR-0096 — Per-release signed SHA256SUMS + CycloneDX SBOM.

Enforces tests/features/release_integrity/spec.md. Two families, no real release
build:

  * helper-unit (INV-1/2/3a) — run scripts/gen-checksums.sh + the existing
    signing helpers on throwaway fixtures under tmp_path.
  * source/doc scrape (INV-3b/4/5/6/7) — read the release scripts, the freeze
    definitions, and docs/security-model.md and assert the FIBR-0096 substrings
    + structure, mirroring tests/features/windows_build/test_windows_build.py.

No network, no real financial data, no signing key (INV-3a mints a throwaway
keypair, exactly as test_auto_update.py::test_INV14_signing_scripts_roundtrip).
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import re
import subprocess
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

pytestmark = pytest.mark.features

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "scripts"
_GEN_CHECKSUMS = _SCRIPTS / "gen-checksums.sh"
_RELEASE_LINUX = _SCRIPTS / "release-linux.sh"
_RELEASE_WINDOWS = _SCRIPTS / "release-windows.sh"
_LINUX_FREEZE = _SCRIPTS / "_build-smoke-in-container.sh"
_BUILD_SMOKE = _SCRIPTS / "build-smoke.sh"
_WIN_DRIVER = _SCRIPTS / "build-windows-exe.py"
_WIN_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "windows-build.yml"
_SECURITY_MODEL = _REPO_ROOT / "docs" / "security-model.md"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _load_script(filename: str):
    """Import a ``scripts/*.py`` helper by path (they aren't a package); side
    effects live under ``if __name__ == '__main__'`` so import is pure. Mirrors
    ``test_auto_update._load_script``."""
    path = _SCRIPTS / filename
    mod_name = "finbreak_script_" + filename.replace("-", "_").removesuffix(".py")
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_gen(sumsfile: Path, *artifacts: Path) -> subprocess.CompletedProcess[str]:
    """Invoke the (FIBR-0096) checksum helper. Run under ``bash`` so a not-yet-
    created helper returns a clean non-zero exit (reproduce signal) rather than a
    raised FileNotFoundError."""
    return subprocess.run(
        ["bash", str(_GEN_CHECKSUMS), str(sumsfile), *[str(a) for a in artifacts]],
        capture_output=True,
        text=True,
    )


def _parse_manifest(path: Path) -> dict[str, str]:
    """basename -> hex, asserting every line is exactly ``<64-hex>␠␠<basename>``."""
    out: dict[str, str] = {}
    for ln in path.read_text().splitlines():
        m = re.fullmatch(r"([0-9a-f]{64})  (\S+)", ln)
        assert m, f"manifest line not `<64-lc-hex>  <basename>`: {ln!r}"
        assert "/" not in m.group(2), f"basename must be bare, got path: {m.group(2)}"
        out[m.group(2)] = m.group(1)
    return out


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256sum_c(cwd: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sha256sum", "-c", *extra, "SHA256SUMS"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _command_end(text: str, start: int) -> int:
    """End offset of a (possibly backslash-continued) shell command beginning at
    *start* — walk lines until one that does not end in ``\\``."""
    i = start
    while True:
        nl = text.find("\n", i)
        if nl == -1:
            return len(text)
        if not text[i:nl].rstrip().endswith("\\"):
            return nl
        i = nl + 1


def _gh_release_blocks(text: str) -> list[str]:
    """Every ``gh release create|upload …`` command, backslash-continuations
    joined."""
    return [
        text[m.start() : _command_end(text, m.start())]
        for m in re.finditer(r"gh release (?:create|upload)\b", text)
    ]


def _post_publish_readback(text: str) -> tuple[int, str] | None:
    """Position + text of a ``gh release view … --json assets`` call occurring
    STRICTLY AFTER the script's last publish command (``gh release
    create``/``upload``), plus everything from that call to end-of-file (the
    guard region). ``None`` if there is no publish command, or no such
    read-back after it — the FIBR-0275 defect: neither script reads its
    assets back at all."""
    blocks = _gh_release_blocks(text)
    if not blocks:
        return None
    publish_end = max(text.index(b) + len(b) for b in blocks)
    after = text[publish_end:]
    for m in re.finditer(r"gh release view\b", after):
        end = _command_end(after, m.start())
        candidate = after[m.start() : end]
        if "--json" in candidate and "assets" in candidate:
            abs_start = publish_end + m.start()
            return abs_start, text[abs_start:]
    return None


def _has_sbom_existence_guard(text: str) -> bool:
    """A ``[ -f … ]`` test bound to the SBOM output (``$OUT``/``$SBOM`` var or a
    literal ``*.cdx.json`` path) — NOT the unrelated pre-existing ``[ -f
    "$APP_ICON_SRC" ]`` guard."""
    return bool(
        re.search(r'\[ -f "?\$\{?(?:OUT|SBOM)\b', text)
        or re.search(r"\[ -f [^\]\n]*\.cdx\.json[^\]\n]*\]", text)
    )


# --------------------------------------------------------------------------- #
# INV-1 — manifest format + sha256sum -c, incl. the single-platform download
# --------------------------------------------------------------------------- #
def test_INV1_manifest_format_and_c_verify(tmp_path):
    appimage = tmp_path / "finbreak-1.2.3-x86_64.AppImage"
    exe = tmp_path / "finbreak-1.2.3-x86_64.exe"
    appimage.write_bytes(b"appimage-payload-" * 64)
    exe.write_bytes(b"windows-payload-" * 64)
    sums = tmp_path / "SHA256SUMS"

    r = _run_gen(sums, appimage, exe)
    assert r.returncode == 0, f"gen-checksums.sh failed: {r.returncode} {r.stderr}"

    parsed = _parse_manifest(sums)
    assert parsed == {appimage.name: _sha256(appimage), exe.name: _sha256(exe)}

    # deterministic order: sorted by basename
    basenames = [ln.split("  ", 1)[1] for ln in sums.read_text().splitlines()]
    assert basenames == sorted(basenames)

    # both present -> -c passes
    assert _sha256sum_c(tmp_path).returncode == 0

    # a flipped byte -> -c fails
    orig = appimage.read_bytes()
    appimage.write_bytes(bytes([orig[0] ^ 0x01]) + orig[1:])
    assert _sha256sum_c(tmp_path).returncode != 0
    appimage.write_bytes(orig)  # restore for the single-platform leg

    # single-platform reality: only one artifact present. plain -c FAILS on the
    # missing other-platform line; --ignore-missing PASSES (the documented flag).
    exe.unlink()
    assert _sha256sum_c(tmp_path).returncode != 0
    ign = _sha256sum_c(tmp_path, "--ignore-missing")
    assert ign.returncode == 0, ign.stderr


# --------------------------------------------------------------------------- #
# INV-2 — merge preserves prior lines (add exe to an AppImage-only manifest)
# --------------------------------------------------------------------------- #
def test_INV2_merge_preserves_prior_lines(tmp_path):
    appimage = tmp_path / "finbreak-9.9.9-x86_64.AppImage"
    appimage.write_bytes(b"linux-appimage-" * 80)
    sums = tmp_path / "SHA256SUMS"

    r1 = _run_gen(sums, appimage)
    assert r1.returncode == 0, r1.stderr
    appimage_hash = _parse_manifest(sums)[appimage.name]

    # phase-2 host has only the exe — the AppImage file is gone; the merge must
    # keep its line without re-reading the file (§ 3.2).
    appimage.unlink()
    exe = tmp_path / "finbreak-9.9.9-x86_64.exe"
    exe.write_bytes(b"windows-exe-" * 80)
    r2 = _run_gen(sums, exe)
    assert r2.returncode == 0, r2.stderr

    parsed = _parse_manifest(sums)
    assert appimage.name in parsed and exe.name in parsed
    assert parsed[appimage.name] == appimage_hash  # carried line byte-identical
    assert parsed[exe.name] == _sha256(exe)


# --------------------------------------------------------------------------- #
# INV-3a — the helper-produced manifest signs + verifies + is tamper-evident
# --------------------------------------------------------------------------- #
def test_INV3a_signed_manifest_roundtrip_and_tamper(tmp_path):
    gen = _load_script("gen-signing-key.py")
    sign = _load_script("sign-release.py")

    key_path = tmp_path / "finbreak-signing.key"
    pub_b64 = gen.generate_keypair(key_path)
    public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64))

    # sign the EXACT bytes the FIBR-0096 helper emits (not a hand-built string).
    artifact = tmp_path / "finbreak-1.2.3-x86_64.AppImage"
    artifact.write_bytes(b"pretend appimage bytes " * 100)
    manifest = tmp_path / "SHA256SUMS"
    r = _run_gen(manifest, artifact)
    assert r.returncode == 0, r.stderr

    sig_path = sign.sign_artifact(key_path, manifest)
    assert sig_path.name == "SHA256SUMS.sig"
    sig = sig_path.read_bytes()
    assert len(sig) == 64  # raw Ed25519 signature over the final manifest bytes

    public_key.verify(sig, manifest.read_bytes())  # the committed-key gate accepts
    tampered = bytearray(manifest.read_bytes())
    tampered[0] ^= 0x01
    with pytest.raises(InvalidSignature):
        public_key.verify(sig, bytes(tampered))


# --------------------------------------------------------------------------- #
# INV-3b — each release script double-verifies against the committed key: the
# fetched manifest before the merge, the re-signed manifest before the upload.
# --------------------------------------------------------------------------- #
def _manifest_verify_starts(text: str) -> list[int]:
    """Offsets of each heredoc that VERIFIES ``SHA256SUMS`` against the key.

    Anchored to the verify block itself -- the ``python3 -`` heredoc fed the
    manifest and its ``.sig``, whose body loads ``RELEASE_PUBLIC_KEY_B64`` and
    calls ``.verify(`` -- not to the two names appearing anywhere in a range.
    The looser form passed with the anti-laundering block deleted, because an
    ``rm -f`` of the same files and the AppImage verify also name them (full
    audit 2026-09-27, row 6).
    """
    starts = []
    for match in re.finditer(
        r'python3 - "\$DIST/SHA256SUMS" "\$DIST/SHA256SUMS\.sig" <<\'PY\'\n(.*?)\nPY\n',
        text,
        re.DOTALL,
    ):
        body = match.group(1)
        if "RELEASE_PUBLIC_KEY_B64" in body and ".verify(" in body:
            starts.append(match.start())
    return starts


@pytest.mark.parametrize(
    "script", [_RELEASE_LINUX, _RELEASE_WINDOWS], ids=lambda p: p.name
)
def test_INV3b_double_verify_gate_bound_to_position(script):
    text = script.read_text()

    merge = re.search(r"^\s*scripts/gen-checksums\.sh ", text, re.MULTILINE)
    assert merge is not None, f"{script.name}: no gen-checksums.sh merge call"
    merge_i = merge.start()

    # the gh release command that publishes the manifest
    upload_i = None
    for block in _gh_release_blocks(text):
        if "SHA256SUMS" in block:
            upload_i = text.index(block)
            break
    assert upload_i is not None, (
        f"{script.name}: no gh release command carries SHA256SUMS"
    )
    assert merge_i < upload_i, f"{script.name}: the merge must precede the upload"

    verifies = _manifest_verify_starts(text)

    # gate 1 — the FETCHED SHA256SUMS.sig verified against the committed key
    # BEFORE the merge (§ 3.3 step 3, anti-laundering). Bound to the verify block
    # itself and its position: deleting it leaves no verify before the merge.
    assert any(i < merge_i for i in verifies), (
        f"{script.name}: no fetched-manifest verify gate (SHA256SUMS.sig vs "
        "RELEASE_PUBLIC_KEY_B64) before the gen-checksums.sh merge"
    )

    # gate 2 — the RE-SIGNED SHA256SUMS.sig verified against the committed key
    # BEFORE the upload (§ 3.3 step 6). Bound to the merge->upload window.
    assert any(merge_i < i < upload_i for i in verifies), (
        f"{script.name}: no re-signed-manifest verify gate (SHA256SUMS.sig vs "
        "RELEASE_PUBLIC_KEY_B64) between the merge and the gh release upload"
    )


# --------------------------------------------------------------------------- #
# INV-4 — both release scripts publish the new artifacts
# --------------------------------------------------------------------------- #
def test_INV4_release_scripts_publish_new_artifacts():
    linux_blocks = _gh_release_blocks(_RELEASE_LINUX.read_text())
    assert linux_blocks, "release-linux.sh: no gh release command found"
    for block in linux_blocks:  # both the create and the upload --clobber branch
        assert "SHA256SUMS.sig" in block, (
            "release-linux.sh: SHA256SUMS.sig not in asset list"
        )
        assert "SHA256SUMS" in block
        assert "-linux.cdx.json" in block, (
            "release-linux.sh: linux SBOM not in asset list"
        )

    windows_blocks = _gh_release_blocks(_RELEASE_WINDOWS.read_text())
    assert windows_blocks, "release-windows.sh: no gh release command found"
    for block in windows_blocks:
        assert "SHA256SUMS.sig" in block, (
            "release-windows.sh: SHA256SUMS.sig not re-uploaded"
        )
        assert "SHA256SUMS" in block
        assert "-windows.cdx.json" in block, (
            "release-windows.sh: windows SBOM not in asset list"
        )


# --------------------------------------------------------------------------- #
# INV-5 — SBOM generated in-build, per platform, over the installed closure
# --------------------------------------------------------------------------- #
def test_INV5_linux_sbom_generated_in_build():
    src = _LINUX_FREEZE.read_text()
    assert "pip-audit==2.10.0" in src, "linux freeze must install the pinned pip-audit"
    assert "pip-audit -r" in src and "--no-deps" in src, (
        "must audit the frozen closure as-is"
    )
    assert "cyclonedx-json" in src, "SBOM must be CycloneDX JSON"
    assert "-linux.cdx.json" in src, "linux SBOM output name missing"
    assert _has_sbom_existence_guard(src), "linux SBOM has no output-existence guard"


def test_INV5_windows_sbom_generated_across_two_files():
    # File 1: the driver captures the runtime closure to a fixed handoff path.
    driver = _WIN_DRIVER.read_text()
    assert "runtime-frozen.txt" in driver, (
        "build-windows-exe.py must write the frozen closure"
    )
    assert "freeze" in driver, (
        "build-windows-exe.py must pip-freeze the runtime closure"
    )

    # File 2: the workflow audits it into a CycloneDX SBOM (bash for `|| true`).
    wf = _WIN_WORKFLOW.read_text()
    assert "pip-audit==2.10.0" in wf, (
        "windows SBOM step must install the pinned pip-audit"
    )
    assert "pip-audit -r" in wf and "--no-deps" in wf, (
        "must audit the frozen closure as-is"
    )
    assert "cyclonedx-json" in wf, "SBOM must be CycloneDX JSON"
    assert "-windows.cdx.json" in wf, "windows SBOM output name missing"
    assert "shell: bash" in wf, (
        "the `|| true` SBOM step must set shell: bash on windows-latest"
    )
    assert _has_sbom_existence_guard(wf), "windows SBOM has no output-existence guard"


# --------------------------------------------------------------------------- #
# INV-6 — SBOM names version-stamped off the single source, never hardcoded
# --------------------------------------------------------------------------- #
def test_INV6_sbom_names_stamped_off_version_env_not_literal():
    linux = _LINUX_FREEZE.read_text()
    assert "finbreak-$VERSION-linux.cdx.json" in linux, (
        "linux SBOM name must embed $VERSION"
    )
    assert not re.search(r"finbreak-\d+\.\d+\.\d+-linux\.cdx\.json", linux), (
        "linux SBOM name must not hardcode a version"
    )

    smoke = _BUILD_SMOKE.read_text()
    assert re.search(r'-e\s+"?VERSION=\$\{VERSION:-\}"?', smoke), (
        "build-smoke.sh must pass a guarded `-e VERSION=${VERSION:-}` to the container"
    )

    windows = _RELEASE_WINDOWS.read_text()
    assert "finbreak-windows.cdx.json" in windows, (
        "must reference the unversioned in-workflow SBOM"
    )
    assert "finbreak-$VERSION-windows.cdx.json" in windows, (
        "release-windows.sh must rename the SBOM to a $VERSION-stamped name on download"
    )
    assert not re.search(r"finbreak-\d+\.\d+\.\d+-windows\.cdx\.json", windows), (
        "windows SBOM name must not hardcode a version"
    )


# --------------------------------------------------------------------------- #
# INV-7 — the signed manifest earns a security-model note + INV-13 definition
# --------------------------------------------------------------------------- #
def test_INV7_security_model_records_signed_manifest_inv13():
    doc = _SECURITY_MODEL.read_text()
    assert "SHA256SUMS" in doc, (
        "security-model.md is missing the signed-SHA256SUMS note"
    )

    idx = doc.find("INV-13")
    assert idx != -1, "security-model.md has no INV-13 definition"
    para = doc[idx : idx + 800]
    assert "SHA256SUMS" in para, "INV-13 must name the signed SHA256SUMS manifest"
    assert re.search(r"sign|Ed25519", para, re.IGNORECASE), (
        "INV-13 must describe the manifest as Ed25519-signed"
    )


# --------------------------------------------------------------------------- #
# FIBR-0184 — the tag `gh release create` makes remotely must land locally too
# --------------------------------------------------------------------------- #
def test_FIBR0184_release_linux_fetches_the_tag_it_published():
    """The script never runs `git tag` — `gh release create` creates the ref on
    the REMOTE. Without a fetch the local clone has no such tag, so the very next
    step (.claude/bump.json's Flatpak `commit:` re-pin, which resolves
    `git rev-parse v<NEW>^{commit}`) fails on a ref that demonstrably exists."""
    # Comment-blind: this file's own prose names both commands, and so do the
    # script's explanatory comments — scan the executable lines only.
    text = "\n".join(
        line
        for line in _RELEASE_LINUX.read_text().splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "git tag" not in text, (
        "release-linux.sh now tags locally — this test's premise (the tag is "
        "created remotely by gh) no longer holds; re-check the fetch is still needed"
    )
    create_at = text.index("gh release create")
    tail = text[create_at:]
    assert "git fetch" in tail and "--tags" in tail, (
        "release-linux.sh: no `git fetch --tags` after the release is published, "
        "so the published tag never reaches the local clone (FIBR-0184)"
    )


# --------------------------------------------------------------------------- #
# INV-8 — each release script reads its assets back after publishing and fails
# loudly on an incomplete set (FIBR-0275). Source-scrape, mirroring INV-3b/4:
# find the post-publish `gh release view --json assets` call, then scrape from
# there to EOF for the phase-correct count, a per-.sig subject-presence
# construct, the platform-correct asset_suffix() literal(s), and a failure
# path that actually aborts rather than being swallowed.
# --------------------------------------------------------------------------- #
_SIG_SUBJECT_CONSTRUCT = re.compile(
    r"%\.sig\b"  # bash ${name%.sig} — strip the .sig suffix
    r'|\*\.sig["\')\s]*\)'  # case ... *.sig) — match .sig entries specifically
    r'|endswith\(\s*"\.sig"\s*\)'  # jq: select(endswith(".sig"))
    r'|sub\(\s*"\\\\\.sig\$?"'  # jq: sub("\\.sig$"; "")
    r"|sed[^\n]*\\\.sig\$"  # sed 's/\.sig$//'
)

_INV8_CASES = [
    pytest.param(
        _RELEASE_LINUX,
        5,
        ["AppImage"],
        id="release-linux.sh",
    ),
    pytest.param(
        _RELEASE_WINDOWS,
        8,
        ["AppImage", "-x86_64.exe"],
        id="release-windows.sh",
    ),
]


@pytest.mark.parametrize("script, expected_count, name_patterns", _INV8_CASES)
def test_INV8_post_publish_readback_present_and_positioned(
    script, expected_count, name_patterns
):
    """Check 1 (§ INV-8): a `gh release view … --json assets` read-back exists,
    strictly after the script's publish command — this is what v0.1.20 (0
    assets, unnoticed 10 days) and v0.1.21 (a silently partial --clobber) had
    neither of."""
    text = script.read_text()
    found = _post_publish_readback(text)
    assert found is not None, (
        f"{script.name}: no post-publish asset read-back found (expected a "
        "`gh release view <TAG> --json assets` call AFTER the `gh release "
        "create`/`upload` command that publishes this phase's assets) — this "
        "is the FIBR-0275 gap: v0.1.20 published a release with 0 assets and "
        "nothing noticed for 10 days"
    )


@pytest.mark.parametrize("script, expected_count, name_patterns", _INV8_CASES)
def test_INV8_readback_checks_the_phase_correct_asset_count(
    script, expected_count, name_patterns
):
    """Check 2 (§ INV-8): the guard compares the read-back to ITS OWN phase's
    total — 5 after release-linux.sh, 8 after release-windows.sh (never 8
    after the Linux phase, which would leave that phase permanently red)."""
    text = script.read_text()
    found = _post_publish_readback(text)
    assert found is not None, (
        f"{script.name}: no post-publish read-back (see INV-8 check 1)"
    )
    _, guard = found

    count_check = re.search(
        rf"(?:-eq|-ne|==|!=|>=|<=)\s*\"?\$?\{{?{expected_count}\b"
        rf"|length\)?\s*(?:==|!=)\s*{expected_count}\b",
        guard,
    )
    assert count_check, (
        f"{script.name}: post-publish read-back does not compare the asset "
        f"count against {expected_count} (this script's own phase total) — "
        "a bare read-back that never checks the count would not have caught "
        "v0.1.20's 0-asset release"
    )


@pytest.mark.parametrize("script, expected_count, name_patterns", _INV8_CASES)
def test_INV8_readback_checks_every_sig_has_its_subject(
    script, expected_count, name_patterns
):
    """Check 3 (§ INV-8): every `.sig` asset's subject (the artifact it signs)
    must also be present. A bare count is not enough — the v0.1.21 failure
    left 5 assets on the release (SHA256SUMS.sig without SHA256SUMS, .exe.sig
    without .exe, plus 3 others), a count a naive `-eq` guard would have
    accepted outright."""
    text = script.read_text()
    found = _post_publish_readback(text)
    assert found is not None, (
        f"{script.name}: no post-publish read-back (see INV-8 check 1)"
    )
    _, guard = found

    assert ".sig" in guard, (
        f"{script.name}: post-publish read-back never mentions `.sig` at all "
        "— it cannot be checking that every signature's subject is present"
    )
    assert _SIG_SUBJECT_CONSTRUCT.search(guard), (
        f"{script.name}: post-publish read-back mentions `.sig` but has no "
        "recognisable per-signature subject-presence construct (a "
        "`${name%.sig}`-style strip, a `*.sig)` case arm, or an "
        '`endswith(".sig")`/`sub("\\\\.sig$";...)` jq filter) — the '
        "v0.1.21 defect was exactly a `.sig` published with its subject "
        "silently missing, which a bare asset COUNT does not catch"
    )


@pytest.mark.parametrize("script, expected_count, name_patterns", _INV8_CASES)
def test_INV8_readback_checks_names_the_updater_actually_greps_for(
    script, expected_count, name_patterns
):
    """Check 4 (§ INV-8): each asset name is checked against what the in-app
    updater greps for — AppImageInstaller/WindowsInstaller.asset_suffix()
    (src/finbreak/services/update_installer.py): `-x86_64.AppImage` and
    `-x86_64.exe`. `.claude/bump.json` already warns in prose that a
    mis-named `.exe` is invisible to the updater with "no automated guard"."""
    text = script.read_text()
    found = _post_publish_readback(text)
    assert found is not None, (
        f"{script.name}: no post-publish read-back (see INV-8 check 1)"
    )
    _, guard = found

    for pattern in name_patterns:
        assert pattern in guard, (
            f"{script.name}: post-publish read-back never checks an asset "
            f"name against {pattern!r} (an asset_suffix() the in-app updater "
            "greps for) — a mis-named artifact would publish successfully "
            "and stay invisible to the updater, exactly what .claude/bump.json "
            "already warns has 'no automated guard'"
        )


@pytest.mark.parametrize("script, expected_count, name_patterns", _INV8_CASES)
def test_INV8_readback_failure_actually_aborts_not_swallowed(
    script, expected_count, name_patterns
):
    """Check 5 (§ INV-8): an incomplete-set finding must abort the script
    (propagate non-zero under `set -euo pipefail`), not be swallowed by a
    `|| true` or discarded. A check that cannot fail the script is
    indistinguishable from no check at all — which is what let v0.1.20 and
    v0.1.21 both ship unnoticed even though nothing here was hidden from a
    human who thought to look."""
    text = script.read_text()
    found = _post_publish_readback(text)
    assert found is not None, (
        f"{script.name}: no post-publish read-back (see INV-8 check 1)"
    )
    _, guard = found

    assert "|| true" not in guard, (
        f"{script.name}: post-publish read-back region contains `|| true`, "
        "which swallows a non-zero exit — a guard that cannot fail the "
        "script is indistinguishable from no guard at all"
    )
    assert re.search(r"\bexit\s+[1-9]\d*\b", guard), (
        f"{script.name}: post-publish read-back region has no `exit <nonzero>` "
        "— under `set -euo pipefail` a failed check must still actually abort "
        "the script for 'fail loudly' to mean anything"
    )


# --------------------------------------------------------------------------- #
# FIBR-0327 — the read-back gate is REACHABLE, and the bump is pushed
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "script", [_RELEASE_LINUX, _RELEASE_WINDOWS], ids=lambda p: p.name
)
def test_FIBR0327_a_failed_publish_still_reaches_the_readback_gate(script):
    """FIBR-0327 — the gate was present, positioned and able to abort, and it
    still never ran on the failure it was written for.

    Under ``set -euo pipefail`` the publish command's own non-zero status ends
    the script on the spot. ``--clobber`` deletes each existing asset before
    replacing it, so a 503 part-way down the list leaves the release SHORT --
    measured on 0.1.21, which ended up carrying SHA256SUMS.sig without
    SHA256SUMS. That is precisely the state the gate reports, and the script
    died before reaching it.

    Structural, like its INV-8 siblings above: executing these scripts needs a
    GitHub release, a signing key and a built AppImage. What it pins is the one
    property the bug violated -- EVERY publish command captures its exit status
    rather than being allowed to end the script.
    """
    text = script.read_text()
    # Fold the two continuation forms so each publish command is one logical line.
    joined = re.sub(r"\\\s*\n\s*", " ", text)
    joined = re.sub(r"\|\|\s*\n\s*", "|| ", joined)

    commands = re.findall(
        r"^\s*gh release (?:create|upload) [^\n]*", joined, re.MULTILINE
    )
    assert commands, f"{script.name}: no publish command found"
    for command in commands:
        assert "UPLOAD_RC=$?" in command, (
            f"{script.name}: a publish command leaves its exit status to "
            "`set -e`, so a failure there skips the read-back gate:\n"
            f"  {command.strip()}"
        )
    assert re.search(r'if \[ "\$UPLOAD_RC" -ne 0 \]', text), (
        f"{script.name}: capturing the status buys nothing unless a failed "
        "publish is reported"
    )


def test_FIBR0327_release_linux_requires_the_bump_to_be_pushed():
    """FIBR-0327 — the dirty-tree check's own message says "commit + push", and
    it tested only ``git status --porcelain``.

    The tag is created on the REMOTE, off the remote's HEAD, so a committed but
    unpushed bump passed the gate and then tagged the PRE-bump commit --
    publishing assets built from a version the tag does not point at. Nothing
    caught it, and .claude/bump.json's own notes recorded the gap.

    The fetch is part of the contract: without it ``@{u}`` is whatever this clone
    last saw, so the comparison answers a stale question.
    """
    text = _RELEASE_LINUX.read_text()
    assert "git fetch --quiet origin" in text, (
        "release-linux.sh must refresh the upstream ref before comparing "
        "against it, or the unpushed check reads a stale @{u}"
    )
    assert "git rev-list --count '@{u}..HEAD'" in text, (
        "release-linux.sh must refuse an unpushed HEAD: the tag is created on "
        "the remote, so an unpushed bump tags the pre-bump commit"
    )
    fetch_at = text.index("git fetch --quiet origin")
    # The INVOCATION, not the header comment that also names the script.
    build_match = re.search(r"^scripts/build-release-appimage\.sh", text, re.MULTILINE)
    assert build_match is not None, "release-linux.sh no longer runs the build"
    build_at = build_match.start()
    assert fetch_at < build_at, (
        "the check must come before the multi-minute build, not after it"
    )


# --------------------------------------------------------------------------- #
# Full audit 2026-09-27 row 41 — the AppImage is built from the commit the tag
# names. EXECUTED, not scraped: the real script runs in a throwaway repo with a
# stub `gh` and a stub build that only records it was reached.
# --------------------------------------------------------------------------- #
_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
}


def _git(cwd: Path, *args: str) -> str:
    import os

    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **_GIT_ENV},
    ).stdout.strip()


def _release_sandbox(tmp_path: Path) -> Path:
    """A clone whose origin is a local bare repo, carrying just enough for
    release-linux.sh's preconditions: every version-bearing file at 1.2.3, the
    real script, and a build stub that drops a marker and fails. The stub `gh`
    lives outside the clone, so the tree stays clean."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    work = tmp_path / "work"
    _git(tmp_path, "clone", "-q", str(origin), str(work))
    for rel, text in {
        "src/finbreak/__init__.py": '__version__ = "1.2.3"\n',
        "pyproject.toml": 'version = "1.2.3"\n',
        "tests/test_smoke.py": 'assert __version__ == "1.2.3"\n',
        "CHANGELOG.md": "## [1.2.3] - 2026-01-01\n",
        "README.md": "Current version: **1.2.3**\n",
        "packaging/obs/io.github.milnet01.finbreak.metainfo.xml": (
            '<release version="1.2.3" date="2026-01-01">\n'
        ),
        "packaging/obs/debian/changelog": "finbreak (1.2.3) unstable\n",
        "packaging/flatpak/io.github.milnet01.finbreak.yaml": "tag: v1.2.3\n",
        "packaging/obs/_service": '<param name="revision">v1.2.3</param>\n',
        ".claude/bump.json": (_REPO_ROOT / ".claude" / "bump.json").read_text(),
        ".gitignore": "build-started\n",
        "scripts/build-release-appimage.sh": "#!/bin/sh\ntouch build-started\nexit 3\n",
    }.items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(text)
    (work / "scripts" / "release-linux.sh").write_bytes(_RELEASE_LINUX.read_bytes())
    for name in ("release-linux.sh", "build-release-appimage.sh"):
        (work / "scripts" / name).chmod(0o755)
    stubs = tmp_path / "bin"
    stubs.mkdir()
    (stubs / "gh").write_text("#!/bin/sh\nexit 1\n")  # every release: not found
    (stubs / "gh").chmod(0o755)
    _commit_and_push(work, "one")
    return work


def _commit_and_push(work: Path, message: str) -> None:
    (work / f"{message}.txt").write_text(message)
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", message)
    _git(work, "push", "-q", "origin", "HEAD")


def _tag_head(work: Path) -> None:
    _git(work, "tag", "-a", "v1.2.3", "-m", "v1.2.3")
    _git(work, "push", "-q", "origin", "v1.2.3")


def _run_release(work: Path) -> subprocess.CompletedProcess[str]:
    import os
    import sys

    stubs = work.parent / "bin"
    env = {
        **os.environ,
        **_GIT_ENV,
        # The venv's interpreter first: the script's precondition imports
        # cryptography through a bare `python3`.
        "PATH": f"{stubs}:{Path(sys.executable).parent}:{os.environ['PATH']}",
        "FINBREAK_SIGNING_KEY": "unused",
    }
    return subprocess.run(
        ["scripts/release-linux.sh"],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_release_linux_refuses_when_the_tag_names_another_commit(tmp_path):
    """cut-release creates the tag before release-linux.sh runs, and the script
    only refused UNPUSHED commits. A commit pushed after the tag was frozen into
    the AppImage for a version whose tag points elsewhere."""
    work = _release_sandbox(tmp_path)
    _tag_head(work)
    _commit_and_push(work, "pushed-after-the-tag")

    result = _run_release(work)

    assert result.returncode != 0
    assert not (work / "build-started").exists(), (
        "the build ran from a commit the tag does not name:\n" + result.stderr
    )
    assert "v1.2.3" in result.stderr and "tag" in result.stderr, result.stderr


def test_release_linux_refuses_a_checkout_behind_the_pushed_branch(tmp_path):
    """No tag yet: `gh release create` tags the REMOTE's head, so a clone BEHIND
    it built one commit and published a tag on another. Counting unpushed
    commits only ever caught the ahead case."""
    work = _release_sandbox(tmp_path)
    _commit_and_push(work, "two")
    _git(work, "reset", "-q", "--hard", "HEAD~1")

    result = _run_release(work)

    assert result.returncode != 0
    assert not (work / "build-started").exists(), result.stderr


def test_release_linux_still_builds_when_the_tag_is_head(tmp_path):
    """The control: a checkout at the pushed tip, with the tag on it, reaches the
    build — so the two refusals above are about the mismatch and nothing else."""
    work = _release_sandbox(tmp_path)
    _tag_head(work)

    result = _run_release(work)

    assert (work / "build-started").exists(), result.stderr


def test_release_linux_builds_from_a_detached_checkout_of_the_tag(tmp_path):
    """The refusal's own advice is `git checkout <tag>`, which leaves no branch
    and so no upstream. The script must accept that, or its fix is unfollowable."""
    work = _release_sandbox(tmp_path)
    _tag_head(work)
    _commit_and_push(work, "pushed-after-the-tag")
    _git(work, "checkout", "-q", "v1.2.3")

    result = _run_release(work)

    assert (work / "build-started").exists(), result.stderr


def test_release_linux_checks_every_file_bump_json_checks(tmp_path):
    """FIBR-0399: the lockstep check said it mirrored bump.json's post_check
    and tested four of its files. A Flatpak tag left on the old version passed
    it and reached the build."""
    work = _release_sandbox(tmp_path)
    flatpak = work / "packaging/flatpak/io.github.milnet01.finbreak.yaml"
    flatpak.write_text("tag: v1.2.2\n")
    _commit_and_push(work, "half-bumped")
    _tag_head(work)

    result = _run_release(work)

    assert result.returncode != 0
    assert not (work / "build-started").exists(), result.stderr
    assert "DRIFT" in result.stderr, result.stderr


def test_release_linux_refuses_while_another_release_run_holds_the_lock(tmp_path):
    """FIBR-0399: both release scripts merge SHA256SUMS, so two at once lose a
    line. A second run refuses before it builds anything."""
    import fcntl

    work = _release_sandbox(tmp_path)
    _tag_head(work)
    lock_path = work / ".git" / "finbreak-release.lock"
    with open(lock_path, "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        result = _run_release(work)

    assert result.returncode != 0
    assert not (work / "build-started").exists(), result.stderr
    assert "another release" in result.stderr, result.stderr


def test_release_windows_takes_the_same_lock():
    text = _RELEASE_WINDOWS.read_text()
    assert 'finbreak-release.lock"' in text and "flock -n" in text


# --------------------------------------------------------------------------- #
# FIBR-0399 — release-windows.sh, EXECUTED with a stub `gh` that logs its calls.
# --------------------------------------------------------------------------- #
_WINDOWS_GH_STUB = """#!/bin/sh
echo "$*" >> "$GH_LOG"
case "$1 $2" in
  "release view") exit 0 ;;
  "run list") echo 100 ;;
  "workflow run") exit 0 ;;
  "run view")
    case "$*" in *conclusion*) echo success ;; *) echo "$GH_RUN_SHA" ;; esac ;;
  "run watch") exit 0 ;;
  *) exit 1 ;;
esac
"""


def _windows_sandbox(tmp_path: Path, *, tagged: bool) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q")
    (work / "src/finbreak").mkdir(parents=True)
    (work / "src/finbreak/__init__.py").write_text('__version__ = "1.2.3"\n')
    (work / "scripts").mkdir()
    script = work / "scripts" / "release-windows.sh"
    script.write_bytes(_RELEASE_WINDOWS.read_bytes())
    script.chmod(0o755)
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "one")
    if tagged:
        _git(work, "tag", "-a", "v1.2.3", "-m", "v1.2.3")
    stubs = tmp_path / "bin"
    stubs.mkdir()
    (stubs / "gh").write_text(_WINDOWS_GH_STUB)
    (stubs / "gh").chmod(0o755)
    return work


def _run_windows(
    work: Path, *args: str, run_sha: str = ""
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    import os
    import sys

    log = work.parent / "gh.log"
    env = {
        **os.environ,
        **_GIT_ENV,
        "PATH": f"{work.parent / 'bin'}:{Path(sys.executable).parent}:"
        f"{os.environ['PATH']}",
        "FINBREAK_SIGNING_KEY": "unused",
        "GH_LOG": str(log),
        "GH_RUN_SHA": run_sha,
        "RELEASE_RETRY_SLEEP": "0",
    }
    result = subprocess.run(
        ["scripts/release-windows.sh", *args],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    calls = log.read_text().splitlines() if log.exists() else []
    return result, calls


def test_release_windows_refuses_a_missing_tag_before_dispatching(tmp_path):
    """FIBR-0399: the tag was resolved after the dispatch, so a missing local
    tag stopped the script with a Windows build already started."""
    work = _windows_sandbox(tmp_path, tagged=False)

    result, calls = _run_windows(work)

    assert result.returncode != 0
    assert not any(c.startswith("workflow run") for c in calls), calls
    assert "v1.2.3" in result.stderr, result.stderr


def test_release_windows_resumes_a_run_and_retries_its_calls(tmp_path):
    """FIBR-0399: a transient error on `gh run view/watch/download` threw away a
    finished build. --run-id resumes it without a second dispatch, and each
    of those calls is retried before the script gives up."""
    work = _windows_sandbox(tmp_path, tagged=True)
    tag_sha = _git(work, "rev-parse", "v1.2.3^{commit}")

    result, calls = _run_windows(work, "--run-id", "555", run_sha=tag_sha)

    assert result.returncode != 0  # the stub download always fails
    assert not any(c.startswith("workflow run") for c in calls), calls
    assert any(c.startswith("run view 555") for c in calls), calls
    downloads = [c for c in calls if c.startswith("run download 555")]
    assert len(downloads) == 3, calls


def test_release_windows_readback_checks_the_exact_eight_names():
    """FIBR-0399: the gate counted eight without naming them, so a stray extra
    asset failed it and a stand-in with the right count passed."""
    found = _post_publish_readback(_RELEASE_WINDOWS.read_text())
    assert found is not None
    _, guard = found
    for name in (
        '"$APPIMAGE"',
        '"$APPIMAGE.sig"',
        '"$EXE"',
        '"$EXE.sig"',
        "SHA256SUMS",
        "SHA256SUMS.sig",
        '"finbreak-$VERSION-linux.cdx.json"',
        '"finbreak-$VERSION-windows.cdx.json"',
    ):
        assert name in guard, name
    assert "UNEXPECTED" in guard, "an asset outside the eight must fail the gate"


def test_release_linux_creates_the_release_on_the_commit_it_built():
    """The create branch: without --target, GitHub tags the default branch's
    head, which need not be the commit the AppImage came from."""
    text = _RELEASE_LINUX.read_text()
    joined = re.sub(r"\\\s*\n\s*", " ", text)
    create = re.search(r"^\s*gh release create [^\n]*", joined, re.MULTILINE)
    assert create is not None
    assert '--target "$HEAD_SHA"' in create.group(0), create.group(0)


# --------------------------------------------------------------------------- #
# Full audit 2026-09-27 row 42 — a release that EXISTS but lists no SHA256SUMS
# is not a fresh start unless nothing else says a manifest was ever published.
# --------------------------------------------------------------------------- #
_FRESH_GUARD = _SCRIPTS / "_manifest-may-start-fresh.sh"


def _may_start_fresh(tmp_path: Path, assets: list[str], other: str) -> int:
    listing = tmp_path / "assets.txt"
    listing.write_text("".join(f"{name}\n" for name in assets))
    return subprocess.run(
        [str(_FRESH_GUARD), str(listing), other], capture_output=True, text=True
    ).returncode


@pytest.mark.parametrize(
    ("assets", "other", "fresh"),
    [
        # cut-release made the release; nothing is attached yet -> fresh.
        ([], "*.exe", True),
        # The 0.1.21 half-state: the sig survived a failed --clobber, the
        # manifest did not. A fresh one drops the other platform's line.
        (["SHA256SUMS.sig"], "*.exe", False),
        # Linux re-run after the Windows half landed without a manifest.
        (
            ["finbreak-1.2.3-x86_64.exe", "finbreak-1.2.3-x86_64.exe.sig"],
            "*.exe",
            False,
        ),
        # Windows run after the Linux half: same, the other way round.
        (["finbreak-1.2.3-x86_64.AppImage"], "*.AppImage", False),
        # This platform's own leftovers are replaced, so they do not block.
        (["finbreak-1.2.3-x86_64.AppImage"], "*.exe", True),
    ],
    ids=["empty", "orphan-sig", "linux-sees-exe", "windows-sees-appimage", "own-only"],
)
def test_a_release_without_sha256sums_starts_fresh_only_when_unambiguous(
    tmp_path, assets, other, fresh
):
    assert (_may_start_fresh(tmp_path, assets, other) == 0) is fresh


@pytest.mark.parametrize(
    ("script", "other"),
    [(_RELEASE_LINUX, "'*.exe'"), (_RELEASE_WINDOWS, "'*.AppImage'")],
    ids=lambda v: getattr(v, "name", v),
)
def test_both_release_scripts_ask_the_guard_before_a_fresh_manifest(script, other):
    """The guard does nothing unless both scripts call it on the existing-release
    branch that finds no SHA256SUMS, naming the OTHER platform's artifact."""
    text = script.read_text()
    call = f'scripts/_manifest-may-start-fresh.sh "$VIEW_ASSETS" {other}'
    assert call in text, f"{script.name} does not call the guard as {call}"
    listed = text.index('if grep -qx SHA256SUMS "$VIEW_ASSETS"; then')
    not_found = text.index('elif grep -qi "release not found" "$VIEW_ERR"; then')
    assert listed < text.index(call) < not_found, (
        f"{script.name}: the guard must sit on the existing-release branch"
    )


def test_build_smoke_prints_no_hand_publish_recipe():
    """Full audit 2026-09-27 row 43 — every release-linux.sh run printed, part
    way through, a `gh release create` attaching two of the eight assets: the
    recipe for the short release FIBR-0203 and FIBR-0275 record. An operator who
    followed it after a later gate refused published a broken --latest release.
    The build now names the script that publishes, and nothing to type."""
    text = (_SCRIPTS / "build-smoke.sh").read_text()
    echoes = [line for line in text.splitlines() if line.lstrip().startswith("echo")]
    assert not any("gh release" in line for line in echoes), [
        line for line in echoes if "gh release" in line
    ]
    assert any("release-linux.sh" in line for line in echoes), (
        "the build must say which script publishes"
    )

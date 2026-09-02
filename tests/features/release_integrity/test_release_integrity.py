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
@pytest.mark.parametrize(
    "script", [_RELEASE_LINUX, _RELEASE_WINDOWS], ids=lambda p: p.name
)
def test_INV3b_double_verify_gate_bound_to_position(script):
    text = script.read_text()

    merge_i = text.find("gen-checksums.sh")
    assert merge_i != -1, f"{script.name}: no gen-checksums.sh merge call"

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

    before_merge = text[:merge_i]
    between = text[merge_i:upload_i]

    # gate 1 — the FETCHED SHA256SUMS.sig verified against the committed key
    # BEFORE the merge (§ 3.3 step 3, anti-laundering). Bound to its subject +
    # position: deleting it strips the only SHA256SUMS.sig verify before merge.
    assert (
        "SHA256SUMS.sig" in before_merge and "RELEASE_PUBLIC_KEY_B64" in before_merge
    ), (
        f"{script.name}: no fetched-manifest verify gate (SHA256SUMS.sig vs "
        "RELEASE_PUBLIC_KEY_B64) before the gen-checksums.sh merge"
    )

    # gate 2 — the RE-SIGNED SHA256SUMS.sig verified against the committed key
    # BEFORE the upload (§ 3.3 step 6). Bound to the merge->upload window.
    assert "SHA256SUMS.sig" in between and "RELEASE_PUBLIC_KEY_B64" in between, (
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
    build_at = re.search(
        r"^scripts/build-release-appimage\.sh", text, re.MULTILINE
    ).start()
    assert fetch_at < build_at, (
        "the check must come before the multi-minute build, not after it"
    )

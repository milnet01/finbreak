"""FIBR-0001 INV-1/INV-2 — the gate's stage list matches its own spec.

Enforces tests/features/harness/spec.md.

The gate judges every other change and nothing judged the gate. Both halves
drifted on 2026-08-05: `FIBR-0001`'s stage table went stale twice (it never
recorded `mypy` from `FIBR-0061`, then described a `ci.yml` shape that had not
existed since the workflow moved into a container), and the `shellcheck` stage
shipped globbing `scripts/*.sh` while its own rationale claimed it covered the
release publish path — it missed the seven `packaging/` recipes entirely.

Prose in a spec cannot catch either. Reading both files and comparing them can.
No network, no vault, no Qt.
"""

import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.features

_ROOT = Path(__file__).resolve().parents[3]
_GATE = _ROOT / "scripts" / "ci-local.sh"
_SPEC = _ROOT / "docs" / "specs" / "FIBR-0001.md"
_CI_YML = _ROOT / ".github" / "workflows" / "ci.yml"

# A stage is announced by `echo "== <name> =="` in the script — the one marker
# that is unambiguous. Matching invocations instead would drag in every helper
# call and every mention inside a comment.
#
# `\s*` is load-bearing, not defensive: the pytest stage announces itself from
# inside an if/else (its label changes when the build smoke-test is opted in),
# so those two echoes are indented. Anchoring at `^echo` silently dropped
# pytest and left the set one short.
_STAGE_ECHO = re.compile(r'^\s*echo "== ([a-z0-9-]+)', re.MULTILINE)

# The spec's INV-1 table rows: `| <n> | `<command>` | <added-by> |`. Only the
# first token of the command is compared — the tool name. Flags are checked
# separately (INV-2) where they are load-bearing; comparing whole command
# strings would make this test fail on a cosmetic edit to either file, and a
# brittle guard gets deleted rather than fixed.
_TABLE_ROW = re.compile(r"^\s*\|\s*\d+\s*\|\s*`([a-z0-9-]+)", re.MULTILINE)


def _script() -> str:
    return _GATE.read_text(encoding="utf-8")


def _spec() -> str:
    return _SPEC.read_text(encoding="utf-8")


def _stages_in_script() -> set[str]:
    # The pytest stage announces itself under two different labels depending on
    # whether the build smoke-test is opted in; both mean the same stage.
    return {name.split()[0] for name in _STAGE_ECHO.findall(_script())}


def _stages_in_spec() -> set[str]:
    return set(_TABLE_ROW.findall(_spec()))


# --------------------------------------------------------------------------- #
# INV-1 — the two lists agree, as an unordered set
# --------------------------------------------------------------------------- #
def test_INV1_every_spec_stage_is_invoked_by_the_gate() -> None:
    """A stage in the contract that the script never runs is a gate that does
    less than it promises — the failure mode `FIBR-0061` and `FIBR-0225` each
    created and nothing caught."""
    missing = _stages_in_spec() - _stages_in_script()
    assert not missing, (
        f"FIBR-0001 INV-1's table lists {sorted(missing)}, which "
        f"scripts/ci-local.sh does not run. Either wire the stage up or "
        f"remove the row — the table is the contract."
    )


def test_INV1_every_gate_stage_is_declared_in_the_spec() -> None:
    """The other direction: a stage running in the gate that the contract does
    not mention. Harmless to the build, but it means the spec has stopped
    describing the gate — which is how INV-1 went stale twice in one day."""
    undeclared = _stages_in_script() - _stages_in_spec()
    assert not undeclared, (
        f"scripts/ci-local.sh runs {sorted(undeclared)}, absent from "
        f"FIBR-0001 INV-1's stage table. Add a row (with the item that "
        f"introduced it) so the contract still describes the gate."
    )


def test_INV1_the_comparison_is_not_vacuous() -> None:
    """Both parsers must actually find something. A regex that silently stops
    matching turns the two assertions above into tests that pass on an empty
    set — the most convincing false pass there is. (Both bounds were wrong when
    first written: one regex lacked `re.MULTILINE` and matched nothing, and the
    expected count ignored that `ruff` runs twice. This guard is why that
    surfaced here instead of as a permanently-green pair of assertions.)

    Nine distinct tool NAMES across eleven stages — two tools run twice:
    `ruff` as `check` and as `format --check`, and `pip-audit` against
    each of its two vulnerability services (`-s pypi`, `-s osv`).

    That both parsers key on the tool name alone is why adding the second
    `pip-audit` stage moved the row count and left the name count where it
    was; a bound that tracked only names would not have noticed the stage
    at all.
    """
    assert len(_TABLE_ROW.findall(_spec())) == 11, (
        "INV-1's stage table no longer has 11 rows — update this bound "
        "deliberately when a stage is added or removed."
    )
    assert len(_stages_in_spec()) == 9, "INV-1 table parse found the wrong names"
    assert len(_stages_in_script()) == 9, "gate stage parse found the wrong names"


# --------------------------------------------------------------------------- #
# INV-2 — gitleaks keeps --redact (this repo is public)
# --------------------------------------------------------------------------- #
def test_INV2_gitleaks_stage_redacts() -> None:
    """`--redact` is security-load-bearing, not cosmetic: finbreak's repo is
    public, so CI logs are world-readable. Without it a real finding prints the
    matched secret verbatim and the stage meant to CATCH a leak publishes it.
    Dropped from the spec's own table during cold-eyes loop 1 and caught in
    loop 2 — hence a test rather than a comment."""
    line = next(
        (ln for ln in _script().splitlines() if ln.strip().startswith("gitleaks ")),
        None,
    )
    assert line is not None, "no gitleaks invocation found in scripts/ci-local.sh"
    assert "--redact" in line, (
        f"the gitleaks stage lost --redact: {line.strip()!r}. On a public repo "
        f"that prints any matched secret into a world-readable CI log."
    )


def test_INV2_spec_table_quotes_the_redacting_invocation() -> None:
    """The spec's table is what an implementer builds the stage from, so the
    unsafe short form must not reappear there either."""
    row = next(
        (ln for ln in _spec().splitlines() if "`gitleaks dir ." in ln),
        None,
    )
    assert row is not None, "FIBR-0001 INV-1's table has no gitleaks row"
    assert "--redact" in row, (
        "FIBR-0001 INV-1's gitleaks row omits --redact; an implementer "
        "building from the table would ship the unsafe invocation."
    )


# --------------------------------------------------------------------------- #
# INV-3 — shellcheck selects by git ls-files, not a directory glob
# --------------------------------------------------------------------------- #
def test_INV3_shellcheck_targets_every_tracked_script() -> None:
    """The first cut globbed `scripts/*.sh` and so skipped the seven packaging
    recipes under packaging/obs/ and packaging/flatpak/ — the OBS and Flathub
    publish path the stage claimed to protect. A glob has to be widened by hand
    whenever scripts appear somewhere new, and nothing reports that it went
    stale; `git ls-files` cannot."""
    script = _script()
    assert "git ls-files '*.sh'" in script, (
        "the shellcheck stage no longer selects via `git ls-files '*.sh'`. A "
        "directory glob silently skips scripts outside it — which is exactly "
        "how the packaging/ release recipes went unlinted (FIBR-0225)."
    )
    assert ".githooks/pre-push" in script, (
        "the pre-push hook is not in the shellcheck targets; it has no .sh "
        "suffix, so `git ls-files '*.sh'` does not cover it and it must be "
        "named explicitly. It is the hook that gates every push."
    )


# --------------------------------------------------------------------------- #
# INV-4 — CI invokes the script rather than restating stages
# --------------------------------------------------------------------------- #
def test_INV4_ci_invokes_the_gate_script_and_restates_no_stage() -> None:
    """FIBR-0001 INV-2: one source of truth. If ci.yml ever inlines a stage,
    the two lists can drift — which is the whole reason it shells out."""
    ci = _CI_YML.read_text(encoding="utf-8")
    assert "./scripts/ci-local.sh" in ci, "ci.yml no longer invokes the gate script"
    # A stage name appearing as its own `run:` command means CI has started
    # re-listing stages. Checked against the spec's table so a newly-added
    # stage is covered automatically.
    for stage in _stages_in_spec():
        assert f"run: {stage}" not in ci, (
            f"ci.yml runs `{stage}` directly instead of via ci-local.sh — "
            f"that is a second definition of the gate list (INV-2)."
        )


# --------------------------------------------------------------------------- #
# INV-5 — the pre-push hook skips only an already-gated tag-only push          #
# --------------------------------------------------------------------------- #
#
# Read, this hook looks obviously right either way; the whole risk is in which
# ref lists it treats as safe. So these run it, with a stub gate that leaves a
# sentinel, and assert on whether the sentinel appears.
_HOOK = _ROOT / ".githooks" / "pre-push"
_ZERO = "0" * 40


# Neutralise INHERITED git configuration in the sandbox (FIBR-0306). A plain
# `git init` inherits the user's global config, and a machine-wide
# `core.hooksPath` therefore applied to this miniature repo — so the sandbox's
# own SETUP push fired somebody else's pre-push hook, which auto-discovered the
# stub `scripts/ci-local.sh` below and touched the sentinel BEFORE the
# assertions began. `test_INV5_the_sandbox_is_not_vacuous` then failed on its
# first line, and the tag-skip test failed on a sentinel it did not create.
#
# Both variables rather than `core.hooksPath` alone: pinning the one setting
# known to have leaked fixes today's symptom and leaves the next global setting
# someone adds free to do the same thing. This makes the sandbox hermetic
# against all of them.
_HERMETIC_GIT = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def _sandbox_env() -> dict[str, str]:
    return {**os.environ, **_HERMETIC_GIT}


def _hook_sandbox(tmp_path: Path) -> tuple[Path, Path, str]:
    """A repo with an origin, one pushed commit and one unpushed commit.

    Returns (worktree, sentinel path, pushed sha). The stub `ci-local.sh`
    writes the sentinel, so its presence means the gate ran.
    """
    import subprocess

    def git(*args: str, cwd: Path) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            env=_sandbox_env(),
        ).stdout.strip()

    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    origin.mkdir()
    work.mkdir()
    subprocess.run(
        ["git", "init", "--bare", "-q"], cwd=origin, check=True, env=_sandbox_env()
    )
    subprocess.run(
        ["git", "init", "-q", "-b", "main"], cwd=work, check=True, env=_sandbox_env()
    )
    git("config", "user.email", "t@example.invalid", cwd=work)
    git("config", "user.name", "t", cwd=work)

    (work / "scripts").mkdir()
    sentinel = work / "gate-ran"
    stub = work / "scripts" / "ci-local.sh"
    stub.write_text(f'#!/usr/bin/env bash\ntouch "{sentinel}"\n', encoding="utf-8")
    stub.chmod(0o755)

    (work / "a.txt").write_text("1\n", encoding="utf-8")
    git("add", "-A", cwd=work)
    git("commit", "-qm", "one", cwd=work)
    git("remote", "add", "origin", str(origin), cwd=work)
    git("push", "-q", "origin", "main", cwd=work)
    pushed = git("rev-parse", "HEAD", cwd=work)

    # A second commit that never reaches origin.
    (work / "a.txt").write_text("2\n", encoding="utf-8")
    git("commit", "-qam", "two", cwd=work)

    return work, sentinel, pushed


def _run_hook(work: Path, stdin: str) -> int:
    import shutil
    import subprocess

    hook = work / "pre-push"
    shutil.copy(_HOOK, hook)
    hook.chmod(0o755)
    return subprocess.run(
        [str(hook), "origin", "file://origin"],
        cwd=work,
        input=stdin,
        text=True,
        capture_output=True,
        env=_sandbox_env(),
    ).returncode


def test_INV5_tag_push_of_a_pushed_commit_skips_the_gate(tmp_path: Path) -> None:
    work, sentinel, pushed = _hook_sandbox(tmp_path)
    rc = _run_hook(work, f"refs/tags/v1 {pushed} refs/tags/v1 {_ZERO}\n")
    assert rc == 0
    assert not sentinel.exists(), (
        "the gate ran for a tag pointing at a commit already on the remote; "
        "that commit was gated by the push that put it there, so this is the "
        "duplicate run INV-5 exists to remove"
    )


def test_INV5_tag_push_of_an_unpushed_commit_runs_the_gate(tmp_path: Path) -> None:
    work, sentinel, _pushed = _hook_sandbox(tmp_path)
    import subprocess

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=work,
        check=True,
        capture_output=True,
        text=True,
        env=_sandbox_env(),
    ).stdout.strip()
    _run_hook(work, f"refs/tags/v2 {head} refs/tags/v2 {_ZERO}\n")
    assert sentinel.exists(), (
        "the gate was skipped for a tag whose commit is NOT on the remote — "
        "that publishes ungated code, which is the case INV-5 must not skip"
    )


def test_INV5_a_branch_ref_in_the_push_runs_the_gate(tmp_path: Path) -> None:
    work, sentinel, pushed = _hook_sandbox(tmp_path)
    _run_hook(
        work,
        f"refs/tags/v1 {pushed} refs/tags/v1 {_ZERO}\n"
        f"refs/heads/main {pushed} refs/heads/main {_ZERO}\n",
    )
    assert sentinel.exists(), (
        "a branch ref shared the push with a tag and the gate was skipped"
    )


def test_INV5_no_ref_list_runs_the_gate(tmp_path: Path) -> None:
    work, sentinel, _pushed = _hook_sandbox(tmp_path)
    _run_hook(work, "")
    assert sentinel.exists(), (
        "with no refs on stdin nothing is known about the push, so the gate "
        "must run; a hand-run hook takes this path"
    )


def test_INV5_the_sandbox_is_not_vacuous(tmp_path: Path) -> None:
    """The skip test only means something if the sentinel CAN appear."""
    work, sentinel, _pushed = _hook_sandbox(tmp_path)
    assert not sentinel.exists()
    _run_hook(work, f"refs/heads/main {_ZERO} refs/heads/main {_ZERO}\n")
    assert sentinel.exists(), (
        "the stub gate never fired at all, so every other INV-5 assertion "
        "about the sentinel proves nothing"
    )


# --------------------------------------------------------------------------- #
# FIBR-0327 — the hook gates the WORKING TREE, so it must refuse a dirty one   #
# --------------------------------------------------------------------------- #
def test_the_hook_refuses_a_dirty_tree_rather_than_gating_the_wrong_bytes(
    tmp_path: Path,
) -> None:
    """`ci-local.sh` reads the files on disk, so the hook's verdict is about the
    WORKING TREE and not about the commits being pushed. Those are the same
    thing after a commit-then-push, and different the moment anything is
    uncommitted — and the dangerous direction is real: a fix present in the
    tree but not in the commit makes the gate green about code that is not
    what reaches origin.

    Refusing is the honest answer. Gating the pushed commit itself would mean
    building it in a throwaway worktree with its own venv, which costs more
    than the case is worth; saying "this run would not be about your push" and
    stopping does not pretend otherwise.
    """
    import subprocess

    work, sentinel, _pushed = _hook_sandbox(tmp_path)
    (work / "a.txt").write_text("uncommitted\n", encoding="utf-8")

    rc = subprocess.run(
        [str(_copy_hook(work)), "origin", "file://origin"],
        cwd=work,
        input=f"refs/heads/main {'0' * 39}1 refs/heads/main {_ZERO}\n",
        text=True,
        capture_output=True,
        env=_sandbox_env(),
    )

    assert rc.returncode != 0, (
        "the hook gated a dirty tree and reported on it as though it were the "
        "push. A change present on disk but not in the commit makes this run "
        "green about bytes that never leave the machine."
    )
    assert not sentinel.exists(), "it must refuse BEFORE spending the gate"
    assert "--no-verify" in (rc.stdout + rc.stderr), (
        "a refusal with no way past it is a refusal someone works around by "
        "guessing; the message must name the escape"
    )


def test_the_hook_still_runs_the_gate_on_a_clean_tree(tmp_path: Path) -> None:
    """The other half — the ordinary commit-then-push must be untouched."""
    import subprocess

    work, sentinel, _pushed = _hook_sandbox(tmp_path)

    subprocess.run(
        [str(_copy_hook(work)), "origin", "file://origin"],
        cwd=work,
        input=f"refs/heads/main {'0' * 39}1 refs/heads/main {_ZERO}\n",
        text=True,
        capture_output=True,
        env=_sandbox_env(),
    )

    assert sentinel.exists(), (
        "a clean tree must still take the gate — refusing a dirty one must not "
        "have become refusing every one"
    )


def _copy_hook(work: Path) -> Path:
    import shutil

    hook = work / "pre-push"
    shutil.copy(_HOOK, hook)
    hook.chmod(0o755)
    return hook

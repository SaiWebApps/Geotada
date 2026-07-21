"""The post-push Render watch must never green-light a commit it did not see deployed.

Root cause locked down here: the commit-identity check was a *grace period*
(``[ "$commit" != "$head_sha" ] && [ "$i" -le 6 ]``). From poll 7 onward the
loop judged whatever deploy was newest — which, when the push produced no
deploy at all, is the PREVIOUS deploy, already ``live``. The hook printed
"✅ ... is LIVE." and exited 0, so the project's stated post-push monitor
reported success for a commit that was never deployed and nothing woke the
session. Commit identity is now a precondition for any terminal verdict.

These tests run the real shell hook against a fake ``render`` CLI on PATH and a
throwaway git repo, with the poll interval set to 0 so they stay fast.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "render-deploy-watch.sh"

_STALE_SHA = "1111111111111111111111111111111111111111"


def _fake_render(bin_dir: Path, deploy_sha: str, status: str) -> None:
    """Install a `render` CLI stub that always reports one deploy."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / "render"
    stub.write_text(
        "#!/bin/bash\n"
        'if [ "$1" = "deploys" ]; then\n'
        f'  echo \'[{{"deploy": {{"id": "dep-fake", "status": "{status}",'
        f' "commit": {{"id": "{deploy_sha}"}}}}}}]\'\n'
        "fi\n"
        "exit 0\n"
    )
    stub.chmod(0o755)


def _git_repo(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    run = lambda *a: subprocess.run(a, cwd=path, check=True, capture_output=True)  # noqa: E731
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "t")
    (path / "f.txt").write_text("hi\n")
    run("git", "add", "f.txt")
    run("git", "commit", "-qm", "c")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True
    ).stdout.strip()


def _run_hook(cwd: Path, bin_dir: Path, **extra: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "RENDER_WATCH_FORCE": "1",
            "RENDER_WATCH_POLL_SECS": "0",
            "RENDER_WATCH_MAX_POLLS": "12",
            "RENDER_WATCH_MAX_NO_MATCH_POLLS": "3",
        }
    )
    env.update(extra)
    return subprocess.run(
        ["bash", str(HOOK)], cwd=cwd, env=env, capture_output=True, text=True, timeout=60
    )


def test_stale_live_deploy_is_never_reported_as_the_pushed_commit(tmp_path: Path) -> None:
    """The bug: an old `live` deploy became a ✅ verdict for a brand-new push."""
    repo = tmp_path / "repo"
    head = _git_repo(repo)
    assert head != _STALE_SHA
    _fake_render(tmp_path / "bin", deploy_sha=_STALE_SHA, status="live")

    proc = _run_hook(repo, tmp_path / "bin")

    combined = proc.stdout + proc.stderr
    assert "LIVE" not in proc.stdout, f"stale deploy reported as live:\n{combined}"
    assert proc.returncode == 2, f"expected wake-the-session exit 2, got {proc.returncode}"
    assert "no Render deploy was created" in combined
    assert head in combined


def test_matching_live_deploy_still_passes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = _git_repo(repo)
    _fake_render(tmp_path / "bin", deploy_sha=head, status="live")

    proc = _run_hook(repo, tmp_path / "bin")

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "is LIVE" in proc.stdout


def test_matching_failed_deploy_wakes_the_session(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = _git_repo(repo)
    _fake_render(tmp_path / "bin", deploy_sha=head, status="build_failed")

    proc = _run_hook(repo, tmp_path / "bin")

    assert proc.returncode == 2
    assert "ended as: build_failed" in proc.stderr


def test_unknown_head_fails_closed(tmp_path: Path) -> None:
    """No HEAD → no way to check identity → must report, never verdict on a deploy."""
    not_a_repo = tmp_path / "loose"
    not_a_repo.mkdir()
    _fake_render(tmp_path / "bin", deploy_sha=_STALE_SHA, status="live")

    proc = _run_hook(not_a_repo, tmp_path / "bin", GIT_CEILING_DIRECTORIES=str(tmp_path))

    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "LIVE" not in proc.stdout
    assert "could not resolve HEAD" in proc.stderr


@pytest.mark.parametrize("clause", ['[ "$i" -le 6 ]', '[ -n "$head_sha" ]'])
def test_grace_period_clauses_stay_removed(clause: str) -> None:
    """Both short-circuits let a non-matching deploy reach a terminal verdict."""
    assert clause not in HOOK.read_text()

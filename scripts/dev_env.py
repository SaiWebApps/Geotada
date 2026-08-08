"""Deterministic execution environments for every supported Make target.

Production configuration is fetched fresh from Render and kept in memory.
Committed profiles contain only non-secret local overrides.  The two are
combined atomically immediately before ``exec`` so a failed local overlay can
never fall back to the production Neo4j connection.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = ROOT / "config" / "profiles"
RENDER_API = "https://api.render.com/v1"
RENDER_SERVICE_ID = "srv-d7qnivjbc2fs73fr6tqg"
KEYCHAIN_SERVICE = "ondoway-render-api-key"
KEYCHAIN_LABEL = "ondoway-dev"
PAGE_LIMIT = 100

# The profile-to-port guard below asserts a committed profile file resolves to the
# port it is supposed to. Deriving it from the profile files themselves would make
# it check a file against itself, so it is taken from preflight's database table --
# the independent statement of the same fact, and the one place a lane is defined.
# Adding a lane there is all that is needed; nothing here restates it.
try:  # run directly as `python scripts/dev_env.py` -- scripts/ is sys.path[0]
    import preflight as _preflight
except ModuleNotFoundError:  # imported as `scripts.dev_env` (pytest)
    from scripts import preflight as _preflight

_LOCAL_PROFILE_PORTS = {spec.profile: spec.port for spec in _preflight.DATABASES}


class EnvironmentError(RuntimeError):
    """Raised when a safe execution environment cannot be constructed."""


def read_profile(name: str) -> dict[str, str]:
    """Load one committed non-secret profile."""
    path = PROFILE_DIR / name
    if not path.is_file():
        raise EnvironmentError(f"unknown execution profile {name!r}: {path} does not exist")
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise EnvironmentError(f"{path}:{number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise EnvironmentError(f"{path}:{number}: empty key")
        values[key] = value.strip()
    return values


def _keychain_account() -> str:
    return os.environ.get("USER") or getpass.getuser()


def keychain_api_key() -> str:
    """Read the Render API key without echoing it.

    The macOS Keychain is preferred: the secret stays in the OS credential store
    and never appears in a shell history, a process listing, or a file.

    ``RENDER_API_KEY`` in the environment is accepted as a fallback so that Linux
    workstations and CI runners -- which have no Keychain, and on which every
    Render-backed target was previously unreachable -- can supply the credential
    the usual way. It is deliberately second, so a successful Keychain lookup
    always wins over a stale exported variable.

    Note the honest limit of that ordering: precedence is decided by whether the
    lookup SUCCEEDS, not by whether an entry exists. If the Keychain is locked or
    the prompt is cancelled, a stale ``RENDER_API_KEY`` is used instead of
    raising. The failure is visible -- Render rejects a dead key on the next
    call -- but it surfaces as an API error, not as "your Keychain is locked".
    """
    if sys.platform == "darwin":
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                _keychain_account(),
                "-s",
                KEYCHAIN_SERVICE,
                "-w",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        key = result.stdout.strip()
        if result.returncode == 0 and key:
            return key

    environment_key = os.environ.get("RENDER_API_KEY", "").strip()
    if environment_key:
        return environment_key

    if sys.platform == "darwin":
        raise EnvironmentError(
            "Render API key is not configured. Run `make render-auth-setup` once, "
            "or export RENDER_API_KEY."
        )
    raise EnvironmentError(
        "Render API key is not configured. This platform has no macOS Keychain, "
        "so export RENDER_API_KEY with a key that can read the ondoway-api service."
    )


def setup_keychain() -> None:
    """Prompt through macOS Keychain so the secret never enters this process."""
    if sys.platform != "darwin":
        raise EnvironmentError("render-auth-setup currently requires macOS Keychain")
    print(
        "Paste a Render API key when Keychain prompts twice. "
        "Create one at https://dashboard.render.com/u/settings?add-api-key="
    )
    result = subprocess.run(
        [
            "security",
            "add-generic-password",
            "-U",
            "-a",
            _keychain_account(),
            "-s",
            KEYCHAIN_SERVICE,
            "-l",
            KEYCHAIN_LABEL,
            "-j",
            "Render API key for Ondoway local development automation",
            "-w",
        ],
        check=False,
    )
    if result.returncode != 0:
        raise EnvironmentError("Keychain did not store the Render API key")
    validate_render_access()


def _request_json(path: str, api_key: str) -> Any:
    request = urllib.request.Request(
        f"{RENDER_API}{path}",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise EnvironmentError(f"Render API returned HTTP {exc.code} for {path}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise EnvironmentError(f"Render API request failed for {path}: {exc}") from exc


def _paginated(path: str, api_key: str) -> list[dict[str, Any]]:
    """Read a cursor-paginated Render collection completely."""
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        separator = "&" if "?" in path else "?"
        query = f"{path}{separator}limit={PAGE_LIMIT}"
        if cursor:
            query += f"&cursor={urllib.parse.quote(cursor, safe='')}"
        page = _request_json(query, api_key)
        if not isinstance(page, list):
            raise EnvironmentError(f"Render API returned a non-list collection for {path}")
        dict_items = [item for item in page if isinstance(item, dict)]
        items.extend(dict_items)
        if len(page) < PAGE_LIMIT:
            return items
        next_cursor = dict_items[-1].get("cursor") if dict_items else None
        if not isinstance(next_cursor, str) or not next_cursor or next_cursor == cursor:
            raise EnvironmentError(f"Render API pagination stalled for {path}")
        cursor = next_cursor


def _unwrap(item: dict[str, Any], key: str) -> dict[str, Any]:
    nested = item.get(key)
    return nested if isinstance(nested, dict) else item


def _group_values(group: dict[str, Any], api_key: str) -> dict[str, str]:
    if not isinstance(group.get("envVars"), list):
        group_id = group.get("id")
        if not isinstance(group_id, str) or not group_id:
            raise EnvironmentError("linked Render environment group has no id")
        detail = _request_json(f"/env-groups/{group_id}", api_key)
        if not isinstance(detail, dict):
            raise EnvironmentError(f"Render environment group {group_id} has invalid detail")
        group = detail
    result: dict[str, str] = {}
    for item in group.get("envVars", []):
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        value = item.get("value")
        if isinstance(key, str) and isinstance(value, str):
            result[key] = value
    return result


def fetch_render_environment(api_key: str) -> dict[str, str]:
    """Fetch the complete service environment, including linked groups."""
    merged: dict[str, str] = {}
    value_sources: dict[str, str] = {}

    groups = _paginated("/env-groups", api_key)
    for wrapper in groups:
        group = _unwrap(wrapper, "envGroup")
        links = group.get("serviceLinks", [])
        linked = any(
            isinstance(link, dict) and link.get("id") == RENDER_SERVICE_ID for link in links
        )
        if not linked:
            continue
        group_id = str(group.get("id", "<unknown>"))
        for key, value in _group_values(group, api_key).items():
            if key in merged and merged[key] != value:
                raise EnvironmentError(
                    f"linked Render environment groups conflict on {key!r}: "
                    f"{value_sources[key]} and {group_id}"
                )
            merged[key] = value
            value_sources[key] = group_id

    direct = _paginated(f"/services/{RENDER_SERVICE_ID}/env-vars", api_key)
    for wrapper in direct:
        env_var = _unwrap(wrapper, "envVar")
        key = env_var.get("key")
        value = env_var.get("value")
        if isinstance(key, str) and isinstance(value, str):
            merged[key] = value

    if not merged:
        raise EnvironmentError("Render returned an empty environment; refusing to execute")
    return merged


def validate_render_access() -> None:
    """Prove that the Keychain key can read the Ondoway service."""
    api_key = keychain_api_key()
    services = _paginated("/services", api_key)
    ids = {
        _unwrap(item, "service").get("id")
        for item in services
        if isinstance(_unwrap(item, "service").get("id"), str)
    }
    if RENDER_SERVICE_ID not in ids:
        raise EnvironmentError("Render API key is valid but cannot access the ondoway-api service")
    print("Render API authentication is valid; ondoway-api is accessible.")


def print_deploy_status() -> None:
    """Print the newest deployment using the same Keychain API credential."""
    api_key = keychain_api_key()
    payload = _request_json(f"/services/{RENDER_SERVICE_ID}/deploys?limit=1", api_key)
    if not isinstance(payload, list) or not payload:
        raise EnvironmentError("Render returned no deployments for ondoway-api")
    item = payload[0]
    if not isinstance(item, dict):
        raise EnvironmentError("Render returned an invalid deployment record")
    deploy = _unwrap(item, "deploy")
    commit = deploy.get("commit")
    commit = commit if isinstance(commit, dict) else {}
    message = str(commit.get("message", "")).splitlines()[0][:56]
    print(
        "ondoway-api:",
        deploy.get("status", "<unknown>"),
        "|",
        deploy.get("id", "<unknown>"),
        "|",
        message,
    )


def _assert_local_profile(profile: str, environment: dict[str, str]) -> None:
    expected_port = _LOCAL_PROFILE_PORTS.get(profile)
    if expected_port is None:
        return
    uri = environment.get("NEO4J_URI", "")
    parsed = urllib.parse.urlparse(uri)
    if (
        parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.port != expected_port
        or environment.get("NEO4J_DATABASE") != "neo4j"
    ):
        raise EnvironmentError(
            f"profile {profile!r} must resolve to local Neo4j port {expected_port}; "
            f"refusing NEO4J_URI={uri!r}"
        )


def build_environment(*, profile: str, render: bool) -> dict[str, str]:
    """Build the final child environment atomically, then validate it."""
    child = dict(os.environ)
    if render:
        child.update(fetch_render_environment(keychain_api_key()))
    if profile == "cloud":
        if not render:
            raise EnvironmentError("cloud profile requires a fresh Render environment")
        uri = child.get("NEO4J_URI", "")
        parsed = urllib.parse.urlparse(uri)
        if not parsed.hostname or parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
            raise EnvironmentError(
                f"cloud profile requires a non-local NEO4J_URI; refusing {uri!r}"
            )
    else:
        child.update(read_profile(profile))
        _assert_local_profile(profile, child)
    return child


def execute(command: Iterable[str], *, profile: str, render: bool) -> None:
    argv = list(command)
    if not argv:
        raise EnvironmentError("no command supplied after --")
    child = build_environment(profile=profile, render=render)
    source = "fresh Render environment + " if render else ""
    print(f"Executing with {source}{profile} profile.", file=sys.stderr)
    os.execvpe(argv[0], argv, child)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("auth-setup")
    sub.add_parser("auth-status")
    sub.add_parser("deploy-status")
    run = sub.add_parser("exec")
    run.add_argument(
        "--profile",
        # Derived from what is actually committed under config/profiles/ rather
        # than restated, so adding a profile file cannot leave this list behind.
        # "cloud" is appended because it has no committed file by design — it is
        # fetched fresh from Render.
        choices=(
            *sorted(p.name for p in PROFILE_DIR.iterdir() if p.is_file() and p.name[0] != "."),
            "cloud",
        ),
        required=True,
    )
    run.add_argument("--render", action="store_true")
    run.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.action == "auth-setup":
            setup_keychain()
        elif args.action == "auth-status":
            validate_render_access()
        elif args.action == "deploy-status":
            print_deploy_status()
        else:
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            execute(command, profile=args.profile, render=args.render)
    except EnvironmentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Deploy-manifest guard — the public Render service must gate off the workbench.

Defects #1 and #2 (both critical, same root cause): ``render.yaml`` provisions
the public ``ondoway-api`` service but never sets ``WORKBENCH_API_ENABLED=false``.

``src/api/app.py`` mounts the editorial-workbench graph-CRUD routers (graph,
nodes, edges, schema) — an UNAUTHENTICATED create / update / DETACH DELETE
surface over the live Neo4j/Aura graph — whenever ``WORKBENCH_API_ENABLED`` is
not an explicit off value (its default is ``"true"``). The code comment and
``tests/test_api_startup.py`` assert the public deployment sets the flag to
``false`` to disengage that surface, but the manifest that actually provisions
prod does not, so the control is off in production and the destructive write
surface is live on the internet.

This test reads the committed manifest and asserts the gate is set to a value
that ``app._workbench_api_enabled()`` actually treats as OFF. It fails on the
un-fixed manifest (flag absent) and passes once the flag is added.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.api.app import _workbench_api_enabled

_RENDER_YAML = Path(__file__).resolve().parents[1] / "render.yaml"


def _ondoway_api_env() -> dict[str, str]:
    """Return the ``ondoway-api`` web service's env-var map from render.yaml."""
    manifest = yaml.safe_load(_RENDER_YAML.read_text())
    services = manifest["services"]
    api = next(s for s in services if s.get("name") == "ondoway-api")
    return {
        var["key"]: var.get("value")
        for var in api.get("envVars", [])
        if "value" in var
    }


def test_public_render_deploy_gates_workbench_crud_off():
    """The manifest must pin WORKBENCH_API_ENABLED to an off value, so the
    unauthenticated graph-CRUD surface is never mounted in production."""
    env = _ondoway_api_env()
    assert "WORKBENCH_API_ENABLED" in env, (
        "render.yaml must set WORKBENCH_API_ENABLED so the public deploy disengages "
        "the unauthenticated graph-CRUD (node/edge create/update/DETACH DELETE) surface"
    )
    value = env["WORKBENCH_API_ENABLED"]
    # Prove the pinned value is one app._workbench_api_enabled() treats as OFF —
    # a truthy/typo'd value would silently leave the surface live.
    import os

    prior = os.environ.get("WORKBENCH_API_ENABLED")
    os.environ["WORKBENCH_API_ENABLED"] = str(value)
    try:
        assert _workbench_api_enabled() is False, (
            f"WORKBENCH_API_ENABLED={value!r} in render.yaml is not treated as OFF "
            "by app._workbench_api_enabled(); the workbench CRUD surface stays mounted"
        )
    finally:
        if prior is None:
            os.environ.pop("WORKBENCH_API_ENABLED", None)
        else:
            os.environ["WORKBENCH_API_ENABLED"] = prior

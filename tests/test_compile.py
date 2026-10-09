"""nix2cf's tests. Every test needs a tendcf checkout for the contract
(schemas, projector, fixtures): set TENDCF_DIR, or have ~/src/tendcf.

The goldens under tests/golden/ are the compiler's own regression test
(paper §6.2): a compiler change that alters output for a host nobody touched
fails here. Regenerate deliberately with NIX2CF_UPDATE_GOLDEN=1 and read the
diff before committing it.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from nix2cf.cli import load_projector, main
from nix2cf.compile import CompileError, HostSpec, compile_host
from nix2cf.sitemodel import Schemas, SiteModel, load_document, load_site_model, validate_site_model

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "examples" / "site"
GOLDEN = REPO / "tests" / "golden"
HOST_KEY = "ed25519:" + "a1" * 32


def _tendcf() -> Path:
    raw = os.environ.get("TENDCF_DIR")
    candidates = [Path(raw).expanduser()] if raw else []
    candidates.append(Path("~/src/tendcf").expanduser())
    for c in candidates:
        if (c / "schema" / "goal-file.schema.json").exists():
            return c
    pytest.skip("no tendcf checkout: set TENDCF_DIR")


@pytest.fixture(scope="session")
def tendcf() -> Path:
    return _tendcf()


@pytest.fixture(scope="session")
def schemas(tendcf: Path) -> Schemas:
    return Schemas(tendcf / "schema")


@pytest.fixture(scope="session")
def projector(tendcf: Path):
    return load_projector(tendcf)


def _model(site: Path) -> SiteModel:
    return load_site_model(site / "services.yml", site / "roles.yml", site / "launchd-writers.yml")


def _host(site: Path, name: str = "mac", platform: str = "macos") -> HostSpec:
    trust = load_document(site / "device-trust.json").data
    return HostSpec(name=name, platform=platform, key=HOST_KEY, device_trust=trust)


def _check_golden(name: str, raw: bytes) -> None:
    path = GOLDEN / name
    if os.environ.get("NIX2CF_UPDATE_GOLDEN"):
        path.write_bytes(raw)
    assert path.exists(), f"missing golden {path}; run with NIX2CF_UPDATE_GOLDEN=1"
    assert raw == path.read_bytes(), f"output for {name} changed; diff the golden before updating"


# --- the end-to-end slice ---------------------------------------------------

def test_site_model_inputs_validate(schemas: Schemas) -> None:
    assert validate_site_model(_model(SITE), schemas) == []


def test_example_site_mac_golden(schemas: Schemas) -> None:
    result = compile_host(_model(SITE), _host(SITE), schemas)
    doc = result.goal_file
    assert doc["schema_version"] == 1
    assert doc["host"] == HOST_KEY
    sup = doc["domains"]["supervision"]
    assert sup["coverage"] == "comprehensive"
    assert set(sup["entries"]["service"]) == {
        "com.djbclark.caddy", "com.djbclark.litellm", "org.tendcf.tailscaled"
    }
    # The fleet-vpn interlock renders because tailscaled is on this host, with
    # the common-schema defaults stated rather than implied.
    ilk = sup["entries"]["interlock"]["tailscale-authenticated-before-lockdown"]
    assert ilk == {
        "state": "present",
        "bundle": "fleet-vpn",
        "pre_action": {"command": ["tailscale", "status", "--json"], "expect_exit": 0, "timeout_seconds": 15},
        "defines_class": "tailscale_authenticated",
        "blocks": "enclosing-bundle",
        "report": True,
    }
    assert set(sup["entries"]["unit-writer"]) == {
        "com.djbclark.*", "org.tendcf.*", "dev.mise.*", "org.nixos.*", "com.apple.*"
    }
    # env carries secret NAMES only, and only when non-empty.
    assert sup["entries"]["service"]["com.djbclark.litellm"]["env"] == {
        "LITELLM_MASTER_KEY": "LITELLM_MASTER_KEY", "OPENAI_API_KEY": "OPENAI_API_KEY"
    }
    assert "env" not in sup["entries"]["service"]["com.djbclark.caddy"]
    assert not result.canonical.endswith(b"\n")
    _check_golden("example-site_mac.goal-file.json", result.canonical)


def test_tendcf_fixtures_mac_golden(tendcf: Path, schemas: Schemas) -> None:
    """tendcf's own examples compile; tailscaled has no hosts/role so only two render."""
    model = _model(tendcf / "examples")
    result = compile_host(model, _host(SITE), schemas)
    sup = result.goal_file["domains"]["supervision"]
    assert set(sup["entries"]["service"]) == {"com.djbclark.caddy", "com.djbclark.litellm"}
    assert "interlock" not in sup["entries"]  # fleet-vpn unused on this host
    assert any("tailscaled" in d and "neither" in d for d in result.diagnostics)
    _check_golden("tendcf-examples_mac.goal-file.json", result.canonical)


def test_output_validates_and_is_canonical(schemas: Schemas) -> None:
    import rfc8785

    result = compile_host(_model(SITE), _host(SITE), schemas)
    assert schemas.errors("goal-file.schema.json", result.goal_file) == []
    assert rfc8785.dumps(json.loads(result.canonical)) == result.canonical


def test_projects_through_tendcf_projector(schemas: Schemas, projector) -> None:
    """The device-side projection accepts what the compiler rendered."""
    result = compile_host(_model(SITE), _host(SITE), schemas)
    raw = projector.project(json.loads(result.canonical))
    assert projector.validate_projection(raw) == []
    vars_ = json.loads(raw)["vars"]
    assert set(vars_) == {"tendcf_service", "tendcf_interlock"}
    assert vars_["tendcf_service"]["org.tendcf.tailscaled"]["state"] == "present"


def test_pure_and_order_independent(schemas: Schemas) -> None:
    a = compile_host(_model(SITE), _host(SITE), schemas).canonical
    model = _model(SITE)
    model.services.data["services"].reverse()
    b = compile_host(model, _host(SITE), schemas).canonical
    assert a == b


# --- merge rules --------------------------------------------------------------

def test_role_main_receives_backup_does_not(schemas: Schemas) -> None:
    model = _model(SITE)
    vps = HostSpec(name="vps-1", platform="macos", key=HOST_KEY, device_trust=_host(SITE).device_trust)
    result = compile_host(model, vps, schemas)
    assert "supervision" not in result.goal_file["domains"]  # nothing selected
    assert any("backup/peer of role 'llm-gateway'" in d for d in result.diagnostics)


def test_non_cfengine_service_is_skipped_loudly(schemas: Schemas) -> None:
    model = _model(SITE)
    model.services.data["services"][0]["managed_by"] = "external"
    result = compile_host(model, _host(SITE), schemas)
    assert "com.djbclark.caddy" not in result.goal_file["domains"]["supervision"]["entries"]["service"]
    assert any("managed_by 'external'" in d for d in result.diagnostics)


def test_unknown_platform_refused(schemas: Schemas) -> None:
    with pytest.raises(CompileError) as exc:
        compile_host(_model(SITE), _host(SITE, platform="linux"), schemas)
    assert "platform is 'macos' and the host is 'linux'" in str(exc.value)


def test_bad_host_key_refused(schemas: Schemas) -> None:
    host = HostSpec(name="mac", platform="macos", key="ed25519:short", device_trust=_host(SITE).device_trust)
    with pytest.raises(CompileError) as exc:
        compile_host(_model(SITE), host, schemas)
    assert "64 lowercase hex" in str(exc.value)


# --- conflict check -------------------------------------------------------------

def test_duplicate_entry_id_names_both_writers(schemas: Schemas) -> None:
    model = _model(SITE)
    services = model.services.data["services"]
    services[1]["launchd"]["label"] = services[0]["launchd"]["label"]
    with pytest.raises(CompileError) as exc:
        compile_host(model, _host(SITE), schemas)
    msg = str(exc.value)
    assert "entry id 'com.djbclark.caddy'" in msg
    assert "'caddy'" in msg and "'litellm-proxy'" in msg
    assert "services.yml:" in msg  # source locations, not just names
    assert "Resolution:" in msg


def test_two_providers_of_one_token_refused(schemas: Schemas) -> None:
    model = _model(SITE)
    model.services.data["services"][1]["provides"].append("port:443")
    with pytest.raises(CompileError) as exc:
        compile_host(model, _host(SITE), schemas)
    assert "token 'port:443'" in str(exc.value)
    assert "Resolution:" in str(exc.value)


def test_mixed_domains_refused(schemas: Schemas) -> None:
    model = _model(SITE)
    doc = model.services.data
    doc["domains"]["second"] = {"description": "x"}
    doc["bundles"]["edge-http"]["domain"] = "second"
    doc["services"][0]["domain"] = "second"
    doc["services"][1]["domain"] = "second"
    with pytest.raises(CompileError) as exc:
        compile_host(model, _host(SITE), schemas)
    assert "2 Site Model domains" in str(exc.value)


def test_label_outside_declared_writers_refused(schemas: Schemas) -> None:
    model = _model(SITE)
    model.services.data["services"][0]["launchd"]["label"] = "com.rogue.caddy"
    with pytest.raises(CompileError) as exc:
        compile_host(model, _host(SITE), schemas)
    assert "falls under no prefix" in str(exc.value)


def test_interlock_without_defines_class_refused(schemas: Schemas) -> None:
    model = _model(SITE)
    del model.services.data["bundles"]["fleet-vpn"]["interlocks"][0]["defines_class"]
    with pytest.raises(CompileError) as exc:
        compile_host(model, _host(SITE), schemas)
    assert "no `defines_class`" in str(exc.value)


def test_unmatched_requires_is_a_note_not_a_refusal(schemas: Schemas) -> None:
    model = _model(SITE)
    model.services.data["services"][0]["requires"].append("service:nothing-provides-this")
    result = compile_host(model, _host(SITE), schemas)
    assert any("requires 'service:nothing-provides-this'" in d for d in result.diagnostics)


def test_yaml_duplicate_key_refused(tmp_path: Path) -> None:
    bad = tmp_path / "services.yml"
    bad.write_text("contract_version: 1\ncontract_version: 2\n")
    from nix2cf.sitemodel import SiteModelError

    with pytest.raises(SiteModelError, match="duplicate key 'contract_version'"):
        load_document(bad)


def test_non_nfc_input_refused(schemas: Schemas) -> None:
    model = _model(SITE)
    model.services.data["services"][0]["command"].append("café")  # NFD é
    with pytest.raises(CompileError, match="NFC"):
        compile_host(model, _host(SITE), schemas)


# --- the command line -------------------------------------------------------------

def _run(args: list[str], tendcf: Path) -> subprocess.CompletedProcess[bytes]:
    env = dict(os.environ, TENDCF_DIR=str(tendcf), PYTHONPATH=str(REPO))
    return subprocess.run([sys.executable, "-m", "nix2cf.cli", *args], capture_output=True, env=env, check=False)


def test_cli_buildfile_matches_library(tendcf: Path, schemas: Schemas) -> None:
    proc = _run(
        ["buildfile", "--host", "mac", "--host-key", HOST_KEY, "--device-trust", str(SITE / "device-trust.json"), "--site", str(SITE)],
        tendcf,
    )
    assert proc.returncode == 0, proc.stderr.decode()
    assert proc.stdout == compile_host(_model(SITE), _host(SITE), schemas).canonical


def test_cli_project_matches_projector(tendcf: Path, schemas: Schemas, projector) -> None:
    proc = _run(
        ["buildfile", "--host", "mac", "--host-key", HOST_KEY, "--device-trust", str(SITE / "device-trust.json"), "--site", str(SITE), "--project"],
        tendcf,
    )
    assert proc.returncode == 0, proc.stderr.decode()
    expected = projector.project(compile_host(_model(SITE), _host(SITE), schemas).goal_file)
    assert proc.stdout == expected


def test_cli_refusal_exits_1(tendcf: Path, tmp_path: Path) -> None:
    site = tmp_path / "site"
    shutil.copytree(SITE, site)
    doc = yaml.safe_load((site / "services.yml").read_text())
    doc["services"][1]["launchd"]["label"] = doc["services"][0]["launchd"]["label"]
    (site / "services.yml").write_text(yaml.safe_dump(doc))
    proc = _run(
        ["buildfile", "--host", "mac", "--host-key", HOST_KEY, "--device-trust", str(site / "device-trust.json"), "--site", str(site)],
        tendcf,
    )
    assert proc.returncode == 1
    assert b"REFUSED" in proc.stderr and proc.stdout == b""


def test_cli_schema_invalid_input_exits_1(tendcf: Path, tmp_path: Path) -> None:
    site = tmp_path / "site"
    shutil.copytree(SITE, site)
    doc = yaml.safe_load((site / "services.yml").read_text())
    doc["domains"]["macos-user-daemons"].pop("opt_out_reason")  # opt-out with no reason
    (site / "services.yml").write_text(yaml.safe_dump(doc))
    proc = _run(
        ["buildfile", "--host", "mac", "--host-key", HOST_KEY, "--device-trust", str(site / "device-trust.json"), "--site", str(site)],
        tendcf,
    )
    assert proc.returncode == 1
    assert b"opt_out_reason" in proc.stderr


# --- the Nix frontend hook ---------------------------------------------------------

@pytest.mark.skipif(shutil.which("nix-instantiate") is None, reason="no Nix install")
def test_nix_expression_equals_yaml(tendcf: Path) -> None:
    proc = _run(["eval-nix", str(SITE / "site.nix")], tendcf)
    assert proc.returncode == 0, proc.stderr.decode()
    assert json.loads(proc.stdout) == yaml.safe_load((SITE / "services.yml").read_text())


def test_eval_nix_without_nix_is_a_clean_error(tendcf: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "")
    proc = _run(["eval-nix", str(SITE / "site.nix")], tendcf)
    assert proc.returncode == 2
    assert b"nix-instantiate not found" in proc.stderr

"""`nix2cf` command line.

    nix2cf buildfile --host mac --host-key ed25519:… --device-trust trust.json \
        --site examples/site [--tendcf ~/src/tendcf] [--project] [-o OUT]

Renders exactly what one host would receive — the Bcfg2 `buildfile` shape the
guide (§4) and the paper (§6.2) say to build first — without touching the
host. Output is the canonical goal file; `--project` instead prints the
`host_specific.json` tendcf's reference projector derives from it, which is
the only shape `cf-agent` reads.

    nix2cf eval-nix site.nix

Evaluates a Nix expression to the JSON the compiler consumes, via
`nix-instantiate --eval --strict --json` (the stable, flake-free evaluator;
Nix manual 2.26, command-ref/nix-instantiate). The Nix *module* frontend of
D12 (`mkOption`/`mkIf`/`mkDefault`) is not built; this is the hook it would
land behind.

Exit codes mirror tendcf's tooling: 0 clean, 1 compile refused, 2 cannot read.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .compile import CompileError, HostSpec, compile_host
from .sitemodel import SITE_FILES, Schemas, SiteModel, SiteModelError, load_document, load_site_model, validate_site_model


def _tendcf_dir(arg: str | None) -> Path | None:
    raw = arg or os.environ.get("TENDCF_DIR")
    return Path(raw).expanduser() if raw else None


def load_projector(tendcf: Path) -> Any:
    """Import tendcf's reference projector from its checkout (no copy here)."""
    path = tendcf / "bin" / "projector.py"
    spec = importlib.util.spec_from_file_location("tendcf_projector", path)
    if spec is None or spec.loader is None:
        raise SiteModelError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cmd_buildfile(args: argparse.Namespace) -> int:
    site = Path(args.site) if args.site else None
    paths = {}
    for attr, default_name in SITE_FILES.items():
        override = getattr(args, attr)
        if override:
            paths[attr] = Path(override)
        elif site is not None:
            paths[attr] = site / default_name
        else:
            print(f"nix2cf: ERROR: --{attr.replace('_', '-')} or --site is required", file=sys.stderr)
            return 2

    try:
        model: SiteModel = load_site_model(paths["services"], paths["roles"], paths["launchd_writers"])
        trust_doc = load_document(Path(args.device_trust))
    except SiteModelError as exc:
        print(f"nix2cf: ERROR: {exc}", file=sys.stderr)
        return 2

    schemas: Schemas | None = None
    tendcf = _tendcf_dir(args.tendcf)
    if tendcf is not None:
        try:
            schemas = Schemas(tendcf / "schema")
        except SiteModelError as exc:
            print(f"nix2cf: ERROR: {exc}", file=sys.stderr)
            return 2
        problems = validate_site_model(model, schemas)
        if problems:
            for p in problems:
                print(f"nix2cf: FAIL: {p}", file=sys.stderr)
            print(f"nix2cf: {len(problems)} Site Model schema finding(s); not compiled", file=sys.stderr)
            return 1

    host = HostSpec(name=args.host, platform=args.platform, key=args.host_key, device_trust=trust_doc.data)
    try:
        result = compile_host(model, host, schemas)
    except CompileError as exc:
        for f in exc.findings:
            print(f"nix2cf: REFUSED: {f}", file=sys.stderr)
        print(f"nix2cf: {len(exc.findings)} finding(s); no goal file written", file=sys.stderr)
        return 1
    for d in result.diagnostics:
        print(f"nix2cf: note: {d}", file=sys.stderr)

    out = result.canonical
    if args.project:
        if tendcf is None:
            print("nix2cf: ERROR: --project needs --tendcf (or TENDCF_DIR) to find bin/projector.py", file=sys.stderr)
            return 2
        projector = load_projector(tendcf)
        try:
            out = projector.project(json.loads(result.canonical))
        except projector.ProjectionRefused as exc:
            print(f"nix2cf: REFUSED by tendcf projector: {exc}", file=sys.stderr)
            return 1

    if args.output:
        Path(args.output).write_bytes(out)
    else:
        sys.stdout.buffer.write(out)
    return 0


def cmd_eval_nix(args: argparse.Namespace) -> int:
    exe = shutil.which("nix-instantiate")
    if exe is None:
        print("nix2cf: ERROR: nix-instantiate not found on PATH; the Nix frontend needs a Nix install", file=sys.stderr)
        return 2
    proc = subprocess.run(
        [exe, "--eval", "--strict", "--json", str(args.file)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        return 2
    try:
        value = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        print(f"nix2cf: ERROR: nix-instantiate did not return JSON: {exc}", file=sys.stderr)
        return 2
    json.dump(value, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nix2cf", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"nix2cf {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("buildfile", help="render what one host would receive")
    b.add_argument("--host", required=True, help="host name as used in the Site Model (hosts:, roles)")
    b.add_argument("--host-key", required=True, help="device public key, ed25519:<64 hex>")
    b.add_argument("--platform", default="macos", choices=["macos", "linux", "android"])
    b.add_argument("--device-trust", required=True, help="JSON/YAML file holding the goal file's device-trust domain verbatim")
    b.add_argument("--site", help="directory holding services.yml, roles.yml, launchd-writers.yml")
    b.add_argument("--services")
    b.add_argument("--roles")
    b.add_argument("--launchd-writers", dest="launchd_writers")
    b.add_argument("--tendcf", help="tendcf checkout (schemas + projector); default $TENDCF_DIR")
    b.add_argument("--project", action="store_true", help="print the projector's host_specific.json instead of the goal file")
    b.add_argument("-o", "--output")
    b.set_defaults(func=cmd_buildfile)

    e = sub.add_parser("eval-nix", help="evaluate a Nix expression to Site Model JSON")
    e.add_argument("file")
    e.set_defaults(func=cmd_eval_nix)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema>=4.21", "rfc3339-validator"]
# ///
"""Lint the nix2cf Site Model contract.

Three layers, cheapest first:

  1. every schema/*.schema.json is itself a valid JSON Schema 2020-12;
  2. every examples/* instance validates against its schema;
  3. cross-file rules JSON Schema cannot express on its own — domain and
     bundle references resolve, service names are unique, launchd labels
     fall under a declared writer prefix, no writer prefix nests inside
     another.

Layer 3 is the point. Layer 1 and 2 catch a broken schema; layer 3 is what
keeps a valid-but-wrong Site Model out of a render (§0 rule 6: prefer
machine-checkable to conventional).

Exit 0 clean, 1 findings, 2 cannot read/parse.
Run from repo root:  bin/schema_lint.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

REPO = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO / "schema"
EXAMPLE_DIR = REPO / "examples"

# example file -> schema file. report-rows.yml is a sequence of rows, each
# validated individually against the row schema.
EXAMPLES: dict[str, tuple[str, bool]] = {
    "services.yml": ("services.schema.json", False),
    "roles.yml": ("roles.schema.json", False),
    "launchd-writers.yml": ("launchd-writers.schema.json", False),
    "report-rows.yml": ("report-row.schema.json", True),
}

findings: list[str] = []


def fail(msg: str) -> None:
    findings.append(msg)
    print(f"schema-lint: FAIL: {msg}")


def die(msg: str) -> None:
    print(f"schema-lint: ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        die(f"cannot read {path.relative_to(REPO)}: {exc}")


def load_schemas() -> tuple[dict[str, dict], Registry]:
    schemas: dict[str, dict] = {}
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        try:
            schemas[path.name] = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            die(f"cannot read {path.relative_to(REPO)}: {exc}")

    registry: Registry = Registry()
    for name, schema in schemas.items():
        if "$id" not in schema:
            die(f"schema/{name} has no $id — relative $refs cannot resolve without one")
        registry = registry.with_resource(
            schema["$id"], Resource.from_contents(schema)
        )
    return schemas, registry


def check_schemas_valid(schemas: dict[str, dict]) -> None:
    for name, schema in schemas.items():
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # noqa: BLE001 - surface whatever it says
            fail(f"schema/{name} is not a valid JSON Schema 2020-12: {exc}")


def validate(instance: Any, schema: dict, registry: Registry, label: str) -> None:
    validator = Draft202012Validator(
        schema, registry=registry, format_checker=FormatChecker()
    )
    for error in sorted(validator.iter_errors(instance), key=lambda e: list(e.path)):
        where = "/".join(str(p) for p in error.path) or "<root>"
        fail(f"{label}: {where}: {error.message}")


# row_type -> the $defs branch of report-row.schema.json that describes it.
ROW_TYPES = {
    "promise_outcome": "promise_outcome",
    "domain_coverage": "domain_coverage_row",
    "device_convergence": "device_convergence",
}


def validate_row(row: Any, schema: dict, registry: Registry, label: str) -> None:
    """Validate one reporting row against the branch its row_type names.

    Validating against the bare oneOf works but reports only "is not valid
    under any of the given schemas", which is the kind of error D16(a) rules
    out for the compiler — resolution needs a human, so the message has to
    say what is wrong and where. Discriminating first buys a field pointer.
    """
    row_type = row.get("row_type") if isinstance(row, dict) else None
    branch = ROW_TYPES.get(row_type)
    if branch is None:
        fail(
            f"{label}: row_type {row_type!r} is not one of {sorted(ROW_TYPES)}"
        )
        return
    validate(
        row,
        {"$ref": f"{schema['$id']}#/$defs/{branch}"},
        registry,
        f"{label} ({row_type})",
    )


def check_examples(schemas: dict[str, dict], registry: Registry) -> dict[str, Any]:
    loaded: dict[str, Any] = {}
    for example_name, (schema_name, is_sequence) in EXAMPLES.items():
        path = EXAMPLE_DIR / example_name
        if not path.exists():
            fail(f"examples/{example_name} is missing — the schema has no fixture")
            continue
        data = load_yaml(path)
        loaded[example_name] = data
        schema = schemas.get(schema_name)
        if schema is None:
            fail(f"schema/{schema_name} is missing (needed by examples/{example_name})")
            continue
        if is_sequence:
            if not isinstance(data, list):
                fail(f"examples/{example_name}: expected a sequence of rows")
                continue
            for i, row in enumerate(data):
                validate_row(row, schema, registry, f"examples/{example_name}[{i}]")
        else:
            validate(data, schema, registry, f"examples/{example_name}")
    return loaded


def check_cross_file(loaded: dict[str, Any]) -> None:
    services_doc = loaded.get("services.yml") or {}
    roles_doc = loaded.get("roles.yml") or {}
    writers_doc = loaded.get("launchd-writers.yml") or {}

    domains = set((services_doc.get("domains") or {}).keys())
    bundles: dict[str, dict] = services_doc.get("bundles") or {}
    services: list[dict] = services_doc.get("services") or []
    roles = set((roles_doc.get("roles") or {}).keys())

    # --- launchd writer prefixes -------------------------------------------
    prefixes: list[str] = []
    seen_prefixes: set[str] = set()
    for writer in writers_doc.get("writers") or []:
        prefix = writer.get("prefix", "")
        if prefix in seen_prefixes:
            fail(f"launchd-writers: prefix {prefix} declared twice — one writer per prefix")
        seen_prefixes.add(prefix)
        prefixes.append(prefix)

    # A prefix nested inside another puts two writers over one namespace,
    # which is the hazard this file exists to remove.
    for outer in prefixes:
        for inner in prefixes:
            if outer == inner:
                continue
            if inner.removesuffix("*").startswith(outer.removesuffix("*")):
                fail(
                    f"launchd-writers: prefix {inner} nests inside {outer} — "
                    "two writers over one label namespace"
                )

    # --- bundles -----------------------------------------------------------
    interlock_ids: set[str] = set()
    for bundle_name, bundle in bundles.items():
        domain = bundle.get("domain")
        if domain not in domains:
            fail(f"services: bundle {bundle_name} names unknown domain {domain!r}")
        for interlock in bundle.get("interlocks") or []:
            iid = interlock.get("id")
            if iid in interlock_ids:
                fail(f"services: interlock id {iid!r} declared twice")
            interlock_ids.add(iid)

    # --- services ----------------------------------------------------------
    names: set[str] = set()
    for service in services:
        name = service.get("name", "<unnamed>")
        if name in names:
            fail(f"services: service name {name!r} declared twice")
        names.add(name)

        if service.get("domain") not in domains:
            fail(f"services: {name} names unknown domain {service.get('domain')!r}")
        if service.get("bundle") not in bundles:
            fail(f"services: {name} names unknown bundle {service.get('bundle')!r}")

        role = service.get("role")
        if role is not None and role not in roles:
            fail(f"services: {name} names unknown role {role!r} (roles.yml)")

        label = (service.get("launchd") or {}).get("label")
        if label is not None:
            matched = [p for p in prefixes if label.startswith(p.removesuffix("*"))]
            if not matched:
                fail(
                    f"services: {name} launchd label {label!r} falls under no declared "
                    "writer prefix (launchd-writers.yml) — this is the two-writers rail"
                )

    for service in services:
        for target in service.get("depends_on") or []:
            if target not in names:
                fail(
                    f"services: {service.get('name')} depends_on unknown service {target!r}"
                )

    # --- roles -------------------------------------------------------------
    for role_name, role in (roles_doc.get("roles") or {}).items():
        main = role.get("main")
        backups = role.get("backups") or []
        peers = role.get("peers") or []
        if main in backups:
            fail(f"roles: {role_name} lists its main host {main!r} as its own backup")
        overlap = set(backups) & set(peers)
        if overlap:
            fail(
                f"roles: {role_name} lists {sorted(overlap)} as both backup and peer — "
                "a peer is explicitly not a candidate for main"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schemas-only",
        action="store_true",
        help="check schema validity only; skip fixtures and cross-file rules",
    )
    args = parser.parse_args()

    schemas, registry = load_schemas()
    if not schemas:
        die("no schemas found in schema/")

    check_schemas_valid(schemas)
    if not args.schemas_only:
        loaded = check_examples(schemas, registry)
        check_cross_file(loaded)

    if findings:
        print(f"schema-lint: {len(findings)} finding(s)")
        return 1
    print(f"schema-lint: OK ({len(schemas)} schemas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

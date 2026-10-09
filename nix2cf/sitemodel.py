"""Load and validate Site Model inputs.

The Site Model is authored as YAML (or JSON) and schema-checked against the
contract that lives in tendcf (`schema/*.schema.json`). This module does two
things the compiler needs that a plain `yaml.safe_load` does not give:

1. **Source locations.** Conflict errors must name where each declaration
   was written (guide §4 stage 2; `common.schema.json#/$defs/source_location`:
   "nix2cf fills it in, authors do not write it"). The YAML loader here
   records the line of every mapping so a service record can be pointed at.
2. **Duplicate keys refused.** PyYAML and `json.loads` both silently
   last-wins on a duplicate key. Two declarations of one key is exactly the
   silent collision the design forbids ("never silent last-wins", guide §2),
   so it is refused at parse time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


class SiteModelError(Exception):
    """An input could not be read, parsed, or validated."""


class _LineLoader(yaml.SafeLoader):
    """SafeLoader that records the source line of every mapping it builds."""

    def __init__(self, stream: Any) -> None:
        super().__init__(stream)
        self.lines: dict[int, int] = {}

    def construct_yaml_map(self, node: yaml.MappingNode):  # type: ignore[override]
        data: dict[str, Any] = {}
        self.lines[id(data)] = node.start_mark.line + 1
        yield data
        data.update(self.construct_mapping(node))

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict:  # type: ignore[override]
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise SiteModelError(
                    f"duplicate key {key!r} at line {key_node.start_mark.line + 1} "
                    "— refused rather than resolved last-wins"
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


_LineLoader.add_constructor("tag:yaml.org,2002:map", _LineLoader.construct_yaml_map)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            raise SiteModelError(f"duplicate key {key!r} — refused rather than resolved last-wins")
        seen.add(key)
    return dict(pairs)


@dataclass
class Document:
    """A parsed input file plus the line of every mapping in it."""

    path: Path
    data: Any
    lines: dict[int, int] = field(default_factory=dict)

    def line_of(self, mapping: Any) -> int | None:
        return self.lines.get(id(mapping))

    def where(self, mapping: Any) -> str:
        line = self.line_of(mapping)
        return f"{self.path}:{line}" if line else str(self.path)


def load_document(path: Path) -> Document:
    """Parse a `.yml`/`.yaml` or `.json` file, refusing duplicate keys."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SiteModelError(f"cannot read {path}: {exc}") from exc
    if path.suffix == ".json":
        try:
            data = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
        except json.JSONDecodeError as exc:
            raise SiteModelError(f"{path} is not JSON: {exc}") from exc
        return Document(path, data)
    loader = _LineLoader(raw)
    try:
        data = loader.get_single_data()
    except yaml.YAMLError as exc:
        raise SiteModelError(f"{path} is not YAML: {exc}") from exc
    finally:
        loader.dispose()
    return Document(path, data, loader.lines)


@dataclass
class SiteModel:
    services: Document
    roles: Document
    launchd_writers: Document


SITE_FILES = {
    "services": "services.yml",
    "roles": "roles.yml",
    "launchd_writers": "launchd-writers.yml",
}
# Site Model file -> the tendcf schema that checks it.
SCHEMA_FOR = {
    "services": "services.schema.json",
    "roles": "roles.schema.json",
    "launchd_writers": "launchd-writers.schema.json",
}
GOAL_FILE_SCHEMA = "goal-file.schema.json"


def load_site_model(services: Path, roles: Path, launchd_writers: Path) -> SiteModel:
    return SiteModel(
        services=load_document(services),
        roles=load_document(roles),
        launchd_writers=load_document(launchd_writers),
    )


class Schemas:
    """tendcf's `schema/` directory, loaded into one `$ref` registry.

    The registry is built the way `tendcf/bin/schema_lint.py` builds its own,
    from each schema's `$id`, so a `$ref` across files resolves identically
    here and in the lint.
    """

    def __init__(self, schema_dir: Path) -> None:
        self.schema_dir = schema_dir
        self.schemas: dict[str, dict] = {}
        registry: Registry = Registry()
        paths = sorted(schema_dir.glob("*.schema.json"))
        if not paths:
            raise SiteModelError(f"no *.schema.json under {schema_dir}")
        for path in paths:
            try:
                schema = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise SiteModelError(f"cannot read schema {path}: {exc}") from exc
            if "$id" not in schema:
                raise SiteModelError(f"{path} has no $id — relative $refs cannot resolve")
            self.schemas[path.name] = schema
            registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
        self.registry = registry

    def validator(self, name: str) -> Draft202012Validator:
        if name not in self.schemas:
            raise SiteModelError(f"tendcf has no schema named {name} under {self.schema_dir}")
        return Draft202012Validator(
            self.schemas[name], registry=self.registry, format_checker=FormatChecker()
        )

    def errors(self, name: str, instance: Any) -> list[str]:
        """Every validation error as `pointer: message`, best-first.

        A bare "is not valid under any of the given schemas" is the error shape
        the design rules out (D16(a)); `best_match` and the pointer are the
        cheapest way to give a reader the field.
        """
        validator = self.validator(name)
        found = []
        for err in sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path)):
            pointer = "/" + "/".join(str(p) for p in err.absolute_path)
            found.append(f"{pointer}: {err.message}")
        return found


def validate_site_model(model: SiteModel, schemas: Schemas) -> list[str]:
    """Schema-validate every Site Model file; returns findings (empty = OK)."""
    findings: list[str] = []
    for attr, schema_name in SCHEMA_FOR.items():
        doc: Document = getattr(model, attr)
        for err in schemas.errors(schema_name, doc.data):
            findings.append(f"{doc.path}: {err}")
    return findings

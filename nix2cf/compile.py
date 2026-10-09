"""The compile path: Site Model → merged per-host picture → conflict check →
canonical goal file.

What this renders is the per-host **goal file** of guide §7 / paper §2.5,
checked by `tendcf/schema/goal-file.schema.json` ("compiler output, consent
object, validator input"). It is *not* the CFEngine Augments file: that is
produced device-side, after approval, by tendcf's policy-free projector
(`tendcf/bin/projector.py`; goal-file reconciliation §9). `buildfile --project`
runs that projector over this output as a preview only.

Stages (guide §4):
  1. merge   — select the services that apply to one host and resolve the
               defaults the goal file refuses to leave implicit;
  2. conflict check — over the already-merged picture: two writers of one
               id or one token on one host is a compile error that names the
               resource, every writer and location, the values, and a
               resolution. Never last-wins;
  3. inference — NOT implemented. Guide §10: "Inference does not start until
               real type definitions exist on two platforms", and goal-file
               v1 carries no edge kind to render into (reconciliation §8);
  4. render  — RFC 8785 (JCS) bytes, no trailing newline, no defaults, no
               prose, no floats, no nulls (reconciliation §2.1).

Every choice the paper leaves open is marked `TODO(operator)` at the spot and
listed under DECIDED in the ClaudeHelm report that landed this file.
"""

from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import rfc8785

from .sitemodel import GOAL_FILE_SCHEMA, Document, Schemas, SiteModel

GOAL_FILE_SCHEMA_VERSION = 1

# The one state domain the reference projector reads
# (`tendcf/bin/projector.py:PROJECTING_DOMAIN`). The Site Model's own domain
# ids (`macos-launchd-services`, …) are authoring-layer names.
# TODO(operator): the Site-Model-domain -> goal-file-domain mapping is not
# written down anywhere in tendcf. This compiler maps the ONE domain a host's
# cfengine-managed services come from onto `supervision` and refuses a host
# whose services span two Site Model domains. Reconciliation §4.1 also says
# every declared Site Model domain should appear in every goal file (as
# `not-yet-migrated` at minimum); the oracle fixture
# `tendcf/examples/goal-file.json` does not do that, so this compiler follows
# the oracle and emits no other domains until the mapping is decided.
SUPERVISION_DOMAIN = "supervision"

HOST_KEY = re.compile(r"^ed25519:[0-9a-f]{64}\Z")
# `launchd` is the only adapter that exists (guide §4: "It handles launchd
# only"; §18 Step 1). The goal file's `unit` oneOf also spells systemd and
# runit, but nothing renders them yet, so a host on another platform is a
# compile error, not a guess.
PLATFORM_SUPERVISOR = {"macos": "launchd"}

# Per-supervisor default for the REQUIRED `working_dir` (goal-file schema:
# "The compiler resolves the per-supervisor default ('/' for launchd and
# systemd system services, the service directory for runit) and states it").
WORKING_DIR_DEFAULT = {"launchd": "/"}

# `common.schema.json#/$defs/interlock` gives these as JSON Schema `default`s;
# the goal file forbids defaults, so the compiler states them.
INTERLOCK_EXPECT_EXIT_DEFAULT = 0
INTERLOCK_TIMEOUT_DEFAULT = 30

# Site Model `launchd.run_at_load` / `keep_alive` are optional; the goal file
# requires both. TODO(operator): the Site Model schema states no default. This
# takes launchd's own (RunAtLoad and KeepAlive are false when the plist omits
# them) — the supervisor default, per the same reasoning as working_dir.
LAUNCHD_BOOL_DEFAULTS = {"run_at_load": False, "keep_alive": False}

TOKEN = re.compile(r"^(service|port|path|class|package|device|network|secret):(.+)\Z")
# Token kinds whose providers are site registries (paths, secret names), not
# Site Model records. tendcf's fixture says so itself ("Port allocations are
# site-private authorities, existence-checked at compile time"). Until the
# guide §15 lookup is wired to those registries, an unmatched `requires` of
# these kinds is counted, not reported one by one.
UNCHECKED_TOKEN_KINDS = frozenset({"path", "secret"})


class CompileError(Exception):
    """The compile is refused. `findings` carries one line per reason."""

    def __init__(self, findings: list[str]) -> None:
        super().__init__("\n".join(findings))
        self.findings = findings


@dataclass(frozen=True)
class HostSpec:
    """Who we are rendering for.

    TODO(operator): inventory (host name -> device public key, platform,
    trust tier) is site-private data whose schema is still "Step 0
    remaining" (guide §18). Until it exists the caller supplies these.
    """

    name: str
    platform: str
    key: str
    # The goal file's `device-trust` domain, verbatim. The compiler cannot
    # derive it: the trust-policy shape is not yet in the Site Model (guide
    # §18 Step 0 remaining), and the digests (policy tree, agent binary) come
    # from the release path (Step 6). Validated as part of the whole goal
    # file against goal-file.schema.json.
    device_trust: dict[str, Any]


@dataclass
class Selected:
    """One service record that applies to the host, with why."""

    record: dict[str, Any]
    reason: str  # "hosts" | "role:<name>"
    where: str


@dataclass
class CompileResult:
    goal_file: dict[str, Any]
    canonical: bytes
    diagnostics: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _by_name(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {s["name"]: s for s in items}


def _prefix_matches(prefix: str, label: str) -> bool:
    """`org.tendcf.*` matches `org.tendcf.x` and `org.tendcf.x.y`, not `org.tendcfx`."""
    assert prefix.endswith(".*")
    stem = prefix[:-2]
    return label == stem or label.startswith(stem + ".")


# --------------------------------------------------------------------------
# Stage 1: merge — which services, with which resolved values, on this host
# --------------------------------------------------------------------------

def select_services(model: SiteModel, host: HostSpec) -> tuple[list[Selected], list[str], list[str]]:
    """Return (selected, diagnostics, errors)."""
    services: list[dict[str, Any]] = model.services.data.get("services", [])
    roles: dict[str, Any] = model.roles.data.get("roles", {})
    selected: list[Selected] = []
    diagnostics: list[str] = []
    errors: list[str] = []

    for record in services:
        name = record.get("name", "<unnamed>")
        where = model.services.where(record)
        reason: str | None = None
        hosts = record.get("hosts") or []
        if host.name in hosts:
            reason = "hosts"
        role = record.get("role")
        if role is not None:
            if role not in roles:
                errors.append(
                    f"{where}: service {name!r} binds role {role!r}, which "
                    f"{model.roles.path} does not declare"
                )
                continue
            # TODO(operator): only the role's `main` host receives the
            # service. roles.schema.json says backups "can take main over" and
            # peers "participate without being candidates"; whether a backup
            # should hold the service stopped, or not at all, is undecided.
            if roles[role].get("main") == host.name:
                reason = reason or f"role:{role}"
            elif host.name in (roles[role].get("backups") or []) or host.name in (
                roles[role].get("peers") or []
            ):
                diagnostics.append(
                    f"{where}: service {name!r}: host {host.name!r} is a backup/peer "
                    f"of role {role!r}; not rendered (only `main` receives a "
                    "role-bound service in this version)"
                )
        if reason is None:
            if not hosts and role is None:
                # TODO(operator): a service with neither `hosts` nor `role`
                # is declared on no host. "Every host of its platform" is
                # the other plausible reading; this compiler takes the
                # narrow one and says so.
                diagnostics.append(
                    f"{where}: service {name!r} has neither `hosts` nor `role`; "
                    "it is declared on no host and is not rendered"
                )
            continue

        platform = record.get("platform")
        if platform not in (host.platform, "any"):
            errors.append(
                f"{where}: service {name!r} is declared on host {host.name!r} "
                f"(via {reason}) but its platform is {platform!r} and the host is "
                f"{host.platform!r}. Resolution: fix `platform:` or `hosts:`/the "
                "role assignment so they agree"
            )
            continue

        managed_by = record.get("managed_by")
        if managed_by != "cfengine":
            # TODO(operator): a service transcribed as managed by mise/nix/
            # external/unmanaged is real device state, but the goal file has
            # no way to say "present and not ours" (v1 service entries are
            # cfengine-actuated). Skipped, loudly, until that is decided.
            diagnostics.append(
                f"{where}: service {name!r} is managed_by {managed_by!r}; only "
                "`cfengine` services render in this version — skipped"
            )
            continue

        selected.append(Selected(record, reason, where))

    return selected, diagnostics, errors


# --------------------------------------------------------------------------
# Stage 2: conflict check over the merged per-host picture
# --------------------------------------------------------------------------

def conflict_check(model: SiteModel, host: HostSpec, selected: list[Selected]) -> tuple[list[str], list[str]]:
    """Return (errors, diagnostics). Errors name resource, writers, values, fix."""
    errors: list[str] = []
    diagnostics: list[str] = []

    # Duplicate service names across the whole file (the Site Model's own
    # uniqueness rule, restated so a merge never sees two records of one name).
    seen_names: dict[str, str] = {}
    for record in model.services.data.get("services", []):
        name = record.get("name")
        where = model.services.where(record)
        if name in seen_names:
            errors.append(
                f"service name {name!r} is declared twice: {seen_names[name]} and "
                f"{where}. Resolution: rename one; `name` is the id depends_on refers to"
            )
        else:
            seen_names[name] = where

    # One id space per host: the entry id (launchd label) is the promiser, and
    # the projector refuses an id that appears twice (P-6.7). Two services
    # with one label is also two writers of one unit — the hazard the
    # unit-writer registry exists to make impossible.
    by_id: dict[str, Selected] = {}
    for sel in selected:
        entry_id = sel.record["launchd"]["label"]
        if entry_id in by_id:
            prior = by_id[entry_id]
            errors.append(
                f"entry id {entry_id!r} on host {host.name!r} is claimed by two "
                f"services: {prior.record['name']!r} ({prior.where}) and "
                f"{sel.record['name']!r} ({sel.where}). Resolution: give one a "
                "different launchd label, or move one off this host"
            )
        else:
            by_id[entry_id] = sel

    # Two providers of one token on one host. Only service-vs-service: a
    # role legitimately re-states what its service provides.
    providers: dict[str, list[Selected]] = {}
    for sel in selected:
        for token in sel.record.get("provides") or []:
            providers.setdefault(token, []).append(sel)
    for token, sels in sorted(providers.items()):
        if len(sels) > 1:
            writers = ", ".join(f"{s.record['name']!r} ({s.where})" for s in sels)
            errors.append(
                f"token {token!r} on host {host.name!r} is provided by {len(sels)} "
                f"services: {writers}. Resolution: only one may provide it — remove "
                "the duplicate `provides` entry, or move one service to another host"
            )

    # Unmatched requires: reported, not refused. The token catalog this would
    # need (every registry, every role, every foreign input) is not available
    # to the compiler yet (guide §15 lookup CLI is unbuilt), so refusing here
    # would refuse the fixtures. TODO(operator): guide §15 says an unmatched
    # `requires` is a compile error listing near-misses and the catalog.
    provided = set(providers)
    for sel in selected:
        provided.add(f"service:{sel.record['name']}")  # auto-provide, guide §10
    roles = model.roles.data.get("roles", {})
    for role in roles.values():
        provided.update(role.get("provides") or [])
    unchecked: dict[str, int] = {}
    for sel in selected:
        for token in sel.record.get("requires") or []:
            if token in provided:
                continue
            kind = TOKEN.match(token).group(1) if TOKEN.match(token) else "?"
            if kind in UNCHECKED_TOKEN_KINDS:
                unchecked[kind] = unchecked.get(kind, 0) + 1
                continue
            near = sorted(t for t in provided if t.startswith(kind + ":"))
            hint = f"; same-kind tokens present: {near}" if near else ""
            diagnostics.append(
                f"{sel.where}: service {sel.record['name']!r} requires {token!r}, "
                f"which nothing on host {host.name!r} provides{hint}"
            )
    for kind, count in sorted(unchecked.items()):
        diagnostics.append(
            f"{count} `requires` of kind {kind!r} on host {host.name!r} not checked: "
            "those tokens are provided by site registries the compiler is not wired to yet"
        )

    return errors, diagnostics


# --------------------------------------------------------------------------
# Stage 4: render (stage 3, inference, is deliberately absent — see module doc)
# --------------------------------------------------------------------------

def _coverage(domain: dict[str, Any]) -> str:
    """Site Model boolean+reason -> goal file's single enum (reconciliation §4.1)."""
    if domain.get("comprehensive", True):
        return "comprehensive"
    return domain["opt_out_reason"]


def render_goal_file(model: SiteModel, host: HostSpec, selected: list[Selected]) -> tuple[dict[str, Any], list[str]]:
    """Build the goal-file document. Returns (document, errors)."""
    errors: list[str] = []
    supervisor = PLATFORM_SUPERVISOR.get(host.platform)
    if supervisor is None:
        return {}, [
            f"host {host.name!r} is {host.platform!r}; the only supervisor adapter "
            f"that exists is launchd (macos). No goal file rendered"
        ]

    domains: dict[str, Any] = {"device-trust": copy.deepcopy(host.device_trust)}
    doc: dict[str, Any] = {
        "schema_version": GOAL_FILE_SCHEMA_VERSION,
        "host": host.key,
        "domains": domains,
    }
    if not selected:
        return doc, errors

    site_domains: dict[str, Any] = model.services.data.get("domains", {})
    bundles: dict[str, Any] = model.services.data.get("bundles", {})

    used_domains = sorted({s.record["domain"] for s in selected})
    if len(used_domains) > 1:
        errors.append(
            f"host {host.name!r} draws cfengine-managed services from "
            f"{len(used_domains)} Site Model domains {used_domains}; the goal file "
            f"has one actuated domain ({SUPERVISION_DOMAIN!r}) and no decided "
            "mapping for several. Resolution: keep one host's services in one domain"
        )
        return doc, errors
    site_domain = used_domains[0]
    if site_domain not in site_domains:
        errors.append(f"domain {site_domain!r} is not declared under `domains`")
        return doc, errors
    coverage = _coverage(site_domains[site_domain])

    service_entries: dict[str, Any] = {}
    used_bundles: set[str] = set()
    for sel in selected:
        rec = sel.record
        bundle = rec["bundle"]
        if bundle not in bundles:
            errors.append(f"{sel.where}: bundle {bundle!r} is not declared under `bundles`")
            continue
        if bundles[bundle].get("domain") != site_domain:
            errors.append(
                f"{sel.where}: service {rec['name']!r} is in domain {site_domain!r} "
                f"but its bundle {bundle!r} belongs to domain "
                f"{bundles[bundle].get('domain')!r}. Resolution: a bundle and its "
                "members share one domain"
            )
            continue
        used_bundles.add(bundle)
        launchd = rec["launchd"]
        entry: dict[str, Any] = {
            "state": "present",
            "bundle": bundle,
            "run_as": rec["runs_as"],
            "command": list(rec["command"]),
            "working_dir": rec.get("working_dir", WORKING_DIR_DEFAULT[supervisor]),
            "unit": {
                "launchd": {
                    k: launchd.get(k, default) for k, default in LAUNCHD_BOOL_DEFAULTS.items()
                }
            },
        }
        env = rec.get("env") or {}
        if env:
            entry["env"] = dict(env)
        service_entries[launchd["label"]] = entry

    interlock_entries: dict[str, Any] = {}
    for bundle_id in sorted(used_bundles):
        for interlock in bundles[bundle_id].get("interlocks") or []:
            iid = interlock["id"]
            where = model.services.where(interlock)
            if iid in interlock_entries:
                errors.append(f"{where}: interlock id {iid!r} is declared twice")
                continue
            if iid in service_entries:
                errors.append(
                    f"{where}: interlock id {iid!r} collides with a service entry id; "
                    "the projector keeps one id space across kinds (P-6.7)"
                )
                continue
            if "defines_class" not in interlock:
                # TODO(operator): common.schema.json makes defines_class
                # optional; goal-file.schema.json requires it. Deriving one
                # (e.g. canonify(id)) would be a second spelling of identity,
                # so the compiler asks the author instead.
                errors.append(
                    f"{where}: interlock {iid!r} has no `defines_class`; the goal "
                    "file requires one. Resolution: add `defines_class: <class>`"
                )
                continue
            pre = interlock["pre_action"]
            interlock_entries[iid] = {
                "state": "present",
                "bundle": bundle_id,
                "pre_action": {
                    "command": list(pre["command"]),
                    "expect_exit": pre.get("expect_exit", INTERLOCK_EXPECT_EXIT_DEFAULT),
                    "timeout_seconds": pre.get("timeout_seconds", INTERLOCK_TIMEOUT_DEFAULT),
                },
                "defines_class": interlock["defines_class"],
                "blocks": "enclosing-bundle",
                "report": True,
            }

    # The unit-writer registry travels in the file because the DEVICE runs
    # extra-entry detection and does not have the Site Model (reconciliation
    # §8). Every declared prefix is carried; repo/note prose is not.
    writers: list[dict[str, Any]] = model.launchd_writers.data.get("writers", [])
    writer_entries: dict[str, Any] = {
        w["prefix"]: {"state": "present", "writer": w["writer"]} for w in writers
    }
    for entry_id in service_entries:
        owners = [w for w in writers if _prefix_matches(w["prefix"], entry_id)]
        if not owners:
            errors.append(
                f"service entry {entry_id!r} falls under no prefix declared in "
                f"{model.launchd_writers.path}. Resolution: declare its prefix with "
                "writer `cfengine`, or relabel the service"
            )
        elif coverage == "comprehensive" and owners[0]["writer"] != "cfengine":
            errors.append(
                f"service entry {entry_id!r} falls under prefix "
                f"{owners[0]['prefix']!r} whose writer is {owners[0]['writer']!r}, "
                f"but domain {site_domain!r} is comprehensive and cfengine would be "
                "a second writer. Resolution: change the writer or the label"
            )

    entries: dict[str, Any] = {}
    if service_entries:
        entries["service"] = service_entries
    if interlock_entries:
        entries["interlock"] = interlock_entries
    if writer_entries:
        entries["unit-writer"] = writer_entries
    if coverage == "deliberately-unmanaged" and entries:
        errors.append(
            f"domain {site_domain!r} is deliberately-unmanaged but declares "
            f"{len(service_entries)} cfengine-managed service(s); the goal file makes "
            "that unrepresentable. Resolution: change the coverage or the services"
        )
    domain_doc: dict[str, Any] = {"coverage": coverage}
    if entries:
        domain_doc["entries"] = entries
    domains[SUPERVISION_DOMAIN] = domain_doc
    return doc, errors


def _non_nfc(node: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str) and not unicodedata.is_normalized("NFC", k):
                found.append(f"{path}/{k} (key)")
            found.extend(_non_nfc(v, f"{path}/{k}"))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            found.extend(_non_nfc(v, f"{path}/{i}"))
    elif isinstance(node, str) and not unicodedata.is_normalized("NFC", node):
        found.append(path or "<root>")
    return found


def canonical_bytes(doc: dict[str, Any]) -> bytes:
    """RFC 8785 bytes, no trailing newline — the bytes are the contract."""
    try:
        return rfc8785.dumps(doc)
    except Exception as exc:  # noqa: BLE001 - rfc8785 raises several types
        raise CompileError([f"goal file carries a value JCS cannot represent: {type(exc).__name__}: {exc}"]) from exc


def compile_host(model: SiteModel, host: HostSpec, schemas: Schemas | None = None) -> CompileResult:
    """The whole path for one host. Raises CompileError; never emits a wrong file."""
    errors: list[str] = []
    diagnostics: list[str] = []
    if not HOST_KEY.match(host.key):
        errors.append(f"host key {host.key!r} is not `ed25519:` + 64 lowercase hex")

    selected, diag, errs = select_services(model, host)
    diagnostics += diag
    errors += errs
    if errors:
        raise CompileError(errors)

    errs, diag = conflict_check(model, host, selected)
    errors += errs
    diagnostics += diag
    if errors:
        raise CompileError(errors)

    doc, errs = render_goal_file(model, host, selected)
    errors += errs
    if errors:
        raise CompileError(errors)

    bad = _non_nfc(doc)
    if bad:
        raise CompileError([f"not NFC-normalized (JCS cannot see this; reconciliation §2.1): {p}" for p in bad])

    if schemas is not None:
        problems = schemas.errors(GOAL_FILE_SCHEMA, doc)
        if problems:
            raise CompileError(
                [f"rendered goal file fails {GOAL_FILE_SCHEMA}: {p}" for p in problems]
            )
    else:
        diagnostics.append(
            "no tendcf schema directory given: the rendered goal file was NOT "
            "validated against goal-file.schema.json (pass --tendcf or set TENDCF_DIR)"
        )

    raw = canonical_bytes(doc)
    return CompileResult(goal_file=doc, canonical=raw, diagnostics=diagnostics)

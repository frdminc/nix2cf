# nix2cf — design notes for the groundwork slice

Authority on the architecture: `tendcf/docs/paper/tendcf-architecture-guide.md`
(the guide); the technical paper and `architecture-DEFINITIVE-v3.md` must agree
with it. This file records only what nix2cf itself decided and why. It is
not a second copy of the architecture.

## What nix2cf renders, and what it does not

**Output is the per-host goal file**, the canonical JSON document of guide §7
and `tendcf/schema/goal-file.schema.json` ("compiler output, consent object,
validator input"). It is RFC 8785 (JCS) bytes with no trailing newline, no
defaults, no prose, no nulls, no floats (goal-file reconciliation §2.1).

**Output is not the CFEngine Augments file.** The README's one-line pipeline
(and map §5) ends at "CFEngine Augments JSON", but the guide (§7) and the
reconciliation (§9) are explicit that the goal file never reaches CFEngine and
that `host_specific.json` is produced *device-side, after approval* by a
policy-free projection whose reference implementation is
`tendcf/bin/projector.py`. nix2cf therefore renders the goal file, and
`buildfile --project` runs tendcf's projector over it as a preview of what
`cf-agent` would read. Two implementations of the projection would drift; the
oracle for the one that exists is `tendcf/examples/host_specific.json`.

**Not implemented, by design of the build order:**

- *Dependency inference* (`provides`/`requires` → ordering edges). Guide §10:
  "Inference does not start until real type definitions exist on two
  platforms." The goal file also has no edge kind (reconciliation §8), so there
  is nothing to render an edge into yet. `provides`/`requires` are used only by
  the conflict check (two providers of one token on one host) and to report
  unmatched `requires` as notes.
- *Every supervisor's units except launchd's.* The goal file's `unit` admits
  launchd, systemd and runit; only the launchd adapter exists (guide §4, §18
  Step 1). A systemd or runit host is stated (its `supervisor` entry) but any
  service selected for it is a compile error here, not a guess. The systemd
  renderer is linux-targets step 6 proper, so none of the v2 systemd fields
  (`restart`, `wanted_by`) or the systemd argv/`working_dir` alphabet is
  written by nix2cf yet. A `nixos` host is complete: it has no units to
  render (see below).
- *Android/Termux* (Step 2) — deferred (linux-targets ruling 2026-10-29). `android`
  is not a `--platform` choice and the platform↔supervisor table refuses it;
  the `runit` flavour exists in the goal file but has no renderer here.
- *Extra-entry reporting* — device-side, needs tendcf-agent.
- *def.json* — MPF glue under the policy-tree digest, never per-host
  (reconciliation §9).

## Language and tooling

Python 3.11+, packaged with `uv` (`pyproject.toml`, `uv run pytest`). The
reasons:

1. The contract's own tooling is Python with the same three libraries
   (`tendcf/bin/schema_lint.py`, `bin/projector.py`: `jsonschema`, `pyyaml`,
   `rfc8785`). Using the same JSON Schema dialect implementation and the same
   JCS implementation means the compiler and the lint cannot disagree on what
   "valid" or "canonical" means.
2. `buildfile --project` imports tendcf's projector in-process, so the preview
   is the reference projection, not a reimplementation.
3. **No flake, no Nix at build time.** D12 says the Nix module frontend "MAY"
   author the Site Model later; the guide (§1, §3) says nobody adopting the
   project has to know Nix and YAML/JSON is the stranger path. Making Nix a
   toolchain requirement of the compiler would invert that. Nix is also not
   installed on the machine this was built on, so a flake could not have been
   tested. The frontend hook is `nix2cf eval-nix FILE`, which shells out to
   `nix-instantiate --eval --strict --json` (the stable, flake-free evaluator
   per the Nix 2.26 manual) and prints the Site Model JSON. `examples/site/
   site.nix` is the same Site Model as `services.yml` as a plain attribute set;
   the test that evaluates it is skipped without a Nix install.

## The contract is consumed, not copied

nix2cf holds no schema. Validation of inputs and of the rendered goal file
loads `tendcf/schema/*.schema.json` from a tendcf checkout (`--tendcf` or
`$TENDCF_DIR`); the registry is built exactly as `schema_lint.py` builds its
own (from each schema's `$id`). Without a tendcf directory the compiler still
renders but says loudly that nothing was schema-validated.

The example site under `examples/site/` is tendcf's own fixtures with one edit
(`tailscaled` declared on host `mac`, so an interlock renders). It is a fixture,
not site data, like tendcf's.

## Merge rules (stage 1) — the open choices, decided conservatively

Each of these is marked `TODO(operator)` in `nix2cf/compile.py` at the spot.

| Choice | Decision here | Where the paper leaves it open |
| --- | --- | --- |
| Site Model domain → goal-file domain | The one domain a host's cfengine services come from becomes `supervision` (the only domain the projector reads). Two domains on one host is a compile error. No other domains are emitted, matching the oracle `tendcf/examples/goal-file.json`. | Reconciliation §4.1 says every declared domain should appear (as `not-yet-migrated` at minimum); the oracle does not do that; no mapping is written down. |
| Which host gets a role-bound service | The role's `main` only. Backups/peers get a note. | `roles.schema.json` says backups "can take main over"; whether they hold the service is unstated. |
| Service with neither `hosts` nor `role` | Declared on no host; a note. | "Every host of its platform" is the other reading. |
| `managed_by` ≠ `cfengine` | Skipped with a note. | v1 service entries are cfengine-actuated; "present and not ours" has no spelling. |
| `working_dir` omitted | `/` for launchd. | Stated by the goal-file schema (F-1). Not open. |
| `run_at_load` / `keep_alive` omitted | `false` (launchd's own default when the plist omits the key). | The Site Model schema states no default. |
| Interlock `expect_exit` / `timeout_seconds` omitted | `0` / `30`. | Stated as `default` in `common.schema.json`. Not open. |
| Interlock without `defines_class` | Compile error. | Optional in the Site Model, required in the goal file; deriving one would be a second spelling of identity. |
| Unit-writer registry | Every declared prefix is carried (the device runs extra-entry detection without the Site Model, reconciliation §8). | — |
| Unmatched `requires` | A note, and `path:`/`secret:` kinds only counted (their providers are site registries, not Site Model records). | Guide §15 says a compile error with near-misses once the lookup exists. |
| `device-trust`, host key, platform | Supplied by the caller (`--device-trust`, `--host-key`, `--platform`). | Inventory and trust-policy shapes are "Step 0 remaining". |
| `supervisor` | A required host input (`--supervisor launchd\|systemd\|runit\|nixos`) next to `platform`, **no default** (house rule; spec Q1/Q8). Written into `device-trust.entries.supervisor` as `{"host":{"name":X,"state":"present"}}`. A supplied `device-trust` document whose `supervisor` entry differs is refused; one that omits it is fine. | No inventory schema exists (spec Q8); the flag goes when it does. |
| Platform ↔ supervisor | `macos` has `launchd`; `linux` has `systemd`, `runit` or `nixos`; any other pairing, and `android`, is refused. | Not in the spec. Android/Termux is deferred (linux-targets ruling 2026-10-29), so `android` is refused rather than mapped to runit. |
| `nixos` host | Any selected service is refused ("host is nixos-supervised; its units are the Nix configuration's"). With none, the goal file carries `supervision: {"coverage": "deliberately-unmanaged"}` and no unit-writer registry; tendcf's projector reads it as `{"vars":{}}`. | Spec §6.2 item 3, Q3. |
| Older `schema_version` | Library only (`compile_host(..., schema_version=N)`): 3 renders without the `supervisor` entry; 4 renders the same file as the current version bar the number (v5 changed no byte nix2cf emits); a `nixos` host is refused below 4; anything else is refused. The CLI always renders the current version, and an older file is not schema-validated (tendcf's schema is a const). | Spec §6.2 item 6; schema-v5 spec §4 item 11. |
| Unit-writer keys (schema v5) | Only launchd prefixes are emitted (from `launchd-writers.yml`, `^[a-z][a-z0-9]*(\.[A-Za-z0-9][A-Za-z0-9_-]*)+\.\*$`, the v4 language launchd and runit keep). No exact/template key, no `unit-package`, no `tendcf-install`, no `dpkg` writer (retired in v5: the writers schema and the goal-file schema both refuse it). A systemd host gets no `supervision` domain (its renderer is not built), so the "systemd prefix must be cfengine" rule has nothing to apply to. | Schema-v5 spec §2.1, §7 item 12: the Site Model has no systemd writer registry. |
| Tombstones | Cannot be rendered: the Site Model has no way to say "absent". So the v5 rules that a tombstone sit under a same-domain `cfengine` claim and that no unit be present in one domain and absent in another cannot fire on nix2cf output. | Goal file supports them; the Site Model does not yet. |

## Conflict check (stage 2)

Over the merged per-host picture, as the guide requires: a refusal names the
resource, every writer with its source location (file:line, recorded by the
YAML loader), the values, and what a resolution would look like. Never
last-wins; duplicate keys are refused at parse time for the same reason.
Rules today: duplicate service names; two services claiming one entry id
(launchd label) on one host; two services providing one token on one host;
an interlock id colliding with a service id (the projector keeps one id space);
a service id outside every declared writer prefix, or under a non-cfengine
prefix in a comprehensive domain; a bundle whose domain differs from its
member's.

## Tests

`uv run pytest` (through `~/ops/site-private/bin/bg` on the operator's machine).
Goldens under `tests/golden/` are the compiler's regression test (paper §6.2);
regenerate with `NIX2CF_UPDATE_GOLDEN=1` and read the diff first. The tests
also validate the output against `goal-file.schema.json`, re-serialize it with
JCS to prove the bytes are canonical, and run tendcf's projector over it with
zero findings.

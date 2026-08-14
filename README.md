# nix2cf

The **compiler tool** for the [tendcf](https://github.com/djbclark/tendcf)
architecture: **Site Model → merge → conflict check → dependency inference →
[CFEngine Augments](https://docs.cfengine.com/docs/3.21/reference-language-concepts-augments.html)**.

The name is historical. YAML and JSON are valid inputs. An optional Nix
module frontend may author the same JSON later. This repo does not hold
site facts, inventory, or the product engine.

Right now this repo holds a **temporary copy of the public contract** — the
Site Model JSON Schemas. **Schemas and types belong in tendcf** (v3 D21).
They sit here until Step 0 finishes that move. The compiler stages come at
tendcf §13 Step 3.

> Authority: `tendcf/docs/architecture/architecture-DEFINITIVE-v3.md`.
> Section numbers (§4, D16, R13…) refer to that document. **The field
> designs in `schema/` are decided — do not re-derive them.** If a schema
> and the architecture document disagree, the document wins and the schema
> is a bug. Do not copy a previous configuration stack into this history.

## What's here

| Path | What |
| --- | --- |
| `schema/common.schema.json` | Shared definitions, including the three D16 fields |
| `schema/services.schema.json` | `registry/services.yml` — one record per service |
| `schema/roles.schema.json` | `registry/roles.yml` — feature roles + assignment |
| `schema/launchd-writers.schema.json` | One writer per launchd label prefix (example of a unit-writer registry; generic supervisors are tendcf D36) |
| `schema/report-row.schema.json` | D18 report rows (JSONL capture shape; SQLite index is tendcf-agent) |
| `examples/` | Fixtures. Not site data — they hold no real facts |
| `bin/schema_lint.py` | Schema validity + fixture validation + cross-file rules |

```sh
bin/schema_lint.py            # exit 0 clean, 1 findings, 2 cannot read
bin/schema_lint.py --schemas-only
```

## The boundary (D21, tendcf v3 §3)

**Schemas belong in tendcf. Instances are site data. nix2cf is the compiler.**

- The type definitions and the JSON Schema they render-validate against
  **belong in tendcf**. Until they move, they live here as a temporary home.
- Concrete Site Model files — a site-private inventory, a site-shared
  recipe, a stranger's fork — live in **those** layers and are supplied
  through this contract.
- A schema change is a tendcf interface change. An instance change is site
  data. They are not the same kind of change and do not move together.

Nothing here holds a hostname, a secret, or anyone's facts. That is what
makes it publishable (R10).

## The three D16 fields, and why each is shaped the way it is

These are the reason Step 0 exists. All three are *local knowledge* by
construction — answerable from inside the one file in front of you, which
is R13's whole argument.

**`provides` / `requires`** (D16(b), D40) — a type states what it supplies
and what it needs; `nix2cf` derives the ordering edges. A service named
`caddy` auto-provides `service:caddy` unless it opts out. Explicit
`depends_on` stays available and stays authoritative where it exists, but
it is a *global knowledge* mechanism: to write it you must already know
someone else's resource exists. Hand-authored order that contradicts its
own install-before-harden rule is what accreted global-knowledge ordering
looks like.

Two rules the compiler must keep, both already decided:
- **Edge attribution is mandatory.** Every compiled edge carries provenance:
  authored (with source location) or inferred (with the rule that produced
  it). Inference's failure mode is a *spurious* edge — "why is this
  waiting?" — which provenance turns from an investigation into a query.
- **Authored edges win and are never silently deduplicated.** Where authored
  and inferred edges exist for the same pair, the coincidence is reported.

**`interlocks`** (D16(c)) — a stated precondition compiling to a CFEngine
guard class plus a bundle-scoped refusal. A failing pre-action blocks
modification of *every* entry in the enclosing bundle and is reported. Blast
radius and reporting are `const` in the schema, not author choices: that is
what structurally closes "the VPN must be authenticated before lockdown may
be enforced" instead of leaving it as a safe default plus a comment.

**`comprehensive` / `opt_out_reason`** (D16(d)) — a domain is comprehensive
unless it declares otherwise. Anything on the device and absent from a
comprehensive domain's description is reported as an **extra entry**. This is
the only mechanism in the design that detects multi-writer skew at all;
CFEngine's default posture, promising only about what is mentioned, cannot
detect it by construction.

Opting out requires a reason from a closed set, because a bare boolean lets an
agent widen the unmanaged surface silently — precisely the R13 failure mode:

- `not-yet-migrated` — real device state nobody has described yet. Backlog,
  and **countable**. This count is the build order's progress metric.
- `deliberately-unmanaged` — genuinely not ours to describe. Permanent, rare.

Keeping them separate is load-bearing. Conflate them and the number stops
meaning anything: one is work remaining, the other is work that will never
happen. Bcfg2's first client run reports `0 managed / 2308 unmanaged`, and the
entire deployment story is grinding that second number down.

## Expect the day-one numbers to look bad

Nearly every domain starts at `not-yet-migrated`. That is the correct state,
not a failure — see tendcf §13 Step 0. The ratio is the progress metric from
then on.

## Versioning

Every file carries `contract_version`. It is bumped **only** when an existing
field is renamed, retyped, or removed. Adding a new optional field never needs
a bump.

## Not here yet

- The compiler stages (tendcf §13 Step 3), in this order: the
  `buildfile`-style render-what-device-X-receives CLI first (it is the
  self-check loop and the compiler's own regression test), then conflict
  check, then extra-entry reporting, then inference.
- The Nix module system authoring frontend (D12). When it lands, the JSON
  Schema is **generated from** the module's option declarations — the two
  type systems must never be hand-maintained in parallel.
- A priority algebra. Reserved deliberately (D16(a)): the conflict check is a
  distinct compiler stage over already-merged declarations, never fused into
  the type definitions, so `mkDefault`/`mkForce` semantics can be adopted later
  as a policy change rather than a schema redesign.
- Peer-action, trust-policy, and generic unit-writer schemas — those belong
  in tendcf with the rest of the contract.

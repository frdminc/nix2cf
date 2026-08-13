# nix2cf

The compile layer for the [fleetopia](https://github.com/djbclark/fleetopia)
architecture: **Site Model → merge → conflict check → dependency inference →
CFEngine Augments**.

Right now this repo holds only its own **public contract** — the Site Model
JSON Schemas. The compiler stages come at §12 Step 3. The schemas come first
because they are schema, and schema is cheapest to get right before there is
data to migrate.

> Authority for every decision referenced here is
> `fleetopia/docs/architecture/architecture-DEFINITIVE-v2.md`. Section numbers
> (§4.1, D16, R13…) refer to that document. **The field designs in `schema/`
> are decided — do not re-derive them.** If a schema and the architecture
> document disagree, the document wins and the schema is a bug.

## What's here

| Path | What |
| --- | --- |
| `schema/common.schema.json` | Shared definitions, including the three D16 fields |
| `schema/services.schema.json` | `registry/services.yml` — one record per service |
| `schema/roles.schema.json` | `registry/roles.yml` — feature roles + assignment |
| `schema/launchd-writers.schema.json` | `registry/launchd-writers.yml` — one writer per label prefix |
| `schema/report-row.schema.json` | D18 local-first reporting rows (§4.7.1) |
| `examples/` | Fixtures. Not site data — they hold no real facts |
| `bin/schema_lint.py` | Schema validity + fixture validation + cross-file rules |

```sh
bin/schema_lint.py            # exit 0 clean, 1 findings, 2 cannot read
bin/schema_lint.py --schemas-only
```

## The boundary (D21, §4.2)

**Schemas are `nix2cf`'s contract. Instances are site data.**

- The type definitions and the JSON Schema they render-validate against live
  **here**.
- Concrete Site Model files — `site-djbclark`, `stayturgid`, a stranger's
  fork — live in **those** repos and are supplied through this contract.
- A schema change is a `nix2cf` interface change. An instance change is site
  data. They are not the same kind of change and do not move together.

Nothing here holds a hostname, a secret, or anyone's facts. That is what makes
it publishable (R10, §11).

## The three D16 fields, and why each is shaped the way it is

These are the reason Step 0 exists. All three were decided 2026-08-13 (§4.5.1)
and all three are *local knowledge* by construction — answerable from inside
the one file in front of you, which is R13's whole argument (§0 rule 6).

**`provides` / `requires`** (D16(b)) — a type states what it supplies and what
it needs; `nix2cf` derives the ordering edges. Explicit `depends_on` stays
available and stays authoritative where it exists, but it is a *global
knowledge* mechanism: to write it you must already know someone else's
resource exists. `stayturgid#288` is what accreted global-knowledge ordering
looks like — a hand-authored order in which `ensure_apps` installs *after*
`app_privileges` hardens, so anything added there goes unhardened for a full
deploy cycle. The humans writing it did not catch it.

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
what structurally closes `stayturgid#289` ("Tailscale must be authenticated
before lockdown may be enforced") instead of leaving it as a safe default plus
a comment.

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
not a failure — see §12 Step 0. The ratio is the progress metric from then on.

## Versioning

Every file carries `contract_version`. It is bumped **only** when an existing
field is renamed, retyped, or removed. Adding a new optional field never needs
a bump — the same rule `site-djbclark`'s `registry/ports.yml` already states,
reused rather than reinvented.

## Not here yet

- The compiler stages (§12 Step 3), in this order: the `buildfile`-style
  render-what-device-X-receives CLI first (it is the self-check loop and the
  compiler's own regression test), then conflict check, then extra-entry
  reporting, then inference.
- The Nix module system authoring frontend (D12, §4.3). When it lands, the
  JSON Schema is **generated from** the module's option declarations — the two
  type systems must never be hand-maintained in parallel.
- A priority algebra. Reserved deliberately (D16(a)): the conflict check is a
  distinct compiler stage over already-merged declarations, never fused into
  the type definitions, so `mkDefault`/`mkForce` semantics can be adopted later
  as a policy change rather than a schema redesign.

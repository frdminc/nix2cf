# nix2cf

The **compiler tool** for the [tendcf](https://github.com/frdminc/tendcf)
architecture: **Site Model → merge → conflict check → (inference, later) →
per-host canonical goal file**.

The name is historical. YAML and JSON are the inputs. An optional Nix module
frontend may author the same JSON later (tendcf D12); `nix2cf eval-nix` is
the hook it would land behind. This repo does not hold site facts, inventory,
schemas, or the product engine.

**Schemas and types live in tendcf** (D21):
[`schema/`](https://github.com/frdminc/tendcf/tree/master/schema),
[`examples/`](https://github.com/frdminc/tendcf/tree/master/examples),
[`bin/schema_lint.py`](https://github.com/frdminc/tendcf/blob/master/bin/schema_lint.py),
[`bin/projector.py`](https://github.com/frdminc/tendcf/blob/master/bin/projector.py).
A schema change is a tendcf interface change. This tool consumes that
contract from a tendcf checkout; it does not own or copy it.

> Authority: `tendcf/docs/paper/tendcf-architecture-guide.md` (vetted
> current-state). If this README and that guide disagree, the guide wins.
> `architecture-DEFINITIVE-v3.md` is the implementer map and must agree
> with the guide. nix2cf's own choices are in [`docs/DESIGN.md`](docs/DESIGN.md).

## What it does today

The first compiler piece the guide (§4) and the paper (§6.2) say to build:
**`buildfile`** — render exactly what one host would receive, without
touching the host.

```sh
export TENDCF_DIR=~/src/tendcf            # schemas + reference projector
uv run nix2cf buildfile \
    --host mac --platform macos --supervisor launchd \
    --host-key ed25519:a1a1…a1 \
    --device-trust examples/site/device-trust.json \
    --site examples/site                  # services.yml, roles.yml, launchd-writers.yml
```

`--supervisor` (`launchd`, `systemd`, `runit` or `nixos`) is required and has
no default. It is written into the goal file's `device-trust.entries.supervisor`;
a `--device-trust` document that already carries a different `supervisor` is
refused. The output is **schema_version 4** (tendcf's `goal-file.schema.json`);
CI fails when `GOAL_FILE_SCHEMA_VERSION` and tendcf's schema const differ.

That prints the host's **goal file**: the canonical (RFC 8785, no trailing
newline) JSON document of guide §7 that a release carries, that consent binds
to, and that `tendcf/schema/goal-file.schema.json` checks. Add `--project` to
print instead the `host_specific.json` that tendcf's *device-side* projector
derives from it — the only shape `cf-agent` reads. nix2cf does not emit
CFEngine Augments itself; see `docs/DESIGN.md` for why.

What the compile does, in order:

1. **Merge** — select the services that apply to the host (`hosts:` or the
   role's `main`), resolve every default the goal file refuses to leave
   implicit (`working_dir`, launchd booleans, interlock exit/timeout), map the
   Site Model's coverage pair onto the goal file's single enum, carry the
   unit-writer registry.
2. **Conflict check** — over the merged per-host picture: two services with
   one launchd label, two providers of one token, an id outside every declared
   writer prefix, a bundle in the wrong domain. A refusal names the resource,
   every writer with its `file:line`, the values, and a resolution. Never
   last-wins, and duplicate keys are refused at parse time.
3. **Render** — JCS bytes, validated against `goal-file.schema.json`, NFC
   checked, and (in the tests) projected through tendcf's reference projector
   with zero findings.

A `nixos` host gets no services: selecting any is refused ("host is
nixos-supervised; its units are the Nix configuration's"), and the goal file
carries `supervision: {"coverage": "deliberately-unmanaged"}` with the
`supervisor` entry, which tendcf's projector reads as `{"vars":{}}`.

`examples/site/` is tendcf's own fixtures with one edit, so an interlock
renders. Fixture, not site data.

## Not here yet

- **Inference** (`provides`/`requires` → ordering edges): waits until real
  types exist on two platforms (guide §10, §18 Step 3), and the goal file has no
  edge kind to render into.
- **Units for any supervisor but launchd** (Steps 1–2, 4, 6). A `systemd` or
  `runit` host gets its `supervisor` entry, but a service selected for it is a
  compile error, not a guess: the systemd renderer (and with it the v2
  `restart`/`wanted_by` fields) is step 6 proper. `nixos` needs no renderer,
  as above. Android has no supervisor decided and is refused.
- **Extra-entry reporting** (device-side, tendcf-agent) and `def.json`.
- **Inventory, trust policy, peer actions** as Site Model inputs (Step 0
  remaining): the host key, platform, supervisor and `device-trust` domain are
  passed on the command line until those schemas exist.
- **Tombstones** from the Site Model (it cannot yet say "absent").
- **The Nix module frontend** (D12). `nix2cf eval-nix FILE` evaluates a plain
  Nix expression with `nix-instantiate --eval --strict --json`; the test for
  it is skipped without a Nix install.

Every choice the paper leaves open is marked `TODO(operator)` in
`nix2cf/compile.py` and tabulated in `docs/DESIGN.md`.

## Tests

```sh
TENDCF_DIR=~/src/tendcf uv run pytest
```

Goldens under `tests/golden/` are the compiler's own regression test; update
them deliberately with `NIX2CF_UPDATE_GOLDEN=1` and read the diff first.
CI checks out `frdminc/tendcf` beside this repo and runs the same command.

License: [GPL-3.0-or-later](LICENSE).

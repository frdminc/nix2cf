# nix2cf

The **compiler tool** for the [tendcf](https://github.com/djbclark/tendcf)
architecture: **Site Model → merge → conflict check → dependency inference →
[CFEngine Augments](https://docs.cfengine.com/docs/3.21/reference-language-concepts-augments.html)**.

The name is historical. YAML and JSON are valid inputs. An optional Nix
module frontend may author the same JSON later. This repo does not hold
site facts, inventory, or the product engine.

**Schemas and types live in tendcf** (v3 D21):
[`schema/`](https://github.com/djbclark/tendcf/tree/master/schema),
[`examples/`](https://github.com/djbclark/tendcf/tree/master/examples),
[`bin/schema_lint.py`](https://github.com/djbclark/tendcf/blob/master/bin/schema_lint.py).
A schema change is a tendcf interface change. This tool consumes that
contract; it does not own it.

> Authority: `tendcf/docs/paper/tendcf-architecture-guide.md` (vetted
> current-state). If this README and that guide disagree, the guide wins.
> `architecture-DEFINITIVE-v3.md` is the implementer map and must agree
> with the guide.

## Not here yet

The compiler stages (tendcf §13 Step 3), in this order:

1. `buildfile`-style render-what-device-X-receives CLI
2. conflict check
3. extra-entry reporting
4. inference (after types exist on two platforms)

Also later: the Nix module authoring frontend (D12), with JSON Schema
generated from the module options so the two type systems are never
hand-maintained in parallel.

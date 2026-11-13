# nix2cf (archived)

**This repository moved into tendcf.** The compiler now lives at
[`frdminc/tendcf/compiler/`](https://github.com/frdminc/tendcf/tree/master/compiler),
with this repository's full history
([frdminc/tendcf#45](https://github.com/frdminc/tendcf/pull/45), 2026-11-13).
Open issues and pull requests there, not here.

What changes next, recorded in tendcf's
[`docs/architecture/plugin-layout.md`](https://github.com/frdminc/tendcf/blob/master/docs/architecture/plugin-layout.md)
(decision D46):

1. The compiler's command becomes `tendcf compile`.
2. The name `nix2cf` moves to tendcf's Nix-module frontend plugin
   (`plugins/frontends/nix/`), where it describes what the code does.

This repository is read-only. Its last state before the move is commit
`572b0b7`.

License: [GPL-3.0-or-later](LICENSE).

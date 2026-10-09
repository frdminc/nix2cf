"""nix2cf — the tendcf compiler tool.

Site Model (YAML/JSON, or a Nix expression evaluated to the same JSON)
→ merge → conflict check → render → one canonical goal file per host.

The contract this consumes lives in tendcf (`schema/`, `examples/`,
`bin/schema_lint.py`, `bin/projector.py`); nothing here redefines it.
Current-design authority: `tendcf/docs/paper/tendcf-architecture-guide.md`.
"""

__version__ = "0.0.1"

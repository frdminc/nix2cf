# nix2cf — notes for AI sessions

Generates CFEngine policy from Nix expressions, so CFEngine semantics are
load-bearing here.
## CFEngine reference book — query it, don't guess (2026-10-03)

`Learning CFEngine` (Diego Zamboni, 2nd ed.; covers CFEngine 3.12) is in the
local book knowledge base as slug `learning-cfengine` — 69 chapters, 210 code
blocks. **Before writing or reviewing CFEngine policy** — promise semantics,
`edit_line`, bundle/body syntax, class expressions, normal ordering, testing —
query it rather than relying on recall:

- `~/ops/site-private/bin/book-kb query '<regex>' learning-cfengine` — exact
  match, ~0.5–5k tokens. **This is what proves a term is or is not in the book.**
- `~/ops/site-private/bin/book-kb toc learning-cfengine` — ~2.5k-token chapter
  index; then read one chapter (~1.2k median). Add `--deep` for `file:line`
  anchors to every sub-heading.
- basic-memory `search_notes(project="books", query=…)` — semantic recall when
  you don't know the author's wording. Ranked by similarity, so a hit is **not**
  a match; confirm with the exact query above.

Never read `~/kb/raw/learning-cfengine.md`: that is the entire book, ~115k
tokens. The index exists so you don't have to. Full detail, including how to add
a book: `site-private/AGENTS.md` ("Book knowledge base").

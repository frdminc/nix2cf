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

## Standing rule: most important work — be pedantic, pay for the best models (2026-10-31)

djbclark, 2026-10-31: tendcf and nix2cf are the most important work he is
doing, and getting it right outranks cost. This overrides `model-routing`'s
cost-first default and its "frontier models are scarce" gating (item 1b) **for
these two repos only**; every other repo keeps the default.

1. **Be pedantic.** Re-read what you changed. Verify every claim by running it,
   never by recall. Read the plan or spec section before changing what it
   describes. On a doubt, look it up (the CFEngine book, upstream source, the
   host itself) instead of assuming. Take the slower path; never narrow scope
   or call something verified that you did not run; say what you did not check.
2. **Models.** The lead session runs Opus 5.5 `high` (never Sonnet as lead;
   Fable is never a lead). Code slices run on Sonnet 5.5 `high` through
   `/bigteam` and climb a tier only on evidence of failure.
3. **Review is cross-vendor, never same-model.** An Opus review of Opus work is
   one model with a fresh context, not an independent check. No PR merges on a
   Claude-only review.
   - Every PR: one frontier review before merge. Order: Codex `gpt-6-astra`
     (`acp-dispatch codex --model gpt-6-astra --kind frontier --effort high`),
     then Fable `high` (`acp-dispatch claude --model fable --kind frontier
     --effort high`), then Gemini 4 Argon (`acp-run agy --model gemini-4-argon
     --effort high`; probed working 2026-10-31, own weekly window).
   - Design rulings (a `schema_version` bump, the privilege or enforcement scope
     on a host, a deploy plan, the unit-writer or consent-diff design): two
     independent frontier reviews, astra and Fable; Argon stands in for
     whichever of the two is short. A disagreement goes to djbclark, not to the
     lead to settle.
   - If all three are short, wait for the reset. Never merge on a weaker
     review, and never substitute an Opus review.
   - The PR body names each reviewer model and effort, quotes the verdict (or
     "no findings") and lists what was fixed.
4. **Limits that still hold.** The quota guard and in-flight reservation
   (`acp-dispatch` exit 5); no Fable `xhigh`/`max` without djbclark's approval;
   one astra slice at a time (four at once emptied Codex's 5-hour window on
   2026-10-18); every slice goes through `acp-dispatch` with `--kind frontier`.
5. **Gemini 4 Carbon** (announced 2026-10-28, not yet accessible to us): recheck
   weekly with `aiuse --available --json` and `acp-run agy`; when it is
   reachable, adopt it as the Google frontier model in place of Argon.

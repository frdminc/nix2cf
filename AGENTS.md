# nix2cf — notes for AI sessions

`CLAUDE.md` is a symlink to this file.

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
doing, and getting it right outranks cost. This lifts `model-routing` item 1b's
*reason* test for these two repos only: here a frontier review needs no "really
needs a frontier model" case, and a second opinion is reason enough. Every
other repo keeps the default. The mechanics stay (item 4): `acp-dispatch`'s
estimate floors, per-wave caps, in-flight reservation and exit 5 are not
overridden. Never use `route-override`, `--est-pct`, `--min-headroom 0` or
`--no-preflight` to get around them.

1. **Be pedantic.** Re-read what you changed. Verify every claim by running it,
   never by recall. Read the plan or spec section before changing what it
   describes. When in doubt, look it up (the CFEngine book, upstream source,
   the host itself) instead of assuming. Take the slower path. Never narrow
   scope or call something verified that you did not run, and say what you did
   not check.
2. **Models.** Every lead session runs Opus 5.5 `high`, pipeline-only sessions
   (merges, waiters) included; `[lead].pipeline_model` does not apply here.
   Never Sonnet as a lead, and Fable is never a lead. Code slices run on
   Sonnet 5.5 `high` or better (agy's Opus pool is fine) on whichever pool
   `route_agent.py plan` picks, through `/bigteam`. Never use a weaker tier
   (GLM, Gemini Flash, Cursor Auto, `gpt-6-luna`) in these repos. A slice
   climbs a tier only on evidence of failure.
3. **Review is cross-model, never same-model.** An Opus review of Opus work is
   one model with a fresh context, not an independent check. No PR merges on a
   review by the model family that wrote the change. For Opus- or
   Sonnet-authored work, astra, Fable or Argon count; for a Codex-authored
   slice, Fable or Argon count.
   - Every PR, docs-only included (this rule's own PR was reviewed this way),
     gets one frontier review before merge. `docs/handoffs/` commits are not
     PRs and keep the push-in-place exception above. Try the reviewers in this
     order:
     1. astra: `acp-dispatch codex --model gpt-6-astra --kind frontier --effort high --perm read-only --frontier-reason "<repo> standing rule: cross-model review" --name NAME -f BRIEF -C WORKTREE`
     2. Fable: `acp-dispatch claude --model fable --kind frontier --effort high --perm read-only --frontier-reason "..." --name NAME -f BRIEF -C WORKTREE`
     3. Gemini 4 Argon: `acp-dispatch agy --model gemini-4-argon --kind frontier --effort high --perm read-only --frontier-reason "..." --name NAME -f BRIEF -C WORKTREE`. Argon is fallback-only: it stands in when astra or Fable is short. Its frontier wiring landed in djbclark-ade PR 224 (merged 2026-11-02).
   - A pool is **short** when `acp-dispatch` answers exit 5 (`unavailable`:
     wont-fit, inflight, headroom or preflight), or when `aiuse --available --json`
     lists it `usable_now: false`. Argon with no fresh `aiuse` reading counts
     as short too: acp-dispatch refuses it as headroom ("no fresh reading").
     Short means move to the next model in the order, never force it.
     Say in the PR body which model was short and why. **Check the actual
     dispatch, never infer availability from the config alone.** Run the
     intended command with `--dry-run`, preserving its model, kind, effort,
     brief, `-C` and output/task directory. Inspect `would refuse: class=...`
     (or `would_refuse_class` with `--json`), not just the exit status:
     dry-run returns 0 for predicted headroom, fit and concurrency refusals.
     It skips preflight, so no predicted refusal is not proof of availability;
     the real dispatch must still pass its checks. **Astra floor in these two
     repos: 20% of Codex quota left** (djbclark, 2026-11-01). The
     `codex:frontier` estimate uses comparable measured history (14 astra/high
     records on 2026-11-01, estimate 2 points). Where a quota window has fewer
     than three measurements, a configured floor stands in. In tendcf and
     nix2cf that floor is 20, and 20 also caps any measured median
     (djbclark-ade `config/routing.toml` `[dispatch.repo_overrides.<repo>.estimate_floor]`,
     keyed on the repository name of `-C`'s `origin`). Every other repository
     keeps the 60% default. On 2026-10-31 a lead treated the 60% fallback as a
     permanent minimum and declared astra short at 45% remaining. That
     comparison alone did not establish that astra was short. Only the dry-run
     and the dispatch decide.
   - Design rulings (a `schema_version` bump, the privilege or enforcement
     scope on a host, a deploy plan, the unit-writer or consent-diff design)
     get two independent frontier reviews, astra and Fable. Argon stands in
     for one of them and never counts twice. With both astra and Fable short,
     take the Argon review now and wait for a reset for the second. A
     disagreement goes to djbclark, not to the lead to settle.
   - If all three are short, wait for the reset. Never merge on a weaker
     review, and never substitute an Opus review. A GitHub app review (for
     example the chatgpt-codex-connector bot) is not the frontier review.
   - The `/bigteam` adversary round (omp Opus) still runs where bigteam calls
     for it. It is additional and never counts as the frontier review.
   - The PR body names each reviewer model and effort, quotes the verdict (or
     "no findings") and lists what was fixed.
4. **Limits that still hold.** The quota guard, estimate floors and in-flight
   reservation (`acp-dispatch` exit 5); per-wave frontier caps
   (`config/gates.toml [frontier]`); no Fable `xhigh`/`max` without djbclark's
   approval; one astra slice at a time (four at once emptied Codex's 5-hour
   window on 2026-10-18). Every astra, Fable or Argon review goes through
   `acp-dispatch --kind frontier`, never a hand-run `acp-run`.
5. **Gemini 4 Carbon** (announced 2026-10-28, not yet reachable by us):
   recheck weekly with `acp-run agy --info --model gemini-4-carbon` and
   `aiuse --available --json`. When it is reachable, adopt it as the Google
   frontier model in place of Argon.

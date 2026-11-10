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

Native routing update: 2026-11-10 (Wave 6 A3/A4; admission limits preserved).

djbclark, 2026-10-31: tendcf and nix2cf are the most important work he is
doing, and getting it right outranks cost. This lifts `model-routing` item 1b's
*reason* test for these two repos only: here a frontier review needs no "really
needs a frontier model" case, and a second opinion is reason enough. Every
other repo keeps the default. The mechanics stay: frontier allowance,
fresh quota readings, estimate floors and caps, headroom, per-wave limits
and in-flight reservations are not overridden. Native routing is described
in djbclark-ade's `skills/model-routing/SKILL.md`, sections D–E. Never
override a route, lower headroom, change the estimate or omit admission
checks to force a review. A printed native launch command or an
`ade.kind=frontier` label is not proof of admission. If the current native
path cannot preserve these checks, hold the review and report the missing check.

1. **Be pedantic.** Re-read what you changed. Verify every claim by running it,
   never by recall. Read the plan or spec section before changing what it
   describes. When in doubt, look it up (the CFEngine book, upstream source,
   the host itself) instead of assuming. Take the slower path. Never narrow
   scope or call something verified that you did not run, and say what you did
   not check.
2. **Models.** Every lead session runs Opus 5.5 `high`, pipeline-only sessions
   (merges, waiters) included; `[lead].pipeline_model` does not apply here.
   Never Sonnet as a lead, and Fable is never a lead. Code slices run on
   Sonnet 5.5 `high` or better (the antigravity provider's Opus pool is fine) on whichever pool
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
     1. Astra: Codex provider, `gpt-6-astra`, `high`.
     2. Fable: Claude provider, its current Fable frontier model, `high`.
     3. Gemini 4 Argon: Antigravity provider, `gemini-4-argon`, `high`.
        Argon is fallback-only when Astra or Fable is short. Require a fresh
        reading for its Google AI Pro subscription pool; an API entitlement is
        not a substitute.

     Plan each review with
     `~/src/djbclark-ade/bin/route_agent.py plan --kinds frontier --repo nix2cf --json`.
     Keep the reviewer order and model-family independence above; a non-frontier model
     cannot satisfy this rule. Re-plan immediately before admission and launch.
     Record the reason `nix2cf standing rule: cross-model review` in the brief
     and admission evidence.

     Use the current ADE review launch path after admission. Preserve the
     enforced `bin/review-launch` boundary when reviewing untrusted external
     input; do not replace it with an unrestricted invocation. Trusted own-agent
     work follows ADE's ordinary permission policy. For reviews relying on
     instructions rather than tool restrictions, direct the reviewer to change
     nothing and compare worktree status and diff before and after; do not claim
     that this is an enforced read-only sandbox.

     Native Paseo launches use the admitted provider/model and `--thinking high`,
     carry `ade.kind=frontier`, `ade.name`, `ade.lead` and `ade.task` labels,
     and use the explicit workspace and cwd verified under ADE's orchestration
     practices. Include the delivery footer in the positional brief. Do not
     translate retired launcher flags into unsupported native flags.
   - A pool is short when a fresh quota reading marks it unusable, the intended
     reviewer does not fit every relevant window with the required headroom,
     or admission refuses it for concurrency, reservation or preflight reasons.
     Missing or stale readings do not establish availability. Move to the next
     eligible reviewer and report the reason; never force admission.

     Read `aiuse --available --json` first, `paseo usage ls --json` second, and
     inspect the fresh planner's structured result. A Paseo report whose status
     is not `available` is unknown. Planner output is not proof that a subsequent
     launch passed admission; native commands do not inherit the old dispatcher's
     exit-code or dry-run contract. Preserve admission and actual launch results.

     **Astra's fallback estimate
     floor and estimate cap in these two repos are 20 percentage points**
     (djbclark, 2026-11-01). The `codex:frontier` estimate uses comparable
     measured history. The configured fallback floor applies separately when
     the scalar or a quota window has fewer than three comparable measurements;
     three measurements overall do not release every window's floor.
     In tendcf and nix2cf the fallback floor is 20, and the resulting scalar
     and per-window estimates are also capped at 20: a measured median of 70
     becomes 20, while a median of 2 from sufficient history stays 2.
     This is not a permanent minimum of 20% quota remaining; headroom, fit,
     in-flight reservation and the other dispatch checks still apply.
     The override is configured in djbclark-ade's `config/routing.toml` at
     `[dispatch.repo_overrides.<repo>.estimate_floor]`, selected explicitly with
     `plan --repo nix2cf`. Every other repository keeps
     the configured 60-point `codex:frontier` fallback floor, which sufficient
     comparable history can replace. On 2026-10-31 a lead treated the 60% fallback as a
     permanent minimum and declared astra short at 45% remaining. That
     comparison alone did not establish that astra was short. Only fresh quota, fit and admission
     evidence establish availability.
   - Design rulings (a `schema_version` bump, the privilege or enforcement
     scope on a host, a deploy plan, the unit-writer or consent-diff design)
     get two independent frontier reviews, astra and Fable. Argon stands in
     for one of them and never counts twice. With both astra and Fable short,
     take the Argon review now and wait for a reset for the second. A
     disagreement goes to djbclark, not to the lead to settle.
   - If all three are short, wait for the reset. Never merge on a weaker
     review, and never substitute an Opus review. A GitHub app review (for
     example the chatgpt-codex-connector bot) is not the frontier review.
   - The additional adversary round still runs where the current ADE workflow
     calls for it, using an eligible judgment route. It never counts as the
     cross-model frontier review and must not revive the retired omp client.
   - The PR body names each reviewer model and effort, quotes the verdict (or
     "no findings") and lists what was fixed.
4. **Limits that still hold.** Preserve the effective frontier allowance
   and per-wave caps from ADE's `config/gates.toml [frontier]`, estimate
   floors/caps, headroom and in-flight reservation accounting. The 20-point
   Astra estimate override is not a permanent minimum quota balance and
   waives no other check. Fable remains advisory; execution or elevated
   effort requires the operator approvals prescribed by ADE. No Fable
   `xhigh`/`max` without djbclark's approval. At most one Astra slice at a time.

   Native `route_agent.py plan` checks fit against the remaining reading
   but does not subtract sibling in-flight reservations. Re-planning alone
   does not restore that protection. Until native reservation admission is
   verified, serialize launches only when one coordinator can establish
   exclusive control of the pool, account for every existing consumer, and
   retain the reservation through completion and refreshed usage
   reconciliation. If that cannot be proven, hold the review; do not launch
   unguarded or revive retired tools. Missing admission parity remains a
   blocker to operational migration completion.
5. **Gemini 4 Carbon** (announced 2026-10-28, availability unverified here):
   recheck weekly with `paseo provider models antigravity` and
   `aiuse --available --json`. Adopt it as the Google frontier model only
   after confirming the intended subscription pool, native routing and
   admission checks.

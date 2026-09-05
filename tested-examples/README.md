# Example audit reports

These are eleven **real, live audit runs** — not fabricated or hand-edited — produced by
actually invoking `audit-orchestrator` against eleven unseen, unrelated public websites
chosen to span different CMS platforms and content patterns. Each finding was
independently verified against the live site (direct fetches, DOM inspection, or a
second confirming request) before being written into the report; nothing here is a
guess at what the tool *would* find.

The goal of running these was to stress generalization the same way the round itself is
graded: no two sites share a CMS, a content pattern, or a scale, and every report is
schema-valid against `skills/audit-orchestrator/references/report-schema.json`.

## Results at a glance

| Site | Profile / CMS | Findings | Notable catch |
|---|---|---|---|
| [eff.org](eff.org.audit-report.json) | Nonprofit / editorial · Drupal | 1 high, 2 low | Zero structured data anywhere (organization, physical address, and article dates all absent) despite the facts existing in plain visible text |
| [basecamp.com](basecamp.com.audit-report.json) | SaaS / transactable · custom-built | 1 high, 3 low | The site's own JSON-LD price description is broken — a failed template interpolation drops both price numbers, even though the correct prices render fine in visible text on the same page |
| [franklinbbq.com](franklinbbq.com.audit-report.json) | Local business / physical location · Squarespace | 1 high, 1 medium, 2 low | Real `LocalBusiness` structured data states the restaurant is closed **every day of the week** (`openingHours: 00:00-00:00`), directly contradicting the correct visible hours — plus a site-wide announcement banner advertising a closure that ended two weeks before the audit |
| [arxiv.org](arxiv.org.audit-report.json) | Research / academic archive · legacy server-rendered | 1 medium | Real, well-formed citation metadata (Highwire Press tags used by Google Scholar) exists, but nothing in schema.org form — a materially milder gap than the other sites' total absence, and scored accordingly |
| [nytimes.com](nytimes.com.audit-report.json) | Major publisher · enterprise CDN / bot-managed | **1 critical**, 1 low | 93% of sampled pages return HTTP 403 with an 11–55 character "enable JS" shell to **any** automated client — including a full headless browser executing real JavaScript — a technical block broader than and independent of the site's own separate, deliberate robots.txt policy against AI crawlers |
| [linear.app](linear.app.audit-report.json) | Modern SaaS · JS-framework marketing site | 1 high, 1 low | Zero schema.org anywhere despite excellent, complete Open Graph/Twitter Card coverage on every page — the first live case distinguishing "invested in the wrong depth of markup" from the other reports' "invested in nothing." Also the first site whose `<time>` elements are present but missing their `datetime` attribute |
| [techcrunch.com](techcrunch.com.audit-report.json) | Major publisher · WordPress VIP | 2 low | Excellent core `Event` markup (correct dates, `EventScheduled`, full `PostalAddress`) for a real, ticketed conference — but its sponsor list is 76 entries deep and every single one is a hollow `{"name": ""}`. Also the first WordPress site tested, and the first robots.txt that doesn't cleanly fit either "blocks everything" or "blocks only training" — it disallows one OpenAI retrieval agent while leaving another unmentioned |
| [airbnb.com](airbnb.com.audit-report.json) | Global marketplace · randomly selected | **2 critical** | Every page on the domain — homepage, listings, everything — serves only a JavaScript-triggered form-POST redirect stub to a non-executing fetcher; confirmed a real headless browser completes it fine, so this is a pure delivery gap, not a technical wall. Independently, robots.txt disallows `PerplexityBot` — and only `PerplexityBot` — from every listing, while Perplexity's own second agent stays permitted. The two findings are unrelated root causes with disjoint scopes, which is itself what this run's fix (below) is about |
| [moma.org](moma.org.audit-report.json) | Museum / cultural institution · randomly selected | 1 high, 1 low | The first live true positive for the "disguised bot challenge" detection mechanism across all eleven sites: a burst of same-URL requests triggers a real Cloudflare challenge on two high-value paths (an individual collection artwork, the exhibitions index), identically for every user-agent tested — but a single, well-paced request to the same URL succeeds, so this is reported as burst-sensitivity, not a permanent block. Separately, real `VisualArtwork` schema (a first) is missing the date, medium, and description already stated in the page's own visible text, while a sampled exhibition page's `Event`/`Offer` markup is fully complete — the site's structured-data investment is real but inconsistent across templates |
| [mercadolibre.com.mx](mercadolibre.com.mx.audit-report.json) | E-commerce marketplace, non-English (`lang="es-mx"`) · randomly selected | **2 critical** | The first non-English site tested, and the first to expose a real classifier blind spot: the answerability skill's density keywords are pure English ("is a", "lets you") and score a maximally definitional Spanish glossary page at zero, which is a fixed methodology gap, not a site defect (see below). The site's own genuine findings: search and category browsing redirect every automated-looking request to an account-verification wall, so no path from this audit's entry points ever reaches an individual product listing — the specific mechanism (review/rating schema at e-commerce scale) this run set out to test — and robots.txt blocks every named agent's live-request crawler (`ChatGPT-User`, `Claude-User`, `Perplexity-User`) while leaving the newer `-SearchBot` variants unmentioned |
| [wsj.com](wsj.com.audit-report.json) | Major publisher, hard paywall · enterprise CDN / bot-managed | **2 critical** | The clearest, most total reachability failure of any site tested: a DataDome challenge (HTTP 401, ~770-byte JS-only shell) blocks the homepage and every article identically for seven agent identities tried — including Googlebot and the three OpenAI agents robots.txt itself explicitly names in its permissive `Allow: /` group. Set out to test a "genuine auth-required paywall" distinct from nytimes.com's bot-wall; found instead that the distinction collapses in practice, since no automated request ever gets far enough to reach whatever paywall logic sits behind the wall. Separately, robots.txt names OpenAI's three agents as allowed but omits Anthropic's and Perplexity's equivalents entirely, so they fall to the file's blanket disallow — a second, independent stage-1 finding |

## Why the severities differ the way they do

The severity model (`skills/audit-orchestrator/references/severity-model.md`) computes
`stage_weight × prevalence × criticality` centrally — nothing here is hand-tuned per
site. A few things worth noticing across these five reports:

- **arxiv.org's finding is deliberately scored lower** (`criticality: supporting`, not
  `core`) than eff.org's or basecamp.com's near-identical-sounding "missing schema.org"
  findings, because arXiv's facts genuinely *are* machine-readable today via a real,
  different vocabulary (Highwire citation tags) — a materially different situation from
  a site with no machine-readable metadata at all. Getting this distinction right is a
  direct test of whether the tool over-penalizes sites with legitimate alternative
  machine-readability.
- **nytimes.com is the only report that reaches `critical`**, and correctly so: stage 1
  (reachability) failures are weighted highest by construction, because everything
  downstream is moot if the content can't be fetched at all. Every other report's
  highest severity tops out at `high`, since stage 4+ findings cannot mathematically
  reach `critical` under the model.
- **Deliberate site policy is not penalized.** nytimes.com's robots.txt explicitly and
  symmetrically blocks every named AI training *and* retrieval agent, with a stated
  legal rationale in its own comments — the audit reports this as context, not as a
  flagged defect, per the skill's own guidance to distinguish an intentional business
  decision from an accidental block. The flagged finding is the separate technical wall
  that also blocks plain, non-AI-labeled requests.
- **Open Graph is not treated as a substitute for schema.org, or penalized for existing.**
  linear.app has complete, well-formed Open Graph and Twitter Card tags on every sampled
  page, and that is correctly *not* a finding — it is scored `criticality: supporting`
  in the missing-schema.org finding precisely because a real, functioning (if
  lower-depth) machine-readable channel already exists, the same distinction arxiv.org's
  report makes for its citation metadata. Two structurally similar "nothing in
  schema.org" findings across the six reports land at different severities depending on
  what, if anything, fills the gap — not on a fixed penalty for the string "missing
  markup."
- **linear.app is also the first of the six sites where the JS-dependency check (stage
  2/3) found nothing to flag** — every sampled page rendered essentially identically
  with and without JavaScript execution, despite the site's modern, animation-heavy feel.
  That result is reported as-is rather than forced into a finding; a visually modern
  stack is not the same thing as a server-rendering gap, and the tool does not assume
  otherwise.
- **techcrunch.com's published finding is not the one first drafted.** An initial manual
  spot-check of the ticketed event page's JSON-LD (reading only the first ~2,000
  characters of a much longer block) appeared to show no `Event` markup at all. Running
  the actual extraction script surfaced the full `@graph` array, which contains a
  complete and correct `Event` node — the manual read was wrong, not the site. The
  published finding instead targets what the full data actually showed to be broken: a
  76-entry sponsor list inside that same correct `Event` node, where every entry's name
  is blank. Left uncorrected, the wrong finding would have told a site owner to add
  markup that already exists.
- **A second engagement-audit pass on techcrunch.com was deliberately not published.**
  Performance and obstruction measurements grew markedly less reliable partway through
  this session's testing (pages that had loaded normally began timing out), consistent
  with the site's own rate-limiting responding to the sustained request volume this
  session had already generated -- not a defect a normal visitor or a single well-paced
  audit would encounter. That result is recorded in `not_assessed` with the reasoning
  rather than published as a finding about the site.
- **airbnb.com's two findings exposed a real bug in `assemble_report.py`'s automatic
  severity suppression, now fixed.** The tool initially capped the universal
  JavaScript-redirect finding at `medium` and marked it `blocked_by` the narrower
  PerplexityBot-specific robots.txt finding, because both happened to be stage-1
  criticals at "site-wide or widespread" prevalence -- the rule the code used at the
  time. But fixing the PerplexityBot-only robots.txt issue would do nothing to fix the
  JavaScript-redirect problem, which independently blocks every *other* agent too; the
  two findings have disjoint scopes and no real dependency. `auto_blockers` now requires
  prevalence to be `site-wide` specifically (>= 0.80) rather than accepting the weaker
  `widespread` band, so a narrower stage-1 finding can no longer auto-suppress an
  unrelated broader one. Verified this doesn't change any of the other seven reports'
  existing `blocked_by` relationship (nytimes.com's blocker is `site-wide` exactly, so
  it is unaffected). Published here is the corrected report: both findings stand
  independently at `critical`.
- **mercadolibre.com.mx's two findings are both stage 1 and neither blocks the other,**
  which is correct: the robots.txt agent-naming gap and the search/category
  verification wall are independent root causes with disjoint scopes, the same
  relationship airbnb.com's two findings turned out to have. A site whose declared
  language (`lang="es-mx"`) is not English also exposed a real classifier gap in
  answerability-audit -- its English-only keyword lists (`is a`, `lets you`, `we
  propose`) scored a maximally definitional Spanish glossary page at zero -- which is
  now a documented exception in that skill (`SKILL.md` Check 3) rather than a site
  defect reported as low density.
- **wsj.com's headline finding is deliberately not a `blocked_by` relationship with its
  robots.txt finding**, even though both are stage 1 and one describes infrastructure
  overriding the other's policy. `assemble_report.py`'s `auto_blockers` rule only
  auto-suppresses *later* stages (`stage > 1`); two stage-1 findings are left to stand on
  their own severity, which is the right outcome here -- the robots.txt gap (Anthropic
  and Perplexity's agents omitted) is a real, independent defect that would still need
  fixing even if the DataDome wall were reconfigured tomorrow to honor robots.txt for
  everyone it currently blocks. Also the first site where a headless-browser check
  (which might have revealed whether a JavaScript-executing client passes the DataDome
  challenge differently than a plain fetch) was unavailable in the run's environment --
  recorded honestly in `not_assessed` rather than silently skipped or guessed at.

## A check that has never fired, and why that itself was checked

`render-extractability-audit` Check 5 (interaction-gated content: accordions/tabs whose
panels are absent from the DOM until clicked) has not produced a true positive across any
of these eleven reports. Rather than leave that unexplained, eleven live production
FAQ/accordion/tab implementations were inspected directly for this check specifically --
Vercel, Notion, Slack and GitHub's pricing pages, Figma's pricing FAQ, Stripe's docs
language-switcher, IRS.gov's FAQ, Docker's docs, and two e-commerce product pages --
spanning native HTML `<details>`, Bootstrap's `accordion-collapse`, Drupal Views, and
custom React/ARIA widgets. Every single one keeps the answer text inside the DOM in the
raw server response, gated only by CSS (`display:none`, `height:0`, a `hidden` attribute)
-- exactly the "hidden but present" case the check is written to *not* flag. A minimal
synthetic fixture (a `fetch()` call populating an empty answer `<div>` only on click) was
built separately to confirm the check's underlying test -- is there text in the container
in the raw fetch -- correctly distinguishes the two cases; it is not a check that cannot
fire, it is a real anti-pattern that turns out to be rare among professionally engineered
sites, likely because modern accessibility and SEO practice converged on keeping content
server-rendered regardless of visual state. That absence-of-evidence is reported here
rather than quietly left unmentioned.

## Reproducing these

Each report's `audit_scope.sampled_urls` and every finding's `reproduction` block name
the exact URLs and a single shell command that reproduces the underlying observation —
that's a design requirement of the report format itself, not something added for these
examples.

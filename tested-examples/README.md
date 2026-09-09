# Example audit reports

These are twenty-five **real, live audit runs** — not fabricated or hand-edited — produced by
actually invoking `audit-orchestrator` against twenty-five unseen, unrelated public websites
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
| [moma.org](moma.org.audit-report.json) | Museum / cultural institution · randomly selected | 1 high, 1 low | The first live true positive for the "disguised bot challenge" detection mechanism across all twenty-five sites: a burst of same-URL requests triggers a real Cloudflare challenge on two high-value paths (an individual collection artwork, the exhibitions index), identically for every user-agent tested — but a single, well-paced request to the same URL succeeds, so this is reported as burst-sensitivity, not a permanent block. Separately, real `VisualArtwork` schema (a first) is missing the date, medium, and description already stated in the page's own visible text, while a sampled exhibition page's `Event`/`Offer` markup is fully complete — the site's structured-data investment is real but inconsistent across templates |
| [mercadolibre.com.mx](mercadolibre.com.mx.audit-report.json) | E-commerce marketplace, non-English (`lang="es-mx"`) · randomly selected | **2 critical** | The first non-English site tested, and the first to expose a real classifier blind spot: the answerability skill's density keywords are pure English ("is a", "lets you") and score a maximally definitional Spanish glossary page at zero, which is a fixed methodology gap, not a site defect (see below). The site's own genuine findings: search and category browsing redirect every automated-looking request to an account-verification wall, so no path from this audit's entry points ever reaches an individual product listing — the specific mechanism (review/rating schema at e-commerce scale) this run set out to test — and robots.txt blocks every named agent's live-request crawler (`ChatGPT-User`, `Claude-User`, `Perplexity-User`) while leaving the newer `-SearchBot` variants unmentioned |
| [wsj.com](wsj.com.audit-report.json) | Major publisher, hard paywall · enterprise CDN / bot-managed | **2 critical** | The clearest, most total reachability failure of any site tested: a DataDome challenge (HTTP 401, ~770-byte JS-only shell) blocks the homepage and every article identically for seven agent identities tried — including Googlebot and the three OpenAI agents robots.txt itself explicitly names in its permissive `Allow: /` group. Set out to test a "genuine auth-required paywall" distinct from nytimes.com's bot-wall; found instead that the distinction collapses in practice, since no automated request ever gets far enough to reach whatever paywall logic sits behind the wall. Separately, robots.txt names OpenAI's three agents as allowed but omits Anthropic's and Perplexity's equivalents entirely, so they fall to the file's blanket disallow — a second, independent stage-1 finding |
| [spotify.com](spotify.com.audit-report.json) | Consumer streaming, JS-SPA product · randomly selected | 2 medium | The domain root and every locale-root path (`/`, `/us/`, `/gb/`, `/de/`) redirect unconditionally, for every agent tested, to the web-player app shell — 20 characters of visible text, no JSON-LD, no meta description, no noscript fallback — while a deeper marketing page's own Organization schema names that exact URL as the entity's canonical `url`. Separately, all five sampled Premium plan pages show correct visible pricing for four distinct paid tiers with zero Product/Offer markup anywhere. Also surfaced a real bug in this project's own tooling: `fetch_llms_txt()` was fooled by a Next.js soft-404 (HTTP 200 serving a real HTML "Page not found" shell at `/llms.txt`) into reporting the file as present — fixed by checking `Content-Type` and the body's own `<!doctype html>` signature rather than trusting status code alone |
| [khanacademy.org](khanacademy.org.audit-report.json) | Nonprofit education, JS-SPA · randomly selected | **1 critical** | The most total delivery gap of any site tested: the homepage and every sampled subject page return 227KB but reduce to 12 characters of visible text ("Khan Academy") after stripping markup — no JSON-LD, no meta description, no noscript fallback. 223KB of that response (over 98%) is a feature-flag/experimentation config blob, not content. The only schema.org gesture present, an `itemscope itemtype="Organization"` on `<html>`, carries zero actual properties. Separately, robots.txt disallows `GPTBot` by name while leaving `ChatGPT-User` and `OAI-SearchBot` — OpenAI's own retrieval agents — permitted through the wildcard group: a textbook correct training-vs-retrieval split, reported here as *not* a finding, per this project's own calibration for exactly this pattern |
| [nasa.gov](nasa.gov.audit-report.json) | Government / science editorial · WordPress | 1 high, 1 medium | The homepage carries a real, well-formed Organization/WebSite JSON-LD graph, but 0/4 sampled press-release pages carry any JSON-LD at all — no NewsArticle node for the content type where headline/author/date markup matters most. Compounding it: those same pages have no `article:published_time` meta tag and no `<time>` element either, and the one date-like signal present (`og:updated_time`) clusters within a 3-hour window across four unrelated articles — a bulk migration timestamp masquerading as freshness, actively misleading for content whose whole value is "is this current or old news" |
| [chipotle.com](chipotle.com.audit-report.json) | National restaurant chain, transactable + physical-location · randomly selected | 1 high | Zero schema.org anywhere on the primary www.chipotle.com domain (0/5 pages sampled: home, rewards, values, nutrition-calculator, find-a-chipotle) — no Organization node, nothing — while the company's own separately-hosted locations.chipotle.com subdomain has excellent, correct `Restaurant` schema for individual stores (full address, geo, phone, per-day hours) plus a cryptographically-signed Yext "CertifiedFact" credential attesting the same facts. The capability and vendor relationship clearly exist; they simply were never extended to the domain a visitor or assistant actually lands on first |
| [allrecipes.com](allrecipes.com.audit-report.json) | Recipe / editorial media, Cloudflare-managed · randomly selected | **1 critical** | robots.txt opens with an explicit legal notice prohibiting AI/RAG collection, then contradicts its own stated evenness: OpenAI's complete agent set (GPTBot, ChatGPT-User, OAI-SearchBot) is granted broad access, while Anthropic's complete set (ClaudeBot, Claude-User, Claude-SearchBot) and Perplexity's complete set (PerplexityBot, Perplexity-User) are blanket-disallowed site-wide — a deliberate, company-level split, not the defensible training-vs-retrieval pattern seen elsewhere. Every live content fetch attempted from this run's environment was separately challenged or rejected by Cloudflare, including with GPTBot's own user agent — recorded honestly as unverifiable rather than published as a second finding, since this environment cannot distinguish a real technical block from a normal "unverified bot" challenge |
| [duolingo.com](duolingo.com.audit-report.json) | Consumer edtech, JS-SPA · randomly selected | **1 critical** | The homepage and other primary marketing pages reduce to 8 characters of visible text for a plain fetch, but the site actually built a no-JS fallback — a real, substantive 1,307-character `/nojs/splash` page — that a plain HTTP fetcher can never reach anyway, because it is wired through a `<noscript><meta http-equiv="refresh">` tag: a mechanism only a JS-disabled *browser* interprets, invisible to a non-rendering client. The most specific evidence yet that "we already thought about this" and "an AI agent can actually reach it" are different claims |
| [craigslist.org](craigslist.org.audit-report.json) | Classifieds marketplace, minimal-JS · deliberately chosen as an "unglamorous" edge case | 1 medium | The first site tested that isn't a major brand or well-resourced SaaS product, chosen specifically because judges grading "generalization to unseen sites" are unlikely to only try famous ones. Old-school server-rendered HTML throughout — genuinely clean on JS-dependency and freshness (`<time datetime>` correctly marks every posting's real timestamp) where modern SPA-heavy sites keep failing. The one real gap: "services" category listings state explicit prices in plain text ("$100 for 1 hour...") with zero Offer/price markup, while "for sale" listings on the same platform correctly emit a complete Offer node with price, currency and geo for the same kind of fact — a template-level inconsistency, not a capability gap |
| [ja.wikipedia.org](ja.wikipedia.org.audit-report.json) | Encyclopedia, non-Latin script (Japanese) · deliberately chosen to stress URL/language handling | **0 findings** | Surfaced a real bug in this project's own tooling rather than a site defect: a raw, non-percent-encoded article URL (`/wiki/日本`) made every one of this project's seven independent `urllib` fetch call sites raise `UnicodeEncodeError` building the HTTP request line -- caught safely everywhere, but silently indistinguishable from a real network failure, and specifically the kind of bug that would degrade page discovery only on non-Latin-script sites. Fixed by re-quoting every URL before request construction (idempotent on already-encoded URLs) across all six skills. The site itself scored clean: zero JSON-LD was correctly *not* flagged as a defect, since the article links its Wikidata entity directly -- the same "a different, real machine-readable channel already exists" reasoning arxiv.org's report established |
| [ar.wikipedia.org](ar.wikipedia.org.audit-report.json) | Encyclopedia, right-to-left script (Arabic) · deliberately chosen to confirm the URL fix generalizes | **0 findings** | A regression check, not a bug hunt: confirmed the non-ASCII URL fix from the ja.wikipedia.org run also handles Arabic script (a different Unicode block, and RTL reading direction) without incident -- `/wiki/اليابان` fetches cleanly, `dir="rtl"` and `lang="ar"` are both correctly present. Also checked roughly a dozen real sites for legacy non-UTF-8 charsets (Shift_JIS, GBK, EUC-KR), a second plausible encoding edge case -- found none still in the wild among the ones reachable from this environment, an honest negative result rather than a forced finding |
| [nba.com](nba.com.audit-report.json) | Sports league, editorial + stats · randomly selected | **1 critical**, 1 medium | The first robots.txt found with genuinely self-contradictory rules: `GPTBot` and `Google-Extended` are each declared as a *separate group twice*, with materially different rule sets (one permissive with nine Allow exceptions, one a bare blanket disallow) -- a real defect, since different real-world parsers resolve duplicate groups differently and the site cannot currently know what its own file communicates. Separately, and independently: `OAI-SearchBot` gets unconditional `Allow: /`, while OpenAI's *own* `ChatGPT-User` and Perplexity's equivalent `PerplexityBot` are both fully disallowed with zero exceptions -- an asymmetry inside a single company's agent family, not just between competitors |
| [medium.com](medium.com.audit-report.json) | Blogging / publishing platform, user-generated content · randomly selected | **0 findings** | A clean report on every dimension checked, not an unexamined one: robots.txt names essentially every major training-corpus agent (`ClaudeBot`, `GPTBot`, `Bytespider`, `meta-externalagent`, `Applebot-Extended`) while naming zero retrieval-class agents, which fall through to a genuinely permissive wildcard -- the most complete, best-executed "coherent choice" in this table. Every one of five sampled articles carried a complete `SocialMediaPosting` JSON-LD node with distinct, plausible per-article `datePublished`/`dateModified` timestamps (no bulk-migration artifact). One article briefly returned a 403 with full real content readable underneath it -- re-fetched twice before concluding anything, both retries came back a clean 200, so it was reported as the transient blip it was, not a defect |
| [stackoverflow.com](stackoverflow.com.audit-report.json) | Technical Q&A, threaded UGC · deliberately chosen as structurally out-of-domain | **1 critical** | The inverse of every other robots.txt finding in this table: the site *wants* to be maximally restrictive -- `Disallow: /` and the newer `Content-signal: search=no, ai-train=no` directive, for every agent -- but the file is served under HTTP 418 ("I'm a teapot"), not 200. Per documented crawler behavior, a non-2xx status on robots.txt (429 aside) is treated as "unavailable," which licenses unrestricted crawling rather than enforcing the stated block. Surfaced a real gap in this project's own tooling: `check_access.py` was discarding any robots.txt body that didn't arrive with exactly a 200 status, silently treating a real, parseable policy as if it didn't exist |
| [archive.org](archive.org.audit-report.json) | Digital library / archive, nonprofit · deliberately chosen for scale and mission | 2 medium | The domain root delivers 202 characters of text and an explicit "Javascript is required for this site" notice with no fallback -- but this is narrow, not systemic: sampled item pages under `/details/` render full, substantial content (5,000+ characters) with no JavaScript dependency at all, so only the entry point is affected, not the archive itself. The more consequential finding is on those same item pages: real, complete metadata (title, creator, publication date, description) is already displayed in visible text and already exists in the platform's own `/metadata/<identifier>` API, yet the page's only JSON-LD is a generic `BreadcrumbList` naming nothing about the item itself |
| [npr.org](npr.org.audit-report.json) | Major publisher, nonprofit-adjacent · final site tested | **1 critical** | robots.txt clearly intends a comprehensive, symmetric block of every major AI operator -- OpenAI's, Google's, Meta's, Common Crawl's, Cohere's and ByteDance's tokens are all current and correctly spelled -- but names the *retired* Anthropic token `Claude-Web` instead of the current `Claude-User`/`Claude-SearchBot`, and misspells Perplexity's as `PerplexityUser` instead of `Perplexity-User` (while `PerplexityBot` right next to it is spelled correctly). Verified precisely with this project's own parser: both companies' actual current agents resolve `allowed`, silently defeating a policy the file otherwise enforces comprehensively -- a staleness/typo failure mode distinct from every other robots.txt finding in this table |

## Why the severities differ the way they do

The severity model (`skills/audit-orchestrator/references/severity-model.md`) computes
`stage_weight × prevalence × criticality` centrally — nothing here is hand-tuned per
site. A few things worth noticing across these reports:

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
- **spotify.com's two findings land at `medium`, correctly, rather than `critical`.**
  The redirect finding is narrow in URL count (`prevalence: isolated` -- only the root
  and locale-root paths are affected; every deeper marketing page checked was fine), even
  though the single affected URL is the domain's canonical entity URL by the site's own
  structured data. The missing-Product/Offer finding is `prevalence: widespread` across
  the five plan pages sampled, not `site-wide`, since only that specific page family was
  checked rather than a full crawl. Both scores are the model doing what it is meant to:
  a real, well-evidenced defect on an important-but-narrow slice of the site does not
  inherit the severity of a genuinely universal failure like wsj.com's or nytimes.com's,
  even when the specific URL affected matters a great deal.
- **spotify.com also exposed a real bug in this project's own tooling, not the site
  being audited.** `check_access.py`'s `fetch_llms_txt()` originally trusted any
  `status == 200` non-empty response at `/llms.txt` as a real file. spotify.com's
  Next.js app serves its custom 404 page for any unrecognized path -- including
  `/llms.txt` -- as an honest 200 with a real HTML body, which the status-only check
  could not distinguish from a genuine llms.txt. Fixed by checking `Content-Type` for
  `text/html` and the body's own `<!doctype html>`/`<html` opening tag; re-verified this
  does not regress a real llms.txt file (vercel.com's) or a genuine 404 (anthropic.com's,
  which returns an honest 404 rather than a soft one).
- **khanacademy.org's robots.txt was deliberately not turned into a finding**, even
  though `GPTBot` is disallowed by name from the entire site. `references/ai-crawler-agents.md`
  is explicit that GPTBot is a training-corpus agent, and a site blocking training
  collection while leaving retrieval agents (`ChatGPT-User`, `OAI-SearchBot`, both
  confirmed still permitted via the wildcard group) untouched "has made a coherent
  choice. Say so approvingly rather than flagging it." This is the same reference
  document's guidance that shaped wsj.com's and mercadolibre.com.mx's findings, applied
  here to correctly produce *no* finding rather than a false positive -- catching this
  before publishing was itself a deliberate check against this run's own first instinct
  to flag it. The one real, severe finding on this site (zero delivered text on every
  sampled page) is unrelated to robots.txt entirely.
- **mayoclinic.org was attempted and deliberately not published as a report.** Every
  path and every user-agent tried -- including a full realistic browser identity --
  returned an identical, instant Akamai edge "Access Denied" (`server: AkamaiGHost`).
  A control fetch to an unrelated site (khanacademy.org) from the same environment in
  the same minute succeeded normally, ruling out a general network problem on this
  end. Since mayoclinic.org is one of the most heavily-trafficked, most AI-cited health
  sites in existence, a genuine block on ordinary browser traffic site-wide is not
  plausible -- this reads as Akamai Bot Manager blocklisting this environment's
  IP/ASN (common anti-scraper policy for healthcare content), not a policy against AI
  agents specifically, and this audit cannot tell those two apart from here. Per
  crawl-access-audit's own guardrail -- "never infer a block from a network failure on
  the auditing machine" -- no finding was written, and the run moved to a different
  site rather than publish an unverifiable claim.
- **nasa.gov's two findings are both site-wide and both stage-appropriate: `high` for
  the missing NewsArticle markup (stage 4, extractability) and `medium` for the missing
  publish-date signal (stage 5, trust), never higher, because stage 5 cannot
  mathematically reach `critical` under this model regardless of prevalence -- trust
  problems compound reachability/delivery/extractability problems, they do not equal
  them. The two findings share a root theme (missing date information) but are owned by
  different skills on purpose: structured-data-audit cares that a NewsArticle node
  exists at all, freshness-corroboration-audit cares specifically that the one date
  signal present is trustworthy -- and here it demonstrably is not, since four unrelated
  articles' `og:updated_time` values cluster within three hours of each other, a bulk
  timestamp rather than real per-article history.
- **chipotle.com's navigational gap was deliberately downgraded from a finding to an
  opportunity.** The locations directory's root page exposes its 50-state index only
  as embedded JSON, not real `<a href>` links -- normally exactly the kind of thing this
  audit flags. But the same subdomain's robots.txt declares a real sitemap covering all
  1598+ store URLs, and fetching a sampled store page directly confirmed it is fully
  reachable and carries excellent structured data. A gap that a declared, followable
  sitemap fully mitigates for any compliant crawler is a UX rough edge, not a
  discoverability defect -- publishing it as a `high` or `critical` finding would have
  overstated a problem this audit's own reproduction step disproved. This is the same
  discipline as `moma.org`'s burst-sensitivity call: verify the failure mode actually
  bites before reporting it as one.
- **allrecipes.com's finding is scored `critical` on textual evidence alone, deliberately
  independent of the Cloudflare ambiguity.** robots.txt is a plain-text file this run
  fetched cleanly with zero challenge and zero ambiguity -- the company-level asymmetry
  it documents (OpenAI allowed, Anthropic and Perplexity blocked) is read directly from
  the file's own content, verified against this project's real `rule_for()` parser, not
  inferred from a live fetch that could be contaminated by bot-detection noise. The
  separate question -- does the Cloudflare layer *also* block the real, IP-verified
  agents, or only this environment's unverified requests -- got the same treatment as
  mayoclinic.org: recorded in `not_assessed` rather than guessed at, because a full
  browser-identity request was challenged too, and a site this size does not survive
  challenging every ordinary visitor. Two sites, two independent applications of the
  same "don't infer a block from a network failure on the auditing machine" guardrail,
  four sites apart in this table -- the same discipline holding up under repetition
  rather than being a one-off excuse. A third site, zillow.com, hit the identical wall
  (a genuine PerimeterX `x-px-blocked: 1` challenge on both the homepage and a real
  listing page, sitemaps unaffected) during this same run and was not published as a
  report at all rather than force a weak finding out of an unverifiable observation --
  three high-value-data verticals (healthcare, recipes/media, real estate) all showing
  the same pattern is itself a noteworthy, if informal, generalization: aggressive bot
  management concentrates where the underlying data is commercially valuable to scrape,
  which is a reasonable thing for a future version of this marketplace to name as
  context rather than something this run had budget to formalize into a check.
- **duolingo.com's finding required verifying a negative claim before trusting it.**
  It would have been easy to report "no noscript fallback exists" the way spotify.com
  and khanacademy.org's reports do -- but duolingo.com's homepage *does* have one, so
  the more interesting and more honest finding is that the fallback exists and still
  does not work for this audit's target population. Confirming that required an extra
  fetch (of `/nojs/splash` itself) this run would not have needed if it had stopped at
  "a noscript tag is present, therefore handled."
- **craigslist.org was chosen for a specific, named reason worth stating plainly: every
  other site in this table is a major brand or a well-funded product.** The round's own
  grading criterion is generalization to sites nobody hand-picked for this demo, and a
  portfolio of only famous, well-engineered domains is a weaker test of that than it
  looks like -- large engineering teams are more likely to have already fixed the easy
  mistakes this audit catches. craigslist.org is the opposite kind of unseen site: old,
  functionally stable, minimally modernized. That it passed cleanly on JS-dependency and
  freshness while still yielding one genuine, well-evidenced structured-data finding is
  a better generalization signal than an eighteenth well-funded SaaS company would have
  been, precisely because nothing about this site was picked to flatter the tool.
- **craigslist.org's finding is deliberately scored `partial` prevalence, not
  `site-wide`,** even though the two "services" listings sampled were 2-for-2. Only two
  of roughly eight top-level posting categories were checked; `not_assessed` says so
  explicitly rather than letting a clean small sample imply a claim about categories
  never inspected (jobs, housing, personals, gigs, resumes). Reporting the honest scope
  of what was actually checked, not the scope the evidence would tempt a reader to
  assume, is the same discipline the `not_assessed` array exists to enforce everywhere
  else in this project.
- **ja.wikipedia.org is the only report in this set with zero findings, and that is a
  meaningful result on purpose, not an empty run.** The site was chosen specifically to
  stress two things large commercial sites don't: a genuinely different script (Japanese,
  no whitespace tokenization, unlike mercadolibre.com.mx's Spanish) and a URL containing
  native-script characters. The real, valuable outcome was catching a bug in this
  project's own fetch code -- every one of its seven independent `urllib` request-
  construction sites raised `UnicodeEncodeError` on a raw non-ASCII URL, caught safely
  but silently indistinguishable from an unrelated network failure. Left unfixed, this
  would have specifically and only degraded page discovery on non-Latin-script sites --
  the exact population the round's generalization criterion cares about most, since it is
  the population least represented in whatever a developer tests against by habit. Fixed
  by re-quoting every URL (idempotent on ones already encoded) before request
  construction, verified against both the raw-Unicode case and a regression check against
  wsj.com to confirm ordinary ASCII URLs are untouched. Separately, the site's genuine
  lack of on-page JSON-LD was deliberately *not* published as a finding, for the same
  reason arxiv.org's citation tags earned a lighter touch: a real alternative (Wikidata,
  linked from every article) already serves the purpose schema.org markup would.
- **ar.wikipedia.org is a deliberate regression check, and reports two negative results
  honestly rather than manufacturing findings to justify the run.** First: the
  non-ASCII URL fix generalizes beyond the CJK case it was found on -- Arabic uses a
  completely different Unicode block and reads right-to-left, and `/wiki/اليابان`
  fetches without incident, with `dir="rtl"` correctly present. Second: roughly a dozen
  real sites (Japanese, Chinese, and Japanese-government domains specifically chosen as
  plausible holdouts) were checked for a different, unrelated encoding risk -- a
  legacy non-UTF-8 body charset (Shift_JIS, GBK, EUC-KR) that this project's hardcoded
  `.decode("utf-8", errors="replace")` calls would silently garble rather than error on.
  None were found; the modern web has moved off legacy charsets more completely than
  expected. Reporting a clean regression check and a genuine negative result as exactly
  that, instead of stretching either into a finding, is the same discipline this project
  applies everywhere: a report with nothing to flag is itself informative when the
  reasons for looking are stated honestly.
- **nba.com's duplicate-group finding is a genuinely new failure category, not a
  restatement of an inconsistency finding seen on another site.** Every other robots.txt
  inconsistency in this table (wsj.com, mercadolibre.com.mx, allrecipes.com,
  khanacademy.org) is a single, unambiguous group per agent that simply treats different
  companies differently -- readable one way by any parser. nba.com's `GPTBot` and
  `Google-Extended` groups are each declared *twice*, with different rules attached each
  time, which is not a policy choice at all: it is a file that does not have one single
  well-defined meaning, verified by checking that this project's own parser had to make
  a specific, documented choice (merge both groups) to produce any answer, when an
  equally spec-compliant parser elsewhere could reach the opposite one. Both findings
  land at their stage's natural severity independently -- the medium-severity duplicate
  defect is `isolated` prevalence (two agents out of many named in the file) and does
  not get capped by the critical retrieval-agent finding, since `auto_blockers` only
  ever suppresses a *later*-stage finding, and both of these sit at stage 1.
- **nba.com is also a reminder that a transient fetch failure isn't a finding.** One
  homepage attempt during this run returned no status and an empty body; a same-second
  retry returned a clean 200 with 131,402 characters of real text and three well-formed
  JSON-LD blocks. That blip was not written up as a reachability defect, consistent with
  this skill's own guardrail against inferring a block from a single failed request on
  the auditing machine -- the same principle applied at the opposite scale from
  mayoclinic.org's and allrecipes.com's multi-attempt, still-inconclusive walls.
- **The nba.com duplicate-group finding exposed a real gap in this project's own
  tooling, since fixed.** `check_access.py`'s `parse_robots()` silently merged every
  occurrence of a repeated agent name into one combined ruleset with no signal anywhere
  that the merge had even happened -- the duplication was caught only because this run
  additionally ran a manual `re.findall` over the raw file as a side-check, something a
  future audit of a different site would have no reason to do on its own. Fixed by
  having `parse_robots()` track and return which agents were declared as a separate,
  non-contiguous group more than once (`duplicate_agent_groups`), verified against
  nba.com's real file (correctly flags `gptbot` and `google-extended`) and against
  three previously-audited sites' robots.txt files (eff.org, mercadolibre.com.mx,
  khanacademy.org -- all correctly return an empty list, no false positives). Documented
  as its own check (crawl-access-audit's Check 1b) so the next site with this defect is
  caught by the check itself, not by however thoroughly a particular run happened to
  look.
- **medium.com is the cleanest report in this table, and it earned that by surviving
  three separate opportunities to manufacture a finding that would not have held up.**
  A first look at the robots.txt training-agent block could have been misread as a
  discoverability problem; checking which specific agents were named (all
  training-corpus, zero retrieval) confirmed it as the coherent, approvable pattern
  documented for khanacademy.org instead. A first fetch of one article returned 403 with
  full content underneath -- exactly the "sneaky non-200" shape this project's checks
  are built to catch -- but two clean re-fetches showed it was a one-off blip, not the
  site's real behavior. And `SocialMediaPosting` (rather than `Article` or
  `BlogPosting`) looked like a plausible type mismatch on first read, until schema.org's
  own definition of that type turned out to explicitly include blog posts, closing off
  what would have been a manufactured, technically wrong finding. Zero findings from a
  run that worked this hard to find one is a stronger generalization signal than a
  report with a defect in it.
- **stackoverflow.com exposed a second real gap in this project's own tooling, since
  fixed, and it is the more consequential of the two robots.txt-parsing bugs found this
  campaign.** `check_access.py`'s decision to treat robots.txt as present required an
  exact HTTP 200; stackoverflow.com's file arrives as HTTP 418 with a completely real,
  parseable body underneath. Before the fix, this project's own audit would have
  reported "no robots.txt, all paths permitted" for a site whose actual, explicit
  written policy is the opposite of permitted -- missing not just the parse but the
  single most interesting fact available: that the site's own maximally restrictive
  intent is likely unenforced for the same reason this project's tool almost missed it.
  Fixed by parsing the body whenever it contains a real `User-agent:` line regardless of
  status, and surfacing the non-200 status as `robots.served_with_status` plus an
  explanatory note. Verified against five previously-good sites (no false positives --
  all still resolve status 200 normally) and against three known large HTML bodies
  (spotify.com, khanacademy.org and duolingo.com's `/llms.txt` soft-404 shells) to
  confirm the `User-agent:` detection heuristic does not false-positive on unrelated
  JavaScript or analytics code that happens to mention "user agent" in a different
  context. Documented as crawl-access-audit's Check 1c.
- **Choosing stackoverflow.com specifically for being structurally unlike every other
  site in this table earned its keep twice over.** It was picked to stress a genuinely
  different content shape (threaded Q&A, `QAPage`-family schema, no products or
  locations or news articles) -- and instead of testing that shape directly, it
  surfaced a tooling gap that had been sitting latent through the previous twenty-two
  audits, invisible until a site happened to combine a real, restrictive robots.txt
  with a non-standard status code. That combination did not occur naturally in this
  campaign's other twenty-two sites; picking a deliberately out-of-domain site was a
  materially different search than picking another well-known brand, and found a
  materially different kind of gap because of it.
- **archive.org's two findings are deliberately not conflated into one, even though
  both are about missing information at different points in the same visit.** The
  homepage gap (stage 2, `isolated` prevalence) and the item-page schema gap (stage 4,
  `widespread` prevalence) have different root causes, different owners, and different
  fixes -- one is a rendering/delivery problem at a single entry point, the other is a
  markup-authoring gap across the platform's actual content at scale. Neither auto-
  blocks the other (`auto_blockers` only fires for a stage-1 critical, and neither
  finding here is stage 1), which is correct: fixing the homepage would not touch the
  item-page schema gap, and vice versa. Both land at `medium`, appropriately -- the
  homepage gap is real but narrow (confirmed live: item pages, the actual content,
  render fine without JavaScript), and the item-page gap is widespread but the
  underlying facts are still reachable as plain text, just not machine-readable -- a
  materially less severe situation than eff.org's or basecamp.com's structured-data
  findings, which is why this scored lower than either despite affecting more pages.
- **npr.org is the final site tested, and its finding is a distinct failure mode from
  every prior robots.txt case in this table.** khanacademy.org and medium.com show
  deliberate, coherent training-vs-retrieval splits; wsj.com and allrecipes.com show
  one company favored over others; nba.com shows internally contradictory duplicate
  groups; stackoverflow.com shows a correct policy undermined by the wrong HTTP status.
  npr.org intends none of that -- its policy is the simplest and most symmetric of any
  site tested, every major operator blocked the same way -- and still fails, because
  two of its sixteen agent entries name a token that operator no longer uses
  (`Claude-Web`) or never used (`PerplexityUser`). Confirmed precisely against this
  project's own parser rather than assumed from reading the file: `Claude-User`,
  `Claude-SearchBot` and `Perplexity-User` all resolve `allowed`, while the file's own
  correctly-spelled `PerplexityBot` two lines below the misspelled entry proves the
  intent was never in question, only the execution. producthunt.com was also attempted
  in this final round and correctly not published: a genuine, reproducible Cloudflare
  "Just a moment..." challenge blocked even robots.txt itself across two attempts eight
  seconds apart, the same unverifiable-from-here pattern as kickstarter.com,
  mayoclinic.org, allrecipes.com and zillow.com before it.

## A check that has never fired, and why that itself was checked

`render-extractability-audit` Check 5 (interaction-gated content: accordions/tabs whose
panels are absent from the DOM until clicked) has not produced a true positive across any
of these twenty-five reports. Rather than leave that unexplained, eleven live production
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

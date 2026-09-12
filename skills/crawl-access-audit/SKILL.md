---
name: crawl-access-audit
description: >
  Determines whether an AI client can obtain a site's pages at all — stage 1 of the
  ai-citability-audit pipeline. Checks robots.txt for directives targeting AI crawlers,
  compares responses to AI-crawler user-agents against browser user-agents to expose
  bot-management blocks, and validates sitemap health, redirect chains and canonical
  integrity. Use when auditing why a site is absent from AI assistants, when a site
  appears healthy to humans but is uncited by LLMs, or when diagnosing whether GPTBot,
  ClaudeBot, PerplexityBot or similar agents are being refused. Invoked by
  audit-orchestrator; findings feed that skill's report.
license: MIT
allowed-tools: [WebFetch, Bash, Read]
---

# Crawl access audit — stage 1, reachability

## The concern this owns

Whether an AI client obtains the bytes. Nothing about what the bytes contain — that
belongs to `render-extractability-audit`.

This stage matters disproportionately because its failures are **silent and absolute**.
A site blocked at this layer looks perfect to its owner: it loads in a browser, it ranks
in Google, analytics show traffic. Meanwhile every assistant that tries to fetch it gets
refused, and the brand simply never appears in an answer. Nobody is notified. This is
the single most common cause of total AI invisibility and the one site owners are least
likely to suspect.

## Inputs

- Canonical origin
- Sampled URL list from the orchestrator
- Detected content patterns (unused at this stage — reachability is pattern-independent)
- Remaining request budget

## Procedure

Run `scripts/check_access.py <origin> --urls <file> --out observations.json` to collect
raw observations, then apply the checks below to turn observations into findings.

Observation and judgment are deliberately separated: the script records what happened,
this file decides what it means. That split is what keeps severity reproducible and
keeps thresholds visible rather than buried in code.

### Check 1 — AI-crawler directives in robots.txt

**Applies:** always.

**Procedure.** Fetch `/robots.txt`. Parse every `User-agent` group. For each agent in
`references/ai-crawler-agents.md`, resolve the effective rule for `/` and for each
sampled path, honouring group specificity — a named agent's group overrides `*`.

**Flag when.** Any AI crawler is disallowed from paths a human can reach. Report
per-agent, since blocking `CCBot` alone is a materially different decision from blocking
`GPTBot` and `ClaudeBot`.

**Do not flag when.** The disallow covers only genuinely non-public paths (`/admin`,
`/cart`, `/checkout`, `/search`, `/*?`), or the site is a staging or internal host, or
the block is on a path also disallowed for all agents including Googlebot — that is a
deliberate site-wide policy, not an AI-specific oversight.

**Distinguish two intents.** A site may block AI crawlers deliberately, to keep its
content out of training corpora. That is a legitimate business decision, not a defect.
Report it as a finding only when the block appears **unintentional** — signalled by
blocking retrieval agents (`OAI-SearchBot`, `PerplexityBot`, `ClaudeBot`) while leaving
training-corpus agents (`GPTBot`, `CCBot`, `Google-Extended`) permitted, or by inheriting
a block from a boilerplate robots file, or by blocking retrieval while the site
simultaneously invests in being found. Where intent is genuinely unclear, report at
reduced confidence and name the ambiguity in the evidence. Blocking training while
allowing retrieval is a coherent, deliberate posture and should be noted approvingly
rather than flagged.

**Evidence format.**
`robots.txt lines 4-6 declare "User-agent: GPTBot / Disallow: /". Retrieval agents OAI-SearchBot and PerplexityBot are also disallowed at /. Googlebot is permitted. All 15 sampled paths are affected.`

**Severity inputs.** stage 1 · prevalence from the fraction of sampled paths disallowed ·
criticality `core` when the homepage or primary offering pages are covered.

### Check 1b — Duplicate or self-contradictory agent groups

**Applies:** always. `scripts/check_access.py`'s `parse_robots()` reports this
structurally as `robots.duplicate_agent_groups` — a non-empty list means this check has
something to report, without needing to re-derive it by hand from the raw file.

**Procedure.** Check whether any single agent name is declared as its own `User-agent`
group more than once, non-contiguously, in the file. This is different from Check 1: that
check asks *which* agents are blocked; this one asks whether the file even has one
well-defined answer to that question for a given agent.

**Flag when.** `duplicate_agent_groups` is non-empty **and** the rule sets attached to
the repeated groups materially disagree (e.g. one occurrence carries `Allow` exceptions
the other lacks, or the two disagree on `/`). Confirmed live on nba.com: `GPTBot` and
`Google-Extended` are each declared twice, one occurrence permissive with nine `Allow`
exceptions, the other a bare `Disallow: /`.

**Do not flag when.** The repeated declarations are identical (a harmless, if untidy,
copy-paste with no ambiguity), or the agent is repeated only as consecutive `User-agent`
lines sharing one group (not a defect — that is how one rule set is meant to apply to
several agents at once, and `parse_robots()` does not count it as a duplicate).

**Why this is not the same as Check 1's "which agents are blocked."** The robots.txt spec
does not define behavior for repeated groups naming the same agent, and real-world
parsers disagree — some honor only the first group for an agent, some only the last, some
merge every rule encountered (this project's own parser merges, a defensible but not
uniquely correct choice). A file with this defect does not have one policy for the
affected agent; it has as many policies as there are plausible parsers, which is a more
fundamental problem than any single interpretation of it being wrong.

**Evidence format.**
`GPTBot is declared as a separate group twice: lines 12-13 attach nine Allow exceptions covering standings, schedule and player pages, but lines 58-59 attach only "Disallow: /" with none. A crawler that only honors the last group for a repeated agent would see a blanket block; one that merges, as this audit's own parser does, would see broad access. The file does not have one answer.`

**Severity inputs.** stage 1 · prevalence `isolated` unless several agents are affected ·
criticality `core`, since the ambiguity affects whether the entity's core content is
reachable at all for the agent in question, not a peripheral path.

### Check 1c — robots.txt served with a non-2xx status

**Applies:** always. `scripts/check_access.py` reports this structurally as
`robots.served_with_status` — non-`null` means this check has something to report.

**Procedure.** Fetch `/robots.txt` and note its HTTP status, independently of whether the
body parses into real directives. A response with a real, parseable body (the script's
own `body_looks_real` test: it contains a `User-agent:` line) served under any status
other than 200 is the concern here, most notably any 4xx.

**Flag when.** robots.txt returns a non-2xx status (429 aside — that means "back off",
not "unavailable") while its body contains genuine directives. Confirmed live on
stackoverflow.com: HTTP 418 carrying `Disallow: /` and `Content-signal: search=no,
ai-train=no` for the whole site.

**Why this matters more than it looks.** Per Google's documented crawler behavior, and
the convention most major crawlers follow, a 4xx status on robots.txt (other than 429) is
treated as "the file is unavailable" — which means an *unrestricted* crawl, not a
restricted one. A site whose robots.txt is maximally restrictive in content but served
under the wrong status code may have a policy that is, in practice, enforced by nobody.
This is the inverse of every other finding in this check: the site is not accidentally
too permissive, it is accidentally not enforcing its own maximally restrictive intent.

**Do not flag when.** The status is a genuine redirect that resolves to a 200 (follow it
first), or the body is empty/junk (that is Check 1's absence case, not this one), or the
status is 429 (rate-limiting, not unavailability).

**Evidence format.**
`robots.txt returns HTTP 418 with a real body: "User-agent: * / Content-signal: search=no, ai-train=no / Disallow: /". Per documented crawler behavior, a non-2xx status other than 429 is treated as "robots.txt unavailable" by major crawlers, meaning this maximally restrictive policy is likely not being enforced by any of the agents it names.`

**Severity inputs.** stage 1 · prevalence `site-wide` (the status affects the whole
file, hence every path) · criticality `core`.

### Check 2 — Bot-versus-browser response parity

**Applies:** always. This is the highest-value check in the marketplace.

**Procedure.** For each sampled URL permitted by robots.txt, issue two requests:

1. A realistic desktop Chrome `User-Agent` with a normal `Accept` header.
2. An AI-crawler `User-Agent` from `references/ai-crawler-agents.md`.

Compare status code, final URL after redirects, response body length, and whether the
body contains an interstitial marker (a challenge page, a CAPTCHA form, a
`cf-mitigated` header, a `<noscript>` block as the entire body).

Send requests with a randomised gap of 200-500 ms. Use the same client, timeouts and
redirect policy for both so the only variable is the user-agent string.

**Flag when.** The AI-agent request yields a different status class, or a body more than
30% shorter, or an interstitial marker the browser request did not receive.

**Do not flag when.** Both requests fail identically — that is a server problem, not a
bot-discrimination problem, and belongs to check 4. Also do not flag when the difference
is confined to content negotiation that does not remove facts, such as an omitted
personalisation banner. Re-test once before flagging: a single 403 can be transient
rate-limiting rather than a policy, and reporting it as a policy would be a false
positive.

**Evidence format.**
`14 of 15 sampled URLs returned HTTP 403 to User-Agent "ClaudeBot/1.0"; the identical requests with a Chrome User-Agent returned HTTP 200 with a median body of 47 KB. Response header "cf-mitigated: challenge" present on all 14. robots.txt does not disallow these paths.`

That last sentence matters: it establishes the block is contradicting the site's own
stated policy, which is what makes this unintentional rather than deliberate.

**Severity inputs.** stage 1 · prevalence from affected fraction · criticality `core`
when core pages are affected.

**Fix mechanism.** The block originates in a WAF or bot-management layer, not in the
application, so no code change resolves it. The fix is to allow the retrieval agents'
published address ranges or verified user-agents in that layer's rules — the same
treatment already given to Googlebot. Verification: `curl -s -o /dev/null -w "%{http_code}" -A "ClaudeBot/1.0" <url>` returns 200.

### Check 2b — Challenge shells served as HTTP 200

**Applies:** always. **This catches the most damaging and least visible form of blocking,
and check 2 alone will miss it.**

A refused fetch returning 403 is at least honest: it appears in logs and someone can act
on it. A bot-management layer that answers with **HTTP 200 and a JavaScript challenge
shell** is invisible. The status is success, analytics look normal, and the site owner
has no signal at all — while every non-executing fetcher receives a few kilobytes of
nothing and the brand silently vanishes from assistant answers.

Check 2 cannot find this. When the challenge is triggered by IP reputation rather than
user-agent, the browser control and the bot request are challenged identically: same
status, same body length, ratio 1.0, no difference to report.

**Procedure.** Independently of any user-agent comparison, examine each response for:

1. **Challenge vendor assets** — request paths such as `/_fs-ch-` (Fastly),
   `/cdn-cgi/challenge` (Cloudflare), `/_Incapsula_Resource`, `/akam/` (Akamai),
   `/_sec/cp_challenge` (Imperva), `/px/` (PerimeterX).
2. **Thin 200** — status 200, body under 8 KB, and under 400 characters of text once
   script and style elements are stripped.
3. **Challenge handshake cookie** — a `Set-Cookie` with a very short `Max-Age` (5-10 s)
   alongside `Cache-Control: no-store` on an ordinary content page.
4. **Cross-page contrast** — some sampled routes return full pages while others return
   near-identical tiny bodies. This is the signature of a rule scoped to page type, and
   no single-page check can see it.

Two or more signals together is a finding. One alone is not: a genuinely minimal page can
be a thin 200, and short-lived cookies have legitimate uses.

**Do not flag when.** Only one signal is present. Do not flag a small page that is simply
small — check the text-character count, not the byte count, and compare against the other
sampled pages before concluding.

**Evidence format.**
`2 of 8 sampled URLs return HTTP 200 with a 3,038-byte body containing 226 characters of text; the remaining 6 return a median of 2,895 characters. The thin responses load /_fs-ch-*/assets/ and set a Max-Age=10 cookie with Cache-Control: no-store. Affected routes: /project/<name>, /user/<name> — the site's two highest-volume templates.`

**Severity inputs.** stage 1 · prevalence from affected fraction · criticality `core` when
the affected routes are the site's primary content templates.

**Fix mechanism.** The challenge is issued by an edge bot-management layer on IP
reputation, so it fires for datacenter traffic regardless of user-agent — which is where
every AI retrieval agent originates. No application change resolves it. Allow verified
retrieval agents at that layer, as is already done for Googlebot, or serve them a
pre-rendered response rather than a challenge. Verification: fetch the affected route from
a datacenter IP and confirm the body contains the page's substantive text.

**Why this ranks above almost everything else.** If a site's highest-volume content
templates return shells, no downstream finding on those pages means anything — the markup,
prose and engagement checks were all run against a challenge page rather than the site.
Findings on affected routes must be marked `blocked_by` this one.

### Check 3 — Sitemap health

**Applies:** always.

**Procedure.** Locate the sitemap via `robots.txt`, `/sitemap.xml` and `/sitemap_index.xml`.
Follow index files one level. Validate that it parses, that URLs use the canonical
origin form, and sample up to 10 listed URLs for status.

**Flag when.** No sitemap is discoverable, or it is not referenced from robots.txt, or
more than 10% of sampled entries return 4xx/5xx, or entries use a non-canonical origin.

**Do not flag when.** The site has fewer than roughly 20 pages and exposes complete
internal linking from the homepage. A small, well-linked site is fully discoverable
without a sitemap, and flagging it would be noise.

**Severity inputs.** stage 1 · `site-wide` · criticality `supporting` for a missing
sitemap, `core` where dead entries point at primary pages.

### Check 4 — Redirect and canonical integrity

**Applies:** always.

**Procedure.** For each sampled URL, record the redirect chain length and terminal
status. Extract `<link rel="canonical">` and check that the target resolves 200 and
shares the canonical origin. Check that exactly one origin form serves 200 while the
others redirect to it.

**Flag when.** A chain exceeds three hops, a canonical points to a 404 or to a different
origin form, both `www` and apex serve 200 without redirecting, or a page canonicalises
to an unrelated URL.

**Do not flag when.** A single hop from `http` to `https` or from apex to `www` — that is
correct configuration. Self-referential canonicals are correct and must not be flagged.

**Severity inputs.** stage 1 · prevalence from affected fraction · criticality by page role.

### Check 5 — Access-blocking response conditions

**Applies:** always.

**Procedure.** Record status codes, response times and any authentication or geo
redirects across the sample. Flag paths where a fetcher would give up: 5xx, timeouts
beyond 10 s, login redirects on pages linked from public navigation, or geo-blocks.

**Flag when.** Any publicly-linked page is unreachable in a plain request.

**Do not flag when.** The page is legitimately gated — a customer portal, an account
area — and is not presented as public content.

**Severity inputs.** stage 1 · prevalence from affected fraction · criticality by page role.

### Check 6 — llms.txt presence and quality

**Applies:** always.

**Procedure.** `scripts/check_access.py` already fetches `/llms.txt` and records
`llms_txt` in its observations: presence, byte count, whether a Markdown heading exists,
and every `[text](url)` link found. Where present, judge whether the linked pages are
genuinely representative of the site's high-value content rather than only boilerplate
(legal, careers) or the homepage repeated — cross-check `sample_links` against the URL
templates the orchestrator sampled.

**Flag when.** The file exists but is hollow — no headings, no links, every linked page
404s — or its links point exclusively at low-value pages while omitting the site's own
primary content entirely.

**Do not flag when.** The file does not exist. `llms.txt` is an emerging, informal
convention that most sites — including well-optimised ones — do not yet publish; its
absence is a forward-looking opportunity, not a defect, and belongs in `opportunities`,
never in `findings`. Only a present-but-broken file is this check's concern.

**Evidence format.**
`/llms.txt returns HTTP 200 with 40 bytes: "# Example" and no further content — no headings beyond the title, no links.`

**Severity inputs.** stage 1 · `site-wide` · criticality `supporting`.

**Fix mechanism.** A present-but-hollow file is worse than none: it signals investment
without substance, and a retrieval-capable assistant that discovers it gets nothing
usable from it. Populate it with links to the site's genuinely highest-value pages —
the same pages this audit's other checks already treat as core content — grouped under
clear headings, rather than leaving a placeholder.

## Degradation

If the sample cannot be fetched at all, emit no findings and record in `not_assessed`:
check name, the reason, and what the reader consequently cannot conclude. Never infer a
block from a network failure on the auditing machine.

## Output

Findings against `../audit-orchestrator/references/report-schema.json`, each carrying
`stage: "reachability"`, `detected_by: "crawl-access-audit"`, the three severity inputs,
and a `reproduction` block with a runnable `curl` command. Severity labels are
recomputed by the orchestrator; report the inputs, not a verdict.

## Guardrails

Read-only. Respect robots.txt including during the parity check — never send an
AI-crawler user-agent to a path that agent is disallowed from, since doing so would
misrepresent the site's policy and abuse it at the same time. Cap at 2 requests per
sampled URL. Never authenticate, never submit a form, never retry a failed request more
than once.

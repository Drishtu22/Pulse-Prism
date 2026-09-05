---
name: crawl-access-audit
description: >
  Determines whether an AI client can obtain a site's pages at all — stage 1 of the
  brand-ai-readiness pipeline. Checks robots.txt for directives targeting AI crawlers,
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

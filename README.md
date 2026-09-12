# ai-citability-audit

An Agent Skill Marketplace that audits any website for the reasons AI assistants fail to
find, read, quote or trust it — and for the reasons visitors who arrive from an assistant
leave without engaging.

**Input:** one website URL or domain.
**Output:** one JSON report — findings with evidence and severity, prioritized fixes, and
proactive opportunities.
**Mode:** read-only. Nothing here modifies a live site.

## The idea

A brand can be invisible in AI assistants while looking perfectly healthy to its owner:
the site loads, it ranks in search, analytics show traffic. Meanwhile assistants asked a
question the brand should win recommend competitors instead, and nobody is notified.

This marketplace diagnoses why. It is not a search tool and not a scraper — it never
ranks pages against a query, and it inspects what a site says only to determine whether a
machine could have obtained it. It never judges whether the site's claims are true, only
whether they are reachable, readable, quotable and corroborated.

## The pipeline the decomposition follows

A fact has to survive six stages to reach an answer. A failure at any stage makes every
later stage moot — which is why the skills split along these lines rather than by topic,
and why the report suppresses findings that sit behind an unresolved blocker.

```
  ┌─ 1 REACHABILITY ── did an AI client get the bytes?
  │      crawl-access-audit
  ├─ 2 DELIVERY ─────── was the fact in the bytes it got?
  ├─ 3 TEXTUALITY ───── was the fact text, or pixels?
  │      render-extractability-audit
  ├─ 4 EXTRACTABILITY ─ does the text parse into a clean claim?
  │      structured-data-audit  ·  answerability-audit
  ├─ 5 TRUST ────────── is the claim current, consistent, corroborated?
  │      freshness-corroboration-audit
  └─ 6 ENGAGEMENT ───── did the visitor who arrived actually stay?
         engagement-audit
```

## Skills

| Skill | Stage | Owns |
|---|---|---|
| **audit-orchestrator** *(entrypoint)* | — | Site profiling, page sampling, invoking the six diagnostic skills, merging and deduplicating their findings, deriving severity, emitting the report |
| **crawl-access-audit** | 1 | robots.txt directives per AI agent, bot-vs-browser response parity, sitemap health, redirect and canonical integrity, `llms.txt` presence and quality |
| **render-extractability-audit** | 2, 3 | JavaScript dependency ratio, core facts missing from raw HTML, facts locked in images, canvas/PDF/video carriers, interaction-gated content |
| **structured-data-audit** | 4 | Schema coverage against detected content patterns, validity and completeness, **agreement with visible text**, identity linkage, Open Graph/Twitter Card completeness |
| **answerability-audit** | 4 | **Question-coverage probe**, definitional clarity, quotable-fact density, question-shaped structure, claim attribution |
| **freshness-corroboration-audit** | 5 | Recency signals on volatile facts, staleness, internal consistency, off-site corroboration, entity ambiguity |
| **engagement-audit** | 6 | Answer continuity above the fold, deep-entry orientation, entry obstruction, delivery performance, next-step clarity |

Stages 2 and 3 share a skill because they are diagnosed from the same three artefacts
(raw HTML, rendered DOM, page assets); splitting them would double the fetch cost for no
diagnostic gain. They are still reported as distinct stages because their fixes differ —
stage 2 is an engineering change, stage 3 a content change.

Stage 4 splits into two skills because the concerns are genuinely different: markup is
engineering work evaluated against a vocabulary, prose is content work evaluated
linguistically. A page can have flawless JSON-LD and still contain no sentence worth
quoting.

## How the entrypoint composes them

1. **Normalise and check permission** — resolve the canonical origin, fetch and parse
   `robots.txt`, set a 5-minute / 60-request budget.
2. **Sample** — `discover_pages.py` gathers candidates from the sitemap and homepage
   links, then selects a *stratified* sample: one page per URL template, seeded so
   re-runs inspect the same pages.
3. **Profile** — detect which content patterns the site exhibits (`transactable`,
   `physical_location`, `editorial`, `documentation`, …). This is the false-positive
   guard: no skill may assert a site is missing Product markup until it is established
   that the site sells something.
4. **Dispatch** — run all six diagnostic skills against the *same* sample, so prevalence
   figures are comparable and the merged report can be reasoned about.
5. **Merge** — deduplicate on root cause, recompute every severity centrally, apply
   blocked-by suppression, sort so reading order is fixing order, assign ids.
6. **Extend** — add opportunities derived from what is *absent* rather than broken.
7. **Emit** — `assemble_report.py` validates, computes summary and stage scores, writes
   `audit-report.json`.

## Design decisions worth knowing

**Severity is derived, not chosen.** `severity = stage_weight × prevalence × criticality`,
computed centrally in `assemble_report.py` from
`skills/audit-orchestrator/references/severity-model.md`. Every finding carries the three
inputs, so a label can be checked rather than trusted, and two runs on an unchanged site
produce identical severities.

**Findings are not independent.** If robots.txt blocks retrieval agents, a missing-JSON-LD
finding is moot — nothing can read the markup anyway. Blocked findings are capped at
medium and carry `blocked_by`, so the report's priority order is actually correct rather
than nominally prioritized.

**Evidence is reproducible.** Every finding carries a `reproduction` block with the URLs,
a single shell command, the observed result and the expected result. A site owner who can
reproduce a finding in ten seconds acts on it; one who cannot, argues with it.

**Measurement is separated from judgment.** Scripts emit raw observations; SKILL.md files
apply thresholds. Thresholds stay visible in readable files rather than buried in code,
and the same observations can be re-judged without re-crawling.

**Checks are conditional, not universal.** The *mechanisms* generalise to any site; the
*expectations* do not. Missing Product markup on a law firm is a false positive, so every
expectation check names the pattern that licenses it and the case where it must stay
silent.

**Gaps are declared.** When a check cannot run — no headless browser, budget exhausted —
it goes in `not_assessed` with a stated impact rather than being silently skipped or
guessed at. Absence of evidence is never reported as evidence of absence.

## Layout

```
ai-citability-audit/
├── marketplace.json
├── README.md
├── validate_marketplace.py
└── skills/
    ├── audit-orchestrator/          ← entrypoint
    │   ├── SKILL.md
    │   ├── scripts/{discover_pages,assemble_report}.py
    │   └── references/{severity-model.md,report-schema.json,content-patterns.md}
    ├── crawl-access-audit/
    │   ├── SKILL.md
    │   ├── scripts/check_access.py
    │   └── references/ai-crawler-agents.md
    ├── render-extractability-audit/  SKILL.md · scripts/render_diff.py
    ├── structured-data-audit/        SKILL.md · scripts/extract_jsonld.py
    ├── answerability-audit/          SKILL.md · scripts/quotability.py
    ├── freshness-corroboration-audit/SKILL.md · scripts/freshness_signals.py
    └── engagement-audit/             SKILL.md · scripts/engagement_probe.py
```

## Running it

The entrypoint is invoked by an agent, which follows `skills/audit-orchestrator/SKILL.md`.
The scripts are standard-library Python 3.8+ with no install step. A headless browser
(Playwright or Puppeteer via Node) is optional — without it, render and viewport checks
report `not_assessed` rather than guessing.

```bash
python3 validate_marketplace.py .      # manifest + skill-format check
```

## Guardrails

Read-only throughout. Respects `robots.txt` without exception, including during the
bot-parity check. No authenticated areas, no form submission, no checkout flows. Requests
are spaced and capped at 60 per audit within a 5-minute budget. Nothing is sent to a
third-party service; validation is local.


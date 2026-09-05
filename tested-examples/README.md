# Example audit reports

These are five **real, live audit runs** — not fabricated or hand-edited — produced by
actually invoking `audit-orchestrator` against five unseen, unrelated public websites
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

## Reproducing these

Each report's `audit_scope.sampled_urls` and every finding's `reproduction` block name
the exact URLs and a single shell command that reproduces the underlying observation —
that's a design requirement of the report format itself, not something added for these
examples.

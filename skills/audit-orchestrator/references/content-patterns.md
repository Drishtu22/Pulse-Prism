# Content patterns

The audit runs on sites the authors have never seen: a plumber, a physics preprint
archive, a municipal portal, a bank, a fan wiki. The *mechanisms* of failure are the
same everywhere, but *expectations* are not. Flagging a law firm for having no
Product markup is a false positive, and false positives are the fastest way to lose a
site owner's trust in the whole report.

So no check may assert what a site ought to contain until the orchestrator has
established what kind of content the site actually has. Patterns are detected, not
assumed, and a site may exhibit several at once — a university typically shows
`organization`, `editorial`, `events`, `documentation` and `listings` together.

## Detection

Detect from the sampled pages, not from the domain name or a guess about the industry.
A pattern is present when at least two independent signals agree; one signal alone is
too weak, and recording a pattern that isn't there re-introduces the false positives
this file exists to prevent.

| Pattern | Signals to look for |
|---------|--------------------|
| `organization` | Any site representing a named entity: an about page, contact details, a masthead or footer identifying an owner, a logo with a name. Assume present unless the site is clearly a personal scratch page. |
| `transactable` | Currency symbols beside item names, add-to-cart or buy or subscribe controls, a pricing or plans route, quantity selectors, checkout paths in the sitemap. |
| `physical_location` | Street address in the footer, opening hours, a map embed, "directions" or "visit us" links, multiple branch or store-locator pages. |
| `editorial` | Dated posts, an author byline, a blog or news or insights route, chronological archive or pagination. |
| `documentation` | Version markers, code blocks, API or reference or docs routes, a persistent sidebar navigation tree, anchored sub-sections. |
| `events` | Dates paired with venues, registration or RSVP controls, an agenda or schedule page, past/upcoming grouping. |
| `listings` | Repeated item cards under a shared template — jobs, properties, courses, directory entries, catalogue members without prices. |
| `research` | Papers or preprints, citation blocks, DOIs, author affiliations, dataset or methodology pages. |

## What each pattern licenses

A check may only assert an expectation when its licensing pattern was detected. The
right-hand column is what the check must fall silent about otherwise.

| Pattern | Licenses expectations about | Do not flag its absence when pattern absent |
|---------|----------------------------|---------------------------------------------|
| `organization` | Organization or LocalBusiness markup, `sameAs` identity links, a plain-language definitional sentence, consistent entity naming | — this pattern is near-universal, so its checks are effectively the floor |
| `transactable` | Product/Offer markup, price and currency and availability in text, stock or lead-time statements | Missing price data is not a defect on a site that sells nothing |
| `physical_location` | Address, geo and openingHours markup, address and hours as selectable text | An online-only service has no address to omit |
| `editorial` | `datePublished`, `dateModified`, author attribution, article markup | An evergreen about page carries no date obligation |
| `documentation` | Stable heading anchors, version labelling, code as text rather than screenshots | — |
| `events` | Event markup with start date, location and status | — |
| `listings` | ItemList or the item-appropriate type, per-item canonical URLs | — |
| `research` | ScholarlyArticle or Dataset markup, citation-ready metadata, author affiliation | — |

## The universal floor

These apply to every URL regardless of detected pattern, because they describe the
pipeline itself rather than any content type:

- An AI client can obtain the bytes at all.
- The substantive content is present without executing JavaScript.
- The facts exist as text rather than only inside images, canvas, video or scanned PDF.
- Somewhere near the top of the page, a self-contained sentence states what this entity
  or page is.
- There is some signal of when the volatile content was last true, where any volatile
  content exists.
- A visitor arriving on a deep page can tell what site they are on and what to do next.

## Rules

1. Record every detected pattern in `audit_scope.content_patterns_detected`. A reader
   must be able to see which conditional checks were in play.
2. When a pattern is detected but its expected markup is absent, that is a finding.
   When the pattern was not detected, the check does not run and is not mentioned.
3. When pattern detection itself is ambiguous — one weak signal, or a sample too small
   to tell — record the check in `not_assessed` rather than guessing in either
   direction. An honest gap costs less than a confident error.
4. Pattern detection never changes a *mechanism* check, only an *expectation* check. A
   JavaScript-only rendering failure is a defect on every kind of site.

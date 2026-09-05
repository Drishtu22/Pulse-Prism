# AI crawler user agents

Two populations, and conflating them produces wrong findings.

**Retrieval agents** fetch a page at the moment a user asks a question, to build an
answer now. Blocking these removes the brand from AI answers immediately. This is almost
always unintentional and is what this audit primarily cares about.

**Training-corpus agents** collect content for future model training. Blocking these is a
common, deliberate, defensible policy decision. It has little bearing on whether a brand
appears in a live assistant answer today.

A site that blocks training agents while permitting retrieval agents has made a coherent
choice. Say so approvingly rather than flagging it.

## Retrieval

| Token | Operator | Notes |
|-------|----------|-------|
| `OAI-SearchBot` | OpenAI | Powers ChatGPT search surfacing. Blocking it removes the site from ChatGPT's live results. |
| `ChatGPT-User` | OpenAI | Fetches a page when a user or a ChatGPT action requests it directly. |
| `PerplexityBot` | Perplexity | Indexing for Perplexity's answer engine. |
| `Perplexity-User` | Perplexity | User-initiated fetch. |
| `Claude-User` | Anthropic | Fetches a page in response to a user request in Claude. |
| `Claude-SearchBot` | Anthropic | Indexing to support Claude search results. |
| `Bingbot` | Microsoft | Feeds Copilot as well as Bing; blocking it affects both. |
| `Applebot` | Apple | Feeds Siri and Spotlight surfacing. |

## Training corpus

| Token | Operator | Notes |
|-------|----------|-------|
| `GPTBot` | OpenAI | Training data collection. |
| `ClaudeBot` | Anthropic | Training data collection. |
| `CCBot` | Common Crawl | Feeds many downstream datasets. |
| `Google-Extended` | Google | Controls Gemini and Vertex training use; does **not** affect Google Search crawling. |
| `Meta-ExternalAgent` | Meta | Training data collection. |
| `Bytespider` | ByteDance | Training data collection; frequently blocked for crawl-rate reasons. |
| `Amazonbot` | Amazon | Mixed retrieval and training use. |
| `cohere-ai` | Cohere | Training data collection. |

## Using this list

For the parity check in check 2, test with at least one agent from each population plus
a browser control. If the two populations behave differently, that is itself the
finding: it reveals the block is a deliberate, targeted policy rather than a blanket
bot-management rule.

Verify the exact current token strings against each operator's published documentation
when the audit runs. Operators rename and add agents, and an audit that tests a retired
token proves nothing. Where a token cannot be verified, test it anyway but record reduced
confidence.

Never use these strings to evade a block. If a path is disallowed for an agent, the
audit does not fetch it with that agent — the disallow is the observation, and fetching
anyway would both misrepresent the site's policy and abuse it.

## Interpreting `Google-Extended`

A frequent source of false positives. `Google-Extended` governs only Gemini training
use. It has no effect on Googlebot, Google Search indexing, or AI Overviews sourcing. A
site disallowing `Google-Extended` has opted out of training, not out of being found.
Do not report it as a discoverability defect.

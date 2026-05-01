# customer-support-agent

> Solo Founder OS agent #9 — triage user messages (signup-broken / forge-stuck / billing / love / spam / novel) → auto-draft replies → HITL queue.

[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](#)

Built by [Alex Ji](https://github.com/alex-jb) — closes the 5th layer of the canonical one-person-company stack (customer support).

## What it does

PH-day or post-launch, your inbox/PH-comments/X-DMs flood with user inquiries. This agent:

1. Reads incoming messages (JSONL inbox file)
2. Classifies each into one of 6 templates via Claude Haiku (or keyword fallback)
3. Drafts a reply for each non-spam classification
4. Writes drafts to `~/.customer-support-agent/queue/pending/` for HITL review

```
$ customer-support-agent triage --inbox messages.jsonl
# Customer support triage — 2026-05-02T13:24:00Z
Messages processed: 14
By label: {'signup_broken': 4, 'love': 5, 'billing': 2, 'forge_stuck': 1, 'spam': 1, 'novel': 1}
Drafts queued: 13
Spam skipped: 1
Novel (need human reply): 1
```

## Install

```bash
pip install customer-support-agent
# or
git clone https://github.com/alex-jb/customer-support-agent
cd customer-support-agent && pip install -e .
```

## Usage

### Triage a batch

Inbox JSONL format (one message per line):

```jsonl
{"source":"email","source_id":"abc123","sender":"alice@x.com","subject":"signup not working","body":"Verification email never arrived..."}
{"source":"producthunt","source_id":"ph_456","sender":"@bob","subject":"","body":"Love this!"}
```

```bash
customer-support-agent triage --inbox inbox.jsonl
```

### One-shot classify

```bash
customer-support-agent classify "I never got the verification email"
# label=signup_broken confidence=0.55
# reasoning: keyword match: signup, verification, email
```

### Check queue

```bash
customer-support-agent queue-status
# # Pending drafts (3)
#   - 2026-05-02-signup_broken-alice-x-com.md
#   - 2026-05-02-billing-bob-x-com.md
#   - 2026-05-02-novel-carol-x-com.md
```

## Six default labels

| Label | Trigger | Action |
|---|---|---|
| `signup_broken` | auth/login/register problems | empathetic + 2-3 troubleshooting steps |
| `forge_stuck` | core flow stuck/broken | "this is on me, fixing now" |
| `billing` | payment/refund/subscription | acknowledge + 24h response promise |
| `love` | positive feedback | brief thank-you |
| `spam` | promo/scam/irrelevant | skipped |
| `novel` | doesn't match any | "I'll think on this" placeholder + flag for human |

## Why all drafts go to HITL

Auto-sending replies to real users is the fastest way to get banned, mocked, or to send something tone-deaf. This agent NEVER sends. It drafts; you review in Obsidian; you send (or paste into Gmail / PH / X).

## MCP server

```bash
pip install 'customer-support-agent[mcp]'
```

```json
{
  "mcpServers": {
    "customer-support": {
      "command": "customer-support-mcp",
      "env": { "ANTHROPIC_API_KEY": "..." }
    }
  }
}
```

Tools: `classify_message(text, subject?, sender?)` · `draft_support_reply(text, subject?, sender?, label?)`

## Roadmap

- [x] **v0.1** — heuristic + Claude classifier · 6 labels · HITL queue · MCP server · 25 tests
- [ ] **v0.2** — IMAP + PH GraphQL ingest (auto-pull instead of JSONL)
- [ ] **v0.3** — auto-send "love" replies (still HITL on first 100, then auto)
- [ ] **v0.4** — Reflexion learning: classifier improves from rejected drafts

## License

MIT.

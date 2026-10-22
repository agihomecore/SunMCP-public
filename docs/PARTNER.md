# SunMCP partner programme (testers who resell)

A tester uses SunMCP and SunAPI, tells us what to fix, and earns by reselling.

## What a tester gets
| | |
|---|---|
| Personal SunAPI key (`sun_t_…`) | OpenAI-compatible endpoint `https://api.sun-agi.com/t/v1` on our own models, daily token limit |
| Client keys (`sun_c_…`) | resell SunAPI access to your own clients; usage is counted per client so you can bill them |
| Referral link `https://api.sun-agi.com/r/<code>` | leads to SunMCP Pro on Gumroad; Gumroad pays your commission on every sale |
| Proposals | ideas and bugs are triaged by our local model and decided by the founder; accepted ones give +1 point |

## Commands
```bash
export SUNAPI_KEY=sun_t_...            # from us, privately
sunmcp partner me                      # link, points, usage by client
sunmcp partner propose "one-line installer for Windows" --kind idea
sunmcp partner proposals               # status and answers
sunmcp partner key-add "Client A"      # client key, shown once
sunmcp partner config                  # sunmcp.json that runs on SunAPI (sun-moe)
sunmcp chat
```

## Models on SunAPI
| id | model | for |
|---|---|---|
| `sun-moe` | Qwen3.6-35B-A3B (MoE, 3B active) | agents, MCP tools, code, long context |
| `sun-14b` | Qwen2.5-14B | steady Russian dialogue |
| `sun-fast` | Qwen2.5-7B | short fast answers |

## Rules
- Keys are personal. A client key can only chat; it cannot see your stats or create keys.
- We store keys as SHA-256 hashes; a lost key is re-issued, not recovered.
- Commission and payouts for SunMCP Pro go through Gumroad's affiliate programme.

# Hardware and support tiers

SunMCP and the BOX family target paying, grateful users: offices and small
businesses on ordinary hardware. Enthusiasts are welcome to try anything
(an old phone, a Xiaomi Mi 5, a Raspberry Pi) on their own, without support.

Status of each number: **measured** (we ran it), **sourced** (public guidance),
**to measure** (not yet verified; do not promise it to customers).

| Tier | Hardware | Chat model | Vision | Support |
|---|---|---|---|---|
| Community | below Standard, old PCs, phones, SBCs | whatever you manage to run | no | none, self-service |
| **Standard** | x86-64 PC (AVX2), 4 cores, 16 GB RAM, SSD, ~20 GB free, no GPU needed | 3-4B, Q4_K_M, context 4-8K (sourced) | `qwen2.5vl:3b`, on command only | yes |
| **Plus** | 8 cores, 32 GB RAM | 7-8B, Q4_K_M (sourced: practical at 32 GB) | 3B on command | yes |
| **GPU** | GPU with 8+ GB VRAM | 7-14B | 7B interactive (to measure) | yes |

## Measured on a CPU-only laptop (0.3 GB VRAM, model of CPU not recorded)
- `qwen2.5:7b` (4.7 GB): tool calling works (add 17+25 = 42, shout "done" = DONE).
- `qwen2.5vl:3b` (3.2 GB): described the real screen correctly, about 5 minutes per image at 768 px.
- `qwen2.5vl:7b` (6.0 GB): no answer within 5+ minutes at 768 px. Not usable on this class of machine.
- `qwen2.5vl` models cannot call tools in Ollama; use a separate tool-capable chat model.

## Rules for the product
1. Vision is a command (`screenshot`, `/screen`), never a background loop on Standard.
2. The installer picks the model by installed RAM; the user never types a model name.
3. Tokens/second on 4 cores: **to measure** before any marketing claim.
4. Default chat model for Standard: to be chosen after the measurement (candidates from public guidance: Qwen 3-4B class).

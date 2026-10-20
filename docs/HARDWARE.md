# Hardware and support tiers

SunMCP and the BOX family target paying, grateful users: offices and small
businesses on ordinary hardware. Enthusiasts are welcome to try anything
(an old phone, a Xiaomi Mi 5, a Raspberry Pi) on their own, without support.

Status of each number: **measured** (we ran it), **sourced** (public guidance),
**to measure** (not yet verified; do not promise it to customers).

**Requirement (what we promise buyers): a CPU above average (8+ cores, 32 GB RAM) or an NVIDIA RTX GPU.** Standard still works, slowly.

| Tier | Hardware | Chat model | Vision | Support |
|---|---|---|---|---|
| Community | below Standard, old PCs, phones, SBCs | whatever you manage to run | no | none, self-service |
| **Standard** | x86-64 PC (AVX2), 4 physical cores, 16 GB RAM, SSD, ~20 GB free, no GPU needed | `qwen2.5:3b`, ~10 tok/s measured on i5-8250U | `qwen2.5vl:3b`, on command, ~100 s per screenshot measured | yes |
| **Plus** | 8 physical cores, 32 GB RAM | 7-8B, Q4_K_M (sourced: practical at 32 GB) | 3B on command | yes |
| **GPU** | NVIDIA GPU (RTX), 8+ GB VRAM; detected automatically by `sunmcp box` | 7-14B | 7B interactive (to measure) | yes |

## Measured on a CPU-only laptop (Intel i5-8250U, 4 cores / 8 threads, 32 GB RAM, 0.3 GB VRAM)
- `qwen2.5:7b` (4.7 GB): tool calling works (add 17+25 = 42, shout "done" = DONE). Speed, 2 runs, 64 tokens (Ollama's own timers): generation 3.7 and 4.8 tok/s, prompt processing 5.6 tok/s cold and 183 tok/s warm, first load 8.8 s. That is borderline for chat: fine for short answers, slow for long ones.
- **Speed, qwen2.5:3b, same laptop, 64 tokens, temperature 0:** Ollama default (`76%/24% CPU/GPU`, ctx 8192): 3.0 tok/s. Ollama with `num_gpu=0`, ctx 2048: 10.2-10.8 tok/s. llama.cpp `llama-server` b11753 (CPU build, 4 threads, ctx 2048): 10.6 tok/s. Same machine, 3 runs each for Ollama, 2 for llama-server. Conclusion: the engine is not the problem; the default GPU offload on a weak iGPU is. `sunmcp box` therefore ships CPU-only Modelfiles.
- `qwen2.5:7b` via llama-server (4 threads, ctx 2048): 4.6 tok/s, same as via Ollama (4.7).
- **End to end with `sunmcp box` (v0.2.6, CPU-only Modelfiles):** chat + two tool calls on qwen2.5:3b: 27 s. Screenshot description with qwen2.5vl:3b at 768 px: 99 s (was 5+ minutes with stock settings). The 3B vision answer was only partly right (it named a browser that was not on screen): treat vision as a rough aid, not a source of truth.
- `qwen2.5vl:3b` (3.2 GB): described the real screen correctly, about 5 minutes per image at 768 px.
- `qwen2.5vl:7b` (6.0 GB): no answer within 5+ minutes at 768 px. Not usable on this class of machine.
- `qwen2.5vl` models cannot call tools in Ollama; use a separate tool-capable chat model.

## Rules for the product
1. Vision is a command (`screenshot`, `/screen`), never a background loop on Standard.
2. The installer picks the model by installed RAM; the user never types a model name.
3. Tokens/second on 4 cores: 7B measured at ~4-5 tok/s (above); 3B **to measure** (expected faster, not verified). Do not quote a number to customers for other hardware.
4. Default chat model for Standard: `qwen2.5:3b` (speed to be measured; tier logic in `sunmcp box`).

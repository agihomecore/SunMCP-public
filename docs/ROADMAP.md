# Roadmap

SunMCP is the hands and eyes of **Salina**, a local assistant for small businesses in Kazakhstan.
Order matters: each step ships on its own and is tested on a real task first.

| Version | What | Status |
|---|---|---|
| 0.3.0 | `sunmcp partner` (SunAPI tester/reseller programme) | released |
| 0.3.1 | `examples/salina_web_server.py`: web tools on official APIs only (Brave Search API with your key, else Wikipedia); docs and cards | in this repo |
| 0.4.0 | Screen, step 1 "See": screenshot + description with the same local model (Gemma 4 sees images) + Windows UI Automation tree (names of buttons and fields) | next |
| 0.4.x | Screen, step 2 "Act": click, type, hotkeys, scroll — every action confirmed; first tasks: type text into a field, find information on the web | planned |
| 0.4.x | Safety: never sees or touches banking, payment, password managers or messengers; never types into a password field; irreversible actions (send, pay, delete, publish) only after an explicit yes; kill switch (mouse to a screen corner); action log without screen contents | planned |
| 0.5.0 | Local bridge for desktop apps (Salina tray app talks to SunMCP on 127.0.0.1) | planned |
| 0.6.0 | macOS | planned |

Principles: local by default, model-agnostic, no vendor lock-in, no secrets in configs (`api_key_env`, `.env`), no scraping or bot-check workarounds — only official APIs.

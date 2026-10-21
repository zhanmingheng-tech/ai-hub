# Changelog

## [0.2.0] - 2026-10-21

### Added
- Group discussion / 讨论组 mode: tick which configured AIs join, send one message, and each replies in turn (labeled with its name) over 1–3 rounds, sharing one transcript. One AI's error doesn't stop the others.
- Portable config: `AI_HUB_CONFIG_DIR` env var, or a `.ai_hub` folder next to `ai_hub.py`, overrides `~/.ai_hub`.

### Unchanged
- Single-AI chat mode works as before.

## [0.1.0] - 2026-10-21

### Added
- Initial release.
- Tkinter desktop chat window using only the Python standard library.
- Providers: DeepSeek, OpenAI, Moonshot (Kimi), Qwen (DashScope OpenAI-compatible mode), and a custom OpenAI-compatible endpoint.
- Settings dialog for per-provider API key, base URL and model, saved to `~/.ai_hub/config.json`.
- Per-session chat history, "Clear chat" button, background-thread requests, readable error messages.

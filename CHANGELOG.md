# Changelog

## [0.3.0] - 2026-10-22

### Added
- WeChat-style UI: sidebar with group rooms and AI members (colored avatars), chat bubbles with name and time.
- Persistent groups/meetings (name, members, topic, host) with history in `.ai_hub/groups/*.json`.
- Meeting modes: round-robin (1–3 rounds), `@Name` single reply, free discussion (members respond to each other, `[跳过]` to pass), host who steers and produces a **meeting summary** (conclusions, disagreements, action items), roll call (“准备好了”), and a Stop button.
- Providers: Anthropic Claude (native Messages API), Google Gemini (OpenAI-compatible), xAI Grok, Doubao / Volcengine Ark, Zhipu GLM.
- Configurable members (name, provider, model, persona, color); one provider can be used by several members.
- Meeting-aware system prompt per AI (group name, members, be concise, address by name, don't repeat).

### Changed
- Config is portable by default: `.ai_hub` next to `ai_hub.py` (created automatically) unless `AI_HUB_CONFIG_DIR` is set. `~/.ai_hub` is no longer used.
- Single-AI mode replaced by groups (a group with one member works as a 1:1 chat).

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

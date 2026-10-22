# AI Hub

[中文说明](README.zh-CN.md)

A beginner-friendly, WeChat-style desktop app that **pulls several AIs into one group meeting**.
Claude, Gemini, Grok, Doubao, ChatGPT, DeepSeek… sit in one group chat and discuss your question together.
Uses **only the Python standard library** (tkinter + urllib + json) — no `pip install`.

## Features (v0.3.0)

- Chat-app UI: left sidebar with group rooms and AI members (colored avatars); right pane with chat bubbles (you on the right, AIs on the left with name + time); input box at the bottom (Enter = send, Shift+Enter = newline).
- **Groups / meetings**: name, member AIs, optional topic, optional **host**. Groups and their history are saved as JSON.
- **Meeting modes**
  - **轮流发言 / Round-robin** – every member replies in turn, seeing the whole transcript, for 1–3 rounds.
  - **@Name** – write `@Grok …` (or choose “@指定成员”) and only that member replies.
  - **自由讨论 / Free discussion** – members reply in turn and respond to each other; a member can pass with `[跳过]`; ends early when everyone passes.
  - **Host** – the host speaks last each round to steer; **📝 会议总结** makes the host summarize conclusions, disagreements and action items.
  - **📣 召集开会** – roll call: every member answers “准备好了”.
  - **⏹ Stop** halts a running meeting (after the current request).
- Each AI gets a system prompt: it is in meeting *X* with members *Y*, should be concise, address others by name and not repeat others. Optional per-member persona.
- Providers: DeepSeek, OpenAI, **Anthropic Claude** (native `/v1/messages`), **Google Gemini** (OpenAI-compatible endpoint), **xAI Grok**, **Doubao / Volcengine Ark** (model = your endpoint id `ep-…`), **Zhipu GLM**, Moonshot (Kimi), Qwen, and any custom OpenAI-compatible endpoint.
- Members are configurable (name, provider, model, persona, color); the same provider can appear several times with different personas.
- Requests run in background threads; one member’s error is shown in a red bubble and the others continue.

## Requirements

Python 3.10+. The python.org Windows installer includes tkinter. On Linux: `sudo apt install python3-tk`.

## Run

```bash
python ai_hub.py
```

1. **⚙ 设置 → 服务商 API Key**: paste the keys you have (members without a key are shown grey).
2. **⚙ 设置 → AI 成员**: add/edit members.
3. **＋ 新建群聊**: name the group, pick members, topic and host.
4. Type a message and send; choose mode and rounds in the bar above the input.

## Where are keys and history stored?

**Portable by default:** in a `.ai_hub` folder next to `ai_hub.py` (`.ai_hub/config.json`, `.ai_hub/groups/*.json`).
Set `AI_HUB_CONFIG_DIR` to use another folder. Nothing is written to your home directory.
Keys are stored in plain text; `.ai_hub/` is in `.gitignore` — never commit or share it.
Upgrading from ≤0.2.0 with `~/.ai_hub/config.json`: move that file into the new `.ai_hub` folder.

## License

[MIT](LICENSE)

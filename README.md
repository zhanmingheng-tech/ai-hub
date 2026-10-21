# AI Hub

[中文说明](README.zh-CN.md)

A tiny, beginner-friendly desktop chat app that lets you talk to several AI providers from one window.
It uses **only the Python standard library** (tkinter + urllib + json) — no `pip install` required.

## Features

- Pick a provider from a dropdown: **DeepSeek**, **OpenAI**, **Moonshot (Kimi)**, **Qwen (DashScope)**, or any **custom OpenAI-compatible** endpoint.
- All providers are called through the OpenAI-compatible `/chat/completions` API.
- Settings dialog: enter your own API key, base URL and model for each provider.
- Chat history is kept for the current session (multi-turn conversation); "Clear chat" resets it.
- Requests run in a background thread, so the window never freezes.
- Readable error messages (invalid key, quota, network problems, etc.).

## Requirements

- Python 3.10 or newer. On Windows, the official installer from python.org includes tkinter.
- On Linux you may need to install tkinter separately, e.g. `sudo apt install python3-tk`.

## Install & Run

```bash
git clone <your-fork-url> ai-hub
cd ai-hub
python ai_hub.py
```

On Windows you can also double-click `ai_hub.py`, or run `py ai_hub.py`.

## Usage

1. Click **Settings**, choose a provider tab and paste your API key. Adjust the model name if you like.
2. Click **Save**.
3. Choose the provider in the dropdown, type a message, and press **Send** (or `Ctrl+Enter`).

For **Custom**, enter the base URL up to `/v1` (for example `http://localhost:11434/v1`), the model name, and a key (any non-empty value if your server does not check keys).

## Group discussion (v0.2.0)

Tick **Group** in the second toolbar row, tick the AIs that should join (each needs its key set in Settings), choose **Rounds** (1–3) and send one message. Each selected AI replies in turn in the same window, labeled with its name. Every AI sees the shared transcript: the user's messages and the other AIs' replies (passed as user messages prefixed with `[Name]:`), plus a short system prompt saying it is in a group chat and should respond to the others. If one AI fails, its error is shown and the others continue. Untick **Group** to return to normal single-AI chat.

## Where is my API key stored?

In `~/.ai_hub/config.json` in your home directory (on Windows: `C:\Users\<you>\.ai_hub\config.json`).

**Portable mode:** if the environment variable `AI_HUB_CONFIG_DIR` is set, that folder is used; otherwise, if a folder named `.ai_hub` exists next to `ai_hub.py`, config is stored there.
It is stored in plain text, is **never** written into the project folder, and `config.json` is listed in `.gitignore`.
Do not share this file.

## License

[MIT](LICENSE)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Hub - 一个简单的桌面 AI 聚合聊天工具
AI Hub - a simple desktop AI aggregator chat app.

只用 Python 标准库 (tkinter + urllib + json)，无需安装任何第三方包。
Uses only the Python standard library (tkinter + urllib + json); no pip install needed.

所有服务商都使用 OpenAI 兼容的 /chat/completions 接口。
All providers use the OpenAI-compatible /chat/completions endpoint.

API Key 保存在用户主目录下的 ~/.ai_hub/config.json，绝不会写进项目目录。
API keys are stored in ~/.ai_hub/config.json in your home directory, never in the repo.
"""

import json
import os
import queue
import threading
import urllib.error
import urllib.request
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

__version__ = "0.2.0"

# 配置文件位置（用户主目录） / Config file location (user's home dir)
CONFIG_DIR = Path.home() / ".ai_hub"
# 便携模式：若设置了环境变量 AI_HUB_CONFIG_DIR，或脚本旁存在 .ai_hub 文件夹，则使用它
# Portable mode: use env AI_HUB_CONFIG_DIR, or a `.ai_hub` folder next to this script, if present
_LOCAL_DIR = Path(__file__).resolve().parent / ".ai_hub"
if os.environ.get("AI_HUB_CONFIG_DIR"):
    CONFIG_DIR = Path(os.environ["AI_HUB_CONFIG_DIR"]).expanduser()
elif _LOCAL_DIR.is_dir():
    CONFIG_DIR = _LOCAL_DIR
CONFIG_PATH = CONFIG_DIR / "config.json"

# 内置服务商：名称 -> 默认接口地址和默认模型
# Built-in providers: name -> default base URL and default model
PROVIDERS = {
    "DeepSeek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "OpenAI": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "Moonshot (Kimi)": {"base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    "Qwen (DashScope)": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "Custom (OpenAI-compatible)": {"base_url": "", "model": ""},
}

REQUEST_TIMEOUT = 120  # 秒 / seconds
GROUP_NAME = "AI Hub 讨论组 / Group Discussion"


def build_group_messages(speaker, participants, transcript, group_name=GROUP_NAME):
    """为某个 AI 构造群聊上下文：自己的发言是 assistant，其他人（用户和其他 AI）是带名字前缀的 user。
    Build the message list for one AI in group mode: its own turns are `assistant`,
    everyone else's (user and other AIs) are `user` messages prefixed with the speaker name.
    transcript: list of (speaker_name, text); the human user is "User"."""
    others = ", ".join(p for p in participants if p != speaker)
    system = (f"You are {speaker}, taking part in a group chat named \"{group_name}\". "
              f"Participants: User (the human), {', '.join(participants)}. "
              f"Other participants besides you: {others or 'none'}. "
              "Messages from others are prefixed with '[Name]:'. Read the whole discussion, "
              "respond to the user and to the other AIs' points (agree, disagree, add), be concise, "
              "and do not prefix your own reply with your name. Reply in the user's language.")
    msgs = [{"role": "system", "content": system}]
    for who, text in transcript:
        if who == speaker:
            msgs.append({"role": "assistant", "content": text})
        else:
            msgs.append({"role": "user", "content": f"[{who}]: {text}"})
    return msgs


# ---------------------------------------------------------------------------
# 配置读写 / Config load & save
# ---------------------------------------------------------------------------
def load_config():
    """读取配置；文件不存在或损坏时返回默认值。
    Load config; return defaults if missing or broken."""
    cfg = {"last_provider": "DeepSeek", "providers": {}}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update(data)
    except (OSError, ValueError):
        pass
    # 为每个服务商补齐字段 / Fill in fields for each provider
    for name, d in PROVIDERS.items():
        p = cfg["providers"].setdefault(name, {})
        p.setdefault("api_key", "")
        p.setdefault("base_url", d["base_url"])
        p.setdefault("model", d["model"])
    return cfg


def save_config(cfg):
    """保存配置到主目录。 Save config to the home directory."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(CONFIG_PATH, 0o600)  # 仅本人可读（Windows 上无影响）/ owner-only on Unix
    except OSError:
        pass


# ---------------------------------------------------------------------------
# 网络请求 / API request
# ---------------------------------------------------------------------------
def chat_completion(base_url, api_key, model, messages):
    """调用 OpenAI 兼容接口，返回助手回复文本；出错时抛出带可读信息的 RuntimeError。
    Call an OpenAI-compatible endpoint and return the reply text.
    Raises RuntimeError with a readable message on failure."""
    if not base_url:
        raise RuntimeError("未设置接口地址 / Base URL is not set. Open Settings.")
    if not api_key:
        raise RuntimeError("未设置 API Key / API key is not set. Open Settings.")
    if not model:
        raise RuntimeError("未设置模型名 / Model is not set. Open Settings.")

    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps({"model": model, "messages": messages}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 尽量取出服务端的错误说明 / Try to extract the server's error message
        detail = ""
        try:
            err = json.loads(e.read().decode("utf-8", "replace"))
            detail = (err.get("error") or {}).get("message", "") if isinstance(err.get("error"), dict) else str(err.get("error") or err)
        except Exception:
            pass
        hints = {
            401: "API Key 无效 / Invalid API key",
            403: "无权限 / Forbidden",
            404: "地址或模型不存在 / URL or model not found",
            429: "请求太频繁或额度不足 / Rate limited or out of quota",
        }
        hint = hints.get(e.code, "服务器错误 / Server error")
        raise RuntimeError(f"HTTP {e.code}: {hint}\n{detail}".strip())
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误 / Network error: {e.reason}")
    except TimeoutError:
        raise RuntimeError("请求超时 / Request timed out")
    except ValueError:
        raise RuntimeError("返回内容不是有效 JSON / Response is not valid JSON")

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("返回格式异常 / Unexpected response format:\n" + str(data)[:500])


# ---------------------------------------------------------------------------
# 设置对话框 / Settings dialog
# ---------------------------------------------------------------------------
class SettingsDialog(tk.Toplevel):
    """为每个服务商填写 API Key、接口地址和模型。
    Enter API key, base URL and model per provider."""

    def __init__(self, master, cfg, on_save):
        super().__init__(master)
        self.title("Settings / 设置")
        self.cfg = cfg
        self.on_save = on_save
        self.resizable(False, False)
        self.transient(master)
        self.entries = {}

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)
        for name in PROVIDERS:
            p = cfg["providers"][name]
            frame = ttk.Frame(nb, padding=10)
            nb.add(frame, text=name.split(" ")[0])
            vars_ = {}
            for row, (key, label, secret) in enumerate([
                ("api_key", "API Key", True),
                ("base_url", "Base URL / 接口地址", False),
                ("model", "Model / 模型", False),
            ]):
                ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
                var = tk.StringVar(value=p.get(key, ""))
                ttk.Entry(frame, textvariable=var, width=50, show="*" if secret else "").grid(
                    row=row, column=1, pady=4, padx=(8, 0))
                vars_[key] = var
            self.entries[name] = vars_

        ttk.Label(self, text=f"保存位置 / Saved to: {CONFIG_PATH}", foreground="gray").pack(padx=10, anchor="w")
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=10, pady=10)
        ttk.Button(btns, text="Save / 保存", command=self.save).pack(side="right")
        ttk.Button(btns, text="Cancel / 取消", command=self.destroy).pack(side="right", padx=6)

    def save(self):
        for name, vars_ in self.entries.items():
            for key, var in vars_.items():
                self.cfg["providers"][name][key] = var.get().strip()
        try:
            save_config(self.cfg)
        except OSError as e:
            messagebox.showerror("Error", f"保存失败 / Save failed:\n{e}", parent=self)
            return
        self.on_save()
        self.destroy()


# ---------------------------------------------------------------------------
# 主窗口 / Main window
# ---------------------------------------------------------------------------
class AIHubApp:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.history = []  # 本次会话的消息记录 / messages for this session
        self.busy = False

        root.title(f"AI Hub v{__version__}")
        root.geometry("760x600")
        root.minsize(500, 400)

        # 顶部工具栏 / Top toolbar
        top = ttk.Frame(root, padding=(8, 8, 8, 0))
        top.pack(fill="x")
        ttk.Label(top, text="Provider / 服务商:").pack(side="left")
        self.provider_var = tk.StringVar(value=self.cfg.get("last_provider", "DeepSeek"))
        if self.provider_var.get() not in PROVIDERS:
            self.provider_var.set("DeepSeek")
        combo = ttk.Combobox(top, textvariable=self.provider_var, values=list(PROVIDERS),
                             state="readonly", width=28)
        combo.pack(side="left", padx=6)
        combo.bind("<<ComboboxSelected>>", self.on_provider_change)
        ttk.Button(top, text="Settings / 设置", command=self.open_settings).pack(side="right")
        ttk.Button(top, text="Clear chat / 清空", command=self.clear_chat).pack(side="right", padx=6)

        # 讨论组栏：勾选参与的 AI 与轮数 / Group bar: tick participating AIs and number of rounds
        group = ttk.Frame(root, padding=(8, 6, 8, 0))
        group.pack(fill="x")
        self.group_mode = tk.BooleanVar(value=False)
        ttk.Checkbutton(group, text="Group / 讨论组:", variable=self.group_mode).pack(side="left")
        self.member_vars = {}
        for name in PROVIDERS:
            v = tk.BooleanVar(value=False)
            self.member_vars[name] = v
            ttk.Checkbutton(group, text=name.split(" ")[0], variable=v).pack(side="left", padx=2)
        self.rounds_var = tk.IntVar(value=1)
        ttk.Spinbox(group, from_=1, to=3, width=3, textvariable=self.rounds_var,
                    state="readonly").pack(side="right")
        ttk.Label(group, text="Rounds / 轮数:").pack(side="right", padx=(6, 2))
        self.transcript = []  # 讨论组共享记录 [(speaker, text)] / shared group transcript

        # 聊天显示区 / Chat display
        self.chat = scrolledtext.ScrolledText(root, wrap="word", state="disabled", font=("TkDefaultFont", 11))
        self.chat.pack(fill="both", expand=True, padx=8, pady=8)
        self.chat.tag_config("user", foreground="#1a5fb4")
        self.chat.tag_config("bot", foreground="#222222")
        self.chat.tag_config("error", foreground="#c01c28")
        self.chat.tag_config("info", foreground="gray")

        # 输入区 / Input area
        bottom = ttk.Frame(root, padding=(8, 0, 8, 8))
        bottom.pack(fill="x")
        self.input = tk.Text(bottom, height=4, wrap="word", font=("TkDefaultFont", 11))
        self.input.pack(side="left", fill="x", expand=True)
        self.input.bind("<Control-Return>", lambda e: (self.send(), "break")[1])
        self.send_btn = ttk.Button(bottom, text="Send / 发送\n(Ctrl+Enter)", command=self.send)
        self.send_btn.pack(side="right", padx=(6, 0), fill="y")

        self.status = tk.StringVar(value="Ready / 就绪")
        ttk.Label(root, textvariable=self.status, anchor="w", padding=(8, 0, 8, 4)).pack(fill="x")

        self.append("info", "欢迎使用 AI Hub！先点击「设置」填写 API Key。\n"
                            "Welcome to AI Hub! Click Settings to enter your API key first.\n\n")

    # --- 辅助方法 / helpers ---
    def append(self, tag, text):
        self.chat.configure(state="normal")
        self.chat.insert("end", text, tag)
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def on_provider_change(self, _event=None):
        self.cfg["last_provider"] = self.provider_var.get()
        try:
            save_config(self.cfg)
        except OSError:
            pass
        self.append("info", f"[切换到 / Switched to {self.provider_var.get()}]\n\n")

    def open_settings(self):
        SettingsDialog(self.root, self.cfg, on_save=lambda: self.status.set("Settings saved / 设置已保存"))

    def clear_chat(self):
        if self.busy:
            return
        self.history.clear()
        self.transcript.clear()
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self.status.set("Chat cleared / 已清空")

    # --- 发送消息 / sending ---
    def send(self):
        if self.busy:
            return
        text = self.input.get("1.0", "end").strip()
        if not text:
            return
        if self.group_mode.get():
            return self.send_group(text)
        name = self.provider_var.get()
        p = self.cfg["providers"][name]
        self.input.delete("1.0", "end")
        self.append("user", f"You / 你:\n{text}\n\n")
        self.history.append({"role": "user", "content": text})
        self.set_busy(True, f"Waiting for {name}... / 等待回复中...")

        # 在后台线程请求，避免窗口卡住 / Run in a background thread so the UI stays responsive
        args = (p["base_url"], p["api_key"], p["model"], list(self.history))
        threading.Thread(target=self._worker, args=(name, args), daemon=True).start()

    def _worker(self, name, args):
        try:
            reply = chat_completion(*args)
            result = ("ok", reply)
        except Exception as e:  # 所有错误都显示给用户 / show every error to the user
            result = ("error", str(e))
        # tkinter 只能在主线程更新界面 / Only update the UI from the main thread
        self.root.after(0, self._on_result, name, result)

    def _on_result(self, name, result):
        kind, text = result
        if kind == "ok":
            self.history.append({"role": "assistant", "content": text})
            self.append("bot", f"{name}:\n{text}\n\n")
            self.set_busy(False, "Ready / 就绪")
        else:
            self.history.pop()  # 失败的问题不计入历史 / drop the failed user message
            self.append("error", f"Error / 错误:\n{text}\n\n")
            self.set_busy(False, "Error / 出错")

    # --- 讨论组 / group discussion ---
    def send_group(self, text):
        members = [n for n, v in self.member_vars.items() if v.get()]
        if not members:
            messagebox.showinfo("AI Hub", "请至少勾选一个 AI / Tick at least one AI.", parent=self.root)
            return
        try:
            rounds = max(1, min(3, int(self.rounds_var.get())))
        except (ValueError, tk.TclError):
            rounds = 1
        self.input.delete("1.0", "end")
        self.append("user", f"You / 你:\n{text}\n\n")
        self.transcript.append(("User", text))
        # 快照配置，线程内不读界面变量 / snapshot config; the thread never touches Tk variables
        conf = {n: dict(self.cfg["providers"][n]) for n in members}
        self.set_busy(True, "Group discussion... / 讨论中...")
        # 后台线程只往队列放结果，主线程轮询队列更新界面
        # The worker only puts events on a queue; the main thread polls it and updates the UI
        self.group_q = queue.Queue()
        threading.Thread(target=self._group_worker, args=(members, conf, rounds), daemon=True).start()
        self.root.after(50, self._poll_group)

    def _poll_group(self):
        try:
            while True:
                ev = self.group_q.get_nowait()
                if ev[0] == "status":
                    self.status.set(ev[1])
                elif ev[0] == "done":
                    self.set_busy(False, "Ready / 就绪")
                    return
                else:
                    self._on_group_reply(*ev[1:])
        except queue.Empty:
            pass
        self.root.after(50, self._poll_group)

    def _group_worker(self, members, conf, rounds):
        # 依次发言；单个 AI 出错不影响其他 AI / speak in turn; one AI's error doesn't stop others
        transcript = list(self.transcript)
        for r in range(1, rounds + 1):
            for name in members:
                self.group_q.put(("status", f"Round {r}/{rounds}: {name}... / 第{r}轮"))
                p = conf[name]
                try:
                    msgs = build_group_messages(name, members, transcript)
                    reply = chat_completion(p["base_url"], p["api_key"], p["model"], msgs)
                    transcript.append((name, reply))
                    self.group_q.put(("reply", name, r, "ok", reply))
                except Exception as e:
                    self.group_q.put(("reply", name, r, "error", str(e)))
        self.group_q.put(("done",))

    def _on_group_reply(self, name, rnd, kind, text):
        if kind == "ok":
            self.transcript.append((name, text))
            self.append("bot", f"{name} (round {rnd} / 第{rnd}轮):\n{text}\n\n")
        else:
            self.append("error", f"{name} error / 错误:\n{text}\n\n")

    def set_busy(self, busy, msg):
        self.busy = busy
        self.send_btn.configure(state="disabled" if busy else "normal")
        self.status.set(msg)


def main():
    root = tk.Tk()
    AIHubApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

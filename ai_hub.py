#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Hub v0.3.0 - 把多个 AI 拉进一个群里开会的桌面聊天工具
AI Hub - a WeChat-style desktop app that pulls several AIs into one group meeting.

只用 Python 标准库 (tkinter + urllib + json)，无需 pip install。
Standard library only (tkinter + urllib + json); no pip install needed.

配置默认保存在 ai_hub.py 旁边的 .ai_hub 文件夹（便携模式），
可用环境变量 AI_HUB_CONFIG_DIR 指定其他位置。不会写到 C 盘用户目录。
Config lives in a `.ai_hub` folder next to ai_hub.py (portable mode) unless
AI_HUB_CONFIG_DIR is set. Nothing is written to the home directory.
"""

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

__version__ = "0.3.0"

# ---------------------------------------------------------------------------
# 配置位置 / Config location (portable by default)
# ---------------------------------------------------------------------------
if os.environ.get("AI_HUB_CONFIG_DIR"):
    CONFIG_DIR = Path(os.environ["AI_HUB_CONFIG_DIR"]).expanduser()
else:
    CONFIG_DIR = Path(__file__).resolve().parent / ".ai_hub"
CONFIG_PATH = CONFIG_DIR / "config.json"
GROUPS_DIR = CONFIG_DIR / "groups"

# 服务商：kind = openai（OpenAI 兼容）或 anthropic（Claude 原生接口）
# Providers: kind = "openai" (OpenAI-compatible) or "anthropic" (native Messages API)
PROVIDERS = {
    "DeepSeek": {"kind": "openai", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "OpenAI": {"kind": "openai", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "Anthropic Claude": {"kind": "anthropic", "base_url": "https://api.anthropic.com/v1", "model": "claude-sonnet-4-5"},
    "Google Gemini": {"kind": "openai", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "model": "gemini-2.5-flash"},
    "xAI Grok": {"kind": "openai", "base_url": "https://api.x.ai/v1", "model": "grok-3-mini"},
    "豆包 (火山方舟)": {"kind": "openai", "base_url": "https://ark.cn-beijing.volces.com/api/v3", "model": ""},
    "Zhipu GLM": {"kind": "openai", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
    "Moonshot (Kimi)": {"kind": "openai", "base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    "Qwen (DashScope)": {"kind": "openai", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    "Custom (OpenAI-compatible)": {"kind": "openai", "base_url": "", "model": ""},
}
MODEL_HINTS = {"豆包 (火山方舟)": "模型填推理接入点 ID，如 ep-2025xxxx / model = endpoint id (ep-...)"}

COLORS = ["#d97757", "#4285f4", "#111111", "#2e7d32", "#10a37f", "#7b1fa2",
          "#c62828", "#00838f", "#f9a825", "#5d4037"]
DEFAULT_MEMBERS = [  # (name, provider)
    ("Claude", "Anthropic Claude"), ("Gemini", "Google Gemini"), ("Grok", "xAI Grok"),
    ("豆包", "豆包 (火山方舟)"), ("ChatGPT", "OpenAI"), ("DeepSeek", "DeepSeek"),
]
REQUEST_TIMEOUT = 120
USER = "我"          # 用户在记录中的名字 / the human's name in transcripts
PASS_TOKEN = "[跳过]"


def now_str():
    return time.strftime("%H:%M")


def new_id():
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# 配置读写 / Config
# ---------------------------------------------------------------------------
def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_config():
    cfg = {"providers": {}, "members": []}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update(data)
    except (OSError, ValueError):
        pass
    for name, d in PROVIDERS.items():
        p = cfg["providers"].setdefault(name, {})
        p.setdefault("api_key", "")
        p.setdefault("base_url", d["base_url"])
        p.setdefault("model", d["model"])
    if not cfg["members"]:  # 首次运行或从 v0.2 升级 / first run or upgrade from v0.2
        for i, (n, prov) in enumerate(DEFAULT_MEMBERS):
            cfg["members"].append({"id": new_id(), "name": n, "provider": prov, "model": "",
                                   "persona": "", "color": COLORS[i % len(COLORS)]})
    for i, m in enumerate(cfg["members"]):
        m.setdefault("id", new_id()); m.setdefault("model", ""); m.setdefault("persona", "")
        m.setdefault("color", COLORS[i % len(COLORS)])
    return cfg


def save_config(cfg):
    _write_json(CONFIG_PATH, cfg)


def load_groups():
    groups = []
    if GROUPS_DIR.is_dir():
        for p in sorted(GROUPS_DIR.glob("*.json")):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    g = json.load(f)
                g.setdefault("history", []); g.setdefault("topic", ""); g.setdefault("host", "")
                groups.append(g)
            except (OSError, ValueError):
                pass
    groups.sort(key=lambda g: g.get("created", 0))
    return groups


def save_group(g):
    _write_json(GROUPS_DIR / f"{g['id']}.json", g)


def delete_group(g):
    try:
        (GROUPS_DIR / f"{g['id']}.json").unlink()
    except OSError:
        pass


def make_group(name, member_ids, topic="", host=""):
    return {"id": new_id(), "name": name, "members": list(member_ids), "topic": topic,
            "host": host, "created": time.time(), "history": []}


# ---------------------------------------------------------------------------
# 网络请求 / HTTP
# ---------------------------------------------------------------------------
def _merge_roles(messages):
    """合并相邻同角色消息（Claude 要求 user/assistant 交替）/ merge consecutive same-role turns."""
    out = []
    for m in messages:
        if out and out[-1]["role"] == m["role"]:
            out[-1] = {"role": m["role"], "content": out[-1]["content"] + "\n\n" + m["content"]}
        else:
            out.append(dict(m))
    return out


def _post(url, headers, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers=dict({"Content-Type": "application/json"}, **headers))
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            err = json.loads(e.read().decode("utf-8", "replace"))
            if isinstance(err, list) and err:
                err = err[0]
            ee = err.get("error") if isinstance(err, dict) else err
            detail = ee.get("message", "") if isinstance(ee, dict) else str(ee or "")
        except Exception:
            pass
        hints = {400: "请求参数有误 / Bad request", 401: "API Key 无效 / Invalid API key",
                 403: "无权限 / Forbidden", 404: "地址或模型不存在 / URL or model not found",
                 429: "请求太频繁或额度不足 / Rate limited or out of quota"}
        raise RuntimeError(f"HTTP {e.code}: {hints.get(e.code, '服务器错误 / Server error')} {detail}".strip())
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误 / Network error: {e.reason}")
    except TimeoutError:
        raise RuntimeError("请求超时 / Request timed out")
    except ValueError:
        raise RuntimeError("返回内容不是有效 JSON / Response is not valid JSON")


def chat_completion(kind, base_url, api_key, model, messages):
    """messages: OpenAI 风格列表（可含 system）。返回回复文本。"""
    if not base_url:
        raise RuntimeError("未设置接口地址 / Base URL not set (设置 → 服务商)")
    if not api_key:
        raise RuntimeError("未设置 API Key / API key not set (设置 → 服务商)")
    if not model:
        raise RuntimeError("未设置模型名 / Model not set")
    base = base_url.rstrip("/")
    if kind == "anthropic":
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        msgs = _merge_roles([m for m in messages if m["role"] != "system"])
        if not msgs or msgs[0]["role"] != "user":
            msgs.insert(0, {"role": "user", "content": "(会议开始 / meeting started)"})
        data = _post(base + "/messages", {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                     {"model": model, "max_tokens": 1024, "system": system, "messages": msgs})
        try:
            return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        except (KeyError, TypeError):
            raise RuntimeError("返回格式异常 / Unexpected response: " + str(data)[:300])
    sys_msgs = [m for m in messages if m["role"] == "system"]
    msgs = sys_msgs[:1] + _merge_roles([m for m in messages if m["role"] != "system"])
    data = _post(base + "/chat/completions", {"Authorization": "Bearer " + api_key},
                 {"model": model, "messages": msgs})
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("返回格式异常 / Unexpected response: " + str(data)[:300])


# ---------------------------------------------------------------------------
# 会议逻辑（与界面无关，可单独测试）/ Meeting logic (UI-independent, testable)
# ---------------------------------------------------------------------------
def build_messages(member, group, members_by_id, history, extra_instruction=""):
    names = [members_by_id[i]["name"] for i in group["members"] if i in members_by_id]
    host = members_by_id.get(group.get("host") or "")
    sys = (f"你是「{member['name']}」，正在一个名为「{group['name']}」的群聊会议中。"
           f"参会者：{USER}（人类用户，会议发起人）、{'、'.join(names)}。")
    if group.get("topic"):
        sys += f"会议主题：{group['topic']}。"
    if host:
        sys += (f"本次会议主持人是「{host['name']}」。" if host["id"] != member["id"]
                else "你是本次会议的主持人，负责引导讨论、控制节奏、必要时点名其他成员。")
    sys += ("其他人的发言会以「[名字]: 」开头。请简洁回答（一般不超过150字），"
            "需要回应某人时直接称呼其名字，不要重复别人已经说过的观点，可以补充、同意或反驳。"
            "不要在回复开头写自己的名字。用用户使用的语言回复。\n"
            f"You are {member['name']} in a group meeting \"{group['name']}\" with members: "
            f"{USER} (human), {', '.join(names)}. Be concise, address others by name, don't repeat others.")
    if member.get("persona"):
        sys += "\n你的角色设定 / Persona: " + member["persona"]
    msgs = [{"role": "system", "content": sys}]
    for h in history:
        if h.get("error"):
            continue
        if h["who"] == member["id"]:
            msgs.append({"role": "assistant", "content": h["text"]})
        else:
            who = USER if h["who"] == "user" else members_by_id.get(h["who"], {}).get("name", h.get("name", "?"))
            msgs.append({"role": "user", "content": f"[{who}]: {h['text']}"})
    if extra_instruction:
        msgs.append({"role": "user", "content": f"[系统提示]: {extra_instruction}"})
    return msgs


def parse_mention(text, members):
    """找出 @名字（最长匹配）。Return member mentioned with @Name, or None."""
    best = None
    for m in members:
        if "@" + m["name"] in text and (best is None or len(m["name"]) > len(best["name"])):
            best = m
    return best


class Meeting:
    """运行一次会议发言。call(member, messages) -> 文本；on_event(dict) 通知界面。
    mode: "round"（轮流发言）| "free"（自由讨论）| "mention"（@某人）| "summary" | "rollcall"."""

    def __init__(self, cfg, group, call=None, on_event=None):
        self.cfg, self.group = cfg, group
        self.by_id = {m["id"]: m for m in cfg["members"]}
        self.call = call or self._default_call
        self.on_event = on_event or (lambda e: None)
        self.stop_event = threading.Event()

    def _default_call(self, member, messages):
        p = self.cfg["providers"].get(member["provider"], {})
        kind = PROVIDERS.get(member["provider"], {}).get("kind", "openai")
        return chat_completion(kind, p.get("base_url", ""), p.get("api_key", ""),
                               member.get("model") or p.get("model", ""), messages)

    def members(self):
        return [self.by_id[i] for i in self.group["members"] if i in self.by_id]

    def _speak(self, member, instruction=""):
        if self.stop_event.is_set():
            return None
        self.on_event({"type": "thinking", "member": member})
        msgs = build_messages(member, self.group, self.by_id, self.group["history"], instruction)
        try:
            text = (self.call(member, msgs) or "").strip()
            entry = {"who": member["id"], "name": member["name"], "text": text or "(空回复)", "time": now_str()}
        except Exception as e:  # 单个成员出错不影响其他人 / one failure doesn't stop others
            entry = {"who": member["id"], "name": member["name"], "text": str(e), "time": now_str(), "error": True}
        if self.stop_event.is_set():
            return None
        self.group["history"].append(entry)
        self.on_event({"type": "message", "entry": entry})
        return entry

    def run(self, user_text, mode="round", rounds=1):
        g = self.group
        if user_text:
            g["history"].append({"who": "user", "name": USER, "text": user_text, "time": now_str()})
        members = self.members()
        host = self.by_id.get(g.get("host") or "")
        try:
            if mode == "summary":
                if not host:
                    host = members[0] if members else None
                if host:
                    self._speak(host, "请以主持人身份总结本次会议：1) 主要结论；2) 分歧点；3) 行动项（谁、做什么）。用列表格式。")
                return
            if mode == "rollcall":
                for m in members:
                    self._speak(m, f"{USER}召集大家开会。请只回复一句简短的话表示你已就位，例如“准备好了”。")
                return
            target = parse_mention(user_text or "", members)
            if mode == "mention" or (target and mode != "free" and mode != "round"):
                target = target or (members[0] if members else None)
                if target:
                    self._speak(target)
                return
            if target and mode in ("round", "free"):  # @ 优先：只让被点名者回复
                self._speak(target)
                return
            order = list(members)
            if host and host in order:  # 主持人最后发言以控场 / host speaks last to steer
                order.remove(host); order.append(host)
            rounds = max(1, min(3, int(rounds)))
            for r in range(rounds):
                passed = 0
                for m in order:
                    if self.stop_event.is_set():
                        return
                    instr = ""
                    if mode == "free" and r > 0:
                        instr = (f"这是第{r+1}轮自由讨论。请回应其他成员的观点（点名回应）。"
                                 f"如果没有新的内容可补充，只回复 {PASS_TOKEN}。")
                    elif host and m is host:
                        instr = "你是主持人：简短点评本轮发言并推动下一步讨论。"
                    e = self._speak(m, instr)
                    if e and not e.get("error") and PASS_TOKEN in e["text"]:
                        passed += 1
                if mode == "free" and r > 0 and passed == len(order):
                    break
        finally:
            save_group(g)
            self.on_event({"type": "done"})


# ---------------------------------------------------------------------------
# 界面 / UI (tkinter)
# ---------------------------------------------------------------------------
try:
    import tkinter as tk
    from tkinter import messagebox, simpledialog, ttk
except ImportError:  # 允许无 tkinter 环境下导入核心逻辑做测试 / allow headless import
    tk = None

BG_SIDE, BG_CHAT, BG_ME, BG_AI = "#2e2e2e", "#f5f5f5", "#95ec69", "#ffffff"
MODES = {"轮流发言": "round", "自由讨论": "free", "@指定成员": "mention"}


def avatar(parent, name, color, size=34, bg=None):
    c = tk.Canvas(parent, width=size, height=size, highlightthickness=0, bg=bg or parent["bg"])
    c.create_oval(1, 1, size - 1, size - 1, fill=color, outline=color)
    c.create_text(size / 2, size / 2, text=(name or "?")[:1], fill="white", font=("Microsoft YaHei", int(size / 2.4), "bold"))
    return c


class MemberDialog(tk.Toplevel if tk else object):
    def __init__(self, master, member, on_ok):
        super().__init__(master)
        self.title("AI 成员 / Member"); self.transient(master); self.grab_set()
        self.member, self.on_ok = member, on_ok
        self.vars = {k: tk.StringVar(value=member.get(k, "")) for k in ("name", "provider", "model", "color")}
        f = ttk.Frame(self, padding=10); f.pack(fill="both", expand=True)
        ttk.Label(f, text="名字").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.vars["name"], width=40).grid(row=0, column=1, sticky="we")
        ttk.Label(f, text="服务商").grid(row=1, column=0, sticky="w")
        ttk.Combobox(f, textvariable=self.vars["provider"], values=list(PROVIDERS), state="readonly").grid(row=1, column=1, sticky="we")
        ttk.Label(f, text="模型(留空=服务商默认)").grid(row=2, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.vars["model"]).grid(row=2, column=1, sticky="we")
        ttk.Label(f, text="头像颜色").grid(row=3, column=0, sticky="w")
        ttk.Combobox(f, textvariable=self.vars["color"], values=COLORS).grid(row=3, column=1, sticky="we")
        ttk.Label(f, text="人设提示词").grid(row=4, column=0, sticky="nw")
        self.persona = tk.Text(f, width=40, height=5); self.persona.grid(row=4, column=1, sticky="we")
        self.persona.insert("1.0", member.get("persona", ""))
        ttk.Button(f, text="保存", command=self.ok).grid(row=5, column=1, sticky="e", pady=6)

    def ok(self):
        name = self.vars["name"].get().strip()
        if not name or self.vars["provider"].get() not in PROVIDERS:
            messagebox.showwarning("AI Hub", "请填写名字并选择服务商", parent=self); return
        for k, v in self.vars.items():
            self.member[k] = v.get().strip()
        self.member["persona"] = self.persona.get("1.0", "end").strip()
        self.on_ok(self.member); self.destroy()


class SettingsDialog(tk.Toplevel if tk else object):
    """服务商 API Key / 地址 / 默认模型 + 成员管理。"""

    def __init__(self, master, app):
        super().__init__(master)
        self.app, self.cfg = app, app.cfg
        self.title("设置 / Settings"); self.transient(master); self.grab_set()
        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True, padx=8, pady=8)
        pf = ttk.Frame(nb, padding=8); nb.add(pf, text="服务商 API Key")
        self.entries = {}
        for r, name in enumerate(PROVIDERS):
            p = self.cfg["providers"][name]
            ttk.Label(pf, text=name).grid(row=r, column=0, sticky="w", padx=3, pady=2)
            row = {}
            for c, (k, w) in enumerate((("api_key", 30), ("base_url", 42), ("model", 20)), start=1):
                v = tk.StringVar(value=p.get(k, ""))
                ttk.Entry(pf, textvariable=v, width=w, show="*" if k == "api_key" else "").grid(row=r, column=c, padx=2)
                row[k] = v
            self.entries[name] = row
        ttk.Label(pf, text="列：API Key | 接口地址 | 默认模型。" + MODEL_HINTS["豆包 (火山方舟)"],
                  foreground="gray").grid(row=len(PROVIDERS), column=0, columnspan=4, sticky="w", pady=4)
        ttk.Label(pf, text=f"保存位置 / Saved to: {CONFIG_PATH}", foreground="gray").grid(
            row=len(PROVIDERS) + 1, column=0, columnspan=4, sticky="w")
        mf = ttk.Frame(nb, padding=8); nb.add(mf, text="AI 成员")
        self.lb = tk.Listbox(mf, height=12, width=50); self.lb.pack(side="left", fill="both", expand=True)
        bf = ttk.Frame(mf); bf.pack(side="left", fill="y", padx=6)
        ttk.Button(bf, text="添加", command=self.add).pack(fill="x")
        ttk.Button(bf, text="编辑", command=self.edit).pack(fill="x", pady=3)
        ttk.Button(bf, text="删除", command=self.remove).pack(fill="x")
        self.refresh()
        ttk.Button(self, text="保存 / Save", command=self.save).pack(pady=(0, 8))

    def refresh(self):
        self.lb.delete(0, "end")
        for m in self.cfg["members"]:
            self.lb.insert("end", f"{m['name']}  —  {m['provider']}  {m.get('model') or ''}")

    def _sel(self):
        s = self.lb.curselection()
        return self.cfg["members"][s[0]] if s else None

    def add(self):
        m = {"id": new_id(), "name": "", "provider": "DeepSeek", "model": "", "persona": "",
             "color": COLORS[len(self.cfg["members"]) % len(COLORS)]}
        MemberDialog(self, m, lambda m: (self.cfg["members"].append(m), self.refresh()))

    def edit(self):
        m = self._sel()
        if m:
            MemberDialog(self, m, lambda _m: self.refresh())

    def remove(self):
        m = self._sel()
        if m and messagebox.askyesno("AI Hub", f"删除成员 {m['name']}？", parent=self):
            self.cfg["members"].remove(m); self.refresh()

    def save(self):
        for name, row in self.entries.items():
            for k, v in row.items():
                self.cfg["providers"][name][k] = v.get().strip()
        try:
            save_config(self.cfg)
        except OSError as e:
            messagebox.showerror("AI Hub", f"保存失败: {e}", parent=self); return
        self.app.refresh_sidebar(); self.destroy()


class GroupDialog(tk.Toplevel if tk else object):
    def __init__(self, master, cfg, on_ok, group=None):
        super().__init__(master)
        self.title("新建群聊 / 会议"); self.transient(master); self.grab_set()
        self.cfg, self.on_ok, self.group = cfg, on_ok, group
        f = ttk.Frame(self, padding=10); f.pack(fill="both", expand=True)
        ttk.Label(f, text="群名").grid(row=0, column=0, sticky="w")
        self.name = tk.StringVar(value=group["name"] if group else "五对一精准扶贫")
        ttk.Entry(f, textvariable=self.name, width=36).grid(row=0, column=1, sticky="we")
        ttk.Label(f, text="会议主题(可选)").grid(row=1, column=0, sticky="w")
        self.topic = tk.StringVar(value=group.get("topic", "") if group else "")
        ttk.Entry(f, textvariable=self.topic).grid(row=1, column=1, sticky="we")
        ttk.Label(f, text="选择成员").grid(row=2, column=0, sticky="nw")
        mf = ttk.Frame(f); mf.grid(row=2, column=1, sticky="w")
        self.checks = {}
        chosen = set(group["members"]) if group else {m["id"] for m in cfg["members"][:5]}
        for i, m in enumerate(cfg["members"]):
            v = tk.BooleanVar(value=m["id"] in chosen)
            ttk.Checkbutton(mf, text=f"{m['name']} ({m['provider']})", variable=v).grid(row=i // 2, column=i % 2, sticky="w")
            self.checks[m["id"]] = v
        ttk.Label(f, text="主持人").grid(row=3, column=0, sticky="w")
        self.names = ["(无)"] + [m["name"] for m in cfg["members"]]
        cur = "(无)"
        if group and group.get("host"):
            cur = next((m["name"] for m in cfg["members"] if m["id"] == group["host"]), "(无)")
        self.host = tk.StringVar(value=cur)
        ttk.Combobox(f, textvariable=self.host, values=self.names, state="readonly").grid(row=3, column=1, sticky="w")
        ttk.Button(f, text="确定", command=self.ok).grid(row=4, column=1, sticky="e", pady=6)

    def ok(self):
        ids = [i for i, v in self.checks.items() if v.get()]
        if not self.name.get().strip() or not ids:
            messagebox.showwarning("AI Hub", "请填写群名并至少选择一位成员", parent=self); return
        host = next((m["id"] for m in self.cfg["members"] if m["name"] == self.host.get()), "")
        if host and host not in ids:
            ids.append(host)
        if self.group:
            self.group.update(name=self.name.get().strip(), members=ids, topic=self.topic.get().strip(), host=host)
            g = self.group
        else:
            g = make_group(self.name.get().strip(), ids, self.topic.get().strip(), host)
        save_group(g); self.on_ok(g); self.destroy()


class AIHubApp:
    def __init__(self, root):
        self.root = root
        root.title(f"AI Hub v{__version__} — AI 群聊会议")
        root.geometry("1000x680"); root.minsize(760, 480)
        self.cfg = load_config()
        save_config(self.cfg)  # 保存默认成员 / persist default members
        self.groups = load_groups()
        self.current = None
        self.meeting = None
        # 左侧栏 / sidebar
        side = tk.Frame(root, bg=BG_SIDE, width=230); side.pack(side="left", fill="y"); side.pack_propagate(False)
        tk.Label(side, text="AI Hub", bg=BG_SIDE, fg="white", font=("Microsoft YaHei", 14, "bold")).pack(pady=(10, 4))
        bar = tk.Frame(side, bg=BG_SIDE); bar.pack(fill="x", padx=8)
        ttk.Button(bar, text="＋ 新建群聊", command=self.new_group).pack(side="left", expand=True, fill="x")
        ttk.Button(bar, text="⚙ 设置", command=lambda: SettingsDialog(root, self)).pack(side="left", padx=(4, 0))
        self.side_list = tk.Frame(side, bg=BG_SIDE); self.side_list.pack(fill="both", expand=True, pady=6)
        tk.Label(side, text=f"配置: {CONFIG_DIR}", bg=BG_SIDE, fg="#888", wraplength=210,
                 justify="left", font=("Microsoft YaHei", 7)).pack(side="bottom", anchor="w", padx=6, pady=4)
        # 右侧 / main pane
        main = tk.Frame(root, bg=BG_CHAT); main.pack(side="left", fill="both", expand=True)
        head = tk.Frame(main, bg="#ededed", height=48); head.pack(fill="x")
        self.title_lbl = tk.Label(head, text="请选择或新建一个群聊", bg="#ededed", font=("Microsoft YaHei", 12, "bold"))
        self.title_lbl.pack(side="left", padx=12, pady=10)
        ttk.Button(head, text="编辑群", command=self.edit_group).pack(side="right", padx=4)
        ttk.Button(head, text="清空记录", command=self.clear_history).pack(side="right", padx=4)
        ttk.Button(head, text="删除群", command=self.del_group).pack(side="right", padx=4)
        wrap = tk.Frame(main, bg=BG_CHAT); wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(wrap, bg=BG_CHAT, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); self.canvas.pack(side="left", fill="both", expand=True)
        self.msgs = tk.Frame(self.canvas, bg=BG_CHAT)
        self.win = self.canvas.create_window((0, 0), window=self.msgs, anchor="nw")
        self.msgs.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"))
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-2, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(2, "units"))
        # 控制条 / controls
        ctl = tk.Frame(main, bg="#ededed"); ctl.pack(fill="x")
        tk.Label(ctl, text="模式", bg="#ededed").pack(side="left", padx=(8, 2))
        self.mode = tk.StringVar(value="轮流发言")
        ttk.Combobox(ctl, textvariable=self.mode, values=list(MODES), state="readonly", width=10).pack(side="left")
        tk.Label(ctl, text="轮数", bg="#ededed").pack(side="left", padx=(8, 2))
        self.rounds = tk.StringVar(value="1")
        ttk.Combobox(ctl, textvariable=self.rounds, values=["1", "2", "3"], state="readonly", width=3).pack(side="left")
        ttk.Button(ctl, text="📣 召集开会", command=self.rollcall).pack(side="left", padx=6)
        ttk.Button(ctl, text="📝 会议总结", command=self.summary).pack(side="left")
        self.stop_btn = ttk.Button(ctl, text="⏹ 停止", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        self.status = tk.Label(ctl, text="", bg="#ededed", fg="#666"); self.status.pack(side="left", padx=6)
        inp = tk.Frame(main, bg="white"); inp.pack(fill="x")
        self.send_btn = ttk.Button(inp, text="发送(Enter)", command=self.send)
        self.send_btn.pack(side="right", padx=8)
        self.input = tk.Text(inp, height=4, font=("Microsoft YaHei", 11), relief="flat", wrap="word")
        self.input.pack(side="left", fill="both", expand=True, padx=8, pady=6)
        self.input.bind("<Return>", self._enter)
        self.refresh_sidebar()
        if self.groups:
            self.open_group(self.groups[-1])

    # ---- 侧栏 / sidebar ----
    def refresh_sidebar(self):
        for w in self.side_list.winfo_children():
            w.destroy()
        def section(t):
            tk.Label(self.side_list, text=t, bg=BG_SIDE, fg="#aaa", font=("Microsoft YaHei", 9)).pack(anchor="w", padx=10, pady=(8, 2))
        section("群聊 / 会议")
        for g in self.groups:
            sel = self.current is g
            row = tk.Frame(self.side_list, bg="#4a4a4a" if sel else BG_SIDE, cursor="hand2"); row.pack(fill="x")
            av = avatar(row, "群", "#07c160", 30); av.pack(side="left", padx=8, pady=4)
            lb = tk.Label(row, text=f"{g['name']} ({len(g['members'])})", bg=row["bg"], fg="white", anchor="w")
            lb.pack(side="left", fill="x")
            for w in (row, av, lb):
                w.bind("<Button-1>", lambda e, g=g: self.open_group(g))
        section("AI 成员")
        for m in self.cfg["members"]:
            row = tk.Frame(self.side_list, bg=BG_SIDE); row.pack(fill="x")
            avatar(row, m["name"], m["color"], 26).pack(side="left", padx=10, pady=2)
            has_key = bool(self.cfg["providers"].get(m["provider"], {}).get("api_key"))
            tk.Label(row, text=m["name"] + ("" if has_key else "  (未配置Key)"), bg=BG_SIDE,
                     fg="white" if has_key else "#888").pack(side="left")

    # ---- 群操作 / groups ----
    def new_group(self):
        GroupDialog(self.root, self.cfg, self._added)

    def _added(self, g):
        if g not in self.groups:
            self.groups.append(g)
        self.open_group(g)

    def edit_group(self):
        if self.current:
            GroupDialog(self.root, self.cfg, self._added, self.current)

    def del_group(self):
        if self.current and not self.meeting and messagebox.askyesno("AI Hub", f"删除群「{self.current['name']}」及其记录？"):
            delete_group(self.current); self.groups.remove(self.current); self.current = None
            self.title_lbl.config(text="请选择或新建一个群聊"); self.render(); self.refresh_sidebar()

    def clear_history(self):
        if self.current and not self.meeting and messagebox.askyesno("AI Hub", "清空本群聊天记录？"):
            self.current["history"] = []; save_group(self.current); self.render()

    def open_group(self, g):
        if self.meeting:
            return
        self.current = g
        by = {m["id"]: m["name"] for m in self.cfg["members"]}
        host = by.get(g.get("host") or "")
        self.title_lbl.config(text=f"{g['name']}（{len(g['members'])}）" + (f"  主持人: {host}" if host else "")
                              + (f"  主题: {g['topic']}" if g.get("topic") else ""))
        self.render(); self.refresh_sidebar()

    # ---- 气泡 / bubbles ----
    def render(self):
        for w in self.msgs.winfo_children():
            w.destroy()
        if self.current:
            for h in self.current["history"]:
                self.bubble(h, scroll=False)
        self.root.after(50, lambda: self.canvas.yview_moveto(1.0))

    def bubble(self, h, scroll=True):
        by = {m["id"]: m for m in self.cfg["members"]}
        row = tk.Frame(self.msgs, bg=BG_CHAT); row.pack(fill="x", pady=4, padx=8)
        if h["who"] == "user":
            avatar(row, USER, "#576b95").pack(side="right", anchor="n", padx=4)
            box = tk.Frame(row, bg=BG_CHAT); box.pack(side="right", anchor="e")
            tk.Label(box, text=h.get("time", ""), bg=BG_CHAT, fg="#999", font=("Microsoft YaHei", 8)).pack(anchor="e")
            tk.Label(box, text=h["text"], bg=BG_ME, wraplength=460, justify="left", padx=10, pady=6,
                     font=("Microsoft YaHei", 10)).pack(anchor="e")
        else:
            m = by.get(h["who"], {"name": h.get("name", "?"), "color": "#999"})
            avatar(row, m["name"], m["color"]).pack(side="left", anchor="n", padx=4)
            box = tk.Frame(row, bg=BG_CHAT); box.pack(side="left", anchor="w")
            tk.Label(box, text=f"{m['name']}  {h.get('time', '')}", bg=BG_CHAT, fg="#888",
                     font=("Microsoft YaHei", 8)).pack(anchor="w")
            err = h.get("error")
            tk.Label(box, text=("⚠ " if err else "") + h["text"], bg="#fde2e2" if err else BG_AI,
                     fg="#b00" if err else "black", wraplength=460, justify="left", padx=10, pady=6,
                     font=("Microsoft YaHei", 10)).pack(anchor="w")
        if scroll:
            self.root.after(50, lambda: self.canvas.yview_moveto(1.0))

    # ---- 会议 / meeting ----
    def _enter(self, e):
        if not (e.state & 0x1):  # Shift+Enter 换行 / newline
            self.send(); return "break"

    def send(self):
        text = self.input.get("1.0", "end").strip()
        if not text or not self.current or self.meeting:
            if not self.current:
                messagebox.showinfo("AI Hub", "请先新建或选择一个群聊")
            return
        self.input.delete("1.0", "end")
        self.start(text, MODES[self.mode.get()])

    def rollcall(self):
        if self.current and not self.meeting:
            self.start("各位，开会了！", "rollcall")

    def summary(self):
        if self.current and not self.meeting:
            self.start("", "summary")

    def start(self, text, mode):
        g = self.current
        self.meeting = Meeting(self.cfg, g, on_event=lambda e: self.root.after(0, self._event, g, e))
        if text:
            self.bubble({"who": "user", "text": text, "time": now_str()})
        self.stop_btn.config(state="normal"); self.send_btn.config(state="disabled")
        rounds = int(self.rounds.get())
        m = self.meeting
        threading.Thread(target=m.run, args=(text, mode, rounds), daemon=True).start()

    def _event(self, g, e):
        if e["type"] == "thinking":
            self.status.config(text=f"{e['member']['name']} 正在输入…")
        elif e["type"] == "message" and self.current is g:
            self.bubble(e["entry"])
        elif e["type"] == "done":
            self.meeting = None
            self.status.config(text="")
            self.stop_btn.config(state="disabled"); self.send_btn.config(state="normal")

    def stop(self):
        if self.meeting:
            self.meeting.stop_event.set()
            self.status.config(text="正在停止…（当前请求结束后停止）")


def main():
    if tk is None:
        raise SystemExit("需要 tkinter / tkinter is required")
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista" if os.name == "nt" else "clam")
    except tk.TclError:
        pass
    AIHubApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

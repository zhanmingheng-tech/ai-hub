# AI Hub

[English](README.md)

一个面向新手的小型桌面聊天程序，在一个窗口里使用多家 AI 服务。
**只用 Python 标准库**（tkinter + urllib + json），无需 `pip install` 任何东西。

## 功能

- 下拉框选择服务商：**DeepSeek**、**OpenAI**、**Moonshot（Kimi）**、**通义千问（DashScope）**，或任意 **自定义 OpenAI 兼容** 接口。
- 统一通过 OpenAI 兼容的 `/chat/completions` 接口调用。
- 设置窗口：为每个服务商分别填写自己的 API Key、接口地址和模型名。
- 当前会话保留聊天记录（支持多轮对话），「清空」按钮可重置。
- 请求在后台线程运行，窗口不会卡住。
- 易读的错误提示（Key 无效、额度不足、网络问题等）。

## 环境要求

- Python 3.10 及以上。Windows 上从 python.org 下载的官方安装包已自带 tkinter。
- Linux 上可能需要单独安装 tkinter，例如 `sudo apt install python3-tk`。

## 安装与运行

```bash
git clone <你的仓库地址> ai-hub
cd ai-hub
python ai_hub.py
```

Windows 上也可以直接双击 `ai_hub.py`，或运行 `py ai_hub.py`。

## 使用方法

1. 点击 **设置**，选择服务商标签页，粘贴你的 API Key，可按需修改模型名。
2. 点击 **保存**。
3. 在下拉框选择服务商，输入消息，点击 **发送**（或按 `Ctrl+Enter`）。

**自定义** 接口：接口地址填到 `/v1` 为止（例如 `http://localhost:11434/v1`），再填模型名和 Key（如果服务端不校验 Key，随便填一个非空值即可）。

## 讨论组（v0.2.0）

在第二行工具栏勾选 **Group / 讨论组**，再勾选要参与的 AI（需先在设置中填好 Key），选择 **轮数**（1–3），发送一条消息即可。被选中的 AI 依次在同一窗口中回复，并标注名字。每个 AI 都能看到共享记录：用户消息和其他 AI 的回复（以带 `[名字]:` 前缀的 user 消息传入），并附带简短的系统提示，说明它正在讨论组中、应回应其他人。某个 AI 出错只会显示错误，不影响其他 AI。取消勾选 **讨论组** 即回到单 AI 聊天。

## API Key 存在哪里？

保存在用户主目录的 `~/.ai_hub/config.json`（Windows：`C:\Users\<用户名>\.ai_hub\config.json`）。

**便携模式：** 若设置了环境变量 `AI_HUB_CONFIG_DIR`，则使用该目录；否则若 `ai_hub.py` 旁边存在名为 `.ai_hub` 的文件夹，配置会保存在那里。
以明文保存，**不会**写入项目目录，且 `config.json` 已加入 `.gitignore`。请勿分享此文件。

## 许可证

[MIT](LICENSE)

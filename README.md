# 微信群聊智能摘要助手

> 自动读取微信群聊一天的聊天记录，使用本地 Ollama 大模型生成摘要，支持重点关注特定人员，并可通过邮件推送摘要。

**核心特点**：通过解密微信本地数据库直接读取消息，**不操控微信界面，无封号风险**。

---

## ⚠️ 免责声明

- **本项目仅供学习研究使用**，不得用于商业用途或侵犯他人隐私
- 使用本工具即表示您自行承担所有法律责任
- 解密微信数据库涉及逆向工程技术，可能违反微信用户协议
- 请仅在自己的设备上使用，不要用于监控他人聊天

---

## 功能特性

- 🔐 **数据库直读**：通过 PyWxDump 解密微信本地加密数据库，无需 UI 自动化
- 🤖 **本地 AI 摘要**：调用 Ollama 大模型（如 qwen2.5）生成结构化摘要
- 👤 **重点关注**：可指定群内特定成员，对其发言进行重点归纳
- 📧 **邮件推送**：摘要自动发送到指定邮箱，支持 QQ/163/Gmail 等
- ⏰ **定时运行**：支持 Windows 计划任务，每日自动执行
- 💾 **消息持久化**：SQLite 存储，自动去重，支持历史查询

---

## 工作原理

```
微信 PC (已登录)
      │
      ▼
┌─────────────────┐
│  PyWxDump       │ ← 从微信进程内存提取数据库密钥
│  (密钥提取)      │
└────┬────────────┘
      │ key
      ▼
┌─────────────────┐
│  wechat_db.py    │ ← SQLCipher 解密 → 读取本地 MSG*.db
│  (消息读取)      │     解析发送人/内容/时间
└────┬────────────┘
      │ messages
      ▼
┌─────────────────┐      ┌─────────────────┐
│  message_store   │ ──→  │  summarizer.py  │ ← Ollama API
│  (SQLite 存储)   │      │  (AI 摘要生成)   │    localhost:11434
└─────────────────┘      └────┬────────────┘
                              │ summary
                              ▼
                     ┌─────────────────┐
                     │  email_sender   │ ← SMTP 发送
                     │  (邮件推送)      │
                     └─────────────────┘
```

---

## 环境要求

| 组件 | 要求 |
|------|------|
| 操作系统 | Windows 10/11 |
| 微信 PC | **3.9.x 系列**（推荐 3.9.10 ~ 3.9.12） |
| Python | 3.11+ |
| Ollama | 需安装并运行（推荐 qwen2.5 模型） |
| Git | 可选（用于克隆项目） |

### ⚠️ 微信版本说明

PyWxDump 3.0.42 的版本偏移表覆盖了微信 **3.2.1 ~ 3.9.11**。**3.9.12+** 可通过动态内存搜索使用，**WeChat 4.x 不支持**。

如果微信自动更新了，需下载 3.9.x 旧版本覆盖安装。

---

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/ancheng2222/wechat-summarizer.git
cd wechat-summarizer
```

### 2. 创建虚拟环境并安装依赖

```bash
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
```

如果网络慢，可使用国内镜像：

```bash
venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
```

### 3. 安装并启动 Ollama

从 [ollama.com](https://ollama.com) 下载 Ollama，安装后拉取模型：

```bash
ollama pull qwen2.5
```

### 4. 运行配置向导

```bash
venv\Scripts\python.exe setup.py
```

配置向导会引导你：
1. 检查依赖和环境
2. 检查 Ollama 连接
3. 配置要监控的群聊和关注人员
4. 设置每日运行时间
5. **自动提取微信数据库密钥**（需微信保持登录）
6. （可选）配置邮件发送

### 5. 试运行

```bash
venv\Scripts\python.exe main.py --once
```

如果一切正常，你会在 `summaries/` 目录下看到生成的摘要文件。

---

## 配置说明

配置文件 `config.yaml`（从 `config.example.yaml` 复制并填写）：

```yaml
# 微信数据库信息（由 setup.py 自动填写）
db_key: "xxxx..."      # 32位hex密钥
db_path: "C:\\..."     # 微信数据目录

# Ollama 模型
ollama_model: "qwen2.5:latest"

# 监控群聊
groups:
  - name: "产品技术群"           # 群名关键字
    focus_persons:              # 重点关注人员
      - "张三"
      - "李四"

# 每日运行时间
schedule_time: "22:00"

# 邮件配置（可选）
email:
  sender_email: "you@qq.com"
  sender_password: "授权码"      # QQ邮箱需获取授权码，非密码
  to_email: "you@qq.com"
```

### QQ 邮箱授权码获取

1. 登录 QQ 邮箱 → 设置 → 账户
2. 找到 POP3/SMTP 服务 → 开启
3. 按提示发短信验证 → 获得 16 位授权码
4. 填入 `sender_password`

---

## 使用方式

```bash
# 单次运行
venv\Scripts\python.exe main.py --once

# 守护进程模式（进程内定时循环）
venv\Scripts\python.exe main.py --daemon

# 重新配置
venv\Scripts\python.exe setup.py
```

### 定时任务

`setup.py` 会自动创建 Windows 计划任务，每天定时运行。也可手动管理：

```bash
# 手动创建
schtasks /Create /SC DAILY /TN "WeChatSummarizer" /TR "venv\Scripts\python.exe main.py --once" /ST 22:00

# 查看状态
schtasks /Query /TN "WeChatSummarizer"

# 删除任务
schtasks /Delete /TN "WeChatSummarizer" /F
```

---

## 项目结构

```
wechat-summarizer/
├── main.py                  # 主入口
├── setup.py                 # 交互式配置向导
├── config.example.yaml      # 配置模板（复制为 config.yaml）
├── config.yaml              # 实际配置（已在 .gitignore）
├── requirements.txt         # Python 依赖
├── LICENSE                  # MIT 许可证
├── prompts/
│   └── summary_prompt.txt   # 摘要 Prompt 模板
├── src/
│   ├── wechat_db.py         # 微信数据库解密与读取
│   ├── message_store.py     # SQLite 消息存储
│   ├── summarizer.py        # Ollama 摘要生成
│   ├── email_sender.py      # SMTP 邮件发送
│   └── scheduler.py         # 定时调度
├── summaries/               # 生成的摘要文件
├── logs/                    # 运行日志
└── data/                    # SQLite 数据库
```

---

## 常见问题

<details>
<summary><b>Q: 能读多少条消息？</b></summary>
理论上无限。实际测试 1000+ 条消息，读取耗时约 5 秒，摘要生成约 2-3 分钟（取决于 Ollama 所在设备的 GPU/CPU 性能）。
</details>

<details>
<summary><b>Q: 会封号吗？</b></summary>
不会。本工具只读取本地加密数据库文件，不操控微信界面，不发送任何请求到微信服务器，微信无法检测。
</details>

<details>
<summary><b>Q: 微信更新了怎么办？</b></summary>
如果微信自动更新到 4.x，密钥提取会失效。需要降级回 3.9.x。建议关闭微信自动更新。
</details>

<details>
<summary><b>Q: 数据库密钥会变化吗？</b></summary>
同一个微信账号在同一台电脑上，密钥通常是固定的。如果重新安装微信或更换设备，需要重新提取。
</details>

<details>
<summary><b>Q: Ollama 需要一直运行吗？</b></summary>
只需要在运行摘要时启动。定时任务触发时 Ollama 必须处于运行状态。
</details>

<details>
<summary><b>Q: 支持多群吗？</b></summary>
支持。在 config.yaml 的 `groups` 列表中配置多个即可。
</details>

<details>
<summary><b>Q: 支持聊天记录导出吗？</b></summary>
SQLite 数据库在 `data/messages.db`，可用任何 SQLite 工具查看。摘要保存在 `summaries/` 目录。
</details>

---

## 依赖

| 包 | 用途 |
|---|------|
| [pywxdump](https://github.com/xaoyaoo/PyWxDump) | 微信数据库解密 |
| [PyYAML](https://pyyaml.org/) | 配置文件读写 |
| [questionary](https://github.com/tmbo/questionary) | 交互式 CLI |
| [loguru](https://github.com/Delgan/loguru) | 日志 |
| [schedule](https://github.com/dbader/schedule) | 定时调度 |
| [requests](https://requests.readthedocs.io/) | HTTP（Ollama API） |

---

## 许可证

MIT License - 详见 [LICENSE](LICENSE)

---

## 致谢

- [PyWxDump](https://github.com/xaoyaoo/PyWxDump) — 提供微信数据库解密能力
- [Ollama](https://ollama.com) — 本地 LLM 推理

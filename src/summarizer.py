"""
LLM 总结模块 —— 调用本地 Ollama API 生成群聊摘要
"""
import requests
import json
import os
from typing import Optional
from loguru import logger

OLLAMA_BASE = "http://localhost:11434"
PROMPT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")


def _load_prompt_template() -> str:
    """加载 prompt 模板"""
    prompt_file = os.path.join(PROMPT_DIR, "summary_prompt.txt")
    if os.path.exists(prompt_file):
        with open(prompt_file, "r", encoding="utf-8") as f:
            return f.read()
    # 兜底默认模板
    return """你是一个群聊消息总结助手。请对以下微信群聊记录进行总结，要求：

1. **群聊概况**：今天总共有多少条消息，主要话题有哪些（列出 3-5 个话题，每个一句话概括）
2. **重点关注人员发言摘要**：请特别关注以下人员的发言，对每个人的发言要点进行归纳：
   {focus_persons}
3. **今日亮点**：有趣/有价值的讨论、达成的共识、待办事项等

以下是群聊记录（格式：[时间] 发言人：内容）：
---
{messages}
---

请用简洁的 Markdown 格式输出总结。"""


def check_ollama() -> Optional[list[str]]:
    """检查 Ollama 服务是否可用，返回可用模型列表"""
    try:
        resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            return models
        return None
    except Exception:
        return None


def summarize(
    messages: list[dict],
    focus_persons: list[str],
    model: str = "qwen2.5:latest",
    max_chars: int = 12000,
) -> Optional[str]:
    """
    调用 Ollama 生成摘要。
    - messages: [{"sender": "张三", "content": "...", "time": "14:30"}, ...]
    - focus_persons: 重点关注人员列表
    - model: Ollama 模型名
    - max_chars: 单次总结最大字符数（超出则分段）
    """
    if not messages:
        return None

    # 拼接消息文本
    msg_lines = []
    total_chars = 0
    for m in messages:
        line = f"[{m.get('time', '?')}] {m['sender']}：{m['content']}"
        msg_lines.append(line)
        total_chars += len(line)

    # 如果消息太多，分段总结
    if total_chars > max_chars:
        return _chunked_summarize(msg_lines, focus_persons, model, max_chars)

    return _call_ollama(msg_lines, focus_persons, model)


def _call_ollama(
    msg_lines: list[str],
    focus_persons: list[str],
    model: str,
) -> Optional[str]:
    """单次调用 Ollama"""
    template = _load_prompt_template()
    prompt = template.format(
        focus_persons="、".join(focus_persons),
        messages="\n".join(msg_lines),
    )

    try:
        resp = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.3},
            },
            timeout=300,
        )
        if resp.status_code == 200:
            return resp.json()["message"]["content"]
        else:
            logger.error(f"Ollama API 错误: {resp.status_code} {resp.text}")
            return None
    except requests.exceptions.Timeout:
        logger.error("Ollama 请求超时（5分钟）")
        return None
    except Exception as e:
        logger.error(f"Ollama 调用异常: {e}")
        return None


def _chunked_summarize(
    msg_lines: list[str],
    focus_persons: list[str],
    model: str,
    max_chars: int,
) -> Optional[str]:
    """
    分段总结：将消息分块 → 每块独立总结 → 合并各块摘要再做总总结
    """
    chunks = []
    current_chunk = []
    current_len = 0

    for line in msg_lines:
        if current_len + len(line) > max_chars and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_len = 0
        current_chunk.append(line)
        current_len += len(line)
    if current_chunk:
        chunks.append(current_chunk)

    logger.info(f"消息过长，分为 {len(chunks)} 段总结")

    # 第一轮：每段独立总结
    chunk_summaries = []
    for i, chunk in enumerate(chunks, 1):
        logger.info(f"总结第 {i}/{len(chunks)} 段...")
        result = _call_ollama(chunk, focus_persons, model)
        if result:
            chunk_summaries.append(result)

    if not chunk_summaries:
        return None

    if len(chunk_summaries) == 1:
        return chunk_summaries[0]

    # 第二轮：合并各段摘要做最终总结
    merge_prompt = f"""请将以下 {len(chunk_summaries)} 段群聊摘要合并为一份完整的今日群聊总结。

重点关注人员：{'、'.join(focus_persons)}

各段摘要：
---
{'='.join(chunk_summaries)}
---

请合并为一份完整的 Markdown 格式总结，包含：群聊概况、重点关注人员发言摘要、今日亮点。"""

    try:
        resp = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": merge_prompt}],
                "stream": False,
                "options": {"temperature": 0.3},
            },
            timeout=300,
        )
        if resp.status_code == 200:
            return resp.json()["message"]["content"]
        else:
            # 合并失败则返回各段摘要拼接
            return "\n\n---\n\n".join(chunk_summaries)
    except Exception:
        return "\n\n---\n\n".join(chunk_summaries)

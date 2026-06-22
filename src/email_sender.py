"""
邮件发送模块 —— 通过 SMTP 发送摘要到指定邮箱
支持 QQ邮箱、163邮箱、Gmail 等
"""
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from typing import Optional
from loguru import logger


# 常见邮箱 SMTP 配置
SMTP_CONFIGS = {
    "qq.com":       {"host": "smtp.qq.com",       "port": 465, "ssl": True},
    "vip.qq.com":   {"host": "smtp.qq.com",       "port": 465, "ssl": True},
    "foxmail.com":  {"host": "smtp.qq.com",       "port": 465, "ssl": True},
    "163.com":      {"host": "smtp.163.com",      "port": 465, "ssl": True},
    "126.com":      {"host": "smtp.126.com",      "port": 465, "ssl": True},
    "yeah.net":     {"host": "smtp.yeah.net",     "port": 465, "ssl": True},
    "gmail.com":    {"host": "smtp.gmail.com",     "port": 587, "ssl": False},
    "outlook.com":  {"host": "smtp-mail.outlook.com", "port": 587, "ssl": False},
    "hotmail.com":  {"host": "smtp-mail.outlook.com", "port": 587, "ssl": False},
    "sina.com":     {"host": "smtp.sina.com",     "port": 465, "ssl": True},
    "sohu.com":     {"host": "smtp.sohu.com",     "port": 465, "ssl": True},
}


def _guess_smtp(email: str) -> dict:
    """根据邮箱地址推测 SMTP 配置"""
    domain = email.split("@")[-1].lower()
    if domain in SMTP_CONFIGS:
        return SMTP_CONFIGS[domain]
    # 默认用 QQ 邮箱配置
    return {"host": "smtp.qq.com", "port": 465, "ssl": True}


def send_email(
    to_email: str,
    subject: str,
    body: str,
    smtp_host: str = "",
    smtp_port: int = 0,
    sender_email: str = "",
    sender_password: str = "",
    use_ssl: bool = True,
) -> bool:
    """
    发送邮件。

    - to_email: 收件人邮箱
    - subject: 邮件主题
    - body: 邮件正文（支持 Markdown，会同时发送纯文本和 HTML 版本）
    - smtp_host / smtp_port / use_ssl: SMTP 服务器配置（留空则自动推断）
    - sender_email: 发件人邮箱
    - sender_password: SMTP 密码/授权码

    返回 True 表示发送成功。
    """
    if not to_email or not sender_email or not sender_password:
        logger.error("邮箱配置不完整，无法发送")
        return False

    # 自动推断 SMTP 配置
    if not smtp_host:
        cfg = _guess_smtp(sender_email)
        smtp_host = cfg["host"]
        smtp_port = smtp_port or cfg["port"]
        use_ssl = cfg.get("ssl", True)

    try:
        # 构建邮件
        msg = MIMEMultipart("alternative")
        msg["From"] = formataddr(("群聊摘要助手", sender_email))
        msg["To"] = to_email
        msg["Subject"] = Header(subject, "utf-8")

        # 纯文本版本（去掉简单 Markdown 标记）
        import re
        plain = re.sub(r"[*#>`\-]", "", body)
        msg.attach(MIMEText(plain, "plain", "utf-8"))

        # HTML 版本：简单的 Markdown → HTML 转换
        html_body = _markdown_to_html(body)
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        # 发送
        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            server.starttls()

        server.login(sender_email, sender_password)
        server.sendmail(sender_email, [to_email], msg.as_string())
        server.quit()

        logger.info(f"[OK] 邮件已发送至 {to_email}")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP 认证失败！请检查邮箱和授权码是否正确")
        return False
    except smtplib.SMTPConnectError:
        logger.error(f"无法连接 SMTP 服务器 {smtp_host}:{smtp_port}")
        return False
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return False


def _markdown_to_html(md: str) -> str:
    """简易 Markdown → HTML（避免引入额外依赖）"""
    import re

    lines = md.split("\n")
    html_lines = []
    in_list = False

    for line in lines:
        # 标题
        if line.startswith("### "):
            html_lines.append(f"<h3>{line[4:]}</h3>")
            continue
        if line.startswith("## "):
            html_lines.append(f"<h2>{line[3:]}</h2>")
            continue
        if line.startswith("# "):
            html_lines.append(f"<h1>{line[2:]}</h1>")
            continue

        # 无序列表
        if line.strip().startswith("- ") or line.strip().startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            content = line.strip()[2:]
            # 粗体
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
            html_lines.append(f"<li>{content}</li>")
            continue
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False

        # 分隔线
        if line.strip() in ("---", "***", "___"):
            html_lines.append("<hr>")
            continue

        # 粗体
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)

        # 普通段落
        if line.strip():
            html_lines.append(f"<p>{line}</p>")
        else:
            html_lines.append("<br>")

    if in_list:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def send_summary_email(
    config: dict,
    group_name: str,
    summary: str,
    date_str: str,
) -> bool:
    """
    从 config 读取邮箱配置并发送摘要邮件。
    这是 main.py 调用的快捷入口。
    """
    email_cfg = config.get("email", {})
    if not email_cfg:
        logger.warning("未配置邮箱，跳过邮件发送")
        return False

    sender_email = email_cfg.get("sender_email", "")
    sender_password = email_cfg.get("sender_password", "")
    to_email = email_cfg.get("to_email", "")
    smtp_host = email_cfg.get("smtp_host", "")
    smtp_port = email_cfg.get("smtp_port", 0)
    use_ssl = email_cfg.get("use_ssl", True)

    if not sender_password:
        logger.warning("未配置邮箱授权码，跳过邮件发送")
        return False

    subject = f"【群聊摘要】{group_name} - {date_str}"

    return send_email(
        to_email=to_email or sender_email,
        subject=subject,
        body=summary,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        sender_email=sender_email,
        sender_password=sender_password,
        use_ssl=use_ssl,
    )

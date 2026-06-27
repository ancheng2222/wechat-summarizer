"""
微信群聊智能摘要助手 —— 主入口（数据库版）
用法:
    python main.py --once        # 单次运行
    python main.py --daemon      # 守护进程模式
"""
import os
import sys
import argparse
import yaml
from datetime import date
from loguru import logger

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(PROJECT_DIR, "config.yaml")
LOG_DIR = os.path.join(PROJECT_DIR, "logs")
SUMMARY_DIR = os.path.join(PROJECT_DIR, "summaries")

sys.path.insert(0, os.path.join(PROJECT_DIR, "src"))


def setup_logger():
    os.makedirs(LOG_DIR, exist_ok=True)
    logger.remove()
    logger.add(
        os.path.join(LOG_DIR, "app_{time:YYYY-MM-DD}.log"),
        rotation="7 days", retention="30 days", level="INFO",
        format="{time:HH:mm:ss} | {level: <7} | {message}",
    )
    logger.add(sys.stdout, level="INFO",
               format="<green>{time:HH:mm:ss}</green> | {level: <7} | {message}")


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        logger.error("配置文件不存在！请先运行: python setup.py")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_once(config: dict | None = None, target_date: date | None = None):
    if config is None:
        config = load_config()

    from message_store import init_db, save_messages, get_messages, get_last_msg_time, get_message_count
    from wechat_db import WeChatDBReader
    from summarizer import summarize, check_ollama

    init_db()

    # 检查 Ollama
    models = check_ollama()
    if not models:
        logger.error("Ollama 服务不可用，请先启动 Ollama")
        return
    logger.info(f"Ollama 可用模型: {', '.join(models[:5])}")

    # 初始化数据库读取器
    key = config.get("db_key", "")
    db_path = config.get("db_path", "")
    if not key or not db_path:
        logger.error("配置中缺少 db_key 或 db_path，请重新运行: python setup.py")
        return

    reader = WeChatDBReader(key=key, db_path=db_path)

    if target_date is None:
        target_date = date.today()
    logger.info(f"开始处理 {target_date} 的群聊消息")

    for group in config.get("groups", []):
        group_name = group["name"]
        focus_persons = group.get("focus_persons", [])
        logger.info(f"\n{'='*40}\n处理群: {group_name}\n关注: {', '.join(focus_persons) if focus_persons else '无'}\n{'='*40}")

        # 读取消息
        today_msgs = reader.get_today_messages(group_keyword=group_name, target_date=target_date)

        if not today_msgs:
            logger.info(f"群 [{group_name}] 今天没有消息")
            continue

        # 保存到数据库
        new_count = save_messages(group_name, today_msgs)
        logger.info(f"群 [{group_name}] 新增 {new_count} 条消息")

        all_today = get_messages(group_name, target_date=target_date)
        total_count = get_message_count(group_name, target_date=target_date)
        logger.info(f"群 [{group_name}] {target_date} 累计 {total_count} 条消息")

        # 生成摘要
        logger.info("正在生成摘要...")
        model = config.get("ollama_model", "qwen2.5:latest")
        max_chars = config.get("max_summary_chars", 12000)

        summary = summarize(all_today, focus_persons, model=model, max_chars=max_chars)

        if summary:
            full_text = f"# {group_name} 每日摘要\n**日期**: {target_date}\n\n{summary}"

            # 保存到文件
            os.makedirs(SUMMARY_DIR, exist_ok=True)
            summary_file = os.path.join(SUMMARY_DIR, f"summary_{group_name}_{target_date}.md")
            with open(summary_file, "w", encoding="utf-8") as f:
                f.write(full_text)
            logger.info(f"[OK] 摘要已保存: {summary_file}")
            logger.info(f"\n{full_text}")

            # 发送邮件
            from email_sender import send_summary_email
            send_summary_email(config, group_name, full_text, str(target_date))
        else:
            logger.warning("摘要生成失败")

    logger.info(f"\n{'='*40}\n全部处理完成！")


def main():
    parser = argparse.ArgumentParser(description="微信群聊智能摘要助手")
    parser.add_argument("--once", action="store_true", help="单次运行")
    parser.add_argument("--daemon", action="store_true", help="守护进程模式")
    parser.add_argument("--date", type=str, default=None,
                        help="指定日期 YYYY-MM-DD（默认今天）")
    args = parser.parse_args()

    setup_logger()
    config = load_config()

    target_date = None
    if args.date:
        try:
            target_date = date.fromisoformat(args.date)
        except ValueError:
            logger.error(f"日期格式错误: {args.date}，请使用 YYYY-MM-DD")
            sys.exit(1)

    if args.daemon:
        from scheduler import run_daemon
        logger.info("启动守护进程模式...")
        run_daemon(config)
    else:
        run_once(config, target_date=target_date)


if __name__ == "__main__":
    main()

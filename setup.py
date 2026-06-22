"""
交互式配置向导 —— 首次运行引导用户配置
"""
import os
import sys
import yaml

# 强制 UTF-8 输出（Python 3.7+）
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from datetime import datetime

PROJECT_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(PROJECT_DIR, "config.yaml")

DEFAULT_CONFIG = {
    "ollama_model": "qwen2.5:latest",
    "groups": [],
    "schedule_time": "22:00",
    "scroll_times": 20,
    "max_summary_chars": 12000,
    "db_key": "",
    "db_path": "",
    "email": {
        "sender_email": "",
        "sender_password": "",
        "to_email": "",
        "smtp_host": "",
        "smtp_port": 0,
        "use_ssl": True,
    },
}


def _interactive_setup():
    """交互式配置流程"""
    print("\n" + "=" * 55)
    print("    微信群聊智能摘要助手 - 首次配置")
    print("    数据库模式（安全，无封号风险）")
    print("=" * 55 + "\n")

    config = {}

    # Step 1: 检查依赖
    print("[Step 1/6] 检查依赖...")
    try:
        import pywxdump  # noqa: F401
        print("   [OK] pywxdump 已安装")
    except ImportError:
        print("   [FAIL] pywxdump 未安装！请先运行: pip install pywxdump==3.0.42")
        sys.exit(1)

    try:
        import requests  # noqa: F401
        print("   [OK] requests 已安装")
    except ImportError:
        print("   [FAIL] requests 未安装！")
        sys.exit(1)

    # Step 2: 检查 Ollama
    print("\n[Step 2/7] 检查 Ollama 服务...")
    from src.summarizer import check_ollama
    models = check_ollama()
    if models:
        print(f"   [OK] Ollama 已连接，可用模型: {', '.join(models[:5])}")
        print(f"   默认使用: {DEFAULT_CONFIG['ollama_model']}")
        config["ollama_model"] = input("   输入模型名 (回车使用默认): ").strip() or DEFAULT_CONFIG["ollama_model"]
    else:
        print("   [WARN] Ollama 未连接，请确认 Ollama 已启动")
        config["ollama_model"] = input("   手动输入模型名: ").strip()
        if not config["ollama_model"]:
            config["ollama_model"] = DEFAULT_CONFIG["ollama_model"]

    # Step 3: 群聊配置
    print("\n[Step 3/7] 配置群聊...")
    groups = []
    while True:
        group_name = input("   要监控的微信群名称（输入群名关键字，如 '产品技术群'，回车结束）: ").strip()
        if not group_name:
            break

        focus_str = input(f"   [{group_name}] 重点关注人员（逗号分隔，如 张三,李四）: ").strip()
        focus_persons = [p.strip() for p in focus_str.split(",") if p.strip()] if focus_str else []

        groups.append({
            "name": group_name,
            "focus_persons": focus_persons,
        })
        print(f"   [OK] 已添加: {group_name} (关注: {', '.join(focus_persons) if focus_persons else '无'})")

    if not groups:
        print("   [WARN] 未添加任何群，将使用示例配置")
        groups = [{"name": "示例群名", "focus_persons": ["张三", "李四"]}]
    config["groups"] = groups

    # Step 4: 定时
    print("\n[Step 4/7] 定时设置...")
    schedule_time = input(f"   每日总结时间（HH:MM 格式，默认 {DEFAULT_CONFIG['schedule_time']}）: ").strip()
    config["schedule_time"] = schedule_time or DEFAULT_CONFIG["schedule_time"]

    # Step 5: 高级选项
    print("\n[Step 5/7] 高级选项（回车使用默认）...")
    scroll_str = input(f"   消息滚动加载次数（默认 {DEFAULT_CONFIG['scroll_times']}）: ").strip()
    config["scroll_times"] = int(scroll_str) if scroll_str.isdigit() else DEFAULT_CONFIG["scroll_times"]

    max_chars_str = input(f"   单次总结最大字符数（默认 {DEFAULT_CONFIG['max_summary_chars']}）: ").strip()
    config["max_summary_chars"] = int(max_chars_str) if max_chars_str.isdigit() else DEFAULT_CONFIG["max_summary_chars"]

    # Step 6: 数据库连接测试
    print("\n[Step 6/7] 测试微信数据库连接...")
    print("   [INFO] 请确保微信 PC 已登录！")
    input("   按回车开始测试...")
    try:
        from pywxdump.wx_info import read_info
        from pywxdump import VERSION_LIST
        result = read_info(VERSION_LIST, is_logging=False)
        if isinstance(result, list) and len(result) > 0:
            info = result[0]
            key = info.get("key", "None")
            file_path = info.get("filePath", "None")
            if key != "None":
                print(f"   [OK] 密钥提取成功！")
                print(f"   数据库路径: {file_path}")
                print(f"   密钥: {key[:16]}...")
                config["db_key"] = key
                config["db_path"] = file_path
            else:
                print(f"   [WARN] 密钥提取失败，请确认微信已登录且版本兼容")
                print(f"   你可以稍后手动编辑 config.yaml 填入 db_key 和 db_path")
                config["db_key"] = ""
                config["db_path"] = ""
        else:
            print(f"   [WARN] 未检测到微信进程，配置已保存但需手动填写 db_key 和 db_path")
            print(f"   提示: 保持微信登录后重新运行 setup.py")
            config["db_key"] = ""
            config["db_path"] = ""
    except Exception as e:
        print(f"   [WARN] 数据库检测失败: {e}")
        print(f"   请确认微信 PC 已登录，稍后可运行 'python main.py --once' 测试")
        config["db_key"] = ""
        config["db_path"] = ""

    # Step 7: 邮箱配置
    print("\n[Step 7/7] 配置邮件发送（可选，回车跳过）...")
    print("   支持 QQ邮箱、163邮箱、Gmail 等")
    print("   QQ邮箱需开启 POP3/SMTP 服务并获取授权码: 设置 → 账户 → POP3/SMTP服务")
    setup_email = input("   是否配置邮件发送？(Y/n): ").strip().lower()
    if setup_email != "n":
        sender = input("   发件人邮箱: ").strip()
        password = input("   SMTP 授权码（非邮箱密码）: ").strip()
        to = input("   收件人邮箱（回车同发件人）: ").strip()
        if sender:
            config["email"] = {
                "sender_email": sender,
                "sender_password": password,
                "to_email": to or sender,
                "smtp_host": "",   # 自动推断
                "smtp_port": 0,
                "use_ssl": True,
            }
            print(f"   [OK] 邮件配置完成: {sender} → {to or sender}")
    else:
        config["email"] = {}
        print("   [INFO] 跳过邮件配置，摘要仅保存到本地文件")

    # 保存配置
    config_with_meta = {
        **config,
        "config_version": 1,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config_with_meta, f, allow_unicode=True, default_flow_style=False)

    print(f"\n[OK] 配置已保存到: {CONFIG_PATH}")

    # 询问是否创建计划任务
    print("\n" + "-" * 50)
    create_task = input("是否创建 Windows 每日定时任务？(Y/n): ").strip().lower()
    if create_task != "n":
        from src.scheduler import create_windows_task, get_python_path
        if create_windows_task("WeChatSummarizer", config["schedule_time"], get_python_path()):
            print("[OK] 计划任务已创建！在 Windows 任务计划程序中可查看")
        else:
            print("[WARN] 计划任务创建失败，可稍后手动创建或使用守护模式")
            print("   守护模式: python main.py --daemon")

    print("\n配置完成！")
    print(f"   单次运行: python main.py --once")
    print(f"   守护模式: python main.py --daemon")
    print(f"   重新配置: python setup.py")
    print()


def main():
    if os.path.exists(CONFIG_PATH):
        print(f"[WARN] 配置文件已存在: {CONFIG_PATH}")
        overwrite = input("是否覆盖重新配置？(y/N): ").strip().lower()
        if overwrite != "y":
            print("已取消。如需重新配置请删除 config.yaml 后重试。")
            return

    _interactive_setup()


if __name__ == "__main__":
    main()

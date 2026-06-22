"""
微信消息读取模块 —— 基于 PyWxDump 解密本地数据库（无封号风险）
"""
import os
import re
import time
import hashlib
import tempfile
import sqlite3
from datetime import date, datetime
from typing import Optional
from loguru import logger

from pywxdump.wx_info.decryption import decrypt as wx_decrypt


class WeChatDBReader:
    """从微信本地加密数据库读取消息"""

    def __init__(self, key: str, db_path: str):
        """
        - key: 数据库密钥（32位hex字符串）
        - db_path: 微信数据目录，如 C:\\...\\WeChat Files\\wxid_xxx
        """
        self.key = key
        self.db_path = db_path
        self.msg_dir = os.path.join(db_path, "Msg", "Multi")
        self._decrypted_dbs: dict[str, str] = {}  # 原始路径 → 临时解密路径
        self._group_name_cache: dict[str, str] = {}  # chatroom_id → 显示名
        self._contact_cache: dict[str, str] = {}  # wxid → 显示名
        self._load_contacts()

    def _load_contacts(self):
        """从 MicroMsg.db 加载联系人和群聊名称"""
        micro_path = os.path.join(self.db_path, "Msg", "MicroMsg.db")
        if not os.path.exists(micro_path):
            logger.warning("MicroMsg.db 不存在，无法加载联系人名称")
            return

        tmp = self._decrypt_db(micro_path)
        if not tmp:
            return
        try:
            conn = sqlite3.connect(tmp)
            # 加载群聊名称（Type=2 和 Type=2050 都是群聊）
            try:
                rows = conn.execute(
                    "SELECT UserName, NickName FROM Contact WHERE Type IN (2, 2050)"
                ).fetchall()
                for r in rows:
                    self._group_name_cache[r[0]] = r[1]
                logger.info(f"加载了 {len(self._group_name_cache)} 个群聊名称")
            except Exception:
                pass

            # 加载联系人名称
            try:
                rows = conn.execute(
                    "SELECT UserName, NickName FROM Contact WHERE Type=1 OR Type=3"
                ).fetchall()
                for r in rows:
                    self._contact_cache[r[0]] = r[1]
                logger.info(f"加载了 {len(self._contact_cache)} 个联系人名称")
            except Exception:
                pass
            conn.close()
        except Exception as e:
            logger.error(f"加载联系人失败: {e}")

    def _decrypt_db(self, db_path: str) -> Optional[str]:
        """解密单个数据库，返回临时文件路径"""
        if db_path in self._decrypted_dbs:
            return self._decrypted_dbs[db_path]

        if not os.path.exists(db_path):
            return None

        # 解密到临时目录
        name = hashlib.md5(db_path.encode()).hexdigest()[:8]
        tmp = os.path.join(tempfile.gettempdir(), f"wx_dec_{name}.db")

        if os.path.exists(tmp):
            # 检查是否今天解密的（避免重复解密）
            mtime = os.path.getmtime(tmp)
            if time.time() - mtime < 3600:  # 1小时内有效
                self._decrypted_dbs[db_path] = tmp
                return tmp

        try:
            if wx_decrypt(self.key, db_path, tmp):
                self._decrypted_dbs[db_path] = tmp
                return tmp
            else:
                logger.error(f"解密失败: {db_path}")
                return None
        except Exception as e:
            logger.error(f"解密异常 {db_path}: {e}")
            return None

    def _resolve_group(self, keyword: str) -> Optional[str]:
        """根据群名关键字查找 chatroom_id（选今天消息最多的那个）"""
        matches = []
        for cid, name in self._group_name_cache.items():
            if keyword in name:
                matches.append(cid)

        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]

        # 多个匹配，选今天消息最多的
        today_start = int(datetime.combine(date.today(), datetime.min.time()).timestamp())
        best_cid = None
        best_count = -1
        for cid in matches:
            count = self._count_today_msgs(cid, today_start)
            if count > best_count:
                best_count = count
                best_cid = cid
        return best_cid

    def _count_today_msgs(self, chatroom_id: str, today_start: int) -> int:
        """统计某个群今天有多少消息"""
        count = 0
        if not os.path.exists(self.msg_dir):
            return 0
        for fname in os.listdir(self.msg_dir):
            if not fname.startswith("MSG") or "FTS" in fname or not fname.endswith(".db"):
                continue
            tmp = self._decrypt_db(os.path.join(self.msg_dir, fname))
            if not tmp:
                continue
            try:
                conn = sqlite3.connect(tmp)
                c = conn.execute(
                    "SELECT COUNT(*) FROM MSG WHERE StrTalker=? AND CreateTime >= ?",
                    (chatroom_id, today_start),
                ).fetchone()
                if c:
                    count += c[0]
                conn.close()
            except Exception:
                pass
        return count

    def get_group_display_name(self, chatroom_id: str) -> str:
        """获取群聊显示名称"""
        return self._group_name_cache.get(chatroom_id, chatroom_id)

    def get_contact_display_name(self, wxid: str) -> str:
        """获取联系人显示名称"""
        return self._contact_cache.get(wxid, wxid)

    @staticmethod
    def _parse_sender_from_extra(bytes_extra: Optional[bytes]) -> Optional[str]:
        """从 BytesExtra protobuf 中提取发送者 wxid"""
        if not bytes_extra:
            return None
        try:
            # wxid 通常在 field 1, subfield 2 附近
            # 简单正则提取: wxid_xxx 或 @chatroom 模式
            text = bytes_extra.decode("utf-8", errors="ignore")
            match = re.search(r"(wxid_[a-z0-9]+)", text)
            if match:
                return match.group(1)
            match = re.search(r"(\d+@chatroom)", text)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    @staticmethod
    def _parse_content(str_content: Optional[str]) -> str:
        """解析消息内容（处理 XML 格式）"""
        if not str_content:
            return ""
        # 普通文本直接返回
        if not str_content.startswith("<"):
            return str_content
        # XML 格式的文本消息
        match = re.search(r"<title>(.*?)</title>", str_content, re.DOTALL)
        if match:
            return match.group(1)
        # 系统消息
        if "<sysmsg" in str_content:
            return "[系统消息]"
        # 图片/文件等
        if "<img" in str_content:
            return "[图片]"
        if "<videomsg" in str_content:
            return "[视频]"
        if "<voicemsg" in str_content:
            return "[语音]"
        if "<appmsg" in str_content:
            title = re.search(r"<title>(.*?)</title>", str_content)
            if title:
                return f"[链接] {title.group(1)}"
            return "[链接]"
        return str_content[:100]

    def get_today_messages(
        self,
        group_keyword: str,
        limit: int = 5000,
    ) -> list[dict]:
        """
        获取指定群今天的消息。
        - group_keyword: 群名关键字
        - limit: 最大消息数
        返回: [{"time": "14:30", "sender": "张三", "content": "你好"}, ...]
        """
        # 先找 chatroom_id
        chatroom_id = self._resolve_group(group_keyword)
        if not chatroom_id:
            logger.error(f"未找到群聊: {group_keyword}")
            logger.info(f"已知群聊: {list(self._group_name_cache.keys())[:10]}")
            return []

        group_name = self.get_group_display_name(chatroom_id)
        today = date.today()
        today_start = int(datetime(today.year, today.month, today.day).timestamp())

        all_messages = []

        # 遍历所有 MSG*.db
        if not os.path.exists(self.msg_dir):
            logger.error(f"消息目录不存在: {self.msg_dir}")
            return []

        for fname in sorted(os.listdir(self.msg_dir)):
            if not fname.startswith("MSG") or fname.endswith("9.db"):
                continue
            if "FTS" in fname:
                continue
            if not fname.endswith(".db"):
                continue

            db_file = os.path.join(self.msg_dir, fname)
            tmp = self._decrypt_db(db_file)
            if not tmp:
                continue

            try:
                conn = sqlite3.connect(tmp)
                rows = conn.execute(
                    """SELECT CreateTime, StrTalker, StrContent, BytesExtra, IsSender
                       FROM MSG
                       WHERE StrTalker = ? AND CreateTime >= ? AND Type = 1
                       ORDER BY CreateTime ASC
                       LIMIT ?""",
                    (chatroom_id, today_start, limit),
                ).fetchall()

                for create_time, str_talker, str_content, bytes_extra, is_sender in rows:
                    content = self._parse_content(str_content)
                    if not content:
                        continue

                    # 获取发送者
                    sender_wxid = self._parse_sender_from_extra(bytes_extra)
                    if sender_wxid:
                        sender_name = self.get_contact_display_name(sender_wxid)
                    else:
                        sender_name = "我" if is_sender == 1 else "未知"

                    msg_time = datetime.fromtimestamp(create_time)
                    time_str = msg_time.strftime("%Y-%m-%d %H:%M:%S")

                    all_messages.append({
                        "time": time_str,
                        "sender": sender_name,
                        "content": content,
                    })

                conn.close()
            except Exception as e:
                logger.warning(f"读取 {fname} 失败: {e}")
                continue

        all_messages.sort(key=lambda x: x["time"])
        logger.info(f"群 [{group_name}] 今天消息: {len(all_messages)} 条")
        return all_messages

    def get_group_list(self) -> list[dict]:
        """获取所有群聊列表（含显示名和chatroom_id）"""
        result = []
        for cid, name in self._group_name_cache.items():
            result.append({"id": cid, "name": name})
        return result

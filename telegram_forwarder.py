#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram 消息转发器 v3.1.5
现代化UI + 完整主题支持 + 无引用转发 + 沉浸式设计 + 消息类型过滤 + 消息同步管理 + Bot API 混合架构
优化：1.启动时检查删除状态 2.支持多文件合并转发 3.集成 Bot API 减轻用户 API 压力
BUG修复：修复合并消息重复转发问题，同时记录所有消息映射
修复：修复发送带超链接文本消息时的 AttributeError
优化：在日志中标注每次功能的API类型
修复：修复停止服务后按钮状态不更新的问题
新增：支持保持即时预览与文本的相对位置（invert_media）
修复：修复超链接格式问题 - 使用formatting_entities参数和EditMessageRequest设置invert_media
新增：编辑带网页预览的消息时也能保持预览位置和格式
新增：点击最小化后程序自动最小化到系统托盘
新增：点击关闭时提示选择"最小化到托盘"或"退出程序"
修复：修复编辑消息时entities偏移量错误导致格式混乱的问题（重新获取编辑后的entities）
"""

import sys
import json
import asyncio
import logging
import traceback
import sqlite3
import aiohttp
from pathlib import Path
from typing import Optional, Dict, List, Set, Tuple, Any, Union
from datetime import datetime
from enum import Enum

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit, QListWidget, QListWidgetItem,
    QDialog, QFormLayout, QComboBox, QCheckBox, QGroupBox, QTabWidget,
    QMessageBox, QInputDialog, QSpinBox, QFrame, QScrollArea, QGridLayout,
    QSystemTrayIcon, QMenu, QAction, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QToolButton
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QPalette, QColor, QIcon, QPainter, QPainterPath, QClipboard
from PyQt5.QtCore import QSettings

from telethon import TelegramClient, events, functions, types
from telethon.errors import SessionPasswordNeededError, FloodWaitError, MessageIdInvalidError, MessageNotModifiedError
from telethon.tl.types import (
    Message, MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage,
    MessageMediaContact, MessageMediaGeo, MessageMediaVenue, MessageMediaGame,
    MessageMediaInvoice, MessageMediaPoll, MessageMediaDice,
    UpdateDeleteMessages, UpdateDeleteChannelMessages  # 添加删除事件类型导入
)
from telethon.tl.functions.messages import EditMessageRequest
from telethon.tl.custom import Message as CustomMessage

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('telegram_forwarder.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MessageType(Enum):
    """消息类型枚举"""
    TEXT = "文本"
    PHOTO = "图片"
    VIDEO = "视频"
    VOICE = "语音"
    DOCUMENT = "文件"
    STICKER = "贴纸"
    AUDIO = "音频"
    WEBPAGE = "网页链接"
    CONTACT = "联系人"
    GEO = "位置"
    VENUE = "地点"
    GAME = "游戏"
    INVOICE = "发票"
    POLL = "投票"
    DICE = "骰子"
    OTHER = "其他"


class BotAPIManager:
    """Bot API 管理器类"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.session: Optional[aiohttp.ClientSession] = None
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.is_available = False
    
    async def initialize(self):
        """初始化 Bot API 连接"""
        try:
            self.session = aiohttp.ClientSession()
            # 测试 Bot 是否可用
            await self.get_me()
            self.is_available = True
            return True
        except Exception as e:
            logger.error(f"Bot API 初始化失败: {e}")
            self.is_available = False
            return False
    
    async def close(self):
        """关闭连接"""
        if self.session:
            await self.session.close()
    
    async def _make_request(self, method: str, params: dict = None):
        """发送 Bot API 请求"""
        try:
            async with self.session.post(f"{self.base_url}/{method}", json=params) as response:
                result = await response.json()
                if result.get('ok'):
                    return result.get('result')
                else:
                    error_msg = result.get('description', 'Unknown error')
                    logger.error(f"Bot API 错误: {error_msg}")
                    raise Exception(f"Bot API error: {error_msg}")
        except Exception as e:
            logger.error(f"Bot API 请求失败: {e}")
            raise
    
    async def get_me(self):
        """获取 Bot 信息"""
        return await self._make_request('getMe')
    
    async def send_message(self, chat_id: str, text: str, reply_to_message_id: int = None, 
                          disable_web_page_preview: bool = True) -> Dict:
        """发送文本消息"""
        params = {
            'chat_id': chat_id,
            'text': text,
            'disable_web_page_preview': disable_web_page_preview
        }
        if reply_to_message_id:
            params['reply_to_message_id'] = reply_to_message_id
        
        return await self._make_request('sendMessage', params)
    
    async def send_photo(self, chat_id: str, photo: str, caption: str = "", 
                        reply_to_message_id: int = None) -> Dict:
        """发送图片"""
        params = {
            'chat_id': chat_id,
            'photo': photo,
            'caption': caption
        }
        if reply_to_message_id:
            params['reply_to_message_id'] = reply_to_message_id
        
        return await self._make_request('sendPhoto', params)
    
    async def send_video(self, chat_id: str, video: str, caption: str = "", 
                        reply_to_message_id: int = None) -> Dict:
        """发送视频"""
        params = {
            'chat_id': chat_id,
            'video': video,
            'caption': caption
        }
        if reply_to_message_id:
            params['reply_to_message_id'] = reply_to_message_id
        
        return await self._make_request('sendVideo', params)
    
    async def send_document(self, chat_id: str, document: str, caption: str = "", 
                           reply_to_message_id: int = None) -> Dict:
        """发送文档"""
        params = {
            'chat_id': chat_id,
            'document': document,
            'caption': caption
        }
        if reply_to_message_id:
            params['reply_to_message_id'] = reply_to_message_id
        
        return await self._make_request('sendDocument', params)
    
    async def send_audio(self, chat_id: str, audio: str, caption: str = "", 
                        reply_to_message_id: int = None) -> Dict:
        """发送音频"""
        params = {
            'chat_id': chat_id,
            'audio': audio,
            'caption': caption
        }
        if reply_to_message_id:
            params['reply_to_message_id'] = reply_to_message_id
        
        return await self._make_request('sendAudio', params)
    
    async def send_media_group(self, chat_id: str, media: List[Dict], 
                              reply_to_message_id: int = None) -> Dict:
        """发送媒体组"""
        params = {
            'chat_id': chat_id,
            'media': media
        }
        if reply_to_message_id:
            params['reply_to_message_id'] = reply_to_message_id
        
        return await self._make_request('sendMediaGroup', params)
    
    async def delete_message(self, chat_id: str, message_id: int) -> Dict:
        """删除消息"""
        params = {
            'chat_id': chat_id,
            'message_id': message_id
        }
        return await self._make_request('deleteMessage', params)
    
    async def edit_message_text(self, chat_id: str, message_id: int, text: str, 
                               disable_web_page_preview: bool = True) -> Dict:
        """编辑消息文本"""
        params = {
            'chat_id': chat_id,
            'message_id': message_id,
            'text': text,
            'disable_web_page_preview': disable_web_page_preview
        }
        return await self._make_request('editMessageText', params)
    
    async def edit_message_caption(self, chat_id: str, message_id: int, caption: str) -> Dict:
        """编辑消息说明"""
        params = {
            'chat_id': chat_id,
            'message_id': message_id,
            'caption': caption
        }
        return await self._make_request('editMessageCaption', params)
    
    async def get_file(self, file_id: str) -> Dict:
        """获取文件信息"""
        params = {'file_id': file_id}
        return await self._make_request('getFile', params)
    
    async def download_file(self, file_path: str, destination: Path) -> bool:
        """下载文件"""
        try:
            url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    with open(destination, 'wb') as f:
                        f.write(await response.read())
                    return True
                else:
                    logger.error(f"下载文件失败: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"下载文件出错: {e}")
            return False


class Database:
    """数据库管理类"""
    
    def __init__(self, db_path="message_mapping.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 消息映射表 - 添加 api_type 字段
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS message_mapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_id INTEGER NOT NULL,
                    source_chat_id TEXT NOT NULL,
                    source_message_id INTEGER NOT NULL,
                    source_topic_id INTEGER,
                    target_chat_id TEXT NOT NULL,
                    target_message_id INTEGER NOT NULL,
                    target_topic_id INTEGER,
                    message_type TEXT NOT NULL,
                    file_id TEXT,  -- Telegram文件ID（用于判断文件是否更改）
                    text_content TEXT,
                    has_webpage INTEGER DEFAULT 0,
                    webpage_url TEXT,
                    grouped_id TEXT,  -- 新增：群组ID
                    is_grouped INTEGER DEFAULT 0,  -- 新增：是否群组消息
                    group_index INTEGER,  -- 新增：在群组中的索引
                    api_type TEXT DEFAULT 'user',  -- 新增：使用的API类型(user/bot)
                    bot_message_data TEXT,  -- 新增：Bot API消息数据
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(source_chat_id, source_message_id, rule_id)
                )
            ''')
            
            # 消息删除记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS deleted_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mapping_id INTEGER NOT NULL,
                    chat_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    is_source INTEGER NOT NULL,  -- 1:源消息, 0:目标消息
                    deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (mapping_id) REFERENCES message_mapping(id) ON DELETE CASCADE
                )
            ''')
            
            # 消息编辑历史表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS edit_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mapping_id INTEGER NOT NULL,
                    old_text TEXT,
                    new_text TEXT,
                    old_file_id TEXT,
                    new_file_id TEXT,
                    edit_type TEXT NOT NULL,  -- 'text', 'file', 'webpage', 'both'
                    edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (mapping_id) REFERENCES message_mapping(id) ON DELETE CASCADE
                )
            ''')
            
            # 编辑通知表（新增）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS edit_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mapping_id INTEGER NOT NULL,
                    notification_type TEXT NOT NULL,  -- 'file_added', 'file_changed', 'file_removed', 'webpage_changed'
                    description TEXT NOT NULL,
                    source_chat_id TEXT NOT NULL,
                    source_message_id INTEGER NOT NULL,
                    source_topic_id INTEGER,
                    target_chat_id TEXT NOT NULL,
                    target_message_id INTEGER NOT NULL,
                    target_topic_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_resolved INTEGER DEFAULT 0,  -- 0:未处理, 1:已处理
                    resolved_at TIMESTAMP,
                    FOREIGN KEY (mapping_id) REFERENCES message_mapping(id) ON DELETE CASCADE
                )
            ''')
            
            conn.commit()
    
    def add_message_mapping(self, rule_id: int, source_chat_id: str, source_message_id: int,
                           source_topic_id: Optional[int], target_chat_id: str, 
                           target_message_id: int, target_topic_id: Optional[int],
                           message_type: str, file_id: Optional[str] = None,
                           text_content: Optional[str] = None, has_webpage: bool = False,
                           webpage_url: Optional[str] = None, 
                           grouped_id: Optional[str] = None, is_grouped: bool = False,
                           group_index: Optional[int] = None,
                           api_type: str = 'user', bot_message_data: Optional[str] = None) -> int:
        """添加消息映射"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO message_mapping 
                (rule_id, source_chat_id, source_message_id, source_topic_id,
                 target_chat_id, target_message_id, target_topic_id,
                 message_type, file_id, text_content, has_webpage, webpage_url,
                 grouped_id, is_grouped, group_index, api_type, bot_message_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (rule_id, str(source_chat_id), source_message_id, source_topic_id,
                  str(target_chat_id), target_message_id, target_topic_id,
                  message_type, file_id, text_content, 1 if has_webpage else 0, webpage_url,
                  grouped_id, 1 if is_grouped else 0, group_index, api_type, bot_message_data))
            mapping_id = cursor.lastrowid
            conn.commit()
            return mapping_id
    
    def get_mapping_by_source(self, source_chat_id: str, source_message_id: int, rule_id: int) -> Optional[Dict]:
        """根据源消息获取映射"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM message_mapping 
                WHERE source_chat_id = ? AND source_message_id = ? AND rule_id = ?
            ''', (str(source_chat_id), source_message_id, rule_id))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_mapping_by_target(self, target_chat_id: str, target_message_id: int) -> Optional[Dict]:
        """根据目标消息获取映射"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM message_mapping 
                WHERE target_chat_id = ? AND target_message_id = ?
            ''', (str(target_chat_id), target_message_id))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_mappings(self) -> List[Dict]:
        """获取所有消息映射（新增）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM message_mapping ORDER BY id DESC')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_mapping_by_channel_message(self, channel_id: int, message_id: int) -> List[Dict]:
        """根据频道消息ID获取映射（新增，处理不带-100前缀的频道ID）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 尝试多种可能的频道ID格式
            channel_id_str = str(channel_id)
            channel_id_with_prefix = f"-100{channel_id_str}"
            
            # 先尝试带-100前缀的格式
            cursor.execute('''
                SELECT * FROM message_mapping 
                WHERE source_chat_id = ? AND source_message_id = ?
                OR target_chat_id = ? AND target_message_id = ?
            ''', (channel_id_with_prefix, message_id, channel_id_with_prefix, message_id))
            
            rows = cursor.fetchall()
            
            if rows:
                return [dict(row) for row in rows]
            
            # 再尝试不带-100前缀的格式
            cursor.execute('''
                SELECT * FROM message_mapping 
                WHERE source_chat_id = ? AND source_message_id = ?
                OR target_chat_id = ? AND target_message_id = ?
            ''', (channel_id_str, message_id, channel_id_str, message_id))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_mapping_by_id(self, mapping_id: int) -> Optional[Dict]:
        """根据ID获取映射"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM message_mapping WHERE id = ?', (mapping_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_grouped_mappings(self, grouped_id: str) -> List[Dict]:
        """根据群组ID获取所有映射（新增）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM message_mapping 
                WHERE grouped_id = ?
                ORDER BY group_index ASC
            ''', (grouped_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def delete_mapping(self, mapping_id: int):
        """删除映射"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM message_mapping WHERE id = ?', (mapping_id,))
            conn.commit()
    
    def delete_mappings_by_grouped_id(self, grouped_id: str):
        """根据群组ID删除所有映射（新增）"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM message_mapping WHERE grouped_id = ?', (grouped_id,))
            conn.commit()
    
    def record_message_deletion(self, mapping_id: int, chat_id: str, message_id: int, is_source: bool):
        """记录消息删除"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO deleted_messages (mapping_id, chat_id, message_id, is_source)
                VALUES (?, ?, ?, ?)
            ''', (mapping_id, str(chat_id), message_id, 1 if is_source else 0))
            conn.commit()
    
    def record_edit_history(self, mapping_id: int, old_text: Optional[str], new_text: Optional[str],
                           old_file_id: Optional[str], new_file_id: Optional[str], edit_type: str):
        """记录编辑历史"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO edit_history (mapping_id, old_text, new_text, old_file_id, new_file_id, edit_type)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (mapping_id, old_text, new_text, old_file_id, new_file_id, edit_type))
            conn.commit()
    
    def add_edit_notification(self, mapping_id: int, notification_type: str, description: str,
                            source_chat_id: str, source_message_id: int, source_topic_id: Optional[int],
                            target_chat_id: str, target_message_id: int, target_topic_id: Optional[int]) -> int:
        """添加编辑通知（新增）"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO edit_notifications 
                (mapping_id, notification_type, description, source_chat_id, source_message_id, source_topic_id,
                 target_chat_id, target_message_id, target_topic_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (mapping_id, notification_type, description, 
                  str(source_chat_id), source_message_id, source_topic_id,
                  str(target_chat_id), target_message_id, target_topic_id))
            notification_id = cursor.lastrowid
            conn.commit()
            return notification_id
    
    def get_pending_notifications(self) -> List[Dict]:
        """获取待处理的编辑通知（新增）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM edit_notifications 
                WHERE is_resolved = 0 
                ORDER BY created_at DESC
            ''')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_notifications_count(self) -> int:
        """获取待处理通知数量（新增）"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM edit_notifications WHERE is_resolved = 0')
            count = cursor.fetchone()[0]
            return count
    
    def delete_notifications_by_mapping_id(self, mapping_id: int):
        """根据映射ID删除通知（新增）"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM edit_notifications WHERE mapping_id = ?', (mapping_id,))
            conn.commit()
    
    def mark_notification_resolved(self, notification_id: int):
        """标记通知为已处理（新增）"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE edit_notifications 
                SET is_resolved = 1, resolved_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (notification_id,))
            conn.commit()
    
    def delete_notification(self, notification_id: int):
        """删除通知（新增）"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM edit_notifications WHERE id = ?', (notification_id,))
            conn.commit()
    
    def update_message_mapping(self, mapping_id: int, file_id: Optional[str] = None,
                              text_content: Optional[str] = None, 
                              webpage_url: Optional[str] = None,
                              api_type: Optional[str] = None,
                              bot_message_data: Optional[str] = None):
        """更新消息映射"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            updates = []
            params = []
            
            if file_id is not None:
                updates.append("file_id = ?")
                params.append(file_id)
            
            if text_content is not None:
                updates.append("text_content = ?")
                params.append(text_content)
            
            if webpage_url is not None:
                updates.append("webpage_url = ?")
                params.append(webpage_url)
            
            if api_type is not None:
                updates.append("api_type = ?")
                params.append(api_type)
            
            if bot_message_data is not None:
                updates.append("bot_message_data = ?")
                params.append(bot_message_data)
            
            if updates:
                updates.append("updated_at = CURRENT_TIMESTAMP")
                query = f"UPDATE message_mapping SET {', '.join(updates)} WHERE id = ?"
                params.append(mapping_id)
                cursor.execute(query, params)
                conn.commit()


class Config:
    """配置管理类"""
    CONFIG_FILE = "config.json"
    
    @staticmethod
    def load() -> dict:
        """加载配置"""
        if Path(Config.CONFIG_FILE).exists():
            with open(Config.CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "api_id": "",
            "api_hash": "",
            "phone": "",
            "session_name": "telegram_forwarder",
            "bot_token": "",  # 新增：Bot Token
            "use_bot_api": True,  # 新增：是否启用 Bot API
            "bot_api_for_text": True,  # 新增：文本消息使用 Bot
            "bot_api_for_media": True,  # 新增：媒体消息使用 Bot
            "bot_api_for_delete": True,  # 新增：删除使用 Bot
            "bot_api_for_edit": True,  # 新增：编辑使用 Bot
            "bot_api_fallback": True,  # 新增：Bot API 失败时回退到用户 API
            "auto_start": False,
            "rules": [],
            "theme": "dark",
            "version": "3.1.5",  # 更新版本号
            "author": "DomAurora",
            "window_geometry": None,
            "window_state": None,
            "enable_message_sync": True,
            "show_tray_notifications": True,
            "enable_deletion_sync": True,
            "check_deleted_on_startup": True
        }
    
    @staticmethod
    def save(config: dict):
        """保存配置"""
        with open(Config.CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)


class TelegramWorker(QThread):
    """Telegram 工作线程"""
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    auth_code_signal = pyqtSignal()
    password_signal = pyqtSignal()
    stopped_signal = pyqtSignal()
    notification_signal = pyqtSignal(str, str)  # 新增：托盘通知信号 (标题, 内容)
    edit_notification_signal = pyqtSignal(dict)  # 新增：编辑通知信号
    notification_count_signal = pyqtSignal(int)  # 新增：通知计数信号
    service_stopped_signal = pyqtSignal()  # 新增：服务完全停止信号
    
    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.client: Optional[TelegramClient] = None
        self.bot_manager: Optional[BotAPIManager] = None
        self.is_running = False
        self.auth_code = None
        self.password = None
        self.loop = None
        self.should_stop = False
        self.db = Database()  # 新增：数据库实例
        self.enable_sync = config.get('enable_message_sync', True)
        self.enable_deletion_sync = config.get('enable_deletion_sync', True)
        self.check_deleted_on_startup = config.get('check_deleted_on_startup', True)
        self.use_bot_api = config.get('use_bot_api', True)
        self.bot_api_for_text = config.get('bot_api_for_text', True)
        self.bot_api_for_media = config.get('bot_api_for_media', True)
        self.bot_api_for_delete = config.get('bot_api_for_delete', True)
        self.bot_api_for_edit = config.get('bot_api_for_edit', True)
        self.bot_api_fallback = config.get('bot_api_fallback', True)
        self.deleted_messages: Set[Tuple[str, int]] = set()
        self.processed_group_messages: Set[Tuple[str, int]] = set()
        self.current_group_processing: Dict[str, Dict] = {}
    
    def run(self):
        """运行工作线程"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            self.loop.run_until_complete(self.start_client())
        except Exception as e:
            if not self.should_stop:
                logger.exception("工作线程异常")
                self.error_signal.emit(f"工作线程异常: {str(e)}\n详细错误信息请查看日志文件")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """清理资源"""
        try:
            if self.loop and not self.loop.is_closed():
                self.loop.run_until_complete(self.close_resources())
                self.loop.close()
        except Exception as e:
            logger.warning(f"清理事件循环时出错: {e}")
        finally:
            self.loop = None
            self.client = None
            self.bot_manager = None
            self.is_running = False
            # 确保发送停止完成信号
            self.stopped_signal.emit()
            self.service_stopped_signal.emit()
    
    async def close_resources(self):
        """关闭资源"""
        # 关闭 Bot API 连接
        if self.bot_manager:
            await self.bot_manager.close()
        
        # 断开客户端连接
        await self.disconnect_client()
    
    async def start_client(self):
        """启动客户端"""
        try:
            self.log_signal.emit(f"[详细日志] 开始创建Telegram客户端...")
            self.log_signal.emit(f"[详细日志] 会话名称: {self.config['session_name']}")
            self.log_signal.emit(f"[详细日志] API ID: {self.config['api_id'][:8]}***")
            self.log_signal.emit(f"[详细日志] API Hash: {self.config['api_hash'][:8]}***")
            self.log_signal.emit(f"[详细日志] 消息同步: {'已启用' if self.enable_sync else '已禁用'}")
            self.log_signal.emit(f"[详细日志] 删除同步: {'已启用' if self.enable_deletion_sync else '已禁用'}")
            self.log_signal.emit(f"[详细日志] 启动检查删除: {'已启用' if self.check_deleted_on_startup else '已禁用'}")
            
            # 初始化 Bot API（如果启用）
            if self.use_bot_api and self.config.get('bot_token'):
                self.log_signal.emit(f"[详细日志] 🔧 正在初始化 Bot API...")
                self.bot_manager = BotAPIManager(self.config['bot_token'])
                bot_initialized = await self.bot_manager.initialize()
                if bot_initialized:
                    self.log_signal.emit(f"[详细日志] ✅ Bot API 初始化成功")
                    self.log_signal.emit(f"[详细日志] 📊 Bot API 使用策略:")
                    self.log_signal.emit(f"[详细日志]   - 文本消息: {'使用 Bot' if self.bot_api_for_text else '使用用户 API'}")
                    self.log_signal.emit(f"[详细日志]   - 媒体消息: {'使用 Bot' if self.bot_api_for_media else '使用用户 API'}")
                    self.log_signal.emit(f"[详细日志]   - 消息删除: {'使用 Bot' if self.bot_api_for_delete else '使用用户 API'}")
                    self.log_signal.emit(f"[详细日志]   - 消息编辑: {'使用 Bot' if self.bot_api_for_edit else '使用用户 API'}")
                    self.log_signal.emit(f"[详细日志]   - 失败回退: {'启用' if self.bot_api_fallback else '禁用'}")
                else:
                    self.log_signal.emit(f"[详细日志] ⚠ Bot API 初始化失败，将仅使用用户 API")
            else:
                self.log_signal.emit(f"[详细日志] ⚠ Bot API 未启用或未配置 Token")
            
            self.client = TelegramClient(
                self.config['session_name'],
                self.config['api_id'],
                self.config['api_hash']
            )
            
            await self.client.connect()
            self.log_signal.emit("[详细日志] ✓ 成功连接到 Telegram 服务器")
            
            if not await self.client.is_user_authorized():
                self.log_signal.emit("[详细日志] 用户未认证，开始认证流程...")
                await self.authenticate()
            else:
                self.log_signal.emit("[详细日志] ✓ 用户已认证，跳过登录流程")
            
            self.log_signal.emit(f"[详细日志] ✓ 已登录账户: {self.config['phone']}")
            self.status_signal.emit("运行中")
            
            # 启动时检查删除状态
            if self.check_deleted_on_startup:
                await self.check_deleted_messages_on_startup()
            
            # 注册消息处理器
            await self.register_handlers()
            
            # 启动删除监听（如果启用删除同步）
            if self.enable_deletion_sync:
                await self.start_deletion_monitoring()
            
            self.is_running = True
            self.log_signal.emit("[详细日志] ✓ 消息转发服务已启动")
            
            # 发送初始通知计数
            await self.send_notification_count()
            
            while not self.should_stop:
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    break
            
        except Exception as e:
            logger.exception("启动客户端失败")
            self.error_signal.emit(f"启动失败: {str(e)}\n详细错误信息请查看日志文件")
            self.status_signal.emit("已停止")
        finally:
            await self.disconnect_client()
    
    async def check_deleted_messages_on_startup(self):
        """启动时检查消息删除状态"""
        try:
            self.log_signal.emit("[详细日志] 🔍 正在检查已删除的消息...")
            
            all_mappings = self.db.get_all_mappings()
            self.log_signal.emit(f"[详细日志] 数据库中共有 {len(all_mappings)} 条消息映射")
            
            deleted_count = 0
            
            for mapping in all_mappings:
                try:
                    # 检查源消息是否存在
                    source_exists = await self.check_message_exists(
                        mapping['source_chat_id'], 
                        mapping['source_message_id']
                    )
                    
                    # 检查目标消息是否存在
                    target_exists = await self.check_message_exists(
                        mapping['target_chat_id'], 
                        mapping['target_message_id']
                    )
                    
                    if not source_exists:
                        self.log_signal.emit(f"[详细日志] ⚠ 源消息 {mapping['source_chat_id']}/{mapping['source_message_id']} 已删除")
                        # 删除对应的目标消息
                        await self.delete_target_message(mapping)
                        deleted_count += 1
                    
                    elif not target_exists:
                        self.log_signal.emit(f"[详细日志] ⚠ 目标消息 {mapping['target_chat_id']}/{mapping['target_message_id']} 已删除")
                        # 同步删除源消息
                        await self.sync_delete_source_message(mapping)
                        deleted_count += 1
                    
                except Exception as e:
                    self.log_signal.emit(f"[详细日志] ✗ 检查消息 {mapping['id']} 时出错: {str(e)}")
                    continue
            
            if deleted_count > 0:
                self.log_signal.emit(f"[详细日志] ✓ 启动检查完成，清理了 {deleted_count} 个已删除的消息")
            else:
                self.log_signal.emit(f"[详细日志] ✓ 启动检查完成，所有消息状态正常")
                
        except Exception as e:
            logger.exception("启动时检查删除状态失败")
            self.log_signal.emit(f"[详细日志] ✗ 启动检查删除状态失败: {str(e)}")
    
    async def check_message_exists(self, chat_id: str, message_id: int) -> bool:
        """检查消息是否存在"""
        try:
            try:
                if str(chat_id).lstrip('-').isdigit():
                    entity_id = int(chat_id)
                else:
                    entity_id = chat_id
            except:
                entity_id = chat_id
            
            msg = await self.client.get_messages(
                entity=entity_id,
                ids=message_id
            )
            
            return msg is not None
            
        except Exception as e:
            if "message not found" in str(e).lower() or "message_id_invalid" in str(e).lower():
                return False
            raise
    
    async def send_notification_count(self):
        """发送通知计数"""
        try:
            count = self.db.get_notifications_count()
            self.notification_count_signal.emit(count)
        except Exception as e:
            logger.exception("获取通知计数失败")
    
    async def start_deletion_monitoring(self):
        """开始监听消息删除"""
        try:
            self.log_signal.emit("[调试] 🔍 正在注册删除事件处理器...")
            
            @self.client.on(events.Raw(types=(UpdateDeleteMessages, UpdateDeleteChannelMessages)))
            async def delete_handler(event):
                await self.handle_message_deletion(event)
            
            self.log_signal.emit("[详细日志] ✓ 消息删除监听已启动")
            self.log_signal.emit("[调试] ✓ 删除事件处理器已注册")
            
        except Exception as e:
            logger.exception("启动删除监听失败")
            self.log_signal.emit(f"[详细日志] ✗ 启动删除监听失败: {str(e)}")
            self.log_signal.emit(f"[调试] ✗ 注册删除事件处理器失败: {str(e)}")
            self.log_signal.emit(f"[调试] 错误详情: {traceback.format_exc()}")
    
    async def handle_message_deletion(self, event):
        """处理消息删除事件"""
        try:
            self.log_signal.emit(f"[调试] 🔔 收到删除事件: {type(event).__name__}")
            
            if hasattr(event, 'channel_id'):
                raw_chat_id = event.channel_id
                messages = event.messages
                is_channel = True
                self.log_signal.emit(f"[调试] 频道消息删除: channel_id={raw_chat_id}, messages={messages}")
            else:
                raw_chat_id = event.chat_id
                messages = event.messages
                is_channel = False
                self.log_signal.emit(f"[调试] 普通消息删除: chat_id={raw_chat_id}, messages={messages}")
            
            chat_id_str = str(raw_chat_id)
            
            if is_channel:
                chat_id_for_db = f"-100{chat_id_str}"
                self.log_signal.emit(f"[调试] 转换频道ID: {chat_id_str} -> {chat_id_for_db}")
            else:
                chat_id_for_db = chat_id_str
            
            self.log_signal.emit(f"[调试] 处理聊天ID: {chat_id_str} (数据库格式: {chat_id_for_db}), 消息ID列表: {messages}")
            
            for message_id in messages:
                self.log_signal.emit(f"[调试] 处理消息ID: {message_id}")
                
                if (chat_id_str, message_id) in self.deleted_messages:
                    self.log_signal.emit(f"[调试] 消息 {message_id} 已在已处理列表中，跳过")
                    continue
                
                self.deleted_messages.add((chat_id_str, message_id))
                self.log_signal.emit(f"[调试] 消息 {message_id} 已添加到已处理列表")
                
                mappings = []
                
                if is_channel:
                    mappings = self.db.get_mapping_by_channel_message(raw_chat_id, message_id)
                    self.log_signal.emit(f"[调试] 使用频道消息查找方法，找到 {len(mappings)} 个映射")
                else:
                    mapping = self.db.get_mapping_by_target(chat_id_for_db, message_id)
                    if mapping:
                        mappings.append(mapping)
                        self.log_signal.emit(f"[调试] 找到目标消息映射")
                    else:
                        with sqlite3.connect(self.db.db_path) as conn:
                            conn.row_factory = sqlite3.Row
                            cursor = conn.cursor()
                            cursor.execute('''
                                SELECT * FROM message_mapping 
                                WHERE source_chat_id = ? AND source_message_id = ?
                            ''', (chat_id_for_db, message_id))
                            rows = cursor.fetchall()
                            mappings = [dict(row) for row in rows]
                            self.log_signal.emit(f"[调试] 找到 {len(mappings)} 个源消息映射")
                
                if mappings:
                    for mapping in mappings:
                        self.log_signal.emit(f"[调试] 处理映射ID: {mapping['id']}")
                        
                        source_chat_id = mapping['source_chat_id']
                        target_chat_id = mapping['target_chat_id']
                        source_message_id = mapping['source_message_id']
                        target_message_id = mapping['target_message_id']
                        
                        self.log_signal.emit(f"[调试] 映射详情: 源={source_chat_id}/{source_message_id}, 目标={target_chat_id}/{target_message_id}")
                        
                        is_source_deleted = False
                        is_target_deleted = False
                        
                        source_match = False
                        if is_channel:
                            source_chat_id_str = str(source_chat_id).lstrip('-100')
                            if source_chat_id_str == chat_id_str and source_message_id == message_id:
                                source_match = True
                        else:
                            if source_chat_id == chat_id_for_db and source_message_id == message_id:
                                source_match = True
                        
                        if source_match:
                            is_source_deleted = True
                            self.log_signal.emit(f"[调试] 检测到源消息被删除")
                        
                        target_match = False
                        if is_channel:
                            target_chat_id_str = str(target_chat_id).lstrip('-100')
                            if target_chat_id_str == chat_id_str and target_message_id == message_id:
                                target_match = True
                        else:
                            if target_chat_id == chat_id_for_db and target_message_id == message_id:
                                target_match = True
                        
                        if target_match:
                            is_target_deleted = True
                            self.log_signal.emit(f"[调试] 检测到目标消息被删除")
                        
                        if is_source_deleted:
                            await self.delete_target_message(mapping)
                            self.db.record_message_deletion(mapping['id'], chat_id_for_db, message_id, True)
                            self.log_signal.emit(f"[详细日志] ⚠ 源消息 {message_id} 被删除，已同步删除目标消息 {mapping['target_message_id']}")
                        elif is_target_deleted:
                            await self.sync_delete_source_message(mapping)
                            self.db.record_message_deletion(mapping['id'], chat_id_for_db, message_id, False)
                            self.log_signal.emit(f"[详细日志] ⚠ 目标消息 {message_id} 被删除，已同步删除源消息 {mapping['source_message_id']}")
                        else:
                            self.log_signal.emit(f"[调试] 警告: 找到映射但无法确定删除的是源消息还是目标消息")
                else:
                    self.log_signal.emit(f"[调试] 消息 {message_id} 未找到映射，忽略")
                
        except Exception as e:
            logger.exception("处理消息删除事件失败")
            self.log_signal.emit(f"[详细日志] ✗ 处理消息删除失败: {str(e)}")
            self.log_signal.emit(f"[调试] ✗ 处理消息删除事件异常: {traceback.format_exc()}")
    
    async def sync_delete_source_message(self, mapping: Dict):
        """同步删除源消息"""
        try:
            source_chat_id = mapping['source_chat_id']
            source_message_id = mapping['source_message_id']
            
            self.log_signal.emit(f"[调试] 🔄 开始同步删除源消息: {source_chat_id}/{source_message_id}")
            
            try:
                if str(source_chat_id).lstrip('-').isdigit():
                    entity_id = int(source_chat_id)
                    self.log_signal.emit(f"[调试] 转换实体ID: 字符串 {source_chat_id} -> 整数 {entity_id}")
                else:
                    entity_id = source_chat_id
                    self.log_signal.emit(f"[调试] 保持实体ID为字符串: {entity_id}")
            except Exception as e:
                self.log_signal.emit(f"[调试] 转换实体ID失败，使用原值: {source_chat_id}, 错误: {e}")
                entity_id = source_chat_id
            
            self.log_signal.emit(f"[调试] 尝试删除消息: entity={entity_id}, message_ids=[{source_message_id}]")
            
            result = await self.client.delete_messages(
                entity=entity_id,
                message_ids=[source_message_id]
            )
            
            self.log_signal.emit(f"[调试] 删除结果: {result}")
            
            self.db.delete_notifications_by_mapping_id(mapping['id'])
            self.log_signal.emit(f"[调试] 已删除映射ID {mapping['id']} 的相关通知")
            
            self.db.delete_mapping(mapping['id'])
            self.log_signal.emit(f"[调试] 已从数据库删除映射ID {mapping['id']}")
            
            self.log_signal.emit(f"[详细日志] ✓ 已同步删除源消息: {mapping['source_message_id']}")
            
            await self.send_notification_count()
            
        except Exception as e:
            logger.exception("同步删除源消息失败")
            self.log_signal.emit(f"[详细日志] ✗ 同步删除源消息失败: {str(e)}")
            self.log_signal.emit(f"[调试] ✗ 同步删除源消息异常: {traceback.format_exc()}")
    
    async def disconnect_client(self):
        """断开客户端连接"""
        if self.client and self.client.is_connected():
            try:
                await self.client.disconnect()
                self.log_signal.emit("[详细日志] ✓ 已断开 Telegram 连接")
            except Exception as e:
                logger.warning(f"断开连接时出错: {e}")
    
    async def authenticate(self):
        """处理认证流程"""
        try:
            self.log_signal.emit(f"[详细日志] 正在向 Telegram 请求验证码...")
            await self.client.send_code_request(self.config['phone'])
            self.log_signal.emit("[详细日志] → 验证码已发送到您的 Telegram")
            
            self.auth_code_signal.emit()
            while self.auth_code is None and not self.should_stop:
                await asyncio.sleep(0.1)
            
            if self.should_stop:
                return
            
            try:
                await self.client.sign_in(self.config['phone'], self.auth_code)
                self.log_signal.emit("[详细日志] ✓ 验证码验证成功")
            except SessionPasswordNeededError:
                self.log_signal.emit("[详细日志] → 需要两步验证密码")
                self.password_signal.emit()
                
                while self.password is None and not self.should_stop:
                    await asyncio.sleep(0.1)
                
                if self.should_stop:
                    return
                
                await self.client.sign_in(password=self.password)
                self.log_signal.emit("[详细日志] ✓ 两步验证密码验证成功")
        except Exception as e:
            logger.exception("认证过程中出错")
            raise
        
        self.auth_code = None
        self.password = None
    
    async def register_handlers(self):
        """注册消息处理器"""
        rules = self.config.get('rules', [])
        
        if not rules:
            self.log_signal.emit("[详细日志] ⚠ 没有配置转发规则")
            return
        
        self.log_signal.emit(f"[详细日志] ✓ 加载了 {len(rules)} 条转发规则")
        
        for i, rule in enumerate(rules):
            if rule.get('enabled', True):
                self.log_signal.emit(f"[详细日志]   规则{i+1}: {rule.get('name', f'规则{i+1}')} - {rule.get('source_name', str(rule.get('source_id', '')))} → {rule.get('target_name', str(rule.get('target_id', '')))}")
        
        @self.client.on(events.NewMessage)
        async def handler(event):
            await self.handle_new_message(event, rules)
        
        if self.enable_sync:
            @self.client.on(events.MessageEdited)
            async def edit_handler(event):
                await self.handle_message_edit(event, rules)
    
    async def handle_new_message(self, event, rules: List[dict]):
        """处理新消息"""
        try:
            message: Message = event.message
            source_id = event.chat_id
            
            message_key = (str(source_id), message.id)
            if message_key in self.processed_group_messages:
                self.log_signal.emit(f"[详细日志] ⏩ 消息 {message.id} 已处理，跳过")
                return
            
            source_topic_id = None
            if message.reply_to and message.reply_to.reply_to_msg_id:
                try:
                    replied_msg = await message.get_reply_message()
                    if replied_msg and replied_msg.id == message.reply_to.reply_to_msg_id:
                        source_topic_id = message.reply_to.reply_to_msg_id
                except Exception as e:
                    logger.debug(f"获取回复消息失败: {e}")
            
            msg_type = self.get_message_type(message)
            
            for rule in rules:
                if not rule.get('enabled', True):
                    continue
                
                if rule['source_id'] != source_id:
                    continue
                
                rule_source_topic = rule.get('source_topic_id')
                if rule_source_topic:
                    if rule_source_topic != source_topic_id:
                        continue
                
                allowed_types = rule.get('message_types', [])
                if allowed_types and msg_type not in allowed_types:
                    continue
                
                await self.send_and_record_message(message, rule, msg_type)
                
        except Exception as e:
            logger.exception("处理新消息失败")
            self.log_signal.emit(f"[详细日志] ✗ 处理新消息失败: {str(e)}")
    
    async def send_and_record_message(self, message: Message, rule: dict, msg_type: str):
        """发送消息并记录到数据库"""
        try:
            target_id = rule['target_id']
            target_topic_id = rule.get('target_topic_id')
            
            kwargs = {}
            if target_topic_id:
                kwargs['reply_to'] = target_topic_id
            
            file_id = self.get_file_id(message)
            text_content = message.text or ""
            has_webpage = isinstance(message.media, MessageMediaWebPage)
            webpage_url = None
            
            if has_webpage and message.media.webpage:
                webpage_url = message.media.webpage.url
            
            sent_messages = []
            
            # 检查是否为群组消息中的一条
            if hasattr(message, 'grouped_id') and message.grouped_id:
                message_key = (str(message.chat_id), message.id)
                self.processed_group_messages.add(message_key)
                
                group_key = f"{message.chat_id}_{message.grouped_id}_{rule['source_id']}"
                if group_key in self.current_group_processing:
                    self.log_signal.emit(f"[详细日志] ⏩ 群组消息 {message.grouped_id} 正在处理中，跳过")
                    return
                
                self.log_signal.emit(f"[详细日志] 🔍 检测到群组消息，群组ID: {message.grouped_id}")
                
                self.current_group_processing[group_key] = {
                    'rule': rule,
                    'msg_type': msg_type,
                    'processing': True
                }
                
                group_messages = []
                async for group_msg in self.client.iter_messages(
                    entity=message.chat_id,
                    min_id=message.id-10,
                    max_id=message.id+10
                ):
                    if hasattr(group_msg, 'grouped_id') and group_msg.grouped_id == message.grouped_id:
                        group_messages.append(group_msg)
                        group_msg_key = (str(message.chat_id), group_msg.id)
                        self.processed_group_messages.add(group_msg_key)
                
                self.log_signal.emit(f"[详细日志] 📦 找到群组中的 {len(group_messages)} 条消息")
                
                group_messages.sort(key=lambda x: x.id)
                
                supported_group_types = [MessageType.PHOTO.value, MessageType.VIDEO.value, 
                                       MessageType.DOCUMENT.value, MessageType.AUDIO.value]
                filtered_group_messages = [msg for msg in group_messages 
                                         if self.get_message_type(msg) in supported_group_types]
                
                if len(filtered_group_messages) > 1:
                    self.log_signal.emit(f"[详细日志] 📤 开始合并转发 {len(filtered_group_messages)} 个文件")
                    sent_messages = await self.send_grouped_messages(filtered_group_messages, target_id, kwargs, rule)
                    
                    if isinstance(sent_messages, list) and len(sent_messages) > 0:
                        self.log_signal.emit(f"[详细日志] 📤 合并发送完成，发送了 {len(sent_messages)} 条消息")
                        
                        rule_id = rule.get('rule_id', self.config['rules'].index(rule))
                        
                        for i, source_msg in enumerate(filtered_group_messages):
                            target_msg_id = sent_messages[0].id if i == 0 else sent_messages[0].id + i
                            
                            if i < len(sent_messages):
                                target_msg_id = sent_messages[i].id
                            else:
                                target_msg_id = sent_messages[0].id + i
                            
                            # 获取使用的 API 类型
                            api_type = 'user'
                            bot_message_data = None
                            
                            mapping_id = self.db.add_message_mapping(
                                rule_id=rule_id,
                                source_chat_id=source_msg.chat_id,
                                source_message_id=source_msg.id,
                                source_topic_id=source_msg.reply_to.reply_to_msg_id if source_msg.reply_to else None,
                                target_chat_id=target_id,
                                target_message_id=target_msg_id,
                                target_topic_id=target_topic_id,
                                message_type=self.get_message_type(source_msg),
                                file_id=self.get_file_id(source_msg),
                                text_content=source_msg.text or "",
                                has_webpage=isinstance(source_msg.media, MessageMediaWebPage),
                                webpage_url=webpage_url if i == 0 else None,
                                grouped_id=str(message.grouped_id),
                                is_grouped=True,
                                group_index=i,
                                api_type=api_type,
                                bot_message_data=bot_message_data
                            )
                            
                            self.log_signal.emit(f"[调试] 💾 已保存群组消息映射 {i+1}/{len(filtered_group_messages)}: "
                                               f"映射ID={mapping_id}, 源消息={source_msg.chat_id}/{source_msg.id}, "
                                               f"目标消息={target_id}/{target_msg_id}, API类型={api_type}")
                else:
                    sent_msg = await self.send_hybrid_message(message, target_id, kwargs, rule)
                    sent_messages = [sent_msg]
                
                del self.current_group_processing[group_key]
                
            else:
                sent_msg = await self.send_hybrid_message(message, target_id, kwargs, rule)
                sent_messages = [sent_msg] if sent_msg else []
            
            # 修复：检查 sent_messages 是否为空，避免 AttributeError
            if not sent_messages:
                self.log_signal.emit(f"[详细日志] ⚠ 消息发送失败，跳过记录")
                return
            
            # 记录非群组消息到数据库
            if not hasattr(message, 'grouped_id') or not message.grouped_id or len(sent_messages) <= 1:
                rule_id = rule.get('rule_id', self.config['rules'].index(rule))
                
                for i, sent_msg in enumerate(sent_messages):
                    # 修复：检查 sent_msg 是否为 None
                    if sent_msg is None:
                        self.log_signal.emit(f"[详细日志] ⚠ 第 {i+1} 条消息发送失败，跳过记录")
                        continue
                        
                    mapping_id = self.db.add_message_mapping(
                        rule_id=rule_id,
                        source_chat_id=message.chat_id,
                        source_message_id=message.id if i == 0 else message.id + i,
                        source_topic_id=message.reply_to.reply_to_msg_id if message.reply_to else None,
                        target_chat_id=target_id,
                        target_message_id=sent_msg.id if hasattr(sent_msg, 'id') else sent_msg.get('message_id'),
                        target_topic_id=target_topic_id,
                        message_type=msg_type,
                        file_id=file_id,
                        text_content=text_content,
                        has_webpage=has_webpage,
                        webpage_url=webpage_url,
                        grouped_id=None,
                        is_grouped=False,
                        group_index=None,
                        api_type='user',  # 默认，实际会在发送时更新
                        bot_message_data=None
                    )
                    
                    self.log_signal.emit(f"[调试] 💾 已保存消息映射: 映射ID={mapping_id}, "
                                       f"源消息={message.chat_id}/{message.id}, "
                                       f"目标消息={target_id}/{sent_msg.id if hasattr(sent_msg, 'id') else sent_msg.get('message_id')}")
            
            source_name = rule.get('source_name', str(rule['source_id']))
            target_name = rule.get('target_name', str(target_id))
            
            log_msg = f"✓ [{source_name}] → [{target_name}] {msg_type}"
            if hasattr(message, 'grouped_id') and message.grouped_id:
                group_count = len([m for m in self.processed_group_messages 
                                 if m[0] == str(message.chat_id) and 
                                 any(gm.grouped_id == message.grouped_id 
                                     for gm in await self.get_grouped_messages(message.chat_id, message.grouped_id) 
                                     if hasattr(gm, 'grouped_id'))])
                log_msg += f" ({group_count}个文件合并发送)"
            if target_topic_id:
                log_msg += f" (→主题:{target_topic_id})"
            
            self.log_signal.emit(log_msg)
            
        except FloodWaitError as e:
            self.log_signal.emit(f"[详细日志] ⚠ 触发限流,等待 {e.seconds} 秒...")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.exception("发送消息失败")
            self.log_signal.emit(f"[详细日志] ✗ 发送失败: {str(e)}")
    
    async def get_grouped_messages(self, chat_id, grouped_id):
        """获取指定群组的所有消息"""
        messages = []
        async for msg in self.client.iter_messages(
            entity=chat_id,
            limit=20
        ):
            if hasattr(msg, 'grouped_id') and msg.grouped_id == grouped_id:
                messages.append(msg)
        return messages
    
    async def send_hybrid_message(self, message: Message, target_id: Union[str, int], 
                                 kwargs: dict, rule: dict) -> Union[Message, Dict, None]:
        """智能选择发送方式：Bot API 或用户 API"""
        msg_type = self.get_message_type(message)
        
        # 判断是否使用 Bot API
        use_bot = False
        bot_reason = ""
        
        if (self.use_bot_api and self.bot_manager and self.bot_manager.is_available):
            if msg_type == MessageType.TEXT.value and self.bot_api_for_text:
                use_bot = True
                bot_reason = "文本消息"
            elif msg_type in [MessageType.PHOTO.value, MessageType.VIDEO.value, 
                             MessageType.DOCUMENT.value, MessageType.AUDIO.value]:
                if self.bot_api_for_media:
                    use_bot = True
                    bot_reason = "媒体消息"
            elif msg_type == MessageType.STICKER.value:
                # 贴纸使用用户 API，Bot API 对贴纸支持有限
                use_bot = False
                bot_reason = "贴纸消息使用用户 API"
        
        if use_bot:
            try:
                self.log_signal.emit(f"[详细日志] 🤖 使用 Bot API 发送 {bot_reason}")
                result = await self.send_with_bot_api(message, target_id, kwargs)
                
                # 如果是 Bot API 返回的结果，转换为类似 Message 的对象
                if isinstance(result, dict):
                    class BotMessage:
                        def __init__(self, bot_result):
                            self.id = bot_result.get('message_id')
                            self.chat_id = target_id
                            self.text = message.text or ""
                    
                    sent_msg = BotMessage(result)
                    # 记录使用的 API 类型
                    self.log_signal.emit(f"[详细日志] ✅ Bot API 发送成功，消息ID: {sent_msg.id}")
                    return sent_msg
                else:
                    return result
                    
            except Exception as e:
                self.log_signal.emit(f"[详细日志] ⚠ Bot API 发送失败: {str(e)}")
                if self.bot_api_fallback:
                    self.log_signal.emit(f"[详细日志] ↪ 回退到用户 API")
                    return await self.send_with_user_api(message, target_id, kwargs)
                else:
                    raise
        else:
            self.log_signal.emit(f"[详细日志] 👤 使用用户 API 发送 {msg_type}")
            return await self.send_with_user_api(message, target_id, kwargs)
    
    async def send_with_bot_api(self, message: Message, target_id: Union[str, int], kwargs: dict) -> Union[Dict, None]:
        """使用 Bot API 发送消息"""
        try:
            reply_to_message_id = kwargs.get('reply_to')
            msg_type = self.get_message_type(message)
            
            if msg_type == MessageType.TEXT.value or msg_type == MessageType.WEBPAGE.value:
                # 发送文本消息或带网页链接的消息
                return await self.bot_manager.send_message(
                    chat_id=target_id,
                    text=message.text or "",
                    reply_to_message_id=reply_to_message_id,
                    disable_web_page_preview=not isinstance(message.media, MessageMediaWebPage)
                )
            
            elif msg_type == MessageType.PHOTO.value:
                # 发送图片
                if message.media and hasattr(message.media, 'photo'):
                    # 需要先获取文件并上传，这里简化处理
                    # 实际应该下载文件后上传
                    file = await message.download_media(file=bytes)
                    # 这里需要实际的文件上传逻辑
                    # 暂时回退到用户 API
                    raise Exception("Bot API 图片上传需要额外实现")
            
            elif msg_type == MessageType.VIDEO.value:
                # 发送视频
                raise Exception("Bot API 视频上传需要额外实现")
            
            elif msg_type == MessageType.DOCUMENT.value:
                # 发送文档
                raise Exception("Bot API 文档上传需要额外实现")
            
            elif msg_type == MessageType.AUDIO.value:
                # 发送音频
                raise Exception("Bot API 音频上传需要额外实现")
            
            else:
                # 其他类型回退到用户 API
                raise Exception(f"Bot API 不支持的消息类型: {msg_type}")
                
        except Exception as e:
            logger.exception("Bot API 发送失败")
            raise
    
    async def send_with_user_api(self, message: Message, target_id: Union[str, int], kwargs: dict) -> Union[Message, None]:
        """使用用户 API 发送消息"""
        try:
            # 特殊处理：带网页预览的消息
            if isinstance(message.media, MessageMediaWebPage):
                if message.text:
                    # 读取原消息的 invert_media 属性
                    invert_media = getattr(message, 'invert_media', False)
                    
                    # 方案：使用高级API的formatting_entities参数
                    # 这能正确保留格式，但可能无法设置invert_media
                    try:
                        # 使用 send_message 并传递 formatting_entities
                        sent_msg = await self.client.send_message(
                            target_id,
                            message.message,  # 使用原始文本
                            formatting_entities=message.entities,  # 保留格式
                            link_preview=True,  # 允许网页预览
                            **kwargs
                        )
                        
                        # 如果需要设置invert_media，尝试编辑消息
                        if invert_media and sent_msg:
                            try:
                                # 尝试编辑消息来设置invert_media
                                await self.client(functions.messages.EditMessageRequest(
                                    peer=await self.client.get_input_entity(target_id),
                                    id=sent_msg.id,
                                    message=message.message,
                                    entities=message.entities if message.entities else [],
                                    no_webpage=False,
                                    invert_media=invert_media
                                ))
                                self.log_signal.emit(
                                    f"[API日志] 👤 用户API发送成功并设置预览位置 "
                                    f"(预览位置: 上方, 格式已保留)"
                                )
                            except Exception as e:
                                # 编辑失败，但消息已发送，只是预览位置可能不对
                                self.log_signal.emit(
                                    f"[API日志] 👤 用户API发送成功但无法设置预览位置 "
                                    f"(预览位置: 默认, 格式已保留) - {str(e)}"
                                )
                        else:
                            self.log_signal.emit(
                                f"[API日志] 👤 用户API发送成功 "
                                f"(预览位置: 下方, 格式已保留)"
                            )
                        
                        return sent_msg
                        
                    except Exception as e:
                        self.log_signal.emit(f"[API日志] ⚠ formatting_entities方法失败: {str(e)}")
                        # 回退到简单方法
                        sent_msg = await self.client.send_message(
                            target_id,
                            message.text,
                            link_preview=True,
                            **kwargs
                        )
                        self.log_signal.emit(f"[API日志] 👤 用户API发送成功（简化模式）")
                        return sent_msg
                else:
                    self.log_signal.emit(f"[API日志] ⚠ 忽略无文本的网页链接消息")
                    return None
            elif message.media:
                sent_msg = await self.client.send_file(
                    target_id,
                    message.media,
                    caption=message.text or "",
                    **kwargs
                )
                self.log_signal.emit(f"[API日志] 👤 用户API发送媒体消息成功")
                return sent_msg
            elif message.text:
                sent_msg = await self.client.send_message(
                    target_id,
                    message.text,
                    **kwargs
                )
                self.log_signal.emit(f"[API日志] 👤 用户API发送文本消息成功")
                return sent_msg
            else:
                self.log_signal.emit(f"[API日志] ⚠ 忽略不支持的消息类型")
                return None
        except Exception as e:
            logger.exception("用户 API 发送失败")
            self.log_signal.emit(f"[API日志] ✗ 用户API发送失败: {str(e)}")
            raise
    
    async def send_grouped_messages(self, group_messages: List[Message], target_id: Union[str, int], 
                                   kwargs: dict, rule: dict):
        """发送合并的消息群组"""
        try:
            # 判断是否使用 Bot API 发送媒体组
            use_bot = (self.use_bot_api and self.bot_manager and self.bot_manager.is_available 
                      and self.bot_api_for_media)
            
            if use_bot:
                try:
                    result = await self.send_grouped_with_bot_api(group_messages, target_id, kwargs)
                    self.log_signal.emit(f"[API日志] 🤖 BotAPI发送媒体组成功")
                    return result
                except Exception as e:
                    self.log_signal.emit(f"[详细日志] ⚠ Bot API 媒体组发送失败: {str(e)}")
                    if self.bot_api_fallback:
                        self.log_signal.emit(f"[详细日志] ↪ 回退到用户 API 发送媒体组")
                    else:
                        raise
            
            # 使用用户 API 发送
            media_list = []
            caption = ""
            
            for i, msg in enumerate(group_messages):
                if msg.media:
                    media_list.append(msg.media)
                    if i == 0 and msg.text:
                        caption = msg.text
            
            if not media_list:
                raise ValueError("群组中没有找到媒体文件")
            
            self.log_signal.emit(f"[详细日志] 📤 正在发送 {len(media_list)} 个合并文件...")
            
            result = await self.client.send_file(
                target_id,
                media_list,
                caption=caption or "",
                **kwargs
            )
            
            self.log_signal.emit(f"[API日志] 👤 用户API发送媒体组成功")
            
            if not isinstance(result, list):
                result = [result]
            
            return result
            
        except Exception as e:
            logger.exception("发送合并消息失败")
            self.log_signal.emit(f"[详细日志] ✗ 发送合并消息失败: {str(e)}")
            raise
    
    async def send_grouped_with_bot_api(self, group_messages: List[Message], target_id: Union[str, int], 
                                       kwargs: dict):
        """使用 Bot API 发送媒体组"""
        # 这里需要实现 Bot API 的媒体组发送
        # 需要下载所有文件并创建 media 参数
        # 由于实现较复杂，暂时回退到用户 API
        raise Exception("Bot API 媒体组发送需要额外实现")
    
    async def handle_message_edit(self, event, rules: List[dict]):
        """处理消息编辑"""
        try:
            message: Message = event.message
            source_id = event.chat_id
            
            for rule in rules:
                if not rule.get('enabled', True) or rule['source_id'] != source_id:
                    continue
                
                rule_source_topic = rule.get('source_topic_id')
                if rule_source_topic:
                    pass
                
                rule_id = rule.get('rule_id', self.config['rules'].index(rule))
                mapping = self.db.get_mapping_by_source(str(source_id), message.id, rule_id)
                
                if not mapping:
                    continue
                
                await self.sync_message_edit(message, mapping, rule)
                
        except Exception as e:
            logger.exception("处理消息编辑失败")
            self.log_signal.emit(f"[详细日志] ✗ 处理消息编辑失败: {str(e)}")
    
    async def sync_message_edit(self, message: Message, mapping: Dict, rule: dict):
        """同步消息编辑"""
        old_text = mapping.get('text_content')
        new_text = message.text or ""
        old_file_id = mapping.get('file_id')
        new_file_id = self.get_file_id(message)
        
        msg_type = self.get_message_type(message)
        mapping_id = mapping['id']
        
        edit_type = self.determine_edit_type(old_text, new_text, old_file_id, new_file_id, msg_type)
        
        self.db.record_edit_history(
            mapping_id=mapping_id,
            old_text=old_text,
            new_text=new_text,
            old_file_id=old_file_id,
            new_file_id=new_file_id,
            edit_type=edit_type
        )
        
        if edit_type in ['text', 'text_only']:
            # 使用适当的 API 编辑消息
            api_type = mapping.get('api_type', 'user')
            self.log_signal.emit(f"[API日志] 🔧 使用{api_type}API编辑文本消息")
            await self.edit_target_message(mapping, new_text, message)
            self.db.update_message_mapping(mapping_id, text_content=new_text)
            
        elif edit_type in ['file_added_to_text', 'file_changed', 'file_removed', 'webpage_changed']:
            notification_data = await self.handle_special_edit_case(edit_type, mapping, message, old_file_id, new_file_id)
            if notification_data:
                self.edit_notification_signal.emit(notification_data)
                await self.send_notification_count()
            
        elif edit_type == 'both':
            if mapping['message_type'] == MessageType.TEXT.value:
                notification_data = await self.handle_special_edit_case('file_added_to_text', mapping, message, old_file_id, new_file_id)
                if notification_data:
                    self.edit_notification_signal.emit(notification_data)
                    await self.send_notification_count()
            else:
                api_type = mapping.get('api_type', 'user')
                self.log_signal.emit(f"[API日志] 🔧 使用{api_type}API编辑媒体消息")
                await self.edit_target_message(mapping, new_text, message)
                self.db.update_message_mapping(mapping_id, text_content=new_text)
    
    async def edit_target_message(self, mapping: Dict, new_text: str, source_message: Message):
        """编辑目标消息"""
        try:
            target_chat_id = mapping['target_chat_id']
            target_message_id = mapping['target_message_id']
            
            # 判断是否使用 Bot API 编辑
            use_bot = (self.use_bot_api and self.bot_manager and self.bot_manager.is_available 
                      and self.bot_api_for_edit and mapping.get('api_type') == 'bot')
            
            if use_bot:
                try:
                    if mapping['message_type'] == MessageType.TEXT.value or mapping['message_type'] == MessageType.WEBPAGE.value:
                        result = await self.bot_manager.edit_message_text(
                            chat_id=target_chat_id,
                            message_id=target_message_id,
                            text=new_text,
                            disable_web_page_preview=not isinstance(source_message.media, MessageMediaWebPage)
                        )
                        self.log_signal.emit(f"[API日志] 🤖 BotAPI编辑文本消息成功")
                    else:
                        # 编辑媒体消息的说明
                        result = await self.bot_manager.edit_message_caption(
                            chat_id=target_chat_id,
                            message_id=target_message_id,
                            caption=new_text
                        )
                        self.log_signal.emit(f"[API日志] 🤖 BotAPI编辑媒体消息说明成功")
                    self.log_signal.emit(f"[详细日志] 🤖 使用 Bot API 编辑消息: {mapping['source_message_id']} → {target_message_id}")
                    return
                except Exception as e:
                    self.log_signal.emit(f"[详细日志] ⚠ Bot API 编辑失败: {str(e)}")
                    if not self.bot_api_fallback:
                        raise
            
            # 使用用户 API 编辑
            try:
                if str(target_chat_id).lstrip('-').isdigit():
                    entity_id = int(target_chat_id)
                else:
                    entity_id = target_chat_id
            except:
                entity_id = target_chat_id
            
            target_msg = await self.client.get_messages(
                entity=entity_id,
                ids=target_message_id
            )
            
            if not target_msg:
                self.log_signal.emit(f"[详细日志] ⚠ 目标消息不存在，无法编辑")
                return
            
            # 获取源消息的原始文本（带格式标记）
            # message.message 和 message.text 可能不同
            raw_message_text = source_message.message if hasattr(source_message, 'message') else source_message.text
            formatted_text = source_message.text if hasattr(source_message, 'text') else ""
            
            self.log_signal.emit(f"[调试] 🔍 原始消息文本长度: {len(raw_message_text) if raw_message_text else 0}")
            self.log_signal.emit(f"[调试] 🔍 格式化文本长度: {len(formatted_text) if formatted_text else 0}")
            
            # 调试：显示原始文本的一部分（避免太长）
            if raw_message_text:
                sample = raw_message_text[:200] + "..." if len(raw_message_text) > 200 else raw_message_text
                self.log_signal.emit(f"[调试] 🔍 原始文本示例: {sample}")
            
            # 检查是否是带网页预览的消息
            is_webpage_message = isinstance(source_message.media, MessageMediaWebPage)
            invert_media = getattr(source_message, 'invert_media', False)
            
            self.log_signal.emit(f"[调试] 🔧 编辑参数: 网页预览={is_webpage_message}, invert_media={invert_media}")
            
            # 关键修改：使用与转发相同的逻辑
            # 对于带网页预览的消息，使用转发消息时的成功方法
            if is_webpage_message:
                try:
                    # 方法1：尝试使用高级API，传递formatting_entities
                    source_entities = source_message.entities if hasattr(source_message, 'entities') else []
                    
                    # 获取peer对象
                    peer = await self.client.get_input_entity(entity_id)
                    
                    # 同时设置所有参数
                    await self.client(functions.messages.EditMessageRequest(
                        peer=peer,
                        id=target_message_id,
                        message=raw_message_text,  # 使用原始消息文本
                        entities=source_entities,
                        no_webpage=False,
                        invert_media=invert_media
                    ))
                    
                    self.log_signal.emit(f"[API日志] 👤 用户API编辑成功 (带网页预览，使用原始文本)")
                    self.log_signal.emit(f"[详细日志] ✓ 已同步编辑消息: {mapping['source_message_id']} → {target_message_id}")
                    return
                    
                except Exception as error1:
                    self.log_signal.emit(f"[调试] ⚠ 方法1失败: {str(error1)}")
                    
                    # 方法2：尝试另一种方式 - 使用高级API的edit_message
                    try:
                        await self.client.edit_message(
                            entity=entity_id,
                            message=target_message_id,
                            text=raw_message_text,  # 使用原始文本
                            formatting_entities=source_entities,
                            link_preview=True,
                            parse_mode=None
                        )
                        
                        # 如果需要设置invert_media
                        if invert_media:
                            try:
                                await self.client(functions.messages.EditMessageRequest(
                                    peer=peer,
                                    id=target_message_id,
                                    invert_media=True
                                ))
                            except:
                                pass
                        
                        self.log_signal.emit(f"[API日志] 👤 用户API编辑成功 (高级API方法)")
                        self.log_signal.emit(f"[详细日志] ✓ 已同步编辑消息: {mapping['source_message_id']} → {target_message_id}")
                        return
                        
                    except Exception as error2:
                        self.log_signal.emit(f"[调试] ⚠ 方法2失败: {str(error2)}")
            
            # 对于普通消息
            try:
                source_entities = source_message.entities if hasattr(source_message, 'entities') else []
                
                # 先尝试使用高级API
                await self.client.edit_message(
                    entity=entity_id,
                    message=target_message_id,
                    text=raw_message_text,  # 使用原始文本
                    formatting_entities=source_entities,
                    link_preview=False,
                    parse_mode=None
                )
                
                self.log_signal.emit(f"[API日志] 👤 用户API编辑成功 (普通消息)")
                self.log_signal.emit(f"[详细日志] ✓ 已同步编辑消息: {mapping['source_message_id']} → {target_message_id}")
                
            except Exception as edit_error:
                self.log_signal.emit(f"[调试] ⚠ 编辑失败: {str(edit_error)}")
                
                # 最后的尝试：使用低级API
                try:
                    peer = await self.client.get_input_entity(entity_id)
                    
                    await self.client(functions.messages.EditMessageRequest(
                        peer=peer,
                        id=target_message_id,
                        message=raw_message_text,
                        entities=source_entities or [],
                        no_webpage=True,
                        invert_media=False
                    ))
                    
                    self.log_signal.emit(f"[API日志] 👤 用户API编辑成功 (低级API回退)")
                    self.log_signal.emit(f"[详细日志] ✓ 已同步编辑消息: {mapping['source_message_id']} → {target_message_id}")
                    
                except Exception as final_error:
                    self.log_signal.emit(f"[调试] ✗ 所有方法都失败: {str(final_error)}")
                    raise
        
        except MessageNotModifiedError:
            self.log_signal.emit(f"[详细日志] ⚠ 消息内容未更改")
        except MessageIdInvalidError:
            self.log_signal.emit(f"[详细日志] ⚠ 目标消息已被删除")
        except Exception as e:
            logger.exception("编辑目标消息失败")
            self.log_signal.emit(f"[详细日志] ✗ 编辑目标消息失败: {str(e)}")
    
    async def delete_target_message(self, mapping: Dict):
        """删除目标消息"""
        try:
            target_chat_id = mapping['target_chat_id']
            target_message_id = mapping['target_message_id']
            
            self.log_signal.emit(f"[调试] 🔄 开始删除目标消息: {target_chat_id}/{target_message_id}")
            
            # 判断是否使用 Bot API 删除
            use_bot = (self.use_bot_api and self.bot_manager and self.bot_manager.is_available 
                      and self.bot_api_for_delete and mapping.get('api_type') == 'bot')
            
            if use_bot:
                try:
                    await self.bot_manager.delete_message(
                        chat_id=target_chat_id,
                        message_id=target_message_id
                    )
                    self.log_signal.emit(f"[API日志] 🤖 BotAPI删除消息成功")
                    self.log_signal.emit(f"[详细日志] 🤖 使用 Bot API 删除目标消息: {target_message_id}")
                except Exception as e:
                    self.log_signal.emit(f"[详细日志] ⚠ Bot API 删除失败: {str(e)}")
                    if not self.bot_api_fallback:
                        raise
            
            # 使用用户 API 删除
            try:
                if str(target_chat_id).lstrip('-').isdigit():
                    entity_id = int(target_chat_id)
                    self.log_signal.emit(f"[调试] 转换实体ID: 字符串 {target_chat_id} -> 整数 {entity_id}")
                else:
                    entity_id = target_chat_id
                    self.log_signal.emit(f"[调试] 保持实体ID为字符串: {entity_id}")
            except Exception as e:
                self.log_signal.emit(f"[调试] 转换实体ID失败，使用原值: {target_chat_id}, 错误: {e}")
                entity_id = target_chat_id
            
            self.log_signal.emit(f"[调试] 尝试删除消息: entity={entity_id}, message_ids=[{target_message_id}]")
            
            await self.client.delete_messages(
                entity=entity_id,
                message_ids=[target_message_id]
            )
            
            self.log_signal.emit(f"[API日志] 👤 用户API删除消息成功")
            
            self.db.delete_notifications_by_mapping_id(mapping['id'])
            self.log_signal.emit(f"[调试] 已删除映射ID {mapping['id']} 的相关通知")
            
            self.db.delete_mapping(mapping['id'])
            self.log_signal.emit(f"[调试] 已从数据库删除映射ID {mapping['id']}")
            
            self.log_signal.emit(f"[详细日志] ✓ 已同步删除目标消息: {mapping['target_message_id']}")
            
            await self.send_notification_count()
            
        except Exception as e:
            logger.exception("删除目标消息失败")
            self.log_signal.emit(f"[详细日志] ✗ 删除目标消息失败: {str(e)}")
            self.log_signal.emit(f"[调试] ✗ 删除目标消息异常: {traceback.format_exc()}")
    
    async def handle_special_edit_case(self, edit_type: str, mapping: Dict, message: Message, 
                                     old_file_id: Optional[str], new_file_id: Optional[str]) -> Optional[Dict]:
        """处理特殊编辑情况（记录日志和通知）"""
        try:
            source_name = mapping.get('source_chat_id', '未知')
            msg_type = self.get_message_type(message)
            
            notifications = {
                'file_added_to_text': f"纯文本消息添加了{msg_type}文件",
                'file_changed': f"{msg_type}文件被替换",
                'file_removed': f"{msg_type}文件被删除",
                'webpage_changed': "网页链接被更改"
            }
            
            if edit_type in notifications:
                notification_msg = f"消息 {mapping['source_message_id']} ({source_name}): {notifications[edit_type]}"
                self.log_signal.emit(f"[详细日志] ⚠ {notification_msg}")
                
                notification_id = self.db.add_edit_notification(
                    mapping_id=mapping['id'],
                    notification_type=edit_type,
                    description=notification_msg,
                    source_chat_id=mapping['source_chat_id'],
                    source_message_id=mapping['source_message_id'],
                    source_topic_id=mapping.get('source_topic_id'),
                    target_chat_id=mapping['target_chat_id'],
                    target_message_id=mapping['target_message_id'],
                    target_topic_id=mapping.get('target_topic_id')
                )
                
                if self.config.get('show_tray_notifications', True):
                    self.notification_signal.emit("消息变更通知", notification_msg)
                
                return {
                    'id': notification_id,
                    'mapping_id': mapping['id'],
                    'type': edit_type,
                    'description': notification_msg,
                    'source_chat_id': mapping['source_chat_id'],
                    'source_message_id': mapping['source_message_id'],
                    'source_topic_id': mapping.get('source_topic_id'),
                    'target_chat_id': mapping['target_chat_id'],
                    'target_message_id': mapping['target_message_id'],
                    'target_topic_id': mapping.get('target_topic_id')
                }
            
            return None
        except Exception as e:
            logger.exception("处理特殊编辑情况失败")
            self.log_signal.emit(f"[详细日志] ✗ 处理特殊编辑情况失败: {str(e)}")
            return None
    
    def determine_edit_type(self, old_text: Optional[str], new_text: Optional[str],
                           old_file_id: Optional[str], new_file_id: Optional[str],
                           msg_type: str) -> str:
        """确定编辑类型"""
        text_changed = old_text != new_text
        file_changed = old_file_id != new_file_id
        
        if text_changed and not file_changed:
            return 'text' if old_file_id else 'text_only'
        elif not text_changed and file_changed:
            if old_file_id and new_file_id:
                return 'file_changed'
            elif old_file_id and not new_file_id:
                return 'file_removed'
            elif not old_file_id and new_file_id:
                return 'file_added_to_text'
        elif text_changed and file_changed:
            return 'both'
        
        if msg_type == MessageType.WEBPAGE.value and text_changed:
            return 'webpage_changed'
        
        return 'unknown'
    
    @staticmethod
    def get_file_id(message: Message) -> Optional[str]:
        """获取文件ID"""
        if message.media:
            if hasattr(message.media, 'document'):
                if message.media.document:
                    return str(message.media.document.id)
            elif hasattr(message.media, 'photo'):
                if message.media.photo:
                    return str(message.media.photo.id)
        return None
    
    @staticmethod
    def get_message_type(message: Message) -> str:
        """获取消息类型"""
        # 重要：先检查贴纸，避免被识别为文件
        if message.sticker:
            return MessageType.STICKER.value
        
        # 重要：再检查网页链接，避免被识别为图片
        if isinstance(message.media, MessageMediaWebPage):
            return MessageType.WEBPAGE.value
        
        # 然后检查其他媒体类型
        if message.photo:
            return MessageType.PHOTO.value
        elif message.voice:
            return MessageType.VOICE.value
        elif message.video:
            return MessageType.VIDEO.value
        elif message.document and not any([message.voice, message.video, message.audio]):
            return MessageType.DOCUMENT.value
        elif message.audio:
            return MessageType.AUDIO.value
        elif isinstance(message.media, MessageMediaContact):
            return MessageType.CONTACT.value
        elif isinstance(message.media, MessageMediaGeo):
            return MessageType.GEO.value
        elif isinstance(message.media, MessageMediaVenue):
            return MessageType.VENUE.value
        elif isinstance(message.media, MessageMediaGame):
            return MessageType.GAME.value
        elif isinstance(message.media, MessageMediaInvoice):
            return MessageType.INVOICE.value
        elif isinstance(message.media, MessageMediaPoll):
            return MessageType.POLL.value
        elif isinstance(message.media, MessageMediaDice):
            return MessageType.DICE.value
        elif message.text:
            return MessageType.TEXT.value
        else:
            return MessageType.OTHER.value


class ModernButton(QPushButton):
    """现代化按钮"""
    def __init__(self, text, primary=False):
        super().__init__(text)
        self.primary = primary
        self.setMinimumHeight(46)
        self.setCursor(Qt.PointingHandCursor)
        
        font = QFont()
        font.setPointSize(11)
        font.setWeight(QFont.Medium)
        self.setFont(font)


class CustomMessageBox(QMessageBox):
    """自定义消息框，支持主题"""
    def __init__(self, parent=None, theme="dark"):
        super().__init__(parent)
        self.theme = theme
        
    def apply_theme(self):
        """应用主题"""
        if self.theme == "dark":
            self.setStyleSheet("""
                QMessageBox {
                    background-color: #1E1E1E;
                    border: 1px solid #353535;
                    border-radius: 12px;
                    padding: 8px;
                }
                QMessageBox QLabel {
                    color: #E0E0E0;
                    font-size: 14px;
                    padding: 4px 8px;
                }
                QMessageBox QPushButton {
                    background-color: #333333;
                    color: #E0E0E0;
                    border: 1px solid #454545;
                    padding: 10px 24px;
                    border-radius: 8px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QMessageBox QPushButton:hover {
                    background-color: #444444;
                    border-color: #555555;
                }
                QMessageBox QPushButton:pressed {
                    background-color: #2D2D2D;
                }
            """)
        else:
            self.setStyleSheet("""
                QMessageBox {
                    background-color: #FFFFFF;
                    border: 1px solid #DDDDDD;
                    border-radius: 12px;
                    padding: 8px;
                }
                QMessageBox QLabel {
                    color: #000000;
                    font-size: 14px;
                    padding: 4px 8px;
                }
                QMessageBox QPushButton {
                    background-color: #F0F0F0;
                    color: #333333;
                    border: 1px solid #CCCCCC;
                    padding: 10px 24px;
                    border-radius: 8px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QMessageBox QPushButton:hover {
                    background-color: #E4E7ED;
                    border-color: #C0C4CC;
                }
                QMessageBox QPushButton:pressed {
                    background-color: #E8E8E8;
                }
            """)


class NotificationsDialog(QDialog):
    """通知管理对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.db = Database()
        self.selected_notifications = []
        self.init_ui()
        self.load_notifications()
        
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("编辑通知管理")
        self.setMinimumSize(1200, 700)
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(30, 30, 30, 30)
        
        title_label = QLabel("📝 编辑通知管理")
        title_label.setStyleSheet("font-weight: 600; font-size: 22px; color: #2c3e50; margin-left: 4px;")
        main_layout.addWidget(title_label)
        
        description = QLabel("以下是需要手动处理的消息变更。请复制链接查看消息，处理完成后点击标记为已处理按钮。")
        description.setStyleSheet("color: #606266; font-size: 14px; margin-left: 4px;")
        description.setWordWrap(True)
        main_layout.addWidget(description)
        
        self.notifications_table = QTableWidget()
        self.notifications_table.setColumnCount(6)
        self.notifications_table.setHorizontalHeaderLabels([
            "", "ID", "变更类型", "描述", "创建时间", "状态"
        ])
        
        self.notifications_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.notifications_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.notifications_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.notifications_table.itemSelectionChanged.connect(self.on_selection_changed)
        main_layout.addWidget(self.notifications_table)
        
        top_button_layout = QHBoxLayout()
        top_button_layout.setSpacing(15)
        
        refresh_btn = ModernButton("🔄 刷新")
        refresh_btn.clicked.connect(self.load_notifications)
        
        mark_all_btn = ModernButton("✅ 全部标记为已处理")
        mark_all_btn.clicked.connect(self.mark_all_resolved)
        
        clear_resolved_btn = ModernButton("🗑️ 清空已处理")
        clear_resolved_btn.clicked.connect(self.clear_resolved)
        
        top_button_layout.addWidget(refresh_btn)
        top_button_layout.addWidget(mark_all_btn)
        top_button_layout.addWidget(clear_resolved_btn)
        top_button_layout.addStretch()
        
        main_layout.addLayout(top_button_layout)
        
        bottom_button_layout = QHBoxLayout()
        bottom_button_layout.setSpacing(15)
        
        copy_source_btn = ModernButton("📋 复制源消息链接")
        copy_source_btn.setEnabled(False)
        copy_source_btn.clicked.connect(self.copy_source_links)
        
        copy_target_btn = ModernButton("📋 复制目标消息链接")
        copy_target_btn.setEnabled(False)
        copy_target_btn.clicked.connect(self.copy_target_links)
        
        mark_selected_btn = ModernButton("✅ 标记选中为已处理")
        mark_selected_btn.setEnabled(False)
        mark_selected_btn.clicked.connect(self.mark_selected_resolved)
        
        bottom_button_layout.addWidget(copy_source_btn)
        bottom_button_layout.addWidget(copy_target_btn)
        bottom_button_layout.addWidget(mark_selected_btn)
        bottom_button_layout.addStretch()
        
        self.copy_source_btn = copy_source_btn
        self.copy_target_btn = copy_target_btn
        self.mark_selected_btn = mark_selected_btn
        
        main_layout.addLayout(bottom_button_layout)
        
        self.setLayout(main_layout)
        
        if self.parent:
            self.apply_theme_from_parent()
    
    def on_selection_changed(self):
        """选中项变化时更新按钮状态"""
        selected_rows = set()
        for item in self.notifications_table.selectedItems():
            selected_rows.add(item.row())
        
        has_selection = len(selected_rows) > 0
        
        self.copy_source_btn.setEnabled(has_selection)
        self.copy_target_btn.setEnabled(has_selection)
        self.mark_selected_btn.setEnabled(has_selection)
        
        self.selected_notifications = []
        for row in selected_rows:
            notification_id_item = self.notifications_table.item(row, 1)
            if notification_id_item:
                notification_id = int(notification_id_item.text())
                with sqlite3.connect(self.db.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute('SELECT * FROM edit_notifications WHERE id = ?', (notification_id,))
                    row_data = cursor.fetchone()
                    if row_data:
                        self.selected_notifications.append(dict(row_data))
    
    def apply_theme_from_parent(self):
        """从父窗口应用主题"""
        if hasattr(self.parent, 'config'):
            theme = self.parent.config.get('theme', 'dark')
            self.apply_theme(theme)
    
    def apply_theme(self, theme):
        """应用主题"""
        if theme == 'dark':
            self.setStyleSheet("""
                QDialog {
                    background-color: #1E1E1E;
                    color: #E0E0E0;
                }
                
                QTableWidget {
                    background-color: #2D2D2D;
                    border: 1px solid #3D3D3D;
                    gridline-color: #3D3D3D;
                    color: #E0E0E0;
                }
                
                QTableWidget::item {
                    padding: 8px;
                }
                
                QTableWidget::item:selected {
                    background-color: #1A3D5C;
                }
                
                QHeaderView::section {
                    background-color: #353535;
                    color: #E0E0E0;
                    padding: 8px;
                    border: 1px solid #3D3D3D;
                }
                
                QPushButton {
                    background-color: #333333;
                    color: #E0E0E0;
                    border: 1px solid #454545;
                    padding: 10px 20px;
                    border-radius: 8px;
                }
                
                QPushButton:hover {
                    background-color: #444444;
                    border-color: #555555;
                }
                
                QPushButton:disabled {
                    background-color: #2D2D2D;
                    color: #666666;
                    border-color: #3D3D3D;
                }
            """)
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #FFFFFF;
                    color: #333333;
                }
                
                QTableWidget {
                    background-color: #FFFFFF;
                    border: 1px solid #E0E0E0;
                    gridline-color: #E0E0E0;
                    color: #333333;
                }
                
                QTableWidget::item {
                    padding: 8px;
                }
                
                QTableWidget::item:selected {
                    background-color: #E6F2FF;
                }
                
                QHeaderView::section {
                    background-color: #F5F5F5;
                    color: #333333;
                    padding: 8px;
                    border: 1px solid #E0E0E0;
                }
                
                QPushButton {
                    background-color: #F0F0F0;
                    color: #333333;
                    border: 1px solid #CCCCCC;
                    padding: 10px 20px;
                    border-radius: 8px;
                }
                
                QPushButton:hover {
                    background-color: #E4E7ED;
                    border-color: #C0C4CC;
                }
                
                QPushButton:disabled {
                    background-color: #F8F8F8;
                    color: #999999;
                    border-color: #E0E0E0;
                }
            """)
    
    def load_notifications(self):
        """加载通知"""
        notifications = self.db.get_pending_notifications()
        self.notifications_table.setRowCount(len(notifications))
        
        for row, notification in enumerate(notifications):
            checkbox_item = QTableWidgetItem()
            checkbox_item.setCheckState(Qt.Unchecked)
            self.notifications_table.setItem(row, 0, checkbox_item)
            
            id_item = QTableWidgetItem(str(notification['id']))
            self.notifications_table.setItem(row, 1, id_item)
            
            type_text = self.get_type_text(notification['notification_type'])
            type_item = QTableWidgetItem(type_text)
            self.notifications_table.setItem(row, 2, type_item)
            
            desc_item = QTableWidgetItem(notification['description'])
            self.notifications_table.setItem(row, 3, desc_item)
            
            time_item = QTableWidgetItem(notification['created_at'])
            self.notifications_table.setItem(row, 4, time_item)
            
            status_item = QTableWidgetItem("待处理")
            status_item.setForeground(QColor("#FFA500"))
            self.notifications_table.setItem(row, 5, status_item)
        
        self.selected_notifications = []
        self.copy_source_btn.setEnabled(False)
        self.copy_target_btn.setEnabled(False)
        self.mark_selected_btn.setEnabled(False)
    
    def get_type_text(self, notification_type: str) -> str:
        """获取类型文本"""
        type_map = {
            'file_added_to_text': '文件添加',
            'file_changed': '文件更改',
            'file_removed': '文件删除',
            'webpage_changed': '链接更改'
        }
        return type_map.get(notification_type, notification_type)
    
    def generate_message_link(self, chat_id: str, message_id: int) -> str:
        """生成消息链接"""
        try:
            if str(chat_id).startswith('-100'):
                channel_id = int(chat_id) + 1000000000000
                return f"https://t.me/c/{channel_id}/{message_id}"
            elif str(chat_id).startswith('@'):
                return f"https://t.me/{chat_id[1:]}/{message_id}"
            else:
                return f"chat_id: {chat_id}, message_id: {message_id}"
        except:
            return f"chat_id: {chat_id}, message_id: {message_id}"
    
    def copy_source_links(self):
        """复制选中的源消息链接"""
        if not self.selected_notifications:
            return
        
        links = []
        for notification in self.selected_notifications:
            link = self.generate_message_link(
                notification['source_chat_id'],
                notification['source_message_id']
            )
            links.append(link)
        
        text_to_copy = "\n".join(links)
        clipboard = QApplication.clipboard()
        clipboard.setText(text_to_copy)
        
        msg_box = CustomMessageBox(self, self.parent.config.get('theme', 'dark') if self.parent else 'dark')
        msg_box.setWindowTitle("成功")
        msg_box.setText(f"已复制 {len(links)} 个源消息链接到剪贴板")
        msg_box.setIcon(QMessageBox.Information)
        msg_box.apply_theme()
        msg_box.exec_()
    
    def copy_target_links(self):
        """复制选中的目标消息链接"""
        if not self.selected_notifications:
            return
        
        links = []
        for notification in self.selected_notifications:
            link = self.generate_message_link(
                notification['target_chat_id'],
                notification['target_message_id']
            )
            links.append(link)
        
        text_to_copy = "\n".join(links)
        clipboard = QApplication.clipboard()
        clipboard.setText(text_to_copy)
        
        msg_box = CustomMessageBox(self, self.parent.config.get('theme', 'dark') if self.parent else 'dark')
        msg_box.setWindowTitle("成功")
        msg_box.setText(f"已复制 {len(links)} 个目标消息链接到剪贴板")
        msg_box.setIcon(QMessageBox.Information)
        msg_box.apply_theme()
        msg_box.exec_()
    
    def mark_selected_resolved(self):
        """标记选中项为已处理"""
        if not self.selected_notifications:
            return
        
        count = 0
        for notification in self.selected_notifications:
            notification_id = notification['id']
            self.db.mark_notification_resolved(notification_id)
            count += 1
        
        self.load_notifications()
        
        msg_box = CustomMessageBox(self, self.parent.config.get('theme', 'dark') if self.parent else 'dark')
        msg_box.setWindowTitle("成功")
        msg_box.setText(f"已标记 {count} 个通知为已处理")
        msg_box.setIcon(QMessageBox.Information)
        msg_box.apply_theme()
        msg_box.exec_()
        
        if self.parent:
            self.parent.check_pending_notifications()
    
    def mark_all_resolved(self):
        """标记所有为已处理"""
        notifications = self.db.get_pending_notifications()
        for notification in notifications:
            self.db.mark_notification_resolved(notification['id'])
        
        self.load_notifications()
        
        msg_box = CustomMessageBox(self, self.parent.config.get('theme', 'dark') if self.parent else 'dark')
        msg_box.setWindowTitle("成功")
        msg_box.setText(f"已标记 {len(notifications)} 个通知为已处理")
        msg_box.setIcon(QMessageBox.Information)
        msg_box.apply_theme()
        msg_box.exec_()
        
        if self.parent:
            self.parent.check_pending_notifications()
    
    def clear_resolved(self):
        """清空已处理的通知"""
        with sqlite3.connect(self.db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM edit_notifications WHERE is_resolved = 1')
            conn.commit()
        
        msg_box = CustomMessageBox(self, self.parent.config.get('theme', 'dark') if self.parent else 'dark')
        msg_box.setWindowTitle("成功")
        msg_box.setText("已清空所有已处理的通知")
        msg_box.setIcon(QMessageBox.Information)
        msg_box.apply_theme()
        msg_box.exec_()


class RuleDialog(QDialog):
    """规则编辑对话框"""
    
    def __init__(self, parent=None, rule: dict = None):
        super().__init__(parent)
        self.rule = rule or {
            "name": "",
            "source_id": 0,
            "source_name": "",
            "source_topic_id": None,
            "target_id": 0,
            "target_name": "",
            "target_topic_id": None,
            "enabled": True,
            "message_types": []
        }
        self.parent = parent
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("编辑转发规则")
        self.setMinimumWidth(800)
        self.setMinimumHeight(700)
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(30, 30, 30, 30)
        
        name_label = QLabel("规则名称")
        name_label.setStyleSheet("font-weight: 600; font-size: 15px; color: #2c3e50; margin-left: 4px;")
        main_layout.addWidget(name_label)
        
        self.name_edit = QLineEdit(self.rule['name'])
        self.name_edit.setPlaceholderText("例如: 新闻频道转发")
        self.name_edit.setStyleSheet("""
            QLineEdit {
                padding: 12px 14px;
                border: 1px solid #dcdfe6;
                border-radius: 10px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #409eff;
            }
        """)
        main_layout.addWidget(self.name_edit)
        
        source_target_layout = QHBoxLayout()
        source_target_layout.setSpacing(20)
        
        source_group = QGroupBox("📥 来源设置")
        source_group.setStyleSheet("""
            QGroupBox {
                font-weight: 600;
                font-size: 14px;
                border: 2px solid #e4e7ed;
                border-radius: 12px;
                padding-top: 20px;
                padding-left: 8px;
                padding-right: 8px;
                padding-bottom: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 12px;
                color: #409eff;
            }
        """)
        source_layout = QVBoxLayout()
        source_layout.setSpacing(12)
        source_layout.setContentsMargins(12, 8, 12, 12)
        
        source_id_label = QLabel("群组/频道 ID 或用户名")
        source_id_label.setStyleSheet("font-size: 14px; color: #606266; margin-left: 4px;")
        source_layout.addWidget(source_id_label)
        
        self.source_id_edit = QLineEdit(str(self.rule['source_id']) if self.rule['source_id'] else "")
        self.source_id_edit.setPlaceholderText("例如: @channelname 或 -1001234567890")
        self.source_id_edit.setStyleSheet("""
            QLineEdit {
                padding: 12px 14px;
                border: 1px solid #dcdfe6;
                border-radius: 10px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #409eff;
            }
        """)
        source_layout.addWidget(self.source_id_edit)
        
        source_topic_label = QLabel("主题 ID (可选)")
        source_topic_label.setStyleSheet("font-size: 14px; color: #606266; margin-left: 4px;")
        source_layout.addWidget(source_topic_label)
        
        topic_hint = QLabel("💡 如何获取主题ID: 复制主题中任意消息链接,如 t.me/c/xxx/16/165")
        topic_hint.setStyleSheet("color: #909399; font-size: 13px; margin-left: 4px;")
        topic_hint.setWordWrap(True)
        source_layout.addWidget(topic_hint)
        
        topic_hint2 = QLabel("   其中 16 就是主题ID(不是165!)")
        topic_hint2.setStyleSheet("color: #409eff; font-size: 13px; font-weight: 600; margin-left: 4px;")
        source_layout.addWidget(topic_hint2)
        
        self.source_topic_edit = QLineEdit(str(self.rule['source_topic_id']) if self.rule['source_topic_id'] else "")
        self.source_topic_edit.setPlaceholderText("留空表示接收所有消息")
        self.source_topic_edit.setStyleSheet("""
            QLineEdit {
                padding: 12px 14px;
                border: 1px solid #dcdfe6;
                border-radius: 10px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #409eff;
            }
        """)
        source_layout.addWidget(self.source_topic_edit)
        
        source_layout.addStretch()
        source_group.setLayout(source_layout)
        source_target_layout.addWidget(source_group)
        
        target_group = QGroupBox("📤 目标设置")
        target_group.setStyleSheet("""
            QGroupBox {
                font-weight: 600;
                font-size: 14px;
                border: 2px solid #e4e7ed;
                border-radius: 12px;
                padding-top: 20px;
                padding-left: 8px;
                padding-right: 8px;
                padding-bottom: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 12px;
                color: #67c23a;
            }
        """)
        target_layout = QVBoxLayout()
        target_layout.setSpacing(12)
        target_layout.setContentsMargins(12, 8, 12, 12)
        
        target_id_label = QLabel("群组/频道 ID 或用户名")
        target_id_label.setStyleSheet("font-size: 14px; color: #606266; margin-left: 4px;")
        target_layout.addWidget(target_id_label)
        
        self.target_id_edit = QLineEdit(str(self.rule['target_id']) if self.rule['target_id'] else "")
        self.target_id_edit.setPlaceholderText("例如: @mychannel 或 -1009876543210")
        self.target_id_edit.setStyleSheet("""
            QLineEdit {
                padding: 12px 14px;
                border: 1px solid #dcdfe6;
                border-radius: 10px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #409eff;
            }
        """)
        target_layout.addWidget(self.target_id_edit)
        
        target_topic_label = QLabel("主题 ID (可选)")
        target_topic_label.setStyleSheet("font-size: 14px; color: #606266; margin-left: 4px;")
        target_layout.addWidget(target_topic_label)
        
        self.target_topic_edit = QLineEdit(str(self.rule['target_topic_id']) if self.rule['target_topic_id'] else "")
        self.target_topic_edit.setPlaceholderText("留空表示发送到主群组")
        self.target_topic_edit.setStyleSheet("""
            QLineEdit {
                padding: 12px 14px;
                border: 1px solid #dcdfe6;
                border-radius: 10px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #409eff;
            }
        """)
        target_layout.addWidget(self.target_topic_edit)
        
        target_layout.addStretch()
        target_group.setLayout(target_layout)
        source_target_layout.addWidget(target_group)
        
        main_layout.addLayout(source_target_layout)
        
        type_group = QGroupBox("🔍 消息类型过滤")
        type_group.setStyleSheet("""
            QGroupBox {
                font-weight: 600;
                font-size: 14px;
                border: 2px solid #e4e7ed;
                border-radius: 12px;
                padding-top: 20px;
                padding-left: 8px;
                padding-right: 8px;
                padding-bottom: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 12px;
                color: #e6a23c;
            }
        """)
        type_layout = QGridLayout()
        type_layout.setSpacing(12)
        type_layout.setContentsMargins(12, 8, 12, 12)
        
        self.message_types = {
            "文本": "文本",
            "图片": "图片",
            "视频": "视频",
            "语音": "语音",
            "文件": "文件",
            "贴纸": "贴纸",
            "音频": "音频",
            "网页链接": "网页链接",
            "联系人": "联系人",
            "位置": "位置",
            "地点": "地点",
            "游戏": "游戏",
            "发票": "发票",
            "投票": "投票",
            "骰子": "骰子",
            "其他": "其他"
        }
        
        self.type_checkboxes = {}
        row, col = 0, 0
        for i, (key, label) in enumerate(self.message_types.items()):
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            if key in self.rule.get('message_types', []):
                checkbox.setChecked(True)
            elif self.rule.get('message_types') and len(self.rule['message_types']) > 0:
                checkbox.setChecked(key in self.rule['message_types'])
            self.type_checkboxes[key] = checkbox
            type_layout.addWidget(checkbox, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1
        
        type_group.setLayout(type_layout)
        main_layout.addWidget(type_group)
        
        self.enabled_check = QCheckBox("启用此规则")
        self.enabled_check.setChecked(self.rule['enabled'])
        self.enabled_check.setStyleSheet("""
            QCheckBox {
                font-size: 14px;
                color: #606266;
                padding: 12px 0;
                margin-left: 4px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        main_layout.addWidget(self.enabled_check)
        
        main_layout.addStretch()
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        
        cancel_btn = ModernButton("取消")
        cancel_btn.clicked.connect(self.reject)
        
        save_btn = ModernButton("保存", primary=True)
        save_btn.clicked.connect(self.accept)
        
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        
        main_layout.addLayout(btn_layout)
        
        self.setLayout(main_layout)
        
        if self.parent:
            self.apply_theme_from_parent()
    
    def apply_theme_from_parent(self):
        """从父窗口应用主题"""
        if hasattr(self.parent, 'config'):
            theme = self.parent.config.get('theme', 'dark')
            self.apply_theme(theme)
    
    def apply_theme(self, theme):
        """应用主题"""
        if theme == 'dark':
            self.setStyleSheet("""
                QDialog {
                    background-color: #1E1E1E;
                    color: #E0E0E0;
                }
                
                QLabel {
                    color: #E0E0E0;
                }
                
                QGroupBox {
                    background-color: #252525;
                    border: 2px solid #353535;
                    border-radius: 12px;
                    padding-top: 20px;
                    padding-left: 8px;
                    padding-right: 8px;
                    padding-bottom: 8px;
                }
                
                QGroupBox::title {
                    color: #66b3ff;
                }
                
                QLineEdit, QCheckBox {
                    color: #E0E0E0;
                }
                
                QLineEdit {
                    background-color: #2A2A2A;
                    border: 1px solid #3A3A3A;
                    border-radius: 10px;
                }
                
                QLineEdit:focus {
                    border-color: #66b3ff;
                }
                
                ModernButton {
                    background-color: #333333;
                    color: #E0E0E0;
                    border: 1px solid #454545;
                    padding: 12px 28px;
                    border-radius: 10px;
                }
                
                ModernButton:hover {
                    background-color: #444444;
                    border-color: #555555;
                }
                
                ModernButton[primary="true"] {
                    background-color: #444444;
                    color: white;
                    border: 1px solid #555555;
                }
                
                ModernButton[primary="true"]:hover {
                    background-color: #555555;
                    border-color: #666666;
                }
            """)
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #F5F5F5;
                    color: #000000;
                }
                
                QLabel {
                    color: #606266;
                }
                
                ModernButton {
                    background-color: #F0F0F0;
                    color: #606266;
                    border: 1px solid #DCDFE6;
                    padding: 12px 28px;
                    border-radius: 10px;
                }
                
                ModernButton:hover {
                    background-color: #E4E7ED;
                    border-color: #C0C4CC;
                }
                
                ModernButton[primary="true"] {
                    background-color: #444444;
                    color: white;
                    border: 1px solid #555555;
                }
                
                ModernButton[primary="true"]:hover {
                    background-color: #555555;
                    border-color: #666666;
                }
            """)
    
    def get_rule(self) -> dict:
        """获取规则"""
        self.rule['name'] = self.name_edit.text().strip()
        
        source_text = self.source_id_edit.text().strip()
        if source_text.startswith('@'):
            self.rule['source_id'] = source_text
            self.rule['source_name'] = source_text
        else:
            try:
                self.rule['source_id'] = int(source_text)
                self.rule['source_name'] = source_text
            except ValueError:
                self.rule['source_id'] = source_text
                self.rule['source_name'] = source_text
        
        source_topic = self.source_topic_edit.text().strip()
        self.rule['source_topic_id'] = int(source_topic) if source_topic else None
        
        target_text = self.target_id_edit.text().strip()
        if target_text.startswith('@'):
            self.rule['target_id'] = target_text
            self.rule['target_name'] = target_text
        else:
            try:
                self.rule['target_id'] = int(target_text)
                self.rule['target_name'] = target_text
            except ValueError:
                self.rule['target_id'] = target_text
                self.rule['target_name'] = target_text
        
        target_topic = self.target_topic_edit.text().strip()
        self.rule['target_topic_id'] = int(target_topic) if target_topic else None
        
        self.rule['message_types'] = []
        for key, checkbox in self.type_checkboxes.items():
            if checkbox.isChecked():
                self.rule['message_types'].append(key)
        
        self.rule['enabled'] = self.enabled_check.isChecked()
        
        return self.rule


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.config = Config.load()
        self.worker: Optional[TelegramWorker] = None
        self.is_service_running = False
        self.tray_icon: Optional[QSystemTrayIcon] = None
        self.notifications_dialog: Optional[NotificationsDialog] = None
        
        self.sync_status_label: Optional[QLabel] = None
        self.deletion_sync_status_label: Optional[QLabel] = None
        self.check_deletion_status_label: Optional[QLabel] = None
        
        self.init_ui()
        self.init_tray_icon()
        self.apply_theme()
        self.restore_window_state()
        
        self.check_pending_notifications()
        self.connect_setting_signals()
    
    def connect_setting_signals(self):
        """连接设置复选框的信号"""
        if hasattr(self, 'enable_sync_check'):
            self.enable_sync_check.stateChanged.connect(self.update_home_status_labels)
        
        if hasattr(self, 'enable_deletion_sync_check'):
            self.enable_deletion_sync_check.stateChanged.connect(self.update_home_status_labels)
        
        if hasattr(self, 'check_deleted_on_startup_check'):
            self.check_deleted_on_startup_check.stateChanged.connect(self.update_home_status_labels)
    
    def update_home_status_labels(self):
        """更新主页状态标签"""
        if self.sync_status_label:
            self.sync_status_label.setText(
                f"消息同步: {'✅ 已启用' if self.config.get('enable_message_sync', True) else '⭕ 已禁用'}"
            )
        
        if self.deletion_sync_status_label:
            self.deletion_sync_status_label.setText(
                f"删除同步: {'✅ 已启用' if self.config.get('enable_deletion_sync', True) else '⭕ 已禁用'}"
            )
        
        if self.check_deletion_status_label:
            self.check_deletion_status_label.setText(
                f"启动检查: {'✅ 已启用' if self.config.get('check_deleted_on_startup', True) else '⭕ 已禁用'}"
            )
    
    def check_pending_notifications(self):
        """检查待处理通知数量"""
        db = Database()
        count = db.get_notifications_count()
        self.update_notifications_button(count)
    
    def update_notifications_button(self, count: int):
        """更新通知按钮文本"""
        if count > 0:
            self.notifications_btn.setText(f"📝 编辑通知 ({count})")
        else:
            self.notifications_btn.setText("📝 编辑通知")
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("Telegram 消息转发器")  # 更新标题
        self.setMinimumSize(1100, 800)
        
        try:
            self.setWindowIcon(QIcon('app.ico'))
        except:
            pass
        
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
            }
        """)
        main_layout.addWidget(self.tabs)
        
        # 主页
        self.create_home_tab()
        
        # 规则页
        self.create_rules_tab()
        
        # 设置页（已添加 Bot API 配置）
        self.create_settings_tab()
        
        # 日志页
        self.create_log_tab()
        
        # 状态栏
        self.status_label = QLabel("未连接")
        self.statusBar().addPermanentWidget(self.status_label)
    
    def init_tray_icon(self):
        """初始化系统托盘图标"""
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self)
            
            try:
                self.tray_icon.setIcon(QIcon('app.ico'))
            except:
                pass
            
            tray_menu = QMenu()
            
            show_action = QAction("显示窗口", self)
            show_action.triggered.connect(self.show_normal)
            tray_menu.addAction(show_action)
            
            notifications_action = QAction("管理编辑通知", self)
            notifications_action.triggered.connect(self.show_notifications_dialog)
            tray_menu.addAction(notifications_action)
            
            tray_menu.addSeparator()
            
            start_action = QAction("启动服务", self)
            start_action.triggered.connect(self.start_service)
            tray_menu.addAction(start_action)
            
            stop_action = QAction("停止服务", self)
            stop_action.triggered.connect(self.stop_service)
            stop_action.setEnabled(False)
            tray_menu.addAction(stop_action)
            
            tray_menu.addSeparator()
            
            exit_action = QAction("退出", self)
            exit_action.triggered.connect(self.close)
            tray_menu.addAction(exit_action)
            
            self.tray_icon.setContextMenu(tray_menu)
            
            self.tray_icon.activated.connect(self.on_tray_icon_activated)
            
            self.tray_icon.show()
    
    def on_tray_icon_activated(self, reason):
        """托盘图标激活事件"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_normal()
    
    def show_normal(self):
        """显示窗口"""
        self.show()
        self.activateWindow()
        self.raise_()
    
    def create_home_tab(self):
        """创建主页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(30)
        
        title_layout = QVBoxLayout()
        title_layout.setSpacing(8)
        
        title = QLabel("Telegram 消息转发器")  # 更新标题
        title_font = QFont()
        title_font.setPointSize(34)
        title_font.setBold(True)
        title_font.setWeight(QFont.Black)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        title_layout.addWidget(title)
        
        subtitle = QLabel("智能消息转发 · Bot API 混合架构 · 24小时不间断运行")  # 更新副标题
        subtitle.setAlignment(Qt.AlignCenter)
        title_layout.addWidget(subtitle)
        
        layout.addLayout(title_layout)
        layout.addSpacing(30)
        
        status_card = QFrame()
        status_card.setObjectName("statusCard")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(40, 40, 40, 40)
        status_layout.setSpacing(25)
        
        status_title = QLabel("运行状态")
        status_title.setObjectName("statusTitle")
        status_layout.addWidget(status_title)
        
        self.status_display = QLabel("未启动")
        status_font = QFont()
        status_font.setPointSize(28)
        status_font.setBold(True)
        self.status_display.setFont(status_font)
        self.status_display.setAlignment(Qt.AlignCenter)
        self.status_display.setObjectName("statusDisplay")
        status_layout.addWidget(self.status_display)
        
        # 状态信息改为水平布局
        status_info_layout = QHBoxLayout()
        status_info_layout.setSpacing(30)
        status_info_layout.setContentsMargins(0, 10, 0, 10)

        status_info_layout.addStretch()
        
        # Bot API 状态
        self.bot_api_status_label = QLabel(f"Bot API: {'✅ 已配置' if self.config.get('bot_token') and self.config.get('use_bot_api', True) else '⭕ 未配置/禁用'}")
        self.bot_api_status_label.setAlignment(Qt.AlignCenter)
        self.bot_api_status_label.setMinimumWidth(180)
        status_info_layout.addWidget(self.bot_api_status_label)
        
        self.sync_status_label = QLabel(f"消息同步: {'✅ 已启用' if self.config.get('enable_message_sync', True) else '⭕ 已禁用'}")
        self.sync_status_label.setAlignment(Qt.AlignCenter)
        self.sync_status_label.setMinimumWidth(140)
        status_info_layout.addWidget(self.sync_status_label)
        
        self.deletion_sync_status_label = QLabel(f"删除同步: {'✅ 已启用' if self.config.get('enable_deletion_sync', True) else '⭕ 已禁用'}")
        self.deletion_sync_status_label.setAlignment(Qt.AlignCenter)
        self.deletion_sync_status_label.setMinimumWidth(140)
        status_info_layout.addWidget(self.deletion_sync_status_label)
        
        self.check_deletion_status_label = QLabel(f"启动检查: {'✅ 已启用' if self.config.get('check_deleted_on_startup', True) else '⭕ 已禁用'}")
        self.check_deletion_status_label.setAlignment(Qt.AlignCenter)
        self.check_deletion_status_label.setMinimumWidth(140)
        status_info_layout.addWidget(self.check_deletion_status_label)
        
        status_info_layout.addStretch()
        status_layout.addLayout(status_info_layout)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(20)
        
        self.start_btn = ModernButton("🚀 启动服务", primary=True)
        self.start_btn.setMinimumHeight(60)
        self.start_btn.setObjectName("startBtn")
        
        self.stop_btn = ModernButton("🛑 停止服务")
        self.stop_btn.setMinimumHeight(60)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setObjectName("stopBtn")
        
        self.notifications_btn = ModernButton("📝 编辑通知")
        self.notifications_btn.setMinimumHeight(60)
        self.notifications_btn.setObjectName("notificationsBtn")
        self.notifications_btn.clicked.connect(self.show_notifications_dialog)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addWidget(self.notifications_btn)
        btn_layout.addStretch()
        
        status_layout.addLayout(btn_layout)
        
        layout.addWidget(status_card)
        
        theme_layout = QHBoxLayout()
        theme_layout.addStretch()
        
        self.theme_btn = ModernButton("🌙 深色模式" if self.config.get('theme') == 'dark' else "☀️ 浅色模式")
        self.theme_btn.setMinimumHeight(40)
        self.theme_btn.setObjectName("themeBtn")
        self.theme_btn.clicked.connect(self.toggle_theme)
        theme_layout.addWidget(self.theme_btn)
        
        theme_layout.addStretch()
        layout.addLayout(theme_layout)
        
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(25)
        
        rules_card = self.create_stat_card(
            "📋 转发规则",
            str(len(self.config.get('rules', []))),
            "#3498db"
        )
        stats_layout.addWidget(rules_card)
        
        active_count = sum(1 for r in self.config.get('rules', []) if r.get('enabled', True))
        active_card = self.create_stat_card(
            "✅ 活跃规则",
            str(active_count),
            "#2ecc71"
        )
        stats_layout.addWidget(active_card)
        
        version_card = self.create_stat_card(
            "📦 版本信息",
            self.config.get('version', '3.1.0'),
            "#9b59b6"
        )
        stats_layout.addWidget(version_card)
        
        layout.addLayout(stats_layout)
        layout.addStretch()
        
        self.tabs.addTab(tab, "🏠 主页")
        
        self.start_btn.clicked.connect(self.start_service)
        self.stop_btn.clicked.connect(self.stop_service)
    
    def create_stat_card(self, title: str, value: str, color: str) -> QFrame:
        """创建统计卡片"""
        card = QFrame()
        card.setObjectName("statCard")
        card.setMinimumHeight(140)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(15)
        
        title_label = QLabel(title)
        title_label.setObjectName("statTitle")
        title_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title_label)
        
        value_label = QLabel(value)
        value_label.setObjectName("statValue")
        value_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(value_label)
        
        return card
    
    def create_rules_tab(self):
        """创建规则页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        header = QHBoxLayout()
        
        title = QLabel("📋 转发规则管理")
        title.setObjectName("rulesTitle")
        header.addWidget(title)
        header.addStretch()
        
        add_btn = ModernButton("➕ 添加规则", primary=True)
        add_btn.setObjectName("addRuleBtn")
        header.addWidget(add_btn)
        
        layout.addLayout(header)
        
        self.rules_list = QListWidget()
        self.rules_list.setObjectName("rulesList")
        self.rules_list.itemDoubleClicked.connect(self.edit_rule)
        layout.addWidget(self.rules_list)
        
        bottom_toolbar = QHBoxLayout()
        bottom_toolbar.setSpacing(15)
        
        edit_btn = ModernButton("✏️ 编辑规则")
        edit_btn.setObjectName("editRuleBtn")
        
        delete_btn = ModernButton("🗑️ 删除规则")
        delete_btn.setObjectName("deleteRuleBtn")
        
        bottom_toolbar.addWidget(edit_btn)
        bottom_toolbar.addWidget(delete_btn)
        bottom_toolbar.addStretch()
        
        layout.addLayout(bottom_toolbar)
        
        self.refresh_rules_list()
        
        add_btn.clicked.connect(self.add_rule)
        edit_btn.clicked.connect(self.edit_rule)
        delete_btn.clicked.connect(self.delete_rule)
        
        self.tabs.addTab(tab, "📋 规则")
    
    def create_settings_tab(self):
        """创建设置页（已添加 Bot API 配置）"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(24)
        
        title = QLabel("⚙️ 系统设置")
        title.setObjectName("settingsTitle")
        layout.addWidget(title)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
            QScrollBar:vertical {
                background-color: transparent;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #666666;
                min-height: 20px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #777777;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                background-color: transparent;
                height: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal {
                background-color: #666666;
                min-width: 20px;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #777777;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
        """)
        
        scroll_widget = QWidget()
        scroll_widget.setObjectName("scrollWidget")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(24)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        
        # 账户设置
        account_group = QGroupBox("👤 账户设置")
        account_group.setObjectName("accountGroup")
        account_layout = QFormLayout()
        account_layout.setSpacing(15)
        account_layout.setContentsMargins(25, 25, 25, 25)
        account_layout.setLabelAlignment(Qt.AlignRight)
        
        self.api_id_edit = QLineEdit(self.config.get('api_id', ''))
        self.api_id_edit.setPlaceholderText("从 https://my.telegram.org 获取")
        self.api_id_edit.setObjectName("apiIdEdit")
        account_layout.addRow(QLabel("API ID:"), self.api_id_edit)
        
        self.api_hash_edit = QLineEdit(self.config.get('api_hash', ''))
        self.api_hash_edit.setPlaceholderText("从 https://my.telegram.org 获取")
        self.api_hash_edit.setObjectName("apiHashEdit")
        account_layout.addRow(QLabel("API Hash:"), self.api_hash_edit)
        
        self.phone_edit = QLineEdit(self.config.get('phone', ''))
        self.phone_edit.setPlaceholderText("+8613800138000")
        self.phone_edit.setObjectName("phoneEdit")
        account_layout.addRow(QLabel("手机号:"), self.phone_edit)
        
        # Bot Token 设置（新增）
        self.bot_token_edit = QLineEdit(self.config.get('bot_token', ''))
        self.bot_token_edit.setPlaceholderText("从 @BotFather 获取")
        self.bot_token_edit.setObjectName("botTokenEdit")
        account_layout.addRow(QLabel("Bot Token:"), self.bot_token_edit)
        
        account_group.setLayout(account_layout)
        scroll_layout.addWidget(account_group)
        
        # Bot API 设置和消息同步设置改为左右布局
        settings_horizontal_layout = QHBoxLayout()
        settings_horizontal_layout.setSpacing(20)
        
        # Bot API 设置（左侧）
        bot_api_group = QGroupBox("🤖 Bot API 设置")
        bot_api_group.setObjectName("botApiGroup")
        bot_api_layout = QVBoxLayout()
        bot_api_layout.setSpacing(15)
        bot_api_layout.setContentsMargins(25, 25, 25, 25)
        
        self.use_bot_api_check = QCheckBox("启用 Bot API 混合架构")
        self.use_bot_api_check.setChecked(self.config.get('use_bot_api', True))
        self.use_bot_api_check.setObjectName("useBotApiCheck")
        bot_api_layout.addWidget(self.use_bot_api_check)
        
        self.bot_api_for_text_check = QCheckBox("文本消息使用 Bot API")
        self.bot_api_for_text_check.setChecked(self.config.get('bot_api_for_text', True))
        self.bot_api_for_text_check.setObjectName("botApiForTextCheck")
        bot_api_layout.addWidget(self.bot_api_for_text_check)
        
        self.bot_api_for_media_check = QCheckBox("媒体消息使用 Bot API")
        self.bot_api_for_media_check.setChecked(self.config.get('bot_api_for_media', True))
        self.bot_api_for_media_check.setObjectName("botApiForMediaCheck")
        bot_api_layout.addWidget(self.bot_api_for_media_check)
        
        self.bot_api_for_delete_check = QCheckBox("消息删除使用 Bot API")
        self.bot_api_for_delete_check.setChecked(self.config.get('bot_api_for_delete', True))
        self.bot_api_for_delete_check.setObjectName("botApiForDeleteCheck")
        bot_api_layout.addWidget(self.bot_api_for_delete_check)
        
        self.bot_api_for_edit_check = QCheckBox("消息编辑使用 Bot API")
        self.bot_api_for_edit_check.setChecked(self.config.get('bot_api_for_edit', True))
        self.bot_api_for_edit_check.setObjectName("botApiForEditCheck")
        bot_api_layout.addWidget(self.bot_api_for_edit_check)
        
        self.bot_api_fallback_check = QCheckBox("Bot API 失败时回退到用户 API")
        self.bot_api_fallback_check.setChecked(self.config.get('bot_api_fallback', True))
        self.bot_api_fallback_check.setObjectName("botApiFallbackCheck")
        bot_api_layout.addWidget(self.bot_api_fallback_check)
        
        bot_api_hint = QLabel("💡 Bot API 优势：\n• 减轻用户 API 压力，降低封禁风险\n• 独立限制配额，不与用户 API 共享\n• 支持文本消息、媒体消息发送和编辑\n• 自动失败回退保证服务连续性")
        bot_api_hint.setWordWrap(True)
        bot_api_layout.addWidget(bot_api_hint)
        
        bot_api_group.setLayout(bot_api_layout)
        settings_horizontal_layout.addWidget(bot_api_group)
        
        # 消息同步设置（右侧）
        sync_group = QGroupBox("🔄 消息同步设置")
        sync_group.setObjectName("syncGroup")
        sync_layout = QVBoxLayout()
        sync_layout.setSpacing(15)
        sync_layout.setContentsMargins(25, 25, 25, 25)
        
        self.enable_sync_check = QCheckBox("启用消息同步（编辑/删除同步）")
        self.enable_sync_check.setChecked(self.config.get('enable_message_sync', True))
        self.enable_sync_check.setObjectName("enableSyncCheck")
        sync_layout.addWidget(self.enable_sync_check)
        
        self.enable_deletion_sync_check = QCheckBox("启用删除同步（双向同步删除）")
        self.enable_deletion_sync_check.setChecked(self.config.get('enable_deletion_sync', True))
        self.enable_deletion_sync_check.setObjectName("enableDeletionSyncCheck")
        sync_layout.addWidget(self.enable_deletion_sync_check)
        
        self.check_deleted_on_startup_check = QCheckBox("启动时检查删除状态（清理已删除消息）")
        self.check_deleted_on_startup_check.setChecked(self.config.get('check_deleted_on_startup', True))
        self.check_deleted_on_startup_check.setObjectName("checkDeletedOnStartupCheck")
        sync_layout.addWidget(self.check_deleted_on_startup_check)
        
        self.show_notifications_check = QCheckBox("显示托盘通知")
        self.show_notifications_check.setChecked(self.config.get('show_tray_notifications', True))
        self.show_notifications_check.setObjectName("showNotificationsCheck")
        sync_layout.addWidget(self.show_notifications_check)
        
        sync_hint = QLabel("💡 消息同步功能可以：\n• 同步删除源消息/目标消息\n• 同步编辑纯文本消息\n• 记录文件/链接变更并通知\n• 支持多文件合并转发（图片、视频、文件、音频）")
        sync_hint.setWordWrap(True)
        sync_layout.addWidget(sync_hint)
        
        sync_group.setLayout(sync_layout)
        settings_horizontal_layout.addWidget(sync_group)
        
        scroll_layout.addLayout(settings_horizontal_layout)
        
        # 程序信息
        info_group = QGroupBox("ℹ️ 程序信息")
        info_group.setObjectName("infoGroup")
        info_layout = QFormLayout()
        info_layout.setSpacing(15)
        info_layout.setContentsMargins(25, 25, 25, 25)
        info_layout.setLabelAlignment(Qt.AlignRight)
        
        version_label = QLabel(self.config.get('version', '3.1.0'))
        info_layout.addRow(QLabel("版本号:"), version_label)
        
        author_label = QLabel(self.config.get('author', 'DomAurora'))
        info_layout.addRow(QLabel("作者:"), author_label)
        
        info_group.setLayout(info_layout)
        scroll_layout.addWidget(info_group)
        
        scroll_layout.addStretch()
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        save_btn = ModernButton("💾 保存设置", primary=True)
        save_btn.setMinimumHeight(55)
        save_btn.setObjectName("saveSettingsBtn")
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)
        
        self.tabs.addTab(tab, "⚙️ 设置")
    
    def create_log_tab(self):
        """创建日志页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        header = QHBoxLayout()
        
        title = QLabel("📜 运行日志")
        title.setObjectName("logTitle")
        header.addWidget(title)
        header.addStretch()
        
        clear_btn = ModernButton("🧹 清空日志")
        clear_btn.setObjectName("clearLogBtn")
        clear_btn.clicked.connect(lambda: self.log_text.clear())
        header.addWidget(clear_btn)
        
        layout.addLayout(header)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_font = QFont()
        log_font.setFamily("Consolas")
        log_font.setPointSize(14)
        self.log_text.setFont(log_font)
        self.log_text.setObjectName("logText")
        layout.addWidget(self.log_text)
        
        self.tabs.addTab(tab, "📜 日志")
    
    def show_notifications_dialog(self):
        """显示通知管理对话框"""
        if not self.notifications_dialog:
            self.notifications_dialog = NotificationsDialog(self)
        
        self.notifications_dialog.show()
        self.notifications_dialog.raise_()
        self.notifications_dialog.activateWindow()
        self.notifications_dialog.load_notifications()
    
    def refresh_rules_list(self):
        """刷新规则列表"""
        self.rules_list.clear()
        rules = self.config.get('rules', [])
        
        for i, rule in enumerate(rules):
            status = "✅" if rule.get('enabled', True) else "⭕"
            name = rule.get('name', f'规则 {i+1}')
            source = rule.get('source_name', str(rule.get('source_id', '')))
            target = rule.get('target_name', str(rule.get('target_id', '')))
            
            source_topic = f" [主题:{rule['source_topic_id']}]" if rule.get('source_topic_id') else ""
            target_topic = f" [主题:{rule['target_topic_id']}]" if rule.get('target_topic_id') else ""
            
            types = rule.get('message_types', [])
            if types:
                type_str = f" [类型:{','.join(types[:3])}{'...' if len(types) > 3 else ''}]"
            else:
                type_str = " [类型:全部]"
            
            text = f"{status}  {name}{type_str}\n    📥 {source}{source_topic}  →  📤 {target}{target_topic}"
            
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, i)
            self.rules_list.addItem(item)
    
    def add_rule(self):
        """添加规则"""
        dialog = RuleDialog(self)
        dialog.apply_theme_from_parent()
        if dialog.exec_() == QDialog.Accepted:
            rule = dialog.get_rule()
            if not rule['name']:
                self.show_message("警告", "请输入规则名称", "warning")
                return
            
            self.config['rules'].append(rule)
            Config.save(self.config)
            self.refresh_rules_list()
            self.add_log(f"✅ 添加规则: {rule['name']}")
    
    def edit_rule(self):
        """编辑规则"""
        current_item = self.rules_list.currentItem()
        if not current_item:
            return
        
        index = current_item.data(Qt.UserRole)
        rule = self.config['rules'][index]
        
        dialog = RuleDialog(self, rule)
        dialog.apply_theme_from_parent()
        if dialog.exec_() == QDialog.Accepted:
            updated_rule = dialog.get_rule()
            self.config['rules'][index] = updated_rule
            Config.save(self.config)
            self.refresh_rules_list()
            self.add_log(f"✏️ 更新规则: {updated_rule['name']}")
    
    def delete_rule(self):
        """删除规则"""
        current_item = self.rules_list.currentItem()
        if not current_item:
            return
        
        msg_box = CustomMessageBox(self, self.config.get('theme', 'dark'))
        msg_box.setWindowTitle("确认删除")
        msg_box.setText("确定要删除此规则吗?")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.apply_theme()
        
        reply = msg_box.exec_()
        
        if reply == QMessageBox.Yes:
            index = current_item.data(Qt.UserRole)
            rule_name = self.config['rules'][index].get('name', '')
            del self.config['rules'][index]
            Config.save(self.config)
            self.refresh_rules_list()
            self.add_log(f"🗑️ 删除规则: {rule_name}")
    
    def save_settings(self):
        """保存设置"""
        self.config['api_id'] = self.api_id_edit.text().strip()
        self.config['api_hash'] = self.api_hash_edit.text().strip()
        self.config['phone'] = self.phone_edit.text().strip()
        
        # 保存 Bot Token 和 Bot API 设置
        self.config['bot_token'] = self.bot_token_edit.text().strip()
        self.config['use_bot_api'] = self.use_bot_api_check.isChecked()
        self.config['bot_api_for_text'] = self.bot_api_for_text_check.isChecked()
        self.config['bot_api_for_media'] = self.bot_api_for_media_check.isChecked()
        self.config['bot_api_for_delete'] = self.bot_api_for_delete_check.isChecked()
        self.config['bot_api_for_edit'] = self.bot_api_for_edit_check.isChecked()
        self.config['bot_api_fallback'] = self.bot_api_fallback_check.isChecked()
        
        # 保存其他设置
        self.config['enable_message_sync'] = self.enable_sync_check.isChecked()
        self.config['enable_deletion_sync'] = self.enable_deletion_sync_check.isChecked()
        self.config['check_deleted_on_startup'] = self.check_deleted_on_startup_check.isChecked()
        self.config['show_tray_notifications'] = self.show_notifications_check.isChecked()
        
        Config.save(self.config)
        self.add_log("✅ 设置已保存")
        self.show_message("成功", "设置已保存", "info")
        
        # 更新主页状态标签
        self.update_home_status_labels()
        
        # 更新 Bot API 状态标签
        if self.bot_api_status_label:
            self.bot_api_status_label.setText(
                f"Bot API: {'✅ 已配置' if self.config.get('bot_token') and self.config.get('use_bot_api', True) else '⭕ 未配置/禁用'}"
            )
    
    def start_service(self):
        """启动服务"""
        if self.is_service_running:
            self.add_log("⚠ 服务已经在运行中")
            return
            
        if not all([self.config.get('api_id'), self.config.get('api_hash'), self.config.get('phone')]):
            self.show_message("警告", "请先在设置中配置 API ID, API Hash 和手机号", "warning")
            self.tabs.setCurrentIndex(2)
            return
        
        if not self.config.get('rules'):
            self.show_message("警告", "请先添加至少一条转发规则", "warning")
            self.tabs.setCurrentIndex(1)
            return
        
        self.add_log("[详细日志] 🔄 正在启动 Telegram 消息转发服务 v3.1.5...")
        self.add_log(f"[详细日志] 配置文件路径: {Path(Config.CONFIG_FILE).absolute()}")
        self.add_log(f"[详细日志] 消息同步: {'已启用' if self.config.get('enable_message_sync', True) else '已禁用'}")
        self.add_log(f"[详细日志] 删除同步: {'已启用' if self.config.get('enable_deletion_sync', True) else '已禁用'}")
        self.add_log(f"[详细日志] 启动检查删除: {'已启用' if self.config.get('check_deleted_on_startup', True) else '已禁用'}")
        
        # 记录 Bot API 配置状态
        if self.config.get('use_bot_api', True) and self.config.get('bot_token'):
            self.add_log(f"[详细日志] 🤖 Bot API 已启用，Token: {self.config['bot_token'][:8]}***")
            self.add_log(f"[详细日志] 📊 Bot API 使用策略:")
            self.add_log(f"[详细日志]   - 文本消息: {'使用 Bot' if self.config.get('bot_api_for_text', True) else '使用用户 API'}")
            self.add_log(f"[详细日志]   - 媒体消息: {'使用 Bot' if self.config.get('bot_api_for_media', True) else '使用用户 API'}")
            self.add_log(f"[详细日志]   - 消息删除: {'使用 Bot' if self.config.get('bot_api_for_delete', True) else '使用用户 API'}")
            self.add_log(f"[详细日志]   - 消息编辑: {'使用 Bot' if self.config.get('bot_api_for_edit', True) else '使用用户 API'}")
            self.add_log(f"[详细日志]   - 失败回退: {'启用' if self.config.get('bot_api_fallback', True) else '禁用'}")
        else:
            self.add_log(f"[详细日志] ⚠ Bot API 未启用或未配置 Token，将仅使用用户 API")
        
        self.add_log("[详细日志] 📦 支持多文件合并转发（图片、视频、文件、音频）")
        
        self.is_service_running = True
        self.worker = TelegramWorker(self.config)
        self.worker.log_signal.connect(self.add_log)
        self.worker.status_signal.connect(self.update_status)
        self.worker.error_signal.connect(self.show_error)
        self.worker.auth_code_signal.connect(self.request_auth_code)
        self.worker.password_signal.connect(self.request_password)
        self.worker.stopped_signal.connect(self.on_service_stopped)
        self.worker.service_stopped_signal.connect(self.on_service_stopped_completed)
        self.worker.notification_signal.connect(self.show_tray_notification)
        self.worker.edit_notification_signal.connect(self.handle_edit_notification)
        self.worker.notification_count_signal.connect(self.update_notifications_button)
        self.worker.start()
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        
        # 更新托盘菜单
        if self.tray_icon:
            menu = self.tray_icon.contextMenu()
            menu.actions()[3].setEnabled(False)
            menu.actions()[4].setEnabled(True)
    
    def stop_service(self):
        """停止服务"""
        if not self.is_service_running or not self.worker:
            return
            
        self.add_log("[详细日志] 🔄 正在停止消息转发服务...")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        
        if self.worker:
            self.worker.should_stop = True
        
        if self.tray_icon:
            menu = self.tray_icon.contextMenu()
            menu.actions()[3].setEnabled(True)
            menu.actions()[4].setEnabled(False)
    
    def handle_edit_notification(self, notification_data: dict):
        """处理编辑通知"""
        self.check_pending_notifications()
        
        if self.notifications_dialog and self.notifications_dialog.isVisible():
            self.notifications_dialog.load_notifications()
    
    def on_service_stopped(self):
        """服务停止时的处理（工作线程完成）"""
        self.add_log("[详细日志] ✅ 消息转发服务已停止")
        self.update_status("已停止")
    
    def on_service_stopped_completed(self):
        """服务完全停止完成时的处理"""
        self.is_service_running = False
        self.worker = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        if self.tray_icon:
            menu = self.tray_icon.contextMenu()
            menu.actions()[3].setEnabled(True)
            menu.actions()[4].setEnabled(False)
    
    def request_auth_code(self):
        """请求认证码"""
        code, ok = QInputDialog.getText(
            self, 
            '验证码', 
            '请输入收到的验证码:',
            QLineEdit.Normal
        )
        
        if ok and code:
            self.worker.auth_code = code.strip()
            self.add_log(f"[详细日志] 收到用户输入的验证码: {code[:2]}***")
    
    def request_password(self):
        """请求两步验证密码"""
        password, ok = QInputDialog.getText(
            self, 
            '两步验证', 
            '请输入两步验证密码:',
            QLineEdit.Password
        )
        
        if ok and password:
            self.worker.password = password
            self.add_log("[详细日志] 收到用户输入的两步验证密码")
    
    def add_log(self, message: str):
        """添加日志"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.log_text.append(f"[{timestamp}] {message}")
    
    def update_status(self, status: str):
        """更新状态"""
        self.status_label.setText(status)
        self.status_display.setText(status)
    
    def show_error(self, error: str):
        """显示错误"""
        self.show_message("错误", error, "error")
    
    def show_message(self, title: str, message: str, msg_type: str = "info"):
        """显示自定义消息框"""
        msg_box = CustomMessageBox(self, self.config.get('theme', 'dark'))
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStandardButtons(QMessageBox.Ok)
        
        if msg_type == "warning":
            msg_box.setIcon(QMessageBox.Warning)
        elif msg_type == "error":
            msg_box.setIcon(QMessageBox.Critical)
        else:
            msg_box.setIcon(QMessageBox.Information)
        
        msg_box.apply_theme()
        msg_box.exec_()
    
    def show_tray_notification(self, title: str, message: str):
        """显示托盘通知"""
        if (self.tray_icon and 
            self.config.get('show_tray_notifications', True) and
            QSystemTrayIcon.supportsMessages()):
            
            self.tray_icon.showMessage(
                title,
                message,
                QSystemTrayIcon.Information,
                3000
            )
    
    def toggle_theme(self):
        """切换主题"""
        if self.config.get('theme', 'dark') == 'dark':
            self.config['theme'] = 'light'
            self.theme_btn.setText("☀️ 浅色模式")
        else:
            self.config['theme'] = 'dark'
            self.theme_btn.setText("🌙 深色模式")
        
        Config.save(self.config)
        self.apply_theme()
    
    def save_window_state(self):
        """保存窗口状态"""
        self.config['window_geometry'] = {
            'x': self.x(),
            'y': self.y(),
            'width': self.width(),
            'height': self.height()
        }
        
        self.config['window_state'] = 'maximized' if self.isMaximized() else 'normal'
        
        Config.save(self.config)
    
    def restore_window_state(self):
        """恢复窗口状态"""
        if 'window_geometry' in self.config and self.config['window_geometry']:
            geom = self.config['window_geometry']
            
            screen_geometry = QApplication.primaryScreen().availableGeometry()
            
            x = max(0, min(geom['x'], screen_geometry.width() - 400))
            y = max(0, min(geom['y'], screen_geometry.height() - 400))
            width = min(geom['width'], screen_geometry.width())
            height = min(geom['height'], screen_geometry.height())
            
            self.setGeometry(x, y, width, height)
        
        if self.config.get('window_state') == 'maximized':
            self.showMaximized()
    
    def apply_theme(self):
        """应用主题（保持不变）"""
        theme = self.config.get('theme', 'dark')
        
        if theme == "dark":
            # 保持原有深色主题样式，只添加 Bot API 相关样式
            self.setStyleSheet(f"""
                /* 主窗口 - 标题栏适配深色模式 */
                QMainWindow {{
                    background-color: #1A1A1A;
                    color: #E0E0E0;
                }}
                
                /* 窗口标题栏 */
                QMainWindow::title {{
                    background-color: #1A1A1A;
                    color: #E0E0E0;
                }}
                
                /* 标签页容器 */
                QTabWidget::pane {{
                    background-color: #1A1A1A;
                    border: none;
                }}
                
                QTabBar::tab {{
                    background-color: #2D2D2D;
                    color: #B0B0B0;
                    padding: 12px 24px;
                    margin-right: 2px;
                    border: 1px solid #3D3D3D;
                    border-bottom: none;
                    border-top-left-radius: 10px;
                    border-top-right-radius: 10px;
                    font-size: 14px;
                    font-weight: 500;
                }}
                
                QTabBar::tab:selected {{
                    background-color: #3D3D3D;
                    color: #FFFFFF;
                    border-color: #4D4D4D;
                    border-bottom-color: #3D3D3D;
                }}
                
                QTabBar::tab:hover {{
                    background-color: #353535;
                    color: #FFFFFF;
                }}
                
                /* 主页样式 */
                QLabel[objectName="statusTitle"] {{
                    font-size: 16px;
                    font-weight: 600;
                    color: #B0B0B0;
                    padding-left: 8px;
                }}
                
                QLabel[objectName="statusDisplay"] {{
                    color: #66B3FF;
                    padding: 8px;
                }}
                
                QLabel[objectName="subtitle"] {{
                    font-size: 18px;
                    color: #A0A0A0;
                    padding: 4px;
                }}
                
                /* 通知按钮 */
                QPushButton[objectName="notificationsBtn"] {{
                    background-color: #555555;
                    color: white;
                    border: 1px solid #666666;
                    border-radius: 14px;
                    padding: 14px 32px;
                    font-size: 16px;
                    font-weight: 600;
                }}
                
                QPushButton[objectName="notificationsBtn"]:hover {{
                    background-color: #666666;
                    border-color: #777777;
                }}
                
                QPushButton[objectName="notificationsBtn"]:pressed {{
                    background-color: #444444;
                }}
                
                /* 统计卡片 */
                QFrame[objectName="statCard"] {{
                    background-color: #2D2D2D;
                    border: 2px solid #3D3D3D;
                    border-radius: 16px;
                    padding: 5px;
                }}
                
                QFrame[objectName="statCard"]:hover {{
                    border: 2px solid #4D4D4D;
                    background-color: #353535;
                }}
                
                QLabel[objectName="statTitle"] {{
                    font-size: 16px;
                    font-weight: 600;
                    color: #B0B0B0;
                    padding: 4px 8px;
                }}
                
                QLabel[objectName="statValue"] {{
                    font-size: 42px;
                    font-weight: bold;
                    padding: 4px 8px;
                }}
                
                /* 状态卡片 */
                QFrame[objectName="statusCard"] {{
                    background-color: #2D2D2D;
                    border: 2px solid #3D3D3D;
                    border-radius: 16px;
                }}
                
                /* 主题切换按钮 */
                QPushButton[objectName="themeBtn"] {{
                    background-color: #333333;
                    color: #E0E0E0;
                    border: 1px solid #454545;
                    border-radius: 12px;
                    padding: 10px 24px;
                    font-size: 14px;
                    font-weight: 500;
                }}
                
                QPushButton[objectName="themeBtn"]:hover {{
                    background-color: #444444;
                    border-color: #555555;
                }}
                
                /* 按钮样式 */
                QPushButton[objectName="startBtn"] {{
                    background-color: #444444;
                    color: white;
                    border: 1px solid #555555;
                    border-radius: 14px;
                    padding: 14px 32px;
                    font-size: 16px;
                    font-weight: 600;
                }}
                
                QPushButton[objectName="startBtn"]:hover {{
                    background-color: #555555;
                    border-color: #666666;
                }}
                
                QPushButton[objectName="startBtn"]:pressed {{
                    background-color: #333333;
                }}
                
                QPushButton[objectName="stopBtn"] {{
                    background-color: #555555;
                    color: white;
                    border: 1px solid #666666;
                    border-radius: 14px;
                    padding: 14px 32px;
                    font-size: 16px;
                    font-weight: 600;
                }}
                
                QPushButton[objectName="stopBtn"]:hover {{
                    background-color: #666666;
                    border-color: #777777;
                }}
                
                QPushButton[objectName="stopBtn"]:pressed {{
                    background-color: #444444;
                }}
                
                /* 规则页 */
                QLabel[objectName="rulesTitle"] {{
                    font-size: 22px;
                    font-weight: bold;
                    color: #FFFFFF;
                    padding-left: 8px;
                }}
                
                QListWidget[objectName="rulesList"] {{
                    background-color: #2D2D2D;
                    border: 2px solid #4D4D4D;
                    border-radius: 12px;
                    padding: 12px;
                    color: #E0E0E0;
                    font-size: 14px;
                }}
                
                QListWidget[objectName="rulesList"]::item {{
                    padding: 16px 20px;
                    border-radius: 10px;
                    margin: 6px 0;
                    border: 1px solid #3D3D3D;
                    background-color: #2D2D2D;
                }}
                
                QListWidget[objectName="rulesList"]::item:selected {{
                    background-color: #1A3D5C;
                    border-color: #66B3FF;
                    color: #66B3FF;
                }}
                
                QListWidget[objectName="rulesList"]::item:hover {{
                    background-color: #353535;
                    border-color: #4D4D4D;
                }}
                
                QPushButton[objectName="addRuleBtn"] {{
                    background-color: #444444;
                    color: white;
                    border: 1px solid #555555;
                    border-radius: 12px;
                }}
                
                QPushButton[objectName="editRuleBtn"] {{
                    background-color: #555555;
                    color: white;
                    border: 1px solid #666666;
                    border-radius: 12px;
                }}
                
                QPushButton[objectName="deleteRuleBtn"] {{
                    background-color: #555555;
                    color: white;
                    border: 1px solid #666666;
                    border-radius: 12px;
                }}
                
                /* 设置页 */
                QLabel[objectName="settingsTitle"] {{
                    font-size: 22px;
                    font-weight: bold;
                    color: #FFFFFF;
                    padding-left: 8px;
                }}
                
                /* Bot API 设置组样式 */
                QGroupBox[objectName="botApiGroup"] {{
                    background-color: #2D2D2D;
                    border: 2px solid #4A4A4A;
                    border-radius: 16px;
                    margin-top: 12px;
                    padding-top: 20px;
                    font-weight: 600;
                    font-size: 16px;
                }}
                
                QGroupBox[objectName="botApiGroup"]::title {{
                    color: #FF6B6B;
                    padding: 0 12px;
                }}
                
                QGroupBox[objectName="accountGroup"] {{
                    background-color: #2D2D2D;
                    border: 2px solid #3D3D3D;
                    border-radius: 16px;
                    margin-top: 12px;
                    padding-top: 20px;
                    font-weight: 600;
                    font-size: 16px;
                }}
                
                QGroupBox[objectName="syncGroup"] {{
                    background-color: #2D2D2D;
                    border: 2px solid #3D3D3D;
                    border-radius: 16px;
                    margin-top: 12px;
                    padding-top: 20px;
                    font-weight: 600;
                    font-size: 16px;
                }}
                
                QGroupBox[objectName="infoGroup"] {{
                    background-color: #2D2D2D;
                    border: 2px solid #3D3D3D;
                    border-radius: 16px;
                    margin-top: 12px;
                    padding-top: 20px;
                    font-weight: 600;
                    font-size: 16px;
                }}
                
                QGroupBox::title {{
                    color: #66B3FF;
                    padding: 0 12px;
                }}
                
                QLineEdit[objectName="apiIdEdit"],
                QLineEdit[objectName="apiHashEdit"],
                QLineEdit[objectName="phoneEdit"],
                QLineEdit[objectName="botTokenEdit"] {{
                    background-color: #3D3D3D;
                    border: 1px solid #4D4D4D;
                    border-radius: 10px;
                    padding: 12px 14px;
                    color: #E0E0E0;
                    font-size: 14px;
                }}
                
                QLineEdit:focus {{
                    border-color: #66B3FF;
                }}
                
                QPushButton[objectName="saveSettingsBtn"] {{
                    background-color: #444444;
                    color: white;
                    border: 1px solid #555555;
                    font-size: 16px;
                    border-radius: 14px;
                }}
                
                /* 日志页 */
                QLabel[objectName="logTitle"] {{
                    font-size: 22px;
                    font-weight: bold;
                    color: #FFFFFF;
                    padding-left: 8px;
                }}
                
                QTextEdit[objectName="logText"] {{
                    background-color: #2D2D2D;
                    border: 2px solid #4D4D4D;
                    border-radius: 12px;
                    padding: 16px 18px;
                    font-size: 14px;
                    color: #E0E0E0;
                }}
                
                QPushButton[objectName="clearLogBtn"] {{
                    background-color: #555555;
                    color: white;
                    border: 1px solid #666666;
                    border-radius: 12px;
                    padding: 10px 20px;
                }}
                
                /* 滚动区域 */
                QScrollArea {{
                    background-color: transparent;
                    border: none;
                }}
                
                QWidget[objectName="scrollWidget"] {{
                    background-color: transparent;
                }}
                
                /* 状态栏 */
                QStatusBar {{
                    background-color: #2D2D2D;
                    color: #B0B0B0;
                    border-top: 1px solid #3D3D3D;
                    font-size: 13px;
                    padding: 6px 12px;
                }}
                
                /* 普通按钮 */
                QPushButton {{
                    background-color: #3D3D3D;
                    color: #E0E0E0;
                    border: 1px solid #4D4D4D;
                    padding: 12px 24px;
                    border-radius: 12px;
                    font-size: 14px;
                    font-weight: 500;
                }}
                
                QPushButton:hover {{
                    background-color: #4D4D4D;
                    border-color: #5D5D5D;
                }}
                
                QPushButton:pressed {{
                    background-color: #2D2D2D;
                }}
                
                QPushButton:disabled {{
                    background-color: #2D2D2D;
                    color: #666666;
                    border-color: #3D3D3D;
                }}
                
                /* 表单标签 */
                QLabel {{
                    padding: 2px 6px;
                }}
                
                /* 组合框下拉菜单 */
                QComboBox QAbstractItemView {{
                    background-color: #2D2D2D;
                    border: 1px solid #4D4D4D;
                    border-radius: 8px;
                    selection-background-color: #1A3D5C;
                }}
                
                /* 滚动条 */
                QScrollBar {{
                    border-radius: 6px;
                }}
            """)
            
        else:
            # 保持原有浅色主题样式，只添加 Bot API 相关样式
            self.setStyleSheet(f"""
                /* 主窗口 - 标题栏适配浅色模式 */
                QMainWindow {{
                    background-color: #F5F5F5;
                    color: #333333;
                }}
                
                /* 窗口标题栏 */
                QMainWindow::title {{
                    background-color: #F5F5F5;
                    color: #333333;
                }}
                
                /* 标签页 */
                QTabWidget::pane {{
                    background-color: #F5F5F5;
                    border: none;
                }}
                
                QTabBar::tab {{
                    background-color: #FFFFFF;
                    color: #666666;
                    padding: 12px 24px;
                    margin-right: 2px;
                    border: 1px solid #E0E0E0;
                    border-bottom: none;
                    border-top-left-radius: 10px;
                    border-top-right-radius: 10px;
                    font-size: 14px;
                    font-weight: 500;
                }}
                
                QTabBar::tab:selected {{
                    background-color: #FFFFFF;
                    color: #0066CC;
                    border-color: #E0E0E0;
                    border-bottom-color: #FFFFFF;
                }}
                
                QTabBar::tab:hover {{
                    background-color: #F8F8F8;
                    color: #333333;
                }}
                
                /* 主页样式 */
                QLabel[objectName="statusTitle"] {{
                    font-size: 16px;
                    font-weight: 600;
                    color: #5D6D7E;
                    padding-left: 8px;
                }}
                
                QLabel[objectName="statusDisplay"] {{
                    color: #0066CC;
                    padding: 8px;
                }}
                
                QLabel[objectName="subtitle"] {{
                    font-size: 18px;
                    color: #7F8C8D;
                    padding: 4px;
                }}
                
                /* 通知按钮 */
                QPushButton[objectName="notificationsBtn"] {{
                    background-color: #666666;
                    color: white;
                    border: 1px solid #777777;
                    border-radius: 14px;
                    padding: 14px 32px;
                    font-size: 16px;
                    font-weight: 600;
                }}
                
                QPushButton[objectName="notificationsBtn"]:hover {{
                    background-color: #777777;
                    border-color: #888888;
                }}
                
                QPushButton[objectName="notificationsBtn"]:pressed {{
                    background-color: #555555;
                }}
                
                /* 统计卡片 */
                QFrame[objectName="statCard"] {{
                    background-color: #FFFFFF;
                    border: 2px solid #E0E0E0;
                    border-radius: 16px;
                    padding: 5px;
                }}
                
                QFrame[objectName="statCard"]:hover {{
                    border: 2px solid #0066CC;
                    background-color: #F0F8FF;
                }}
                
                QLabel[objectName="statTitle"] {{
                    font-size: 16px;
                    font-weight: 600;
                    color: #5D6D7E;
                    padding: 4px 8px;
                }}
                
                QLabel[objectName="statValue"] {{
                    font-size: 42px;
                    font-weight: bold;
                    padding: 4px 8px;
                }}
                
                /* 状态卡片 */
                QFrame[objectName="statusCard"] {{
                    background-color: #FFFFFF;
                    border: 2px solid #E0E0E0;
                    border-radius: 16px;
                }}
                
                /* 主题切换按钮 */
                QPushButton[objectName="themeBtn"] {{
                    background-color: #F0F0F0;
                    color: #333333;
                    border: 1px solid #CCCCCC;
                    border-radius: 12px;
                    padding: 10px 24px;
                    font-size: 14px;
                    font-weight: 500;
                }}
                
                QPushButton[objectName="themeBtn"]:hover {{
                    background-color: #E4E7ED;
                    border-color: #C0C4CC;
                }}
                
                /* 按钮样式 */
                QPushButton[objectName="startBtn"] {{
                    background-color: #444444;
                    color: white;
                    border: 1px solid #555555;
                    border-radius: 14px;
                    padding: 14px 32px;
                    font-size: 16px;
                    font-weight: 600;
                }}
                
                QPushButton[objectName="startBtn"]:hover {{
                    background-color: #555555;
                    border-color: #666666;
                }}
                
                QPushButton[objectName="startBtn"]:pressed {{
                    background-color: #333333;
                }}
                
                QPushButton[objectName="stopBtn"] {{
                    background-color: #666666;
                    color: white;
                    border: 1px solid #777777;
                    border-radius: 14px;
                    padding: 14px 32px;
                    font-size: 16px;
                    font-weight: 600;
                }}
                
                QPushButton[objectName="stopBtn"]:hover {{
                    background-color: #777777;
                    border-color: #888888;
                }}
                
                QPushButton[objectName="stopBtn"]:pressed {{
                    background-color: #555555;
                }}
                
                /* 规则页 */
                QLabel[objectName="rulesTitle"] {{
                    font-size: 22px;
                    font-weight: bold;
                    color: #2C3E50;
                    padding-left: 8px;
                }}
                
                QListWidget[objectName="rulesList"] {{
                    background-color: #FFFFFF;
                    border: 2px solid #E0E0E0;
                    border-radius: 12px;
                    padding: 12px;
                    color: #333333;
                    font-size: 14px;
                }}
                
                QListWidget[objectName="rulesList"]::item {{
                    padding: 16px 20px;
                    border-radius: 10px;
                    margin: 6px 0;
                    border: 1px solid #F0F0F0;
                    background-color: #FFFFFF;
                }}
                
                QListWidget[objectName="rulesList"]::item:selected {{
                    background-color: #E6F2FF;
                    border-color: #66B3FF;
                    color: #0066CC;
                }}
                
                QListWidget[objectName="rulesList"]::item:hover {{
                    background-color: #F8F8F8;
                    border-color: #E0E0E0;
                }}
                
                QPushButton[objectName="addRuleBtn"] {{
                    background-color: #444444;
                    color: white;
                    border: 1px solid #555555;
                    border-radius: 12px;
                }}
                
                QPushButton[objectName="editRuleBtn"] {{
                    background-color: #555555;
                    color: white;
                    border: 1px solid #666666;
                    border-radius: 12px;
                }}
                
                QPushButton[objectName="deleteRuleBtn"] {{
                    background-color: #555555;
                    color: white;
                    border: 1px solid #666666;
                    border-radius: 12px;
                }}
                
                /* 设置页 */
                QLabel[objectName="settingsTitle"] {{
                    font-size: 22px;
                    font-weight: bold;
                    color: #2C3E50;
                    padding-left: 8px;
                }}
                
                /* Bot API 设置组样式 */
                QGroupBox[objectName="botApiGroup"] {{
                    background-color: #FFFFFF;
                    border: 2px solid #E6A23C;
                    border-radius: 16px;
                    margin-top: 12px;
                    padding-top: 20px;
                    font-weight: 600;
                    font-size: 16px;
                }}
                
                QGroupBox[objectName="botApiGroup"]::title {{
                    color: #E6A23C;
                    padding: 0 12px;
                }}
                
                QGroupBox[objectName="accountGroup"] {{
                    background-color: #FFFFFF;
                    border: 2px solid #E0E0E0;
                    border-radius: 16px;
                    margin-top: 12px;
                    padding-top: 20px;
                    font-weight: 600;
                    font-size: 16px;
                }}
                
                QGroupBox[objectName="syncGroup"] {{
                    background-color: #FFFFFF;
                    border: 2px solid #E0E0E0;
                    border-radius: 16px;
                    margin-top: 12px;
                    padding-top: 20px;
                    font-weight: 600;
                    font-size: 16px;
                }}
                
                QGroupBox[objectName="infoGroup"] {{
                    background-color: #FFFFFF;
                    border: 2px solid #E0E0E0;
                    border-radius: 16px;
                    margin-top: 12px;
                    padding-top: 20px;
                    font-weight: 600;
                    font-size: 16px;
                }}
                
                QGroupBox::title {{
                    color: #0066CC;
                    padding: 0 12px;
                }}
                
                QLineEdit[objectName="apiIdEdit"],
                QLineEdit[objectName="apiHashEdit"],
                QLineEdit[objectName="phoneEdit"],
                QLineEdit[objectName="botTokenEdit"] {{
                    background-color: #FFFFFF;
                    border: 1px solid #E0E0E0;
                    border-radius: 10px;
                    padding: 12px 14px;
                    color: #333333;
                    font-size: 14px;
                }}
                
                QLineEdit:focus {{
                    border-color: #66B3FF;
                }}
                
                QPushButton[objectName="saveSettingsBtn"] {{
                    background-color: #444444;
                    color: white;
                    border: 1px solid #555555;
                    font-size: 16px;
                    border-radius: 14px;
                }}
                
                /* 日志页 */
                QLabel[objectName="logTitle"] {{
                    font-size: 22px;
                    font-weight: bold;
                    color: #2C3E50;
                    padding-left: 8px;
                }}
                
                QTextEdit[objectName="logText"] {{
                    background-color: #FFFFFF;
                    border: 2px solid #E0E0E0;
                    border-radius: 12px;
                    padding: 16px 18px;
                    font-size: 14px;
                    color: #333333;
                }}
                
                QPushButton[objectName="clearLogBtn"] {{
                    background-color: #666666;
                    color: white;
                    border: 1px solid #777777;
                    border-radius: 12px;
                    padding: 10px 20px;
                }}
                
                /* 滚动区域 */
                QScrollArea {{
                    background-color: transparent;
                    border: none;
                }}
                
                QWidget[objectName="scrollWidget"] {{
                    background-color: transparent;
                }}
                
                /* 状态栏 */
                QStatusBar {{
                    background-color: #FFFFFF;
                    color: #666666;
                    border-top: 1px solid #E0E0E0;
                    font-size: 13px;
                    padding: 6px 12px;
                }}
                
                /* 普通按钮 */
                QPushButton {{
                    background-color: #F8F8F8;
                    color: #333333;
                    border: 1px solid #E0E0E0;
                    padding: 12px 24px;
                    border-radius: 12px;
                    font-size: 14px;
                    font-weight: 500;
                }}
                
                QPushButton:hover {{
                    background-color: #F0F0F0;
                    border-color: #CCCCCC;
                }}
                
                QPushButton:pressed {{
                    background-color: #E8E8E8;
                }}
                
                QPushButton:disabled {{
                    background-color: #F8F8F8;
                    color: #999999;
                    border-color: #E0E0E0;
                }}
                
                /* 表单标签 */
                QLabel {{
                    padding: 2px 6px;
                }}
                
                /* 组合框下拉菜单 */
                QComboBox QAbstractItemView {{
                    background-color: #FFFFFF;
                    border: 1px solid #E0E0E0;
                    border-radius: 8px;
                    selection-background-color: #E6F2FF;
                }}
                
                /* 滚动条 */
                QScrollBar {{
                    border-radius: 6px;
                }}
            """)
        
        # 设置统计卡片的特定颜色
        stat_cards = self.findChildren(QFrame, "statCard")
        for card in stat_cards:
            title_label = card.findChild(QLabel, "statTitle")
            value_label = card.findChild(QLabel, "statValue")
            if title_label and value_label:
                title_text = title_label.text()
                if "转发规则" in title_text:
                    value_label.setStyleSheet("color: #3498db; font-size: 42px; font-weight: bold; padding: 4px 8px;")
                elif "活跃规则" in title_text:
                    value_label.setStyleSheet("color: #2ecc71; font-size: 42px; font-weight: bold; padding: 4px 8px;")
                elif "版本信息" in title_text:
                    value_label.setStyleSheet("color: #9b59b6; font-size: 42px; font-weight: bold; padding: 4px 8px;")
    
    def changeEvent(self, event):
        """窗口状态改变事件"""
        if event.type() == event.WindowStateChange:
            # 当窗口最小化时，隐藏到托盘
            if self.isMinimized() and self.tray_icon and self.tray_icon.isVisible():
                event.ignore()
                self.hide()
                if self.config.get('show_tray_notifications', True):
                    self.tray_icon.showMessage(
                        "Telegram 消息转发器",
                        "程序已最小化到系统托盘",
                        QSystemTrayIcon.Information,
                        2000
                    )
        super().changeEvent(event)
    
    def closeEvent(self, event):
        """关闭事件"""
        # 创建自定义对话框，提供三个选项
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("退出确认")
        msg_box.setText("选择操作：")
        msg_box.setIcon(QMessageBox.Question)
        
        # 添加按钮
        minimize_btn = msg_box.addButton("最小化到托盘", QMessageBox.ActionRole)
        exit_btn = msg_box.addButton("退出程序", QMessageBox.DestructiveRole)
        cancel_btn = msg_box.addButton("取消", QMessageBox.RejectRole)
        
        # 应用主题
        theme = self.config.get('theme', 'dark')
        if theme == 'dark':
            msg_box.setStyleSheet("""
                QMessageBox {
                    background-color: #2B2B2B;
                    color: #FFFFFF;
                }
                QMessageBox QLabel {
                    color: #FFFFFF;
                    font-size: 14px;
                    min-width: 300px;
                }
                QMessageBox QPushButton {
                    background-color: #444444;
                    color: white;
                    border: 1px solid #555555;
                    padding: 8px 20px;
                    border-radius: 6px;
                    min-width: 100px;
                }
                QMessageBox QPushButton:hover {
                    background-color: #555555;
                }
            """)
        else:
            msg_box.setStyleSheet("""
                QMessageBox {
                    background-color: #FFFFFF;
                    color: #333333;
                }
                QMessageBox QLabel {
                    color: #333333;
                    font-size: 14px;
                    min-width: 300px;
                }
                QMessageBox QPushButton {
                    background-color: #F0F0F0;
                    color: #333333;
                    border: 1px solid #CCCCCC;
                    padding: 8px 20px;
                    border-radius: 6px;
                    min-width: 100px;
                }
                QMessageBox QPushButton:hover {
                    background-color: #E0E0E0;
                }
            """)
        
        msg_box.exec_()
        clicked_button = msg_box.clickedButton()
        
        if clicked_button == minimize_btn:
            # 最小化到托盘
            event.ignore()
            self.hide()
            if self.config.get('show_tray_notifications', True) and self.tray_icon:
                self.tray_icon.showMessage(
                    "Telegram 消息转发器",
                    "程序已最小化到系统托盘，双击托盘图标可恢复窗口",
                    QSystemTrayIcon.Information,
                    3000
                )
        elif clicked_button == exit_btn:
            # 退出程序
            self.save_window_state()
            
            if self.worker and self.worker.isRunning():
                # 如果服务正在运行，再次确认
                confirm_box = CustomMessageBox(self, self.config.get('theme', 'dark'))
                confirm_box.setWindowTitle("确认退出")
                confirm_box.setText("服务正在运行,确定要退出吗?")
                confirm_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                confirm_box.apply_theme()
                
                reply = confirm_box.exec_()
                
                if reply == QMessageBox.Yes:
                    self.stop_service()
                    # 等待工作线程完全停止
                    while self.worker and self.worker.isRunning():
                        QApplication.processEvents()
                        QThread.msleep(100)
                    event.accept()
                else:
                    event.ignore()
            else:
                event.accept()
        else:
            # 取消
            event.ignore()


def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    app.setApplicationName("Telegram 消息转发器 v3.1.5")
    app.setOrganizationName("TelegramForwarder")
    
    font = QFont()
    font.setFamily("Microsoft YaHei")
    font.setPointSize(10)
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
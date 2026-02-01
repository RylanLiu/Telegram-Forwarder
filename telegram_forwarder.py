#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram 消息转发器 v3.0.0
现代化UI + 完整主题支持 + 无引用转发 + 沉浸式设计 + 消息类型过滤 + 消息同步管理
"""

import sys
import json
import asyncio
import logging
import traceback
import sqlite3
from pathlib import Path
from typing import Optional, Dict, List, Set, Tuple, Any
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

from telethon import TelegramClient, events
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


class Database:
    """数据库管理类"""
    
    def __init__(self, db_path="message_mapping.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 消息映射表
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
                           webpage_url: Optional[str] = None) -> int:
        """添加消息映射"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO message_mapping 
                (rule_id, source_chat_id, source_message_id, source_topic_id,
                 target_chat_id, target_message_id, target_topic_id,
                 message_type, file_id, text_content, has_webpage, webpage_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (rule_id, str(source_chat_id), source_message_id, source_topic_id,
                  str(target_chat_id), target_message_id, target_topic_id,
                  message_type, file_id, text_content, 1 if has_webpage else 0, webpage_url))
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
    
    def delete_mapping(self, mapping_id: int):
        """删除映射"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM message_mapping WHERE id = ?', (mapping_id,))
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
                              webpage_url: Optional[str] = None):
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
            "auto_start": False,
            "rules": [],
            "theme": "dark",
            "version": "3.0.0",  # 更新版本号
            "author": "DomAurora",
            "window_geometry": None,
            "window_state": None,
            "enable_message_sync": True,  # 新增：是否启用消息同步
            "show_tray_notifications": True,  # 新增：是否显示托盘通知
            "enable_deletion_sync": True  # 新增：是否启用删除同步
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
    
    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.client: Optional[TelegramClient] = None
        self.is_running = False
        self.auth_code = None
        self.password = None
        self.loop = None
        self.should_stop = False
        self.db = Database()  # 新增：数据库实例
        self.enable_sync = config.get('enable_message_sync', True)  # 是否启用消息同步
        self.enable_deletion_sync = config.get('enable_deletion_sync', True)  # 是否启用删除同步
        self.deleted_messages: Set[Tuple[str, int]] = set()  # 记录已删除的消息
    
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
                self.loop.close()
        except Exception as e:
            logger.warning(f"清理事件循环时出错: {e}")
        finally:
            self.loop = None
            self.client = None
            self.is_running = False
            self.stopped_signal.emit()
    
    async def start_client(self):
        """启动客户端"""
        try:
            self.log_signal.emit(f"[详细日志] 开始创建Telegram客户端...")
            self.log_signal.emit(f"[详细日志] 会话名称: {self.config['session_name']}")
            self.log_signal.emit(f"[详细日志] API ID: {self.config['api_id'][:8]}***")
            self.log_signal.emit(f"[详细日志] API Hash: {self.config['api_hash'][:8]}***")
            self.log_signal.emit(f"[详细日志] 消息同步: {'已启用' if self.enable_sync else '已禁用'}")
            self.log_signal.emit(f"[详细日志] 删除同步: {'已启用' if self.enable_deletion_sync else '已禁用'}")
            
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
    
    async def send_notification_count(self):
        """发送通知计数"""
        try:
            count = self.db.get_notifications_count()
            self.notification_count_signal.emit(count)
        except Exception as e:
            logger.exception("获取通知计数失败")
    
    async def start_deletion_monitoring(self):
        """开始监听消息删除（新增）"""
        try:
            self.log_signal.emit("[调试] 🔍 正在注册删除事件处理器...")
            
            # 监听DeleteMessages事件
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
        """处理消息删除事件（新增）"""
        try:
            self.log_signal.emit(f"[调试] 🔔 收到删除事件: {type(event).__name__}")
            
            # 获取删除的消息ID和聊天ID
            if hasattr(event, 'channel_id'):
                # 频道消息删除
                raw_chat_id = event.channel_id
                messages = event.messages
                is_channel = True
                self.log_signal.emit(f"[调试] 频道消息删除: channel_id={raw_chat_id}, messages={messages}")
            else:
                # 私聊或群组消息删除
                raw_chat_id = event.chat_id
                messages = event.messages
                is_channel = False
                self.log_signal.emit(f"[调试] 普通消息删除: chat_id={raw_chat_id}, messages={messages}")
            
            # 处理聊天ID格式
            chat_id_str = str(raw_chat_id)
            
            # 如果是频道，添加-100前缀用于数据库匹配
            if is_channel:
                chat_id_for_db = f"-100{chat_id_str}"
                self.log_signal.emit(f"[调试] 转换频道ID: {chat_id_str} -> {chat_id_for_db}")
            else:
                chat_id_for_db = chat_id_str
            
            self.log_signal.emit(f"[调试] 处理聊天ID: {chat_id_str} (数据库格式: {chat_id_for_db}), 消息ID列表: {messages}")
            
            for message_id in messages:
                self.log_signal.emit(f"[调试] 处理消息ID: {message_id}")
                
                # 检查是否为已处理的消息
                if (chat_id_str, message_id) in self.deleted_messages:
                    self.log_signal.emit(f"[调试] 消息 {message_id} 已在已处理列表中，跳过")
                    continue
                
                # 标记为已处理
                self.deleted_messages.add((chat_id_str, message_id))
                self.log_signal.emit(f"[调试] 消息 {message_id} 已添加到已处理列表")
                
                # 在数据库中查找映射
                mappings = []
                
                if is_channel:
                    # 使用新的方法查找频道消息映射
                    mappings = self.db.get_mapping_by_channel_message(raw_chat_id, message_id)
                    self.log_signal.emit(f"[调试] 使用频道消息查找方法，找到 {len(mappings)} 个映射")
                else:
                    # 普通聊天，先查目标消息
                    mapping = self.db.get_mapping_by_target(chat_id_for_db, message_id)
                    if mapping:
                        mappings.append(mapping)
                        self.log_signal.emit(f"[调试] 找到目标消息映射")
                    else:
                        # 再查源消息
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
                        
                        # 检查是源消息还是目标消息
                        source_chat_id = mapping['source_chat_id']
                        target_chat_id = mapping['target_chat_id']
                        source_message_id = mapping['source_message_id']
                        target_message_id = mapping['target_message_id']
                        
                        self.log_signal.emit(f"[调试] 映射详情: 源={source_chat_id}/{source_message_id}, 目标={target_chat_id}/{target_message_id}")
                        
                        # 检查删除的是源消息还是目标消息
                        is_source_deleted = False
                        is_target_deleted = False
                        
                        # 检查源消息
                        source_match = False
                        if is_channel:
                            # 频道ID比较需要特殊处理
                            source_chat_id_str = str(source_chat_id).lstrip('-100')
                            if source_chat_id_str == chat_id_str and source_message_id == message_id:
                                source_match = True
                        else:
                            if source_chat_id == chat_id_for_db and source_message_id == message_id:
                                source_match = True
                        
                        if source_match:
                            is_source_deleted = True
                            self.log_signal.emit(f"[调试] 检测到源消息被删除")
                        
                        # 检查目标消息
                        target_match = False
                        if is_channel:
                            # 频道ID比较需要特殊处理
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
                            # 源消息被删除，同步删除目标消息
                            await self.delete_target_message(mapping)
                            self.db.record_message_deletion(mapping['id'], chat_id_for_db, message_id, True)
                            self.log_signal.emit(f"[详细日志] ⚠ 源消息 {message_id} 被删除，已同步删除目标消息 {mapping['target_message_id']}")
                        elif is_target_deleted:
                            # 目标消息被删除，同步删除源消息
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
        """同步删除源消息（新增）"""
        try:
            source_chat_id = mapping['source_chat_id']
            source_message_id = mapping['source_message_id']
            
            self.log_signal.emit(f"[调试] 🔄 开始同步删除源消息: {source_chat_id}/{source_message_id}")
            
            # 修复：将字符串转换为正确的实体ID
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
            
            # 尝试删除消息
            result = await self.client.delete_messages(
                entity=entity_id,
                message_ids=[source_message_id]
            )
            
            self.log_signal.emit(f"[调试] 删除结果: {result}")
            
            # 从数据库中删除相关通知
            self.db.delete_notifications_by_mapping_id(mapping['id'])
            self.log_signal.emit(f"[调试] 已删除映射ID {mapping['id']} 的相关通知")
            
            # 从数据库中删除映射
            self.db.delete_mapping(mapping['id'])
            self.log_signal.emit(f"[调试] 已从数据库删除映射ID {mapping['id']}")
            
            self.log_signal.emit(f"[详细日志] ✓ 已同步删除源消息: {mapping['source_message_id']}")
            
            # 更新通知计数
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
        
        # 注册新消息处理器
        @self.client.on(events.NewMessage)
        async def handler(event):
            await self.handle_new_message(event, rules)
        
        # 注册消息编辑处理器（如果启用同步）
        if self.enable_sync:
            @self.client.on(events.MessageEdited)
            async def edit_handler(event):
                await self.handle_message_edit(event, rules)
    
    async def handle_new_message(self, event, rules: List[dict]):
        """处理新消息"""
        try:
            message: Message = event.message
            source_id = event.chat_id
            
            # 获取主题ID
            source_topic_id = None
            if message.reply_to and message.reply_to.reply_to_msg_id:
                try:
                    replied_msg = await message.get_reply_message()
                    if replied_msg and replied_msg.id == message.reply_to.reply_to_msg_id:
                        source_topic_id = message.reply_to.reply_to_msg_id
                except Exception as e:
                    logger.debug(f"获取回复消息失败: {e}")
            
            # 获取消息类型
            msg_type = self.get_message_type(message)
            
            # 匹配规则
            for rule in rules:
                if not rule.get('enabled', True):
                    continue
                
                if rule['source_id'] != source_id:
                    continue
                
                rule_source_topic = rule.get('source_topic_id')
                if rule_source_topic:
                    if rule_source_topic != source_topic_id:
                        continue
                
                # 检查消息类型过滤
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
            
            # 获取文件ID（如果有）
            file_id = self.get_file_id(message)
            text_content = message.text or ""
            has_webpage = isinstance(message.media, MessageMediaWebPage)
            webpage_url = None
            
            if has_webpage and message.media.webpage:
                webpage_url = message.media.webpage.url
            
            # 发送消息
            if isinstance(message.media, MessageMediaWebPage):
                if message.text:
                    sent_msg = await self.client.send_message(
                        target_id,
                        message.text,
                        **kwargs
                    )
                else:
                    self.log_signal.emit(f"[详细日志] ⚠ 忽略无文本的网页链接消息")
                    return
            elif message.media:
                sent_msg = await self.client.send_file(
                    target_id,
                    message.media,
                    caption=message.text or "",
                    **kwargs
                )
            elif message.text:
                sent_msg = await self.client.send_message(
                    target_id,
                    message.text,
                    **kwargs
                )
            else:
                self.log_signal.emit(f"[详细日志] ⚠ 忽略不支持的消息类型")
                return
            
            # 记录到数据库
            rule_id = rule.get('rule_id', self.config['rules'].index(rule))
            mapping_id = self.db.add_message_mapping(
                rule_id=rule_id,
                source_chat_id=message.chat_id,
                source_message_id=message.id,
                source_topic_id=message.reply_to.reply_to_msg_id if message.reply_to else None,
                target_chat_id=target_id,
                target_message_id=sent_msg.id,
                target_topic_id=target_topic_id,
                message_type=msg_type,
                file_id=file_id,
                text_content=text_content,
                has_webpage=has_webpage,
                webpage_url=webpage_url
            )
            
            source_name = rule.get('source_name', str(rule['source_id']))
            target_name = rule.get('target_name', str(target_id))
            
            log_msg = f"✓ [{source_name}] → [{target_name}] {msg_type}"
            if target_topic_id:
                log_msg += f" (→主题:{target_topic_id})"
            
            self.log_signal.emit(log_msg)
            
            # 调试日志
            self.log_signal.emit(f"[调试] 💾 已保存消息映射: 映射ID={mapping_id}, "
                               f"源消息={message.chat_id}/{message.id}, "
                               f"目标消息={target_id}/{sent_msg.id}")
            
        except FloodWaitError as e:
            self.log_signal.emit(f"[详细日志] ⚠ 触发限流,等待 {e.seconds} 秒...")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.exception("发送消息失败")
            self.log_signal.emit(f"[详细日志] ✗ 发送失败: {str(e)}")
    
    async def handle_message_edit(self, event, rules: List[dict]):
        """处理消息编辑"""
        try:
            message: Message = event.message
            source_id = event.chat_id
            
            # 查找对应的规则
            for rule in rules:
                if not rule.get('enabled', True) or rule['source_id'] != source_id:
                    continue
                
                # 检查主题ID
                rule_source_topic = rule.get('source_topic_id')
                if rule_source_topic:
                    # 需要检查消息是否在指定主题中
                    # 这里简化处理，实际需要更复杂的逻辑
                    pass
                
                # 查找数据库映射
                rule_id = rule.get('rule_id', self.config['rules'].index(rule))
                mapping = self.db.get_mapping_by_source(str(source_id), message.id, rule_id)
                
                if not mapping:
                    continue
                
                # 处理消息编辑
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
        
        # 判断编辑类型
        edit_type = self.determine_edit_type(old_text, new_text, old_file_id, new_file_id, msg_type)
        
        # 记录编辑历史
        self.db.record_edit_history(
            mapping_id=mapping_id,
            old_text=old_text,
            new_text=new_text,
            old_file_id=old_file_id,
            new_file_id=new_file_id,
            edit_type=edit_type
        )
        
        # 根据编辑类型处理
        if edit_type in ['text', 'text_only']:
            # 纯文本编辑或文本内容编辑，同步更新
            await self.edit_target_message(mapping, new_text, message)
            self.db.update_message_mapping(mapping_id, text_content=new_text)
            
        elif edit_type in ['file_added_to_text', 'file_changed', 'file_removed', 'webpage_changed']:
            # 文件相关或网页链接更改，记录日志和通知
            notification_data = await self.handle_special_edit_case(edit_type, mapping, message, old_file_id, new_file_id)
            if notification_data:
                # 发送编辑通知信号
                self.edit_notification_signal.emit(notification_data)
                # 更新通知计数
                await self.send_notification_count()
            
        elif edit_type == 'both':
            # 文本和文件同时更改
            if mapping['message_type'] == MessageType.TEXT.value:
                # 纯文本消息添加了文件
                notification_data = await self.handle_special_edit_case('file_added_to_text', mapping, message, old_file_id, new_file_id)
                if notification_data:
                    self.edit_notification_signal.emit(notification_data)
                    # 更新通知计数
                    await self.send_notification_count()
            else:
                # 带文件的消息文本被编辑
                await self.edit_target_message(mapping, new_text, message)
                self.db.update_message_mapping(mapping_id, text_content=new_text)
    
    async def edit_target_message(self, mapping: Dict, new_text: str, source_message: Message):
        """编辑目标消息"""
        try:
            target_chat_id = mapping['target_chat_id']
            target_message_id = mapping['target_message_id']
            
            # 修复：将字符串转换为正确的实体ID
            try:
                if str(target_chat_id).lstrip('-').isdigit():
                    entity_id = int(target_chat_id)
                else:
                    entity_id = target_chat_id
            except:
                entity_id = target_chat_id
            
            # 获取当前目标消息的媒体
            target_msg = await self.client.get_messages(
                entity=entity_id,
                ids=target_message_id
            )
            
            if not target_msg:
                self.log_signal.emit(f"[详细日志] ⚠ 目标消息不存在，无法编辑")
                return
            
            # 编辑消息
            await self.client.edit_message(
                entity=entity_id,
                message=target_message_id,
                text=new_text,
                file=target_msg.media if target_msg.media else None
            )
            
            self.log_signal.emit(f"[详细日志] ✓ 已同步编辑消息: {mapping['source_message_id']} → {target_message_id}")
            
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
            
            # 修复：将字符串转换为正确的实体ID
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
            
            # 从数据库中删除相关通知
            self.db.delete_notifications_by_mapping_id(mapping['id'])
            self.log_signal.emit(f"[调试] 已删除映射ID {mapping['id']} 的相关通知")
            
            # 从数据库中删除映射
            self.db.delete_mapping(mapping['id'])
            self.log_signal.emit(f"[调试] 已从数据库删除映射ID {mapping['id']}")
            
            self.log_signal.emit(f"[详细日志] ✓ 已同步删除目标消息: {mapping['target_message_id']}")
            
            # 更新通知计数
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
                
                # 创建通知记录
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
                
                # 发送托盘通知
                if self.config.get('show_tray_notifications', True):
                    self.notification_signal.emit("消息变更通知", notification_msg)
                
                # 返回通知数据
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
        
        # 检查网页链接更改
        if msg_type == MessageType.WEBPAGE.value and text_changed:
            # 这里可以添加更精确的网页链接检测逻辑
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
        if message.photo:
            return MessageType.PHOTO.value
        elif message.voice:
            return MessageType.VOICE.value
        elif message.video:
            return MessageType.VIDEO.value
        elif message.document and not any([message.voice, message.video, message.audio]):
            return MessageType.DOCUMENT.value
        elif message.sticker:
            return MessageType.STICKER.value
        elif message.audio:
            return MessageType.AUDIO.value
        elif isinstance(message.media, MessageMediaWebPage):
            return MessageType.WEBPAGE.value
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
    """通知管理对话框（新增）"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.db = Database()
        self.selected_notifications = []  # 存储选中的通知
        self.init_ui()
        self.load_notifications()
        
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("编辑通知管理")
        self.setMinimumSize(1200, 700)
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(30, 30, 30, 30)
        
        # 标题
        title_label = QLabel("📝 编辑通知管理")
        title_label.setStyleSheet("font-weight: 600; font-size: 22px; color: #2c3e50; margin-left: 4px;")
        main_layout.addWidget(title_label)
        
        # 说明文本
        description = QLabel("以下是需要手动处理的消息变更。请复制链接查看消息，处理完成后点击标记为已处理按钮。")
        description.setStyleSheet("color: #606266; font-size: 14px; margin-left: 4px;")
        description.setWordWrap(True)
        main_layout.addWidget(description)
        
        # 表格
        self.notifications_table = QTableWidget()
        self.notifications_table.setColumnCount(6)  # 减少一列，去掉操作列
        self.notifications_table.setHorizontalHeaderLabels([
            "", "ID", "变更类型", "描述", "创建时间", "状态"
        ])
        
        # 设置第一列为复选框列
        self.notifications_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.notifications_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.notifications_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.notifications_table.itemSelectionChanged.connect(self.on_selection_changed)
        main_layout.addWidget(self.notifications_table)
        
        # 按钮区域 - 上部操作按钮
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
        
        # 按钮区域 - 下部选中项操作按钮
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
        
        # 存储按钮引用
        self.copy_source_btn = copy_source_btn
        self.copy_target_btn = copy_target_btn
        self.mark_selected_btn = mark_selected_btn
        
        main_layout.addLayout(bottom_button_layout)
        
        self.setLayout(main_layout)
        
        # 应用父窗口主题
        if self.parent:
            self.apply_theme_from_parent()
    
    def on_selection_changed(self):
        """选中项变化时更新按钮状态"""
        selected_rows = set()
        for item in self.notifications_table.selectedItems():
            selected_rows.add(item.row())
        
        has_selection = len(selected_rows) > 0
        
        # 更新按钮状态
        self.copy_source_btn.setEnabled(has_selection)
        self.copy_target_btn.setEnabled(has_selection)
        self.mark_selected_btn.setEnabled(has_selection)
        
        # 更新选中的通知列表
        self.selected_notifications = []
        for row in selected_rows:
            notification_id_item = self.notifications_table.item(row, 1)  # ID列
            if notification_id_item:
                notification_id = int(notification_id_item.text())
                # 从数据库中获取完整的通知信息
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
            # 复选框列
            checkbox_item = QTableWidgetItem()
            checkbox_item.setCheckState(Qt.Unchecked)
            self.notifications_table.setItem(row, 0, checkbox_item)
            
            # ID
            id_item = QTableWidgetItem(str(notification['id']))
            self.notifications_table.setItem(row, 1, id_item)
            
            # 变更类型
            type_text = self.get_type_text(notification['notification_type'])
            type_item = QTableWidgetItem(type_text)
            self.notifications_table.setItem(row, 2, type_item)
            
            # 描述
            desc_item = QTableWidgetItem(notification['description'])
            self.notifications_table.setItem(row, 3, desc_item)
            
            # 创建时间
            time_item = QTableWidgetItem(notification['created_at'])
            self.notifications_table.setItem(row, 4, time_item)
            
            # 状态
            status_item = QTableWidgetItem("待处理")
            status_item.setForeground(QColor("#FFA500"))  # 橙色
            self.notifications_table.setItem(row, 5, status_item)
        
        # 重置选中状态
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
            # 处理不同的chat_id格式
            if str(chat_id).startswith('-100'):
                # 频道ID，转换为公开链接格式
                channel_id = int(chat_id) + 1000000000000
                return f"https://t.me/c/{channel_id}/{message_id}"
            elif str(chat_id).startswith('@'):
                # 用户名
                return f"https://t.me/{chat_id[1:]}/{message_id}"
            else:
                # 普通群组或私聊
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
        
        # 显示提示
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
        
        # 显示提示
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
            # 标记为已处理
            self.db.mark_notification_resolved(notification_id)
            count += 1
        
        # 重新加载列表
        self.load_notifications()
        
        # 显示提示
        msg_box = CustomMessageBox(self, self.parent.config.get('theme', 'dark') if self.parent else 'dark')
        msg_box.setWindowTitle("成功")
        msg_box.setText(f"已标记 {count} 个通知为已处理")
        msg_box.setIcon(QMessageBox.Information)
        msg_box.apply_theme()
        msg_box.exec_()
        
        # 通知父窗口更新计数
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
        
        # 通知父窗口更新计数
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
            "message_types": []  # 新增：消息类型过滤
        }
        self.parent = parent
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("编辑转发规则")
        self.setMinimumWidth(800)  # 增加宽度以适应左右布局
        self.setMinimumHeight(700)
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(30, 30, 30, 30)
        
        # 规则名称
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
        
        # 来源和目标设置的左右布局
        source_target_layout = QHBoxLayout()
        source_target_layout.setSpacing(20)
        
        # 来源设置 (左)
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
        
        # 目标设置 (右)
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
        
        # 消息类型过滤器 (下方)
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
        
        # 定义消息类型
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
        
        # 创建复选框
        self.type_checkboxes = {}
        row, col = 0, 0
        for i, (key, label) in enumerate(self.message_types.items()):
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)  # 默认全选
            if key in self.rule.get('message_types', []):
                checkbox.setChecked(True)
            elif self.rule.get('message_types') and len(self.rule['message_types']) > 0:
                # 如果已有配置但不是全选，则只选已配置的
                checkbox.setChecked(key in self.rule['message_types'])
            self.type_checkboxes[key] = checkbox
            type_layout.addWidget(checkbox, row, col)
            col += 1
            if col > 2:  # 每行3个
                col = 0
                row += 1
        
        type_group.setLayout(type_layout)
        main_layout.addWidget(type_group)
        
        # 启用状态
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
        
        # 按钮
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
        
        # 应用父窗口主题
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
            # 深色模式
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
            # 浅色模式
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
        
        # 获取选中的消息类型
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
        self.init_ui()
        self.init_tray_icon()  # 初始化托盘图标
        self.apply_theme()
        self.restore_window_state()
        
        # 检查待处理通知数量
        self.check_pending_notifications()
        
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
        
        # 设置页（需要添加新选项）
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
                # 使用默认图标
                pass
            
            # 创建托盘菜单
            tray_menu = QMenu()
            
            show_action = QAction("显示窗口", self)
            show_action.triggered.connect(self.show_normal)
            tray_menu.addAction(show_action)
            
            # 添加通知管理菜单项
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
            
            # 托盘图标点击事件
            self.tray_icon.activated.connect(self.on_tray_icon_activated)
            
            # 显示托盘图标
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
        
        # 标题区域
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
        
        subtitle = QLabel("智能消息转发 · 消息同步管理 · 24小时不间断运行")  # 更新副标题
        subtitle.setAlignment(Qt.AlignCenter)
        title_layout.addWidget(subtitle)
        
        layout.addLayout(title_layout)
        layout.addSpacing(30)
        
        # 状态卡片
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
        
        # 同步状态
        sync_status = QLabel(f"消息同步: {'✅ 已启用' if self.config.get('enable_message_sync', True) else '⭕ 已禁用'}")
        sync_status.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(sync_status)
        
        # 删除同步状态
        deletion_sync_status = QLabel(f"删除同步: {'✅ 已启用' if self.config.get('enable_deletion_sync', True) else '⭕ 已禁用'}")
        deletion_sync_status.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(deletion_sync_status)
        
        # 控制按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(20)
        
        self.start_btn = ModernButton("🚀 启动服务", primary=True)
        self.start_btn.setMinimumHeight(60)
        self.start_btn.setObjectName("startBtn")
        
        self.stop_btn = ModernButton("🛑 停止服务")
        self.stop_btn.setMinimumHeight(60)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setObjectName("stopBtn")
        
        # 通知管理按钮（新增）
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
        
        # 主题切换按钮区域
        theme_layout = QHBoxLayout()
        theme_layout.addStretch()
        
        self.theme_btn = ModernButton("🌙 深色模式" if self.config.get('theme') == 'dark' else "☀️ 浅色模式")
        self.theme_btn.setMinimumHeight(40)
        self.theme_btn.setObjectName("themeBtn")
        self.theme_btn.clicked.connect(self.toggle_theme)
        theme_layout.addWidget(self.theme_btn)
        
        theme_layout.addStretch()
        layout.addLayout(theme_layout)
        
        # 统计信息
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(25)
        
        # 规则数量卡片
        rules_card = self.create_stat_card(
            "📋 转发规则",
            str(len(self.config.get('rules', []))),
            "#3498db"
        )
        stats_layout.addWidget(rules_card)
        
        # 活跃规则卡片
        active_count = sum(1 for r in self.config.get('rules', []) if r.get('enabled', True))
        active_card = self.create_stat_card(
            "✅ 活跃规则",
            str(active_count),
            "#2ecc71"
        )
        stats_layout.addWidget(active_card)
        
        # 版本信息卡片
        version_card = self.create_stat_card(
            "📦 版本信息",
            self.config.get('version', '3.0.0'),  # 更新版本号
            "#9b59b6"
        )
        stats_layout.addWidget(version_card)
        
        layout.addLayout(stats_layout)
        layout.addStretch()
        
        self.tabs.addTab(tab, "🏠 主页")
        
        # 连接按钮信号
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
        
        # 标题和工具栏
        header = QHBoxLayout()
        
        title = QLabel("📋 转发规则管理")
        title.setObjectName("rulesTitle")
        header.addWidget(title)
        header.addStretch()
        
        add_btn = ModernButton("➕ 添加规则", primary=True)
        add_btn.setObjectName("addRuleBtn")
        header.addWidget(add_btn)
        
        layout.addLayout(header)
        
        # 规则列表
        self.rules_list = QListWidget()
        self.rules_list.setObjectName("rulesList")
        self.rules_list.itemDoubleClicked.connect(self.edit_rule)
        layout.addWidget(self.rules_list)
        
        # 底部工具栏
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
        
        # 连接信号
        add_btn.clicked.connect(self.add_rule)
        edit_btn.clicked.connect(self.edit_rule)
        delete_btn.clicked.connect(self.delete_rule)
        
        self.tabs.addTab(tab, "📋 规则")
    
    def create_settings_tab(self):
        """创建设置页（添加新选项）"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(24)
        
        # 标题
        title = QLabel("⚙️ 系统设置")
        title.setObjectName("settingsTitle")
        layout.addWidget(title)
        
        # 滚动区域
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
        
        account_group.setLayout(account_layout)
        scroll_layout.addWidget(account_group)
        
        # 消息同步设置（新增）- 调整为圆角风格
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
        
        self.show_notifications_check = QCheckBox("显示托盘通知")
        self.show_notifications_check.setChecked(self.config.get('show_tray_notifications', True))
        self.show_notifications_check.setObjectName("showNotificationsCheck")
        sync_layout.addWidget(self.show_notifications_check)
        
        sync_hint = QLabel("💡 消息同步功能可以：\n• 同步删除源消息/目标消息\n• 同步编辑纯文本消息\n• 记录文件/链接变更并通知")
        sync_hint.setWordWrap(True)
        sync_layout.addWidget(sync_hint)
        
        sync_group.setLayout(sync_layout)
        scroll_layout.addWidget(sync_group)
        
        # 程序信息
        info_group = QGroupBox("ℹ️ 程序信息")
        info_group.setObjectName("infoGroup")
        info_layout = QFormLayout()
        info_layout.setSpacing(15)
        info_layout.setContentsMargins(25, 25, 25, 25)
        info_layout.setLabelAlignment(Qt.AlignRight)
        
        version_label = QLabel(self.config.get('version', '3.0.0'))  # 更新版本号
        info_layout.addRow(QLabel("版本号:"), version_label)
        
        author_label = QLabel(self.config.get('author', 'DomAurora'))
        info_layout.addRow(QLabel("作者:"), author_label)
        
        info_group.setLayout(info_layout)
        scroll_layout.addWidget(info_group)
        
        scroll_layout.addStretch()
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # 保存按钮
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
        
        # 标题和工具栏
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
        
        # 日志文本
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
        """显示通知管理对话框（新增）"""
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
            
            # 显示消息类型过滤
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
        
        # 保存新设置
        self.config['enable_message_sync'] = self.enable_sync_check.isChecked()
        self.config['enable_deletion_sync'] = self.enable_deletion_sync_check.isChecked()
        self.config['show_tray_notifications'] = self.show_notifications_check.isChecked()
        
        Config.save(self.config)
        self.add_log("✅ 设置已保存")
        self.show_message("成功", "设置已保存", "info")
    
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
        
        self.add_log("[详细日志] 🔄 正在启动 Telegram 消息转发服务 v3.0.0...")
        self.add_log(f"[详细日志] 配置文件路径: {Path(Config.CONFIG_FILE).absolute()}")
        self.add_log(f"[详细日志] 消息同步: {'已启用' if self.config.get('enable_message_sync', True) else '已禁用'}")
        self.add_log(f"[详细日志] 删除同步: {'已启用' if self.config.get('enable_deletion_sync', True) else '已禁用'}")
        
        self.is_service_running = True
        self.worker = TelegramWorker(self.config)
        self.worker.log_signal.connect(self.add_log)
        self.worker.status_signal.connect(self.update_status)
        self.worker.error_signal.connect(self.show_error)
        self.worker.auth_code_signal.connect(self.request_auth_code)
        self.worker.password_signal.connect(self.request_password)
        self.worker.stopped_signal.connect(self.on_service_stopped)
        self.worker.notification_signal.connect(self.show_tray_notification)  # 连接通知信号
        self.worker.edit_notification_signal.connect(self.handle_edit_notification)  # 连接编辑通知信号
        self.worker.notification_count_signal.connect(self.update_notifications_button)  # 连接通知计数信号
        self.worker.start()
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        
        # 更新托盘菜单
        if self.tray_icon:
            menu = self.tray_icon.contextMenu()
            menu.actions()[3].setEnabled(False)  # 禁用启动
            menu.actions()[4].setEnabled(True)   # 启用停止
    
    def stop_service(self):
        """停止服务"""
        if not self.is_service_running or not self.worker:
            return
            
        self.add_log("[详细日志] 🔄 正在停止消息转发服务...")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        
        if self.worker:
            self.worker.should_stop = True
            QTimer.singleShot(100, self.check_worker_status)
        
        # 更新托盘菜单
        if self.tray_icon:
            menu = self.tray_icon.contextMenu()
            menu.actions()[3].setEnabled(True)   # 启用启动
            menu.actions()[4].setEnabled(False)  # 禁用停止
    
    def handle_edit_notification(self, notification_data: dict):
        """处理编辑通知（新增）"""
        # 更新通知按钮文本
        self.check_pending_notifications()
        
        # 如果通知对话框已打开，刷新它
        if self.notifications_dialog and self.notifications_dialog.isVisible():
            self.notifications_dialog.load_notifications()
    
    def check_worker_status(self):
        """检查工作线程状态"""
        if self.worker and self.worker.isRunning():
            # 如果工作线程还在运行，继续检查
            QTimer.singleShot(100, self.check_worker_status)
    
    def on_service_stopped(self):
        """服务停止完成时的处理"""
        self.is_service_running = False
        self.worker = None
        self.update_status("已停止")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.add_log("[详细日志] ✅ 消息转发服务已停止")
        
        # 更新托盘菜单
        if self.tray_icon:
            menu = self.tray_icon.contextMenu()
            menu.actions()[3].setEnabled(True)   # 启用启动
            menu.actions()[4].setEnabled(False)  # 禁用停止
    
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
                3000  # 3秒
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
        # 保存窗口几何信息
        self.config['window_geometry'] = {
            'x': self.x(),
            'y': self.y(),
            'width': self.width(),
            'height': self.height()
        }
        
        # 保存窗口状态（最大化/最小化）
        self.config['window_state'] = 'maximized' if self.isMaximized() else 'normal'
        
        # 保存到配置文件
        Config.save(self.config)
    
    def restore_window_state(self):
        """恢复窗口状态"""
        if 'window_geometry' in self.config and self.config['window_geometry']:
            geom = self.config['window_geometry']
            
            # 确保窗口不会超出屏幕
            screen_geometry = QApplication.primaryScreen().availableGeometry()
            
            # 恢复位置和大小，确保在屏幕内
            x = max(0, min(geom['x'], screen_geometry.width() - 400))
            y = max(0, min(geom['y'], screen_geometry.height() - 400))
            width = min(geom['width'], screen_geometry.width())
            height = min(geom['height'], screen_geometry.height())
            
            self.setGeometry(x, y, width, height)
        
        # 恢复窗口状态
        if self.config.get('window_state') == 'maximized':
            self.showMaximized()
    
    def apply_theme(self):
        """应用主题"""
        theme = self.config.get('theme', 'dark')
        
        # 设置窗口标题栏颜色
        if theme == 'dark':
            # 深色主题 - 标题栏适配深色模式
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
                QLineEdit[objectName="phoneEdit"] {{
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
                    /* 修改：调大日志文本字号 */
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
            # 浅色主题 - 标题栏适配浅色模式
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
                QLineEdit[objectName="phoneEdit"] {{
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
                    /* 修改：调大日志文本字号 */
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
    
    def closeEvent(self, event):
        """关闭事件"""
        # 保存窗口状态
        self.save_window_state()
        
        if self.worker and self.worker.isRunning():
            msg_box = CustomMessageBox(self, self.config.get('theme', 'dark'))
            msg_box.setWindowTitle("确认退出")
            msg_box.setText("服务正在运行,确定要退出吗?")
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.apply_theme()
            
            reply = msg_box.exec_()
            
            if reply == QMessageBox.Yes:
                self.stop_service()
                # 等待工作线程完成
                while self.worker and self.worker.isRunning():
                    QApplication.processEvents()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 设置应用信息
    app.setApplicationName("Telegram 消息转发器 v3.0.0")
    app.setOrganizationName("TelegramForwarder")
    
    # 设置全局字体
    font = QFont()
    font.setFamily("Microsoft YaHei")
    font.setPointSize(10)
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
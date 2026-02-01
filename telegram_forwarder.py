#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram 消息转发器 v2.2
现代化UI + 完整主题支持 + 无引用转发 + 沉浸式设计
"""

import sys
import json
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit, QListWidget, QListWidgetItem,
    QDialog, QFormLayout, QComboBox, QCheckBox, QGroupBox, QTabWidget,
    QMessageBox, QInputDialog, QSpinBox, QFrame, QScrollArea
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QPalette, QColor, QIcon, QPainter, QPainterPath

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.tl.types import Message, MessageMediaPhoto, MessageMediaDocument

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
            "theme": "dark",  # 默认改为深色模式
            "version": "2.2",
            "author": "DomAurora"
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
    stopped_signal = pyqtSignal()  # 新增：停止完成信号
    
    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.client: Optional[TelegramClient] = None
        self.is_running = False
        self.auth_code = None
        self.password = None
        self.loop = None
        self.should_stop = False  # 新增：控制停止的标志
        
    def run(self):
        """运行工作线程"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            self.loop.run_until_complete(self.start_client())
        except Exception as e:
            if not self.should_stop:  # 如果不是主动停止导致的错误
                logger.exception("工作线程异常")
                self.error_signal.emit(f"错误: {str(e)}")
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
            self.stopped_signal.emit()  # 发出停止完成信号
    
    async def start_client(self):
        """启动客户端"""
        try:
            # 创建客户端（无代理）
            self.client = TelegramClient(
                self.config['session_name'],
                self.config['api_id'],
                self.config['api_hash']
            )
            
            await self.client.connect()
            self.log_signal.emit("✓ 连接到 Telegram 服务器")
            
            # 认证
            if not await self.client.is_user_authorized():
                await self.authenticate()
            
            self.log_signal.emit(f"✓ 已登录账户: {self.config['phone']}")
            self.status_signal.emit("运行中")
            
            # 注册消息处理器
            await self.register_handlers()
            
            self.is_running = True
            self.log_signal.emit("✓ 消息转发服务已启动")
            
            # 保持运行
            while not self.should_stop:
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    break
            
        except Exception as e:
            logger.exception("启动客户端失败")
            self.error_signal.emit(f"启动失败: {str(e)}")
            self.status_signal.emit("已停止")
        finally:
            await self.disconnect_client()
    
    async def disconnect_client(self):
        """断开客户端连接"""
        if self.client and self.client.is_connected():
            try:
                await self.client.disconnect()
                self.log_signal.emit("✓ 已断开 Telegram 连接")
            except Exception as e:
                logger.warning(f"断开连接时出错: {e}")
    
    async def authenticate(self):
        """处理认证流程"""
        await self.client.send_code_request(self.config['phone'])
        self.log_signal.emit("→ 验证码已发送到您的 Telegram")
        
        # 请求验证码
        self.auth_code_signal.emit()
        while self.auth_code is None and not self.should_stop:
            await asyncio.sleep(0.1)
        
        if self.should_stop:
            return
        
        try:
            await self.client.sign_in(self.config['phone'], self.auth_code)
        except SessionPasswordNeededError:
            # 需要两步验证密码
            self.log_signal.emit("→ 需要两步验证密码")
            self.password_signal.emit()
            
            while self.password is None and not self.should_stop:
                await asyncio.sleep(0.1)
            
            if self.should_stop:
                return
            
            await self.client.sign_in(password=self.password)
        
        self.auth_code = None
        self.password = None
    
    async def register_handlers(self):
        """注册消息处理器"""
        rules = self.config.get('rules', [])
        
        if not rules:
            self.log_signal.emit("⚠ 没有配置转发规则")
            return
        
        self.log_signal.emit(f"✓ 加载了 {len(rules)} 条转发规则")
        
        @self.client.on(events.NewMessage)
        async def handler(event):
            await self.handle_message(event, rules)
    
    async def handle_message(self, event, rules: List[dict]):
        """处理新消息"""
        try:
            message: Message = event.message
            source_id = event.chat_id
            
            # 正确获取主题ID
            source_topic_id = None
            if message.reply_to and message.reply_to.reply_to_msg_id:
                try:
                    replied_msg = await message.get_reply_message()
                    if replied_msg and replied_msg.id == message.reply_to.reply_to_msg_id:
                        source_topic_id = message.reply_to.reply_to_msg_id
                except:
                    pass
            
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
                
                await self.send_message(message, rule)
                
        except Exception as e:
            logger.exception("处理消息失败")
            self.log_signal.emit(f"✗ 处理消息失败: {str(e)}")
    
    async def send_message(self, message: Message, rule: dict):
        """发送消息(不带转发引用)"""
        try:
            target_id = rule['target_id']
            target_topic_id = rule.get('target_topic_id')
            
            kwargs = {}
            
            if target_topic_id:
                kwargs['reply_to'] = target_topic_id
            
            if message.media:
                await self.client.send_file(
                    target_id,
                    message.media,
                    caption=message.text or "",
                    **kwargs
                )
            elif message.text:
                await self.client.send_message(
                    target_id,
                    message.text,
                    **kwargs
                )
            
            source_name = rule.get('source_name', str(rule['source_id']))
            target_name = rule.get('target_name', str(target_id))
            msg_type = self.get_message_type(message)
            
            log_msg = f"✓ [{source_name}] → [{target_name}] {msg_type}"
            if target_topic_id:
                log_msg += f" (→主题:{target_topic_id})"
            
            self.log_signal.emit(log_msg)
            
        except FloodWaitError as e:
            self.log_signal.emit(f"⚠ 触发限流,等待 {e.seconds} 秒...")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.exception("发送消息失败")
            self.log_signal.emit(f"✗ 发送失败: {str(e)}")
    
    @staticmethod
    def get_message_type(message: Message) -> str:
        """获取消息类型"""
        if message.photo:
            return "图片"
        elif message.voice:
            return "语音"
        elif message.video:
            return "视频"
        elif message.document:
            return "文件"
        elif message.sticker:
            return "贴纸"
        elif message.audio:
            return "音频"
        elif message.text:
            return "文本"
        else:
            return "其他"
    
    def stop(self):
        """停止客户端"""
        self.should_stop = True
        if self.client and self.client.is_connected():
            # 在工作线程中执行断开连接
            asyncio.run_coroutine_threadsafe(
                self.disconnect_client(),
                self.loop
            )


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
            "enabled": True
        }
        self.parent = parent
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("编辑转发规则")
        self.setMinimumWidth(600)
        self.setMinimumHeight(650)
        
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # 规则名称
        name_label = QLabel("规则名称")
        name_label.setStyleSheet("font-weight: 600; font-size: 15px; color: #2c3e50; margin-left: 4px;")
        layout.addWidget(name_label)
        
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
        layout.addWidget(self.name_edit)
        
        # 来源设置
        source_group = QGroupBox("📥 来源设置")
        source_group.setStyleSheet("""
            QGroupBox {
                font-weight: 600;
                font-size: 14px;
                border: 2px solid #e4e7ed;
                border-radius: 12px;
                margin-top: 12px;
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
        
        source_group.setLayout(source_layout)
        layout.addWidget(source_group)
        
        # 目标设置
        target_group = QGroupBox("📤 目标设置")
        target_group.setStyleSheet("""
            QGroupBox {
                font-weight: 600;
                font-size: 14px;
                border: 2px solid #e4e7ed;
                border-radius: 12px;
                margin-top: 12px;
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
        
        target_group.setLayout(target_layout)
        layout.addWidget(target_group)
        
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
        layout.addWidget(self.enabled_check)
        
        layout.addStretch()
        
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
        
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
        
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
                    margin-top: 12px;
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
        
        self.rule['enabled'] = self.enabled_check.isChecked()
        
        return self.rule


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.config = Config.load()
        self.worker: Optional[TelegramWorker] = None
        self.is_service_running = False  # 新增：服务运行状态标志
        self.init_ui()
        self.apply_theme()
        
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("Telegram 消息转发器")
        self.setMinimumSize(1100, 800)
        
        # 设置程序图标
        try:
            self.setWindowIcon(QIcon('app.ico'))
        except:
            pass
        
        # 设置窗口标志
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        
        # 中心窗口
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 标签页
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
        
        # 设置页
        self.create_settings_tab()
        
        # 日志页
        self.create_log_tab()
        
        # 状态栏
        self.status_label = QLabel("未连接")
        self.statusBar().addPermanentWidget(self.status_label)
    
    def create_home_tab(self):
        """创建主页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(30)
        
        # 标题区域
        title_layout = QVBoxLayout()
        title_layout.setSpacing(8)
        
        title = QLabel("Telegram 消息转发器")
        title_font = QFont()
        title_font.setPointSize(34)
        title_font.setBold(True)
        title_font.setWeight(QFont.Black)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        title_layout.addWidget(title)
        
        subtitle = QLabel("智能消息转发 · 支持主题对话 · 24小时不间断运行")
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
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
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
            self.config.get('version', '2.2'),
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
        """创建设置页"""
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
        
        # 程序信息
        info_group = QGroupBox("ℹ️ 程序信息")
        info_group.setObjectName("infoGroup")
        info_layout = QFormLayout()
        info_layout.setSpacing(15)
        info_layout.setContentsMargins(25, 25, 25, 25)
        info_layout.setLabelAlignment(Qt.AlignRight)
        
        version_label = QLabel(self.config.get('version', '2.2'))
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
        log_font.setPointSize(12)
        self.log_text.setFont(log_font)
        self.log_text.setObjectName("logText")
        layout.addWidget(self.log_text)
        
        self.tabs.addTab(tab, "📜 日志")
    
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
            
            text = f"{status}  {name}\n    📥 {source}{source_topic}  →  📤 {target}{target_topic}"
            
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
        
        self.add_log("🔄 正在启动服务...")
        
        self.is_service_running = True
        self.worker = TelegramWorker(self.config)
        self.worker.log_signal.connect(self.add_log)
        self.worker.status_signal.connect(self.update_status)
        self.worker.error_signal.connect(self.show_error)
        self.worker.auth_code_signal.connect(self.request_auth_code)
        self.worker.password_signal.connect(self.request_password)
        self.worker.stopped_signal.connect(self.on_service_stopped)  # 连接停止完成信号
        self.worker.start()
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
    
    def stop_service(self):
        """停止服务"""
        if not self.is_service_running or not self.worker:
            return
            
        self.add_log("🔄 正在停止服务...")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        
        # 设置停止标志并等待工作线程完成
        if self.worker:
            self.worker.stop()
            # 等待工作线程完成，但不阻塞UI线程
            QTimer.singleShot(100, self.check_worker_status)
    
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
        self.add_log("✅ 服务已停止")
    
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
                    font-size: 13px;
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
                    font-size: 13px;
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
    app.setApplicationName("Telegram 消息转发器")
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
"""编号资料管理器 - PyQt6重构版
基于原customtkinter版本重构，保持所有功能完整
作者：Rylan
日期：2026年02月11日
PyQt6重构版本 - 添加预设配置功能和字段标签存储
"""
import sys
import os
import json
import time
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QGridLayout, QLabel, QLineEdit, QTextEdit, QPushButton,
                             QFrame, QScrollArea, QMessageBox, QFileDialog, QSizePolicy,
                             QGroupBox, QRadioButton, QButtonGroup, QDialog, QProgressDialog,
                             QComboBox, QSpinBox, QCheckBox, QListWidget, QListWidgetItem,
                             QInputDialog, QMenu)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize, QRect, QPropertyAnimation, QEasingCurve, QUrl, QPoint
from PyQt6.QtGui import QFont, QPalette, QColor, QClipboard, QKeyEvent, QIcon, QPainter, QLinearGradient, QDesktopServices, QAction

# ========== 预设配置管理器 ==========
class PresetManager:
    """预设配置管理类 - 增加资源字段和前缀预设保存"""
    def __init__(self):
        self.presets_file = "field_presets.json"
        self.presets = self.load_presets()
        
    def load_presets(self) -> Dict:
        """加载所有预设"""
        try:
            if os.path.exists(self.presets_file):
                with open(self.presets_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"加载预设失败: {e}")
        return {}
    
    def save_preset(self, name: str, field_labels: Dict, field_visibility: Dict = None, 
                   resource_text: str = "", prefix_text: str = "") -> bool:
        """保存预设 - 增加资源文本框内容和编号前缀保存"""
        try:
            preset_data = {
                "labels": field_labels.copy(),
                "visibility": field_visibility.copy() if field_visibility else {},
                "resource_text": resource_text,  # 保存资源文本框内容
                "prefix_text": prefix_text       # 保存编号前缀
            }
            self.presets[name] = preset_data
            with open(self.presets_file, 'w', encoding='utf-8') as f:
                json.dump(self.presets, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存预设失败: {e}")
            return False
    
    def delete_preset(self, name: str) -> bool:
        """删除预设"""
        if name in self.presets:
            del self.presets[name]
            try:
                with open(self.presets_file, 'w', encoding='utf-8') as f:
                    json.dump(self.presets, f, ensure_ascii=False, indent=2)
                return True
            except Exception as e:
                print(f"删除预设失败: {e}")
        return False
    
    def get_preset_names(self) -> List[str]:
        """获取所有预设名称"""
        return list(self.presets.keys())
    
    def get_preset(self, name: str) -> Dict:
        """获取指定预设"""
        preset_data = self.presets.get(name, {})
        if isinstance(preset_data, dict):
            # 兼容旧格式：如果是直接存储的标签字典，转换为新格式
            if "labels" not in preset_data and "visibility" not in preset_data:
                return {
                    "labels": preset_data,
                    "visibility": {},
                    "resource_text": "",
                    "prefix_text": ""
                }
        return preset_data


# ========== 预设配置对话框（已废弃，保留空类以兼容）==========
class PresetDialog(QDialog):
    """预设管理对话框 - 已废弃，保留空类以兼容"""
    def __init__(self, preset_manager, current_labels, parent=None):
        super().__init__(parent)
        self.preset_manager = preset_manager
        self.current_labels = current_labels
        self.selected_preset = None
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("字段标签预设管理")
        self.setGeometry(300, 300, 500, 400)
        self.setStyleSheet("""
            QDialog {
                background-color: #252525;
            }
            QLabel {
                color: #E0E0E0;
            }
            QLineEdit {
                background-color: #2A2A2A;
                border: 1px solid #3A3A3A;
                border-radius: 4px;
                color: #E0E0E0;
                padding: 6px;
            }
            QListWidget {
                background-color: #2A2A2A;
                border: 1px solid #3A3A3A;
                border-radius: 4px;
                color: #E0E0E0;
            }
            QPushButton {
                background-color: #4A4A4A;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #5A5A5A;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # 标题
        title = QLabel("字段标签预设管理")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # 当前配置显示
        current_frame = QFrame()
        current_layout = QVBoxLayout(current_frame)
        current_layout.addWidget(QLabel("当前配置："))
        
        labels_text = f"主演: {self.current_labels.get('actor', '主演')} | 来源: {self.current_labels.get('source', '来源')} | 记录: {self.current_labels.get('record', '记录')}"
        self.current_label = QLabel(labels_text)
        self.current_label.setStyleSheet("background-color: #333333; padding: 8px; border-radius: 4px;")
        current_layout.addWidget(self.current_label)
        layout.addWidget(current_frame)
        
        # 预设列表
        list_label = QLabel("已保存的预设：")
        layout.addWidget(list_label)
        
        self.preset_list = QListWidget()
        self.preset_list.itemClicked.connect(self.on_preset_selected)
        layout.addWidget(self.preset_list)
        
        # 预设名称输入
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("预设名称："))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("输入预设名称")
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.save_btn = QPushButton("💾 保存为预设")
        self.save_btn.clicked.connect(self.save_preset)
        button_layout.addWidget(self.save_btn)
        
        self.apply_btn = QPushButton("✅ 应用预设")
        self.apply_btn.clicked.connect(self.apply_preset)
        self.apply_btn.setEnabled(False)
        button_layout.addWidget(self.apply_btn)
        
        self.delete_btn = QPushButton("🗑️ 删除预设")
        self.delete_btn.clicked.connect(self.delete_preset)
        self.delete_btn.setEnabled(False)
        button_layout.addWidget(self.delete_btn)
        
        button_layout.addStretch()
        
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.close)
        button_layout.addWidget(self.close_btn)
        
        layout.addLayout(button_layout)
        
        # 加载预设列表
        self.load_preset_list()
        
    def load_preset_list(self):
        """加载预设列表"""
        self.preset_list.clear()
        for name in self.preset_manager.get_preset_names():
            self.preset_list.addItem(name)
            
    def on_preset_selected(self, item):
        """预设选中事件"""
        self.selected_preset = item.text()
        self.apply_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)
        self.name_input.setText(item.text())
        
    def save_preset(self):
        """保存预设"""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入预设名称")
            return
            
        if self.preset_manager.save_preset(name, self.current_labels.copy()):
            QMessageBox.information(self, "成功", f"预设 '{name}' 保存成功")
            self.load_preset_list()
        else:
            QMessageBox.critical(self, "错误", "保存失败")
            
    def apply_preset(self):
        """应用预设"""
        if self.selected_preset:
            preset = self.preset_manager.get_preset(self.selected_preset)
            self.parent().apply_preset_config(preset)
            self.accept()
            
    def delete_preset(self):
        """删除预设"""
        if self.selected_preset:
            reply = QMessageBox.question(self, "确认删除", 
                                       f"确定要删除预设 '{self.selected_preset}' 吗？",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                if self.preset_manager.delete_preset(self.selected_preset):
                    self.load_preset_list()
                    self.apply_btn.setEnabled(False)
                    self.delete_btn.setEnabled(False)
                    self.name_input.clear()
                    self.selected_preset = None


# ========== 数据管理器类（优化数据库结构）==========
class DataManager:
    """数据管理类 - 使用SQLite数据库优化搜索性能
       优化：存储字段标签配置，每条记录独立保存标签配置
    """
    def __init__(self):
        self.data_dir = ""
        self.db_path = ""
        self.conn = None
        
        # 保留文件缓存用于兼容性
        self.file_cache: Dict[str, Dict] = {}
        self.cache_timestamp = 0
        self.cache_expiry = 5

    def set_data_dir(self, directory: str) -> None:
        """设置数据目录并初始化数据库"""
        self.data_dir = directory
        if directory:
            # 数据库文件放在数据目录下
            self.db_path = os.path.join(directory, ".records.db")
            self._init_database()
            self.load_cache(force=True)

    def _init_database(self) -> None:
        """初始化数据库 - 简化结构"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            cursor = self.conn.cursor()
            
            # 创建记录表 - 存储完整的JSON数据和字段标签配置
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS records (
                    code TEXT PRIMARY KEY,
                    json_data TEXT NOT NULL,
                    field_labels TEXT,  -- 存储该记录保存时的字段标签配置
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建搜索索引 - 只对常用字段建立简单索引
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_updated ON records(updated_at)
            ''')
            
            self.conn.commit()
        except Exception as e:
            print(f"数据库初始化失败: {e}")

    def load_cache(self, force: bool = False) -> None:
        """加载文件缓存（保持兼容性）"""
        current_time = time.time()
        if not force and current_time - self.cache_timestamp < self.cache_expiry:
            return

        self.file_cache.clear()
        if not self.data_dir or not os.path.exists(self.data_dir):
            return

        try:
            for filename in os.listdir(self.data_dir):
                if filename.endswith(".json"):
                    file_path = os.path.join(self.data_dir, filename)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    key = filename.replace(".json", "")
                    self.file_cache[key] = data
            self.cache_timestamp = current_time
        except Exception as e:
            print(f"加载缓存失败: {e}")

    def get_next_code(self, prefix: str) -> str:
        """获取下一个编号"""
        if not self.data_dir:
            return ""
        
        max_num = 0
        for name in self.file_cache.keys():
            if name.startswith(prefix):
                try:
                    num_part = name[len(prefix):len(prefix)+6]
                    n = int(num_part)
                    max_num = max(max_num, n)
                except (ValueError, IndexError):
                    continue
        
        return prefix + str(max_num + 1).zfill(6)

    def save_record(self, data: Dict, field_labels: Dict = None) -> bool:
        """保存记录（同时保存到JSON和数据库）
           增加参数：field_labels - 保存时的字段标签配置
           JSON文件使用字段标签作为键名，数据库保持固定键名
        """
        try:
            if not self.data_dir:
                return False
            
            code = data.get("编号", "")
            if not code:
                return False
            
            # 1. 保存到JSON文件 - 使用字段标签作为键名
            json_data_for_file = {
                "编号": data.get("编号", ""),
                "创建时间": data.get("创建时间", "")
            }
            
            # 根据字段标签配置添加数据（使用标签作为键名）
            if field_labels:
                # 主演字段 - 使用标签作为键名
                actor_label = field_labels.get("actor", "主演")
                if data.get("主演"):
                    json_data_for_file[actor_label] = data.get("主演", "")
                
                # 来源字段 - 使用标签作为键名
                source_label = field_labels.get("source", "来源")
                if data.get("来源"):
                    json_data_for_file[source_label] = data.get("来源", "")
                
                # 标签字段 - 固定为"标签"
                if data.get("标签"):
                    json_data_for_file["标签"] = data.get("标签", [])
                
                # 记录字段 - 使用标签作为键名
                record_label = field_labels.get("record", "记录")
                if data.get("记录"):
                    json_data_for_file[record_label] = data.get("记录", "")
                
                # 资源字段 - 固定为"资源"
                if data.get("资源"):
                    json_data_for_file["资源"] = data.get("资源", "")
                
                # 简介字段 - 固定为"简介"
                if data.get("简介"):
                    json_data_for_file["简介"] = data.get("简介", "")
            else:
                # 如果没有字段标签配置，使用默认键名
                json_data_for_file.update({k: v for k, v in data.items() if k not in ["编号", "创建时间"]})
            
            file_path = os.path.join(self.data_dir, f"{code}.json")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(json_data_for_file, f, ensure_ascii=False, indent=2)
            
            # 2. 保存到数据库 - 保持固定键名，完全不变
            if self.conn:
                cursor = self.conn.cursor()
                
                # 数据库保存固定格式的数据
                db_data = {
                    "编号": data.get("编号", ""),
                    "创建时间": data.get("创建时间", ""),
                    "主演": data.get("主演", ""),
                    "来源": data.get("来源", ""),
                    "标签": data.get("标签", []),
                    "记录": data.get("记录", ""),
                    "资源": data.get("资源", ""),
                    "简介": data.get("简介", "")
                }
                
                json_data = json.dumps(db_data, ensure_ascii=False)
                field_labels_json = json.dumps(field_labels, ensure_ascii=False) if field_labels else None
                
                # 使用REPLACE实现插入或更新
                cursor.execute('''
                    REPLACE INTO records 
                    (code, json_data, field_labels, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ''', (code, json_data, field_labels_json))
                
                self.conn.commit()
            
            # 3. 更新缓存（使用固定键名以保持兼容）
            self.file_cache[code] = {
                "编号": data.get("编号", ""),
                "创建时间": data.get("创建时间", ""),
                "主演": data.get("主演", ""),
                "来源": data.get("来源", ""),
                "标签": data.get("标签", []),
                "记录": data.get("记录", ""),
                "资源": data.get("资源", ""),
                "简介": data.get("简介", "")
            }
            return True
        except Exception as e:
            print(f"保存失败: {e}")
            return False

    def delete_record(self, code: str) -> bool:
        """删除记录（同时从JSON和数据库删除）"""
        try:
            if not self.data_dir:
                return False
            
            # 1. 删除JSON文件
            file_path = os.path.join(self.data_dir, f"{code}.json")
            if os.path.exists(file_path):
                os.remove(file_path)
            
            # 2. 从数据库删除
            if self.conn:
                cursor = self.conn.cursor()
                cursor.execute('DELETE FROM records WHERE code = ?', (code,))
                self.conn.commit()
            
            # 3. 从缓存中移除
            if code in self.file_cache:
                del self.file_cache[code]
            
            return True
        except Exception as e:
            print(f"删除失败: {e}")
            return False

    def search_records(self, keyword: str) -> List[str]:
        """搜索记录 - 使用JSON字段全文搜索"""
        if not keyword:
            # 空搜索返回所有记录（按更新时间倒序）
            if self.conn:
                cursor = self.conn.cursor()
                cursor.execute('SELECT code FROM records ORDER BY updated_at DESC')
                return [row[0] for row in cursor.fetchall()]
            else:
                return sorted(self.file_cache.keys(), reverse=True)
        
        keyword = keyword.lower()
        
        # 使用数据库JSON搜索
        if self.conn:
            try:
                cursor = self.conn.cursor()
                # 由于SQLite JSON1扩展可能不可用，使用简单的LIKE搜索
                # 通过搜索json_data字符串来查找所有字段
                search_pattern = f'%{keyword}%'
                cursor.execute('''
                    SELECT code FROM records 
                    WHERE json_data LIKE ?
                    ORDER BY updated_at DESC
                ''', (search_pattern,))
                
                return [row[0] for row in cursor.fetchall()]
            except Exception as e:
                print(f"数据库搜索失败，使用缓存搜索: {e}")
        
        # 降级到内存搜索（如果数据库不可用）
        results = []
        for name, data in self.file_cache.items():
            if (keyword in data.get("编号", "").lower() 
                or keyword in data.get("主演", "").lower() 
                or keyword in data.get("来源", "").lower()
                or keyword in data.get("记录", "").lower()
                or keyword in data.get("资源", "").lower()
                or keyword in data.get("简介", "").lower()
                or any(keyword in tag.lower() for tag in data.get("标签", []))):
                results.append(name)
        return sorted(results, reverse=True)

    def get_record(self, code: str) -> Dict:
        """获取指定编号的记录"""
        # 优先从数据库获取
        if self.conn:
            try:
                cursor = self.conn.cursor()
                cursor.execute('SELECT json_data FROM records WHERE code = ?', (code,))
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0])
            except Exception as e:
                print(f"数据库读取失败，使用缓存: {e}")
        
        # 降级到缓存
        return self.file_cache.get(code, {})
    
    def get_record_with_labels(self, code: str) -> Tuple[Dict, Dict]:
        """获取指定编号的记录及其保存时的字段标签配置"""
        if self.conn:
            try:
                cursor = self.conn.cursor()
                cursor.execute('SELECT json_data, field_labels FROM records WHERE code = ?', (code,))
                row = cursor.fetchone()
                if row:
                    record = json.loads(row[0])
                    labels = json.loads(row[1]) if row[1] else {}
                    return record, labels
            except Exception as e:
                print(f"数据库读取记录和标签失败: {e}")
        
        # 降级到缓存
        record = self.file_cache.get(code, {})
        return record, {}
    
    def __del__(self):
        """析构时关闭数据库连接"""
        if self.conn:
            self.conn.close()


# ========== 自定义组件（保持不变）==========
class ToastMessage(QWidget):
    """悬浮提示组件 - 使用柔和颜色"""
    def __init__(self, parent=None, message="", message_type="info"):
        super().__init__(parent)
        self.message = message
        self.message_type = message_type
        self.init_ui()
        
    def init_ui(self):
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        if self.message_type == "success":
            bg_color = "#4CAF50"
            border_color = "#388E3C"
        elif self.message_type == "warning":
            bg_color = "#FF9800"
            border_color = "#F57C00"
        elif self.message_type == "error":
            bg_color = "#F44336"
            border_color = "#D32F2F"
        else:
            bg_color = "#2196F3"
            border_color = "#1976D2"
        
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 6px;
                padding: 8px 12px;
            }}
            QLabel {{
                color: white;
                font-size: 13px;
                font-weight: 500;
            }}
        """)
        
        layout = QHBoxLayout(self)
        self.label = QLabel(self.message)
        self.label.setStyleSheet("color: white; font-weight: 500;")
        layout.addWidget(self.label)
        
        self.adjustSize()
        
    def show_toast(self, duration=1800):
        self.show()
        if self.parent():
            parent_rect = self.parent().geometry()
            x = parent_rect.x() + parent_rect.width() - self.width() - 20
            y = parent_rect.y()
            self.move(x, y)
        
        QTimer.singleShot(duration, self.close)


class StyledButton(QPushButton):
    """自定义样式按钮"""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setMinimumHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
    def set_style(self, bg_color, hover_color, text_color="#FFFFFF"):
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_color};
                color: {text_color};
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {bg_color};
            }}
            QPushButton:disabled {{
                background-color: #CCCCCC;
                color: #666666;
            }}
        """)


# ========== 分页文件列表组件（修改版）==========
class PaginatedFileList(QWidget):
    """分页文件列表组件 - 修改版，将分页控件移到标题行"""
    itemClicked = pyqtSignal(int)  # 选中索引信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.current_page = 1
        self.page_size = 200  # 固定每页200条
        self.total_pages = 0
        self.filtered_items = []
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # ===== 标题和分页控件合并在一行 =====
        title_frame = QFrame()
        title_layout = QHBoxLayout(title_frame)
        title_layout.setContentsMargins(0, 0, 0, 0)
        
        # 标题
        list_title = QLabel("📋 文件列表")
        list_title.setObjectName("section_title")
        title_font = QFont("Segoe UI", 13, QFont.Weight.Bold)
        list_title.setFont(title_font)
        title_layout.addWidget(list_title)
        
        # 每页200条提示
        page_size_label = QLabel("每页200条")
        page_size_label.setObjectName("page_size_label")
        page_size_label.setStyleSheet("color: #AAAAAA; font-size: 11px; padding-left: 10px;")
        title_layout.addWidget(page_size_label)
        
        title_layout.addStretch()
        
        # ===== 分页控件（放在标题行右侧）=====
        pagination_widget = QWidget()
        pagination_layout = QHBoxLayout(pagination_widget)
        pagination_layout.setContentsMargins(0, 0, 0, 0)
        pagination_layout.setSpacing(8)
        
        # 上一页按钮
        self.prev_btn = StyledButton("◀ 上一页")
        self.prev_btn.set_style("#555555", "#444444")
        self.prev_btn.setFixedHeight(28)
        self.prev_btn.clicked.connect(self.prev_page)
        self.prev_btn.setEnabled(False)
        pagination_layout.addWidget(self.prev_btn)
        
        # 页码信息
        self.page_label = QLabel("第 1 / 1 页")
        self.page_label.setObjectName("page_label")
        self.page_label.setStyleSheet("color: #E0E0E0;")
        pagination_layout.addWidget(self.page_label)
        
        # 下一页按钮
        self.next_btn = StyledButton("下一页 ▶")
        self.next_btn.set_style("#555555", "#444444")
        self.next_btn.setFixedHeight(28)
        self.next_btn.clicked.connect(self.next_page)
        self.next_btn.setEnabled(False)
        pagination_layout.addWidget(self.next_btn)
        
        title_layout.addWidget(pagination_widget)
        layout.addWidget(title_frame)
        
        # ===== 列表容器（缩小高度）=====
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(2)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 滚动区域 - 固定高度120
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.list_container)
        self.scroll_area.setFixedHeight(120)  # 固定高度，缩小文件列表区域
        self.scroll_area.setObjectName("list_scroll")
        layout.addWidget(self.scroll_area)
        
    def set_items(self, items):
        """设置列表项"""
        self.items = items
        self.filtered_items = items.copy()
        self.total_pages = max(1, (len(self.filtered_items) + self.page_size - 1) // self.page_size)
        self.current_page = 1
        self.update_display()
        
    def filter_items(self, keyword):
        """过滤列表项"""
        if not keyword:
            self.filtered_items = self.items.copy()
        else:
            keyword = keyword.lower()
            self.filtered_items = [item for item in self.items if keyword in item.lower()]
        
        self.total_pages = max(1, (len(self.filtered_items) + self.page_size - 1) // self.page_size)
        self.current_page = 1
        self.update_display()
        
    def update_display(self):
        """更新显示"""
        # 清空列表
        for i in reversed(range(self.list_layout.count())):
            widget = self.list_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        
        if not self.filtered_items:
            label = QLabel("未找到匹配的记录")
            label.setObjectName("empty_list_label")
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            label.setContentsMargins(10, 5, 10, 5)
            self.list_layout.addWidget(label)
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            self.page_label.setText("第 0 / 0 页")
            return
        
        # 计算当前页的数据
        start_idx = (self.current_page - 1) * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.filtered_items))
        page_items = self.filtered_items[start_idx:end_idx]
        
        # 添加列表项
        for i, code in enumerate(page_items):
            actual_index = start_idx + i
            self.create_list_item(actual_index, i, code)
        
        # 更新分页控件
        self.page_label.setText(f"第 {self.current_page} / {self.total_pages} 页")
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < self.total_pages)
        
    def create_list_item(self, actual_index, display_index, code):
        """创建列表项"""
        item_frame = QFrame()
        item_frame.setObjectName("list_item")
        item_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        item_frame.setFixedHeight(24)  # 稍微减小列表项高度
        
        if display_index % 2 == 0:
            item_frame.setProperty("even", True)
        else:
            item_frame.setProperty("odd", True)
            
        item_layout = QHBoxLayout(item_frame)
        item_layout.setContentsMargins(10, 0, 10, 0)
        
        index_label = QLabel(f"{actual_index+1:03d}.")
        index_label.setObjectName("list_index")
        
        file_label = QLabel(code)
        file_label.setObjectName("list_filename")
        
        item_layout.addWidget(index_label)
        item_layout.addWidget(file_label)
        item_layout.addStretch()
        
        item_frame.mousePressEvent = lambda e, idx=actual_index: self.itemClicked.emit(idx)
        
        self.list_layout.addWidget(item_frame)
        
    def prev_page(self):
        """上一页"""
        if self.current_page > 1:
            self.current_page -= 1
            self.update_display()
            
    def next_page(self):
        """下一页"""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.update_display()
            
    def get_item_at_index(self, index):
        """获取指定索引的项"""
        if 0 <= index < len(self.filtered_items):
            return self.filtered_items[index]
        return None


# ========== 主窗口类 ==========
class MainWindow(QMainWindow):
    """主窗口 - PyQt6重构版"""
    
    def __init__(self):
        super().__init__()
        self.data_manager = DataManager()
        self.preset_manager = PresetManager()
        self.current_theme = "dark"
        self.field_labels = {
            "actor": "主演",
            "source": "来源",
            "record": "记录",
            "resource": "资源"
        }
        self.field_visibility = {
            "actor": True,
            "source": True,
            "record": True,
            "resource": True
        }
        self.current_selected_index = -1
        self.current_selected_record_labels = {}  # 当前选中记录的字段标签配置
        
        # 编辑状态标记
        self.is_editing = False
        self.normal_field_labels = {}  # 保存正常状态下的字段标签
        self.normal_field_visibility = {}  # 保存正常状态下的字段可见性
        self.normal_resource_text = ""  # 保存正常状态下的资源文本框内容
        self.normal_prefix_text = ""  # 保存正常状态下的编号前缀
        
        # 设置程序图标
        self.setWindowIcon(QIcon("app.ico") if os.path.exists("app.ico") else QIcon())
        
        self.init_ui()
        self.load_window_state()
        
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("编号资料管理器")
        self.setGeometry(100, 100, 1200, 850)
        
        # 设置中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 创建顶部工具栏
        self.create_top_toolbar(main_layout)
        
        # 创建主内容区域
        self.create_main_content(main_layout)
        
        # 应用主题
        self.apply_theme()
        
    def create_top_toolbar(self, parent_layout):
        """创建顶部工具栏 - 包含目录选择和预设管理"""
        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("toolbar_frame")
        toolbar_frame.setFixedHeight(60)
        
        toolbar_layout = QHBoxLayout(toolbar_frame)
        toolbar_layout.setContentsMargins(20, 10, 20, 10)
        
        # 标题
        title_label = QLabel("编号资料管理器")
        title_label.setObjectName("title_label")
        title_font = QFont("Segoe UI", 15, QFont.Weight.Bold)
        title_label.setFont(title_font)
        toolbar_layout.addWidget(title_label)
        
        toolbar_layout.addStretch()
        
        # ===== 右侧控制区域（目录 + 预设）=====
        right_controls = QFrame()
        right_layout = QHBoxLayout(right_controls)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(15)
        
        # 目录选择区域 - 调整布局，将路径显示放在按钮左边
        dir_frame = QFrame()
        dir_layout = QHBoxLayout(dir_frame)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.setSpacing(10)
        dir_layout.setDirection(QHBoxLayout.Direction.RightToLeft)  # 设置为从右到左布局
        
        self.dir_button = StyledButton("📂 选择存储目录")
        self.dir_button.set_style("#555555", "#444444")
        self.dir_button.clicked.connect(self.choose_folder)
        
        self.folder_label = QLabel("未选择目录")
        self.folder_label.setObjectName("folder_label")
        self.folder_label.setMinimumWidth(200)
        self.folder_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        # 先添加按钮（会在右侧），再添加路径标签（会在左侧）
        dir_layout.addWidget(self.dir_button)
        dir_layout.addWidget(self.folder_label)
        
        # 预设管理区域 - 优化版
        preset_frame = QFrame()
        preset_layout = QHBoxLayout(preset_frame)
        preset_layout.setContentsMargins(0, 0, 0, 0)
        preset_layout.setSpacing(10)
        
        preset_layout.addWidget(QLabel("预设:"))
        
        # 预设下拉框 - 直接点击应用
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(150)
        self.preset_combo.setStyleSheet("""
            QComboBox {
                background-color: #2A2A2A;
                border: 1px solid #3A3A3A;
                border-radius: 4px;
                color: #E0E0E0;
                padding: 6px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #E0E0E0;
                margin-right: 5px;
            }
        """)
        self.preset_combo.activated.connect(self.on_preset_activated)  # 直接激活事件
        
        self.save_preset_btn = StyledButton("💾 保存当前")
        self.save_preset_btn.set_style("#4A90D9", "#3A7BC8")  # 蓝色
        self.save_preset_btn.clicked.connect(self.save_current_preset)
        
        # 预设操作按钮（带右键菜单）
        self.preset_action_btn = StyledButton("⚙️")
        self.preset_action_btn.set_style("#666666", "#555555")
        self.preset_action_btn.setFixedWidth(36)
        self.preset_action_btn.clicked.connect(self.show_preset_menu)
        
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addWidget(self.save_preset_btn)
        preset_layout.addWidget(self.preset_action_btn)
        
        # 添加到右侧控制区域
        right_layout.addWidget(dir_frame)
        right_layout.addWidget(preset_frame)
        
        toolbar_layout.addWidget(right_controls)
        parent_layout.addWidget(toolbar_frame)
        
    def show_preset_menu(self):
        """显示预设右键菜单"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2A2A2A;
                border: 1px solid #3A3A3A;
                border-radius: 4px;
                color: #E0E0E0;
                padding: 5px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 2px;
            }
            QMenu::item:selected {
                background-color: #4A4A4A;
            }
            QMenu::separator {
                height: 1px;
                background-color: #3A3A3A;
                margin: 5px 0px;
            }
        """)
        
        # 添加预设列表作为菜单项
        preset_names = self.preset_manager.get_preset_names()
        if preset_names:
            for name in preset_names:
                action = QAction(f"📋 {name}", self)
                action.triggered.connect(lambda checked, n=name: self.on_preset_activated_by_name(n))
                menu.addAction(action)
            
            menu.addSeparator()
            
            # 添加删除操作（带确认）
            delete_action = QAction("🗑️ 删除预设...", self)
            delete_action.triggered.connect(self.delete_preset_from_menu)
            menu.addAction(delete_action)
        else:
            no_preset_action = QAction("暂无预设", self)
            no_preset_action.setEnabled(False)
            menu.addAction(no_preset_action)
        
        # 显示菜单
        menu.exec(self.preset_action_btn.mapToGlobal(QPoint(0, self.preset_action_btn.height())))
        
    def delete_preset_from_menu(self):
        """从菜单删除预设"""
        preset_names = self.preset_manager.get_preset_names()
        if not preset_names:
            self.show_toast_message("没有可删除的预设", "warning")
            return
        
        # 显示选择对话框
        name, ok = QInputDialog.getItem(
            self, 
            "删除预设", 
            "选择要删除的预设：",
            preset_names,
            0,
            False
        )
        
        if ok and name:
            reply = QMessageBox.question(
                self, 
                "确认删除",
                f"确定要删除预设 '{name}' 吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                if self.preset_manager.delete_preset(name):
                    self.load_preset_combo()
                    self.show_toast_message(f"✅ 预设 '{name}' 已删除", "success")
                else:
                    self.show_error_message("错误", "删除失败")
        
    def on_preset_activated(self, index):
        """预设下拉框激活事件 - 直接应用"""
        if index == 0 or self.is_editing:  # 跳过"选择预设..."
            return
        
        preset_name = self.preset_combo.currentText()
        preset_data = self.preset_manager.get_preset(preset_name)
        if preset_data:
            self.apply_preset_config(preset_data)
            
    def on_preset_activated_by_name(self, preset_name):
        """通过名称应用预设"""
        if self.is_editing:
            self.show_toast_message("编辑状态下不能切换预设", "warning")
            return
            
        preset_data = self.preset_manager.get_preset(preset_name)
        if preset_data:
            self.apply_preset_config(preset_data)
            # 同步下拉框选中
            index = self.preset_combo.findText(preset_name)
            if index >= 0:
                self.preset_combo.setCurrentIndex(index)
        
    def create_main_content(self, parent_layout):
        """创建主内容区域"""
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(15, 0, 15, 15)
        content_layout.setSpacing(15)
        
        # 左侧输入区域
        self.create_left_panel(content_layout)
        
        # 右侧预览区域
        self.create_right_panel(content_layout)
        
        parent_layout.addWidget(content_widget)
        
    def create_left_panel(self, parent_layout):
        """创建左侧面板（输入区域）"""
        left_frame = QFrame()
        left_frame.setObjectName("left_frame")
        left_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(15)
        
        # 标题
        title_label = QLabel("📝 数据录入")
        title_label.setObjectName("section_title")
        title_font = QFont("Segoe UI", 13, QFont.Weight.Bold)
        title_label.setFont(title_font)
        left_layout.addWidget(title_label)
        
        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # 输入区域容器
        input_container = QWidget()
        self.input_layout = QVBoxLayout(input_container)
        self.input_layout.setContentsMargins(5, 5, 5, 5)
        self.input_layout.setSpacing(8)  # 稍微减小间距
        
        # 字段标签配置区域（只保留三个字段，一行显示）
        self.create_field_labels_section()
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("separator")
        self.input_layout.addWidget(line)
        
        # 前缀输入
        self.create_prefix_input()
        
        # 编号显示（只读）
        self.create_code_display()
        
        # 主演输入
        self.create_actor_input()
        
        # 来源输入
        self.create_source_input()
        
        # 标签输入
        self.create_tags_section()
        
        # 记录输入
        self.create_record_input()
        
        # 资源输入（保留）
        self.create_resource_input()
        
        # 简介输入
        self.create_description_section()
        
        # 按钮区域
        self.create_button_section()
        
        scroll_area.setWidget(input_container)
        scroll_area.setMinimumWidth(400)
        left_layout.addWidget(scroll_area)
        
        parent_layout.addWidget(left_frame, 1)
        
    def create_field_labels_section(self):
        """创建字段标签配置区域 - 一行显示三个字段（去掉资源）"""
        # 标题
        label_title = QLabel("⚙️ 字段标签设置：")
        label_title.setObjectName("field_label_title")
        label_font = QFont("Segoe UI", 10, QFont.Weight.Normal)  # 字号减小一号
        label_title.setFont(label_font)
        self.input_layout.addWidget(label_title)
        
        # 一行布局
        row_layout = QHBoxLayout()
        row_layout.setSpacing(10)  # 稍微减小间距
        
        # 主演字段
        actor_frame = QFrame()
        actor_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        actor_layout = QHBoxLayout(actor_frame)
        actor_layout.setContentsMargins(0, 0, 0, 0)
        actor_layout.setSpacing(5)
        actor_label = QLabel("主演：")
        actor_label_font = QFont("Segoe UI", 9, QFont.Weight.Normal)  # 字号减小一号
        actor_label.setFont(actor_label_font)
        actor_layout.addWidget(actor_label)
        
        self.actor_label_entry = QLineEdit(self.field_labels["actor"])
        self.actor_label_entry.setPlaceholderText("主演")
        self.actor_label_entry.setFixedWidth(68)  # 缩短15% (80 -> 68)
        self.actor_label_entry.setFont(actor_label_font)
        actor_layout.addWidget(self.actor_label_entry)
        
        self.actor_visibility_btn = StyledButton("显示")
        self.actor_visibility_btn.set_style("#666666", "#555555")
        self.actor_visibility_btn.clicked.connect(lambda: self.toggle_field_visibility("actor"))
        actor_layout.addWidget(self.actor_visibility_btn)
        row_layout.addWidget(actor_frame)
        
        # 来源字段
        source_frame = QFrame()
        source_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        source_layout = QHBoxLayout(source_frame)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(5)
        source_label = QLabel("来源：")
        source_label_font = QFont("Segoe UI", 9, QFont.Weight.Normal)  # 字号减小一号
        source_label.setFont(source_label_font)
        source_layout.addWidget(source_label)
        
        self.source_label_entry = QLineEdit(self.field_labels["source"])
        self.source_label_entry.setPlaceholderText("来源")
        self.source_label_entry.setFixedWidth(68)  # 缩短15% (80 -> 68)
        self.source_label_entry.setFont(source_label_font)
        source_layout.addWidget(self.source_label_entry)
        
        self.source_visibility_btn = StyledButton("显示")
        self.source_visibility_btn.set_style("#666666", "#555555")
        self.source_visibility_btn.clicked.connect(lambda: self.toggle_field_visibility("source"))
        source_layout.addWidget(self.source_visibility_btn)
        row_layout.addWidget(source_frame)
        
        # 记录字段
        record_frame = QFrame()
        record_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        record_layout = QHBoxLayout(record_frame)
        record_layout.setContentsMargins(0, 0, 0, 0)
        record_layout.setSpacing(5)
        record_label = QLabel("记录：")
        record_label_font = QFont("Segoe UI", 9, QFont.Weight.Normal)  # 字号减小一号
        record_label.setFont(record_label_font)
        record_layout.addWidget(record_label)
        
        self.record_label_entry = QLineEdit(self.field_labels["record"])
        self.record_label_entry.setPlaceholderText("记录")
        self.record_label_entry.setFixedWidth(68)  # 缩短15% (80 -> 68)
        self.record_label_entry.setFont(record_label_font)
        record_layout.addWidget(self.record_label_entry)
        
        self.record_visibility_btn = StyledButton("显示")
        self.record_visibility_btn.set_style("#666666", "#555555")
        self.record_visibility_btn.clicked.connect(lambda: self.toggle_field_visibility("record"))
        record_layout.addWidget(self.record_visibility_btn)
        row_layout.addWidget(record_frame)
        
        row_layout.addStretch()
        self.input_layout.addLayout(row_layout)
        
        # 连接信号
        self.actor_label_entry.textChanged.connect(self.on_field_label_changed)
        self.source_label_entry.textChanged.connect(self.on_field_label_changed)
        self.record_label_entry.textChanged.connect(self.on_field_label_changed)
        
    def create_prefix_input(self):
        """创建前缀输入"""
        row_layout = QHBoxLayout()
        
        label = QLabel("前缀：")
        label.setObjectName("input_label")
        label.setFixedWidth(50)  # 缩短15% (60 -> 50)
        row_layout.addWidget(label)
        
        self.prefix_entry = QLineEdit()
        self.prefix_entry.setObjectName("input_field")
        self.prefix_entry.setPlaceholderText("例如: AV")
        self.prefix_entry.textChanged.connect(self.refresh_code)
        row_layout.addWidget(self.prefix_entry, 1)
        
        self.input_layout.addLayout(row_layout)
        
    def create_code_display(self):
        """创建编号显示"""
        row_layout = QHBoxLayout()
        
        label = QLabel("编号：")
        label.setObjectName("input_label")
        label.setFixedWidth(50)  # 缩短15% (60 -> 50)
        row_layout.addWidget(label)
        
        self.code_entry = QLineEdit()
        self.code_entry.setObjectName("readonly_field")
        self.code_entry.setReadOnly(True)
        row_layout.addWidget(self.code_entry, 1)
        
        self.input_layout.addLayout(row_layout)
        
    def create_actor_input(self):
        """创建主演输入"""
        row_layout = QHBoxLayout()
        
        self.actor_label = QLabel(self.field_labels["actor"])
        self.actor_label.setObjectName("input_label")
        self.actor_label.setFixedWidth(50)  # 缩短15% (60 -> 50)
        row_layout.addWidget(self.actor_label)
        
        self.actor_entry = QLineEdit()
        self.actor_entry.setObjectName("input_field")
        self.actor_entry.setPlaceholderText(f"输入{self.field_labels['actor']}")
        self.actor_entry.textChanged.connect(self.update_preview)
        row_layout.addWidget(self.actor_entry, 1)
        
        self.input_layout.addLayout(row_layout)
        
    def create_source_input(self):
        """创建来源输入"""
        row_layout = QHBoxLayout()
        
        self.source_label = QLabel(self.field_labels["source"])
        self.source_label.setObjectName("input_label")
        self.source_label.setFixedWidth(50)  # 缩短15% (60 -> 50)
        row_layout.addWidget(self.source_label)
        
        self.source_entry = QLineEdit()
        self.source_entry.setObjectName("input_field")
        self.source_entry.setPlaceholderText(f"输入{self.field_labels['source']}")
        self.source_entry.textChanged.connect(self.update_preview)
        row_layout.addWidget(self.source_entry, 1)
        
        self.input_layout.addLayout(row_layout)
        
    def create_tags_section(self):
        """创建标签输入区域"""
        row_layout = QHBoxLayout()
        
        label = QLabel("标签：")
        label.setObjectName("input_label")
        label.setFixedWidth(50)  # 缩短15% (60 -> 50)
        row_layout.addWidget(label)
        
        # 5个标签输入框
        self.tag_entries = []
        tag_container = QWidget()
        tag_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tag_layout = QHBoxLayout(tag_container)
        tag_layout.setContentsMargins(0, 0, 0, 0)
        tag_layout.setSpacing(5)
        
        for i in range(5):
            tag_entry = QLineEdit()
            tag_entry.setObjectName("input_field")
            tag_entry.setPlaceholderText(f"标签{i+1}")
            tag_entry.setMinimumWidth(60)  # 设置最小宽度，不设置固定宽度以实现自适应
            tag_entry.textChanged.connect(self.update_preview)
            self.tag_entries.append(tag_entry)
            tag_layout.addWidget(tag_entry)
        
        tag_layout.addStretch()
        row_layout.addWidget(tag_container, 1)
        self.input_layout.addLayout(row_layout)
        
    def create_record_input(self):
        """创建记录输入"""
        row_layout = QHBoxLayout()
        
        self.record_label = QLabel(self.field_labels["record"])
        self.record_label.setObjectName("input_label")
        self.record_label.setFixedWidth(50)  # 缩短15% (60 -> 50)
        row_layout.addWidget(self.record_label)
        
        self.record_entry = QLineEdit()
        self.record_entry.setObjectName("input_field")
        self.record_entry.setPlaceholderText(f"输入{self.field_labels['record']}")
        self.record_entry.textChanged.connect(self.update_preview)
        row_layout.addWidget(self.record_entry, 1)
        
        self.input_layout.addLayout(row_layout)
        
    def create_resource_input(self):
        """创建资源输入（保留）- 增加预设值加载"""
        row_layout = QHBoxLayout()
        
        self.resource_label = QLabel(self.field_labels["resource"])
        self.resource_label.setObjectName("input_label")
        self.resource_label.setFixedWidth(50)  # 缩短15% (60 -> 50)
        row_layout.addWidget(self.resource_label)
        
        self.resource_entry = QLineEdit()
        self.resource_entry.setObjectName("input_field")
        self.resource_entry.setPlaceholderText(f"输入{self.field_labels['resource']}")
        self.resource_entry.textChanged.connect(self.update_preview)
        row_layout.addWidget(self.resource_entry, 1)
        
        self.input_layout.addLayout(row_layout)
        
    def create_description_section(self):
        """创建简介输入区域"""
        row_layout = QHBoxLayout()
        
        label = QLabel("简介：")
        label.setObjectName("input_label")
        label.setFixedWidth(50)  # 缩短15% (60 -> 50)
        row_layout.addWidget(label)
        
        self.desc_entry = QTextEdit()
        self.desc_entry.setObjectName("desc_field")
        self.desc_entry.setMinimumHeight(120)
        self.desc_entry.textChanged.connect(self.update_preview)
        row_layout.addWidget(self.desc_entry, 1)
        
        self.input_layout.addLayout(row_layout)
        
    def create_button_section(self):
        """创建按钮区域"""
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        self.save_button = StyledButton("💾 保存记录")
        self.save_button.set_style("#666666", "#555555")
        self.save_button.clicked.connect(self.save_record_with_toast)
        button_layout.addWidget(self.save_button)
        
        self.clear_button = StyledButton("🗑️ 清空输入")
        self.clear_button.set_style("#888888", "#777777")
        self.clear_button.clicked.connect(self.clear_inputs)
        button_layout.addWidget(self.clear_button)
        
        self.input_layout.addLayout(button_layout)
        
    def create_right_panel(self, parent_layout):
        """创建右侧面板（预览区域）- 调整布局权重，将文件列表缩小的部分均分给预览区域"""
        right_frame = QFrame()
        right_frame.setObjectName("right_frame")
        right_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(12)
        
        # 实时预览区域 - 增加拉伸因子
        self.create_realtime_preview(right_layout)
        
        # 搜索区域
        self.create_search_section(right_layout)
        
        # 文件列表区域（分页）- 使用固定高度，不占用拉伸空间
        self.create_file_list(right_layout)
        
        # 选中记录预览区域 - 增加拉伸因子
        self.create_selected_preview(right_layout)
        
        # 设置布局拉伸因子：实时预览(4), 搜索(0), 文件列表(0), 选中预览(4)
        right_layout.setStretchFactor(self.preview_container, 4) if hasattr(self, 'preview_container') else None
        right_layout.setStretchFactor(self.selected_preview_container, 4) if hasattr(self, 'selected_preview_container') else None
        
        parent_layout.addWidget(right_frame, 1)
        
    def create_realtime_preview(self, parent_layout):
        """创建实时预览区域"""
        # 创建容器以便设置拉伸因子
        self.preview_container = QWidget()
        preview_container_layout = QVBoxLayout(self.preview_container)
        preview_container_layout.setContentsMargins(0, 0, 0, 0)
        preview_container_layout.setSpacing(5)
        
        title_layout = QHBoxLayout()
        
        title_label = QLabel("👁️ 实时预览")
        title_label.setObjectName("section_title")
        title_font = QFont("Segoe UI", 13, QFont.Weight.Bold)
        title_label.setFont(title_font)
        
        self.copy_preview_button = StyledButton("📋 复制预览")
        self.copy_preview_button.set_style("#555555", "#444444")
        self.copy_preview_button.clicked.connect(self.copy_preview_with_toast)
        
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.copy_preview_button)
        
        preview_container_layout.addLayout(title_layout)
        
        self.preview_text = QTextEdit()
        self.preview_text.setObjectName("preview_text")
        self.preview_text.setReadOnly(True)
        preview_container_layout.addWidget(self.preview_text)
        
        parent_layout.addWidget(self.preview_container, 4)  # 拉伸因子4
        
    def create_search_section(self, parent_layout):
        """创建搜索区域"""
        search_layout = QHBoxLayout()
        
        search_label = QLabel("🔍 搜索：")
        search_label.setObjectName("search_label")
        
        self.search_entry = QLineEdit()
        self.search_entry.setObjectName("search_field")
        self.search_entry.setPlaceholderText("输入关键词搜索文件...")
        self.search_entry.textChanged.connect(self.on_search_changed)
        
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_entry, 1)
        
        parent_layout.addLayout(search_layout)  # 拉伸因子0
        
    def create_file_list(self, parent_layout):
        """创建文件列表（分页）- 使用固定高度"""
        # 使用分页列表组件
        self.paginated_list = PaginatedFileList()
        self.paginated_list.itemClicked.connect(self.on_list_item_clicked)
        parent_layout.addWidget(self.paginated_list)  # 拉伸因子0，使用固定高度
        
    def create_selected_preview(self, parent_layout):
        """创建选中记录预览区域"""
        # 创建容器以便设置拉伸因子
        self.selected_preview_container = QWidget()
        selected_preview_container_layout = QVBoxLayout(self.selected_preview_container)
        selected_preview_container_layout.setContentsMargins(0, 0, 0, 0)
        selected_preview_container_layout.setSpacing(5)
        
        preview_title = QLabel("📄 选中记录预览")
        preview_title.setObjectName("section_title")
        selected_preview_container_layout.addWidget(preview_title)
        
        self.selected_preview_text = QTextEdit()
        self.selected_preview_text.setObjectName("selected_preview_text")
        self.selected_preview_text.setReadOnly(True)
        selected_preview_container_layout.addWidget(self.selected_preview_text)
        
        button_layout = QHBoxLayout()
        
        self.edit_button = StyledButton("✏️ 编辑")
        self.edit_button.set_style("#4A90D9", "#3A7BC8")
        self.edit_button.clicked.connect(self.edit_selected_record)
        self.edit_button.setEnabled(False)
        
        self.delete_button = StyledButton("🗑️ 删除")
        self.delete_button.set_style("#D9534F", "#C9302C")
        self.delete_button.clicked.connect(self.delete_selected_record)
        self.delete_button.setEnabled(False)
        
        self.copy_selected_button = StyledButton("📋 复制选中记录")
        self.copy_selected_button.set_style("#555555", "#444444")
        self.copy_selected_button.clicked.connect(self.copy_selected_preview_with_toast)
        
        button_layout.addWidget(self.edit_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addStretch()
        button_layout.addWidget(self.copy_selected_button)
        
        selected_preview_container_layout.addLayout(button_layout)
        
        parent_layout.addWidget(self.selected_preview_container, 4)  # 拉伸因子4
        
    # ========== 预设管理方法 ==========
    def load_preset_combo(self):
        """加载预设到下拉框"""
        self.preset_combo.clear()
        self.preset_combo.addItem("📋 选择预设...")  # 修改为更明确的提示
        for name in self.preset_manager.get_preset_names():
            self.preset_combo.addItem(name)
            
    def on_preset_selected(self, preset_name):
        """预设选中事件 - 已废弃，使用on_preset_activated"""
        pass
            
    def apply_preset_config(self, preset_data):
        """应用预设配置 - 同时应用字段标签、可见性、资源文本框内容和编号前缀"""
        # 获取标签、可见性、资源文本和前缀配置
        if isinstance(preset_data, dict):
            if "labels" in preset_data:
                labels = preset_data["labels"]
            else:
                labels = preset_data  # 兼容旧格式
                
            visibility = preset_data.get("visibility", {})
            resource_text = preset_data.get("resource_text", "")  # 获取保存的资源文本
            prefix_text = preset_data.get("prefix_text", "")      # 获取保存的编号前缀
        
        # 应用字段标签
        if "actor" in labels:
            self.field_labels["actor"] = labels["actor"]
            self.actor_label_entry.setText(labels["actor"])
            self.actor_label.setText(labels["actor"])
            self.actor_entry.setPlaceholderText(f"输入{labels['actor']}")
            
        if "source" in labels:
            self.field_labels["source"] = labels["source"]
            self.source_label_entry.setText(labels["source"])
            self.source_label.setText(labels["source"])
            self.source_entry.setPlaceholderText(f"输入{labels['source']}")
            
        if "record" in labels:
            self.field_labels["record"] = labels["record"]
            self.record_label_entry.setText(labels["record"])
            self.record_label.setText(labels["record"])
            self.record_entry.setPlaceholderText(f"输入{labels['record']}")
        
        # 应用资源文本框内容（如果有）
        if resource_text:
            self.resource_entry.setText(resource_text)
            
        # 应用编号前缀（如果有）
        if prefix_text:
            self.prefix_entry.setText(prefix_text)
            self.refresh_code()  # 刷新编号
        
        # 应用字段可见性
        # 先确保所有字段都显示（重置状态）
        self.reset_all_fields_visibility()
        
        # 然后应用预设的可见性配置
        for field, visible in visibility.items():
            if field in ["actor", "source", "record"]:
                # 如果预设中保存的状态是隐藏，则切换为隐藏
                if not visible:
                    # 如果当前是显示状态，则切换
                    if self.field_visibility.get(field, True):
                        self.toggle_field_visibility(field)
        
        self.update_preview()
        self.save_window_state()
        self.show_toast_message(f"✅ 已应用预设: {self.preset_combo.currentText()}", "success")
        
    def reset_all_fields_visibility(self):
        """重置所有字段为显示状态"""
        fields = ["actor", "source", "record"]
        for field in fields:
            if not self.field_visibility.get(field, True):
                self.toggle_field_visibility(field)
        
    def save_current_preset(self):
        """保存当前配置为预设 - 同时保存字段标签、可见性、资源文本框内容和编号前缀"""
        name, ok = QInputDialog.getText(self, "保存预设", "请输入预设名称:")
        if ok and name.strip():
            current_labels = {
                "actor": self.actor_label_entry.text().strip() or "主演",
                "source": self.source_label_entry.text().strip() or "来源",
                "record": self.record_label_entry.text().strip() or "记录"
            }
            current_visibility = self.field_visibility.copy()
            current_resource_text = self.resource_entry.text().strip()  # 获取资源文本框内容
            current_prefix_text = self.prefix_entry.text().strip()      # 获取编号前缀
            
            if self.preset_manager.save_preset(name.strip(), current_labels, current_visibility, 
                                              current_resource_text, current_prefix_text):
                self.load_preset_combo()
                # 设置为默认选择项
                index = self.preset_combo.findText(name.strip())
                if index >= 0:
                    self.preset_combo.setCurrentIndex(index)
                self.show_toast_message(f"✅ 预设 '{name}' 保存成功", "success")
            else:
                self.show_error_message("错误", "保存失败")
                
    def manage_presets(self):
        """管理预设 - 已废弃，功能整合到右键菜单"""
        pass
        
    # ========== Enter键导航 ==========
    def setup_enter_key_navigation(self):
        """设置Enter键导航功能"""
        # 字段标签设置区域的文本框（只有三个）
        field_label_entries = [
            self.actor_label_entry,
            self.source_label_entry,
            self.record_label_entry
        ]
        
        # 主要输入区域的文本框
        main_entries = [
            self.prefix_entry,
            self.actor_entry,
            self.source_entry,
            *self.tag_entries,
            self.record_entry,
            self.resource_entry
        ]
        
        # 所有文本框列表（除了简介）
        all_entries = field_label_entries + main_entries
        
        # 为每个文本框设置Enter键跳转
        for i, entry in enumerate(all_entries):
            if i < len(all_entries) - 1:
                next_entry = all_entries[i + 1]
                entry.returnPressed.connect(lambda checked=False, ne=next_entry: ne.setFocus())
            else:
                entry.returnPressed.connect(lambda: self.desc_entry.setFocus())
        
        # 简介文本框的特殊处理：Ctrl+Enter保存记录
        self.desc_entry.keyPressEvent = self.desc_key_press_event
        
    def desc_key_press_event(self, event):
        """简介文本框的按键事件处理"""
        if event.key() == Qt.Key.Key_Return and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.save_record_with_toast()
        else:
            QTextEdit.keyPressEvent(self.desc_entry, event)
        
    # ========== 事件处理方法 ==========
    def choose_folder(self):
        """选择存储目录"""
        folder = QFileDialog.getExistingDirectory(self, "选择存储目录")
        if folder:
            self.data_manager.set_data_dir(folder)
            self.folder_label.setText(folder)
            self.refresh_list()
            self.refresh_code()
            
    def refresh_code(self):
        """刷新编号"""
        prefix = self.prefix_entry.text()
        next_code = self.data_manager.get_next_code(prefix)
        self.code_entry.setText(next_code)
        self.update_preview()
        
    def on_search_changed(self):
        """搜索内容变化处理"""
        self.refresh_list()
        
    def refresh_list(self):
        """刷新文件列表"""
        if not self.data_manager.data_dir:
            self.paginated_list.set_items([])
            return
            
        keyword = self.search_entry.text()
        results = self.data_manager.search_records(keyword)
        self.paginated_list.set_items(results)
        
    def on_list_item_clicked(self, index):
        """列表项点击事件"""
        self.current_selected_index = index
        
        # 启用按钮
        self.edit_button.setEnabled(True)
        self.delete_button.setEnabled(True)
        
        # 获取并显示记录
        code = self.paginated_list.get_item_at_index(index)
        if code:
            record, labels = self.data_manager.get_record_with_labels(code)
            if record:
                self.current_selected_record_labels = labels
                self.display_selected_record(record, labels)
                
    def display_selected_record(self, record, labels=None):
        """显示选中的记录 - 使用保存时的字段标签"""
        tags_text = " ".join(f"#{tag}" for tag in record.get("标签", []) if tag)
        content = f"编号：#{record.get('编号', '')}\n"
        
        # 使用保存时的字段标签（如果存在），否则使用默认标签
        actor_label = labels.get("actor", "主演") if labels else "主演"
        if record.get('主演'):
            content += f"{actor_label}：#{record.get('主演', '')}\n"
            
        source_label = labels.get("source", "来源") if labels else "来源"
        if record.get('来源'):
            content += f"{source_label}：#{record.get('来源', '')}\n"
            
        if tags_text:
            content += f"标签：{tags_text}\n"
            
        record_label = labels.get("record", "记录") if labels else "记录"
        if record.get('记录'):
            content += f"{record_label}：{record.get('记录', '')}\n"
            
        # 资源字段始终显示为"资源"
        if record.get('资源'):
            content += f"\n资源：{record.get('资源', '')}\n"
            
        desc = record.get('简介', '')
        if desc:
            content += f"简介：{desc}"
            
        self.selected_preview_text.setText(content)
        
    def update_preview(self):
        """更新实时预览 - 使用当前输入区的字段标签"""
        content = f"编号：#{self.code_entry.text()}\n"
        
        # 只有字段可见时才显示在预览中
        if self.field_visibility.get("actor", True):
            actor_label = self.actor_label_entry.text().strip() or self.field_labels["actor"]
            actor_value = self.actor_entry.text().strip()
            if actor_label and actor_value:
                content += f"{actor_label}：#{actor_value}\n"
            
        if self.field_visibility.get("source", True):
            source_label = self.source_label_entry.text().strip() or self.field_labels["source"]
            source_value = self.source_entry.text().strip()
            if source_label and source_value:
                content += f"{source_label}：#{source_value}\n"
            
        tags = []
        for entry in self.tag_entries:
            tag = entry.text().strip()
            if tag:
                tags.append(f"#{tag}")
        if tags:
            content += f"标签：{' '.join(tags)}\n"
            
        if self.field_visibility.get("record", True):
            record_label = self.record_label_entry.text().strip() or self.field_labels["record"]
            record_value = self.record_entry.text().strip()
            if record_label and record_value:
                content += f"{record_label}：{record_value}\n"
            
        resource_label = self.field_labels["resource"]
        resource_value = self.resource_entry.text().strip()
        if resource_label and resource_value:
            content += f"\n{resource_label}：{resource_value}\n"
            
        desc = self.desc_entry.toPlainText().strip()
        if desc:
            content += f"简介：{desc}"
            
        self.preview_text.setText(content)
        
    def save_record_with_toast(self):
        """保存记录 - 同时保存当前字段标签配置
           JSON文件使用字段标签作为键名，数据库保持固定键名
        """
        if not self.data_manager.data_dir:
            self.show_warning_message("提示", "请先选择存储目录")
            return
            
        # 构建保存的数据 - 使用固定键名用于数据库和内部处理
        data = {
            "编号": self.code_entry.text(),
            "创建时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # 根据字段标签配置添加数据（使用固定键名）
        actor_label = self.actor_label_entry.text().strip() or self.field_labels["actor"]
        if actor_label and self.field_visibility.get("actor", True):
            data["主演"] = self.actor_entry.text()
            
        source_label = self.source_label_entry.text().strip() or self.field_labels["source"]
        if source_label and self.field_visibility.get("source", True):
            data["来源"] = self.source_entry.text()
            
        tags = [entry.text() for entry in self.tag_entries if entry.text().strip()]
        if tags:
            data["标签"] = tags
            
        record_label = self.record_label_entry.text().strip() or self.field_labels["record"]
        if record_label and self.field_visibility.get("record", True):
            data["记录"] = self.record_entry.text()
            
        data["资源"] = self.resource_entry.text()
            
        desc = self.desc_entry.toPlainText().strip()
        if desc:
            data["简介"] = desc
            
        if not data["编号"]:
            self.show_warning_message("提示", "编号不能为空")
            return
            
        # 保存当前的字段标签配置
        current_labels = {
            "actor": self.actor_label_entry.text().strip() or "主演",
            "source": self.source_label_entry.text().strip() or "来源",
            "record": self.record_label_entry.text().strip() or "记录"
        }
            
        if self.data_manager.save_record(data, current_labels):
            self.show_toast_message("✅ 记录保存成功！", "success")
            self.refresh_list()
            self.refresh_code()
            
            # 如果处于编辑状态，恢复正常的字段标签、可见性和资源文本框内容
            if self.is_editing:
                self.restore_normal_labels()
        else:
            self.show_error_message("错误", "保存失败，请检查数据格式")
            
    def copy_preview_with_toast(self):
        """复制预览内容"""
        content = self.preview_text.toPlainText()
        if not content.strip():
            self.show_warning_message("提示", "没有内容可复制")
            return
            
        clipboard = QApplication.clipboard()
        clipboard.setText(content)
        self.show_toast_message("📋 预览内容已复制", "info")
        
    def copy_selected_preview_with_toast(self):
        """复制选中记录预览内容"""
        content = self.selected_preview_text.toPlainText()
        if not content.strip():
            self.show_warning_message("提示", "请先选中一个记录")
            return
            
        clipboard = QApplication.clipboard()
        clipboard.setText(content)
        self.show_toast_message("📋 选中记录已复制", "info")
        
    def edit_selected_record(self):
        """编辑选中的记录 - 切换为记录的字段标签"""
        if self.current_selected_index == -1:
            self.show_warning_message("提示", "请先选择一个记录")
            return
            
        code = self.paginated_list.get_item_at_index(self.current_selected_index)
        if not code:
            return
            
        # 保存当前正常的字段标签、可见性和资源文本框内容
        self.normal_field_labels = {
            "actor": self.actor_label_entry.text().strip() or self.field_labels["actor"],
            "source": self.source_label_entry.text().strip() or self.field_labels["source"],
            "record": self.record_label_entry.text().strip() or self.field_labels["record"]
        }
        self.normal_field_visibility = self.field_visibility.copy()
        self.normal_resource_text = self.resource_entry.text().strip()  # 保存正常资源文本
        
        # 获取记录及其保存时的字段标签
        record, labels = self.data_manager.get_record_with_labels(code)
        
        if not record:
            self.show_error_message("错误", "无法加载记录数据")
            return
            
        # 将记录数据填充到输入区域（使用固定键名）
        self.code_entry.setText(record.get("编号", ""))
        self.actor_entry.setText(record.get("主演", ""))
        self.source_entry.setText(record.get("来源", ""))
        self.record_entry.setText(record.get("记录", ""))
        self.resource_entry.setText(record.get("资源", ""))
        
        tags = record.get("标签", [])
        for i, entry in enumerate(self.tag_entries):
            if i < len(tags):
                entry.setText(tags[i])
            else:
                entry.clear()
                
        self.desc_entry.setText(record.get("简介", ""))
        
        # 切换到记录的字段标签
        if labels:
            # 先重置所有字段为显示状态
            self.reset_all_fields_visibility()
            
            # 更新字段标签显示
            if "actor" in labels:
                self.actor_label_entry.setText(labels["actor"])
                self.actor_label.setText(labels["actor"])
                self.actor_entry.setPlaceholderText(f"输入{labels['actor']}")
                
            if "source" in labels:
                self.source_label_entry.setText(labels["source"])
                self.source_label.setText(labels["source"])
                self.source_entry.setPlaceholderText(f"输入{labels['source']}")
                
            if "record" in labels:
                self.record_label_entry.setText(labels["record"])
                self.record_label.setText(labels["record"])
                self.record_entry.setPlaceholderText(f"输入{labels['record']}")
        
        # 标记为编辑状态
        self.is_editing = True
        
        # 禁用预设切换
        self.preset_combo.setEnabled(False)
        
        # 更新预览
        self.update_preview()
        self.show_toast_message("📝 记录加载成功（已切换到记录字段标签）", "info")
        
    def restore_normal_labels(self):
        """恢复正常的字段标签、可见性和资源文本框内容"""
        if self.normal_field_labels:
            # 恢复字段标签
            if "actor" in self.normal_field_labels:
                self.actor_label_entry.setText(self.normal_field_labels["actor"])
                self.actor_label.setText(self.normal_field_labels["actor"])
                self.actor_entry.setPlaceholderText(f"输入{self.normal_field_labels['actor']}")
                self.field_labels["actor"] = self.normal_field_labels["actor"]
                
            if "source" in self.normal_field_labels:
                self.source_label_entry.setText(self.normal_field_labels["source"])
                self.source_label.setText(self.normal_field_labels["source"])
                self.source_entry.setPlaceholderText(f"输入{self.normal_field_labels['source']}")
                self.field_labels["source"] = self.normal_field_labels["source"]
                
            if "record" in self.normal_field_labels:
                self.record_label_entry.setText(self.normal_field_labels["record"])
                self.record_label.setText(self.normal_field_labels["record"])
                self.record_entry.setPlaceholderText(f"输入{self.normal_field_labels['record']}")
                self.field_labels["record"] = self.normal_field_labels["record"]
        
        # 恢复资源文本框内容
        if self.normal_resource_text:
            self.resource_entry.setText(self.normal_resource_text)
        else:
            self.resource_entry.clear()
        
        # 恢复字段可见性
        if self.normal_field_visibility:
            # 先重置所有字段为显示状态
            self.reset_all_fields_visibility()
            
            # 然后应用保存的可见性配置
            for field, visible in self.normal_field_visibility.items():
                if field in ["actor", "source", "record"]:
                    if not visible and self.field_visibility.get(field, True):
                        self.toggle_field_visibility(field)
        
        # 清除编辑状态
        self.is_editing = False
        self.normal_field_labels = {}
        self.normal_field_visibility = {}
        self.normal_resource_text = ""
        
        # 启用预设切换
        self.preset_combo.setEnabled(True)
        
        # 更新预览
        self.update_preview()
        
    def delete_selected_record(self):
        """删除选中的记录"""
        if self.current_selected_index == -1:
            self.show_warning_message("提示", "请先选择一个记录")
            return
            
        code = self.paginated_list.get_item_at_index(self.current_selected_index)
        if not code:
            return
        
        reply = QMessageBox.question(
            self, 
            "确认删除",
            f"确定要删除记录 '{code}' 吗？\n此操作无法撤销！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if self.data_manager.delete_record(code):
                self.show_toast_message("✅ 记录删除成功！", "success")
                self.refresh_list()
                self.selected_preview_text.clear()
                self.edit_button.setEnabled(False)
                self.delete_button.setEnabled(False)
                self.refresh_code()
                
                # 如果处于编辑状态且删除的是当前编辑的记录，恢复正常标签
                if self.is_editing:
                    self.restore_normal_labels()
            else:
                self.show_error_message("错误", "删除失败，请检查文件权限")
                
    def clear_inputs(self):
        """清空输入框"""
        self.actor_entry.clear()
        self.source_entry.clear()
        self.record_entry.clear()
        self.resource_entry.clear()
        for entry in self.tag_entries:
            entry.clear()
        self.desc_entry.clear()
        self.refresh_code()
        self.update_preview()
        
        # 如果处于编辑状态，恢复正常的字段标签、可见性和资源文本框内容
        if self.is_editing:
            self.restore_normal_labels()
        
    def on_field_label_changed(self):
        """字段标签变化事件"""
        # 如果在编辑状态，不保存到全局配置
        if self.is_editing:
            # 只更新预览，不保存状态
            self.update_preview()
            return
            
        # 更新标签文本
        actor_label = self.actor_label_entry.text().strip()
        source_label = self.source_label_entry.text().strip()
        record_label = self.record_label_entry.text().strip()
        
        if actor_label:
            self.field_labels["actor"] = actor_label
            self.actor_label.setText(actor_label)
            self.actor_entry.setPlaceholderText(f"输入{actor_label}")
            
        if source_label:
            self.field_labels["source"] = source_label
            self.source_label.setText(source_label)
            self.source_entry.setPlaceholderText(f"输入{source_label}")
            
        if record_label:
            self.field_labels["record"] = record_label
            self.record_label.setText(record_label)
            self.record_entry.setPlaceholderText(f"输入{record_label}")
            
        self.update_preview()
        self.save_window_state()
        
    def toggle_field_visibility(self, field_type: str):
        """切换字段的显示/隐藏状态"""
        if field_type == "actor":
            btn = self.actor_visibility_btn
            label = self.actor_label
            entry = self.actor_entry
        elif field_type == "source":
            btn = self.source_visibility_btn
            label = self.source_label
            entry = self.source_entry
        elif field_type == "record":
            btn = self.record_visibility_btn
            label = self.record_label
            entry = self.record_entry
        else:
            return
            
        current_text = btn.text()
        
        if current_text == "显示":
            btn.setText("隐藏")
            label.hide()
            entry.hide()
            btn.set_style("#888888", "#777777")
            self.field_visibility[field_type] = False
        else:
            btn.setText("显示")
            label.show()
            entry.show()
            btn.set_style("#666666", "#555555")
            self.field_visibility[field_type] = True
            
        self.update_preview()  # 更新预览以反映可见性变化
        self.save_window_state()
        
    # ========== 工具方法 ==========
    def show_toast_message(self, message, msg_type="info"):
        """显示悬浮提示"""
        toast = ToastMessage(self, message, msg_type)
        toast.show_toast()
        
    def show_warning_message(self, title, message):
        """显示警告消息"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #2D2D2D;
            }
            QLabel {
                color: #E0E0E0;
            }
            QPushButton {
                background-color: #4A4A4A;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #5A5A5A;
            }
        """)
        msg_box.exec()
        
    def show_error_message(self, title, message):
        """显示错误消息"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #2D2D2D;
            }
            QLabel {
                color: #E0E0E0;
            }
            QPushButton {
                background-color: #4A4A4A;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #5A5A5A;
            }
        """)
        msg_box.exec()
        
    def apply_theme(self):
        """应用主题样式"""
        self.apply_dark_theme()
        self.style().unpolish(self)
        self.style().polish(self)
        
    def apply_dark_theme(self):
        """应用深色主题"""
        style = """
        QMainWindow {
            background-color: #1A1A1A;
        }
        
        #toolbar_frame {
            background-color: #252525;
            border-bottom: 1px solid #353535;
        }
        
        #title_label {
            color: #FFFFFF;
        }
        
        #folder_label {
            color: #AAAAAA;
        }
        
        #left_frame, #right_frame {
            background-color: #252525;
            border: 1px solid #353535;
            border-radius: 10px;
        }
        
        .section_title {
            color: #FFFFFF;
            font-size: 13px;
            font-weight: bold;
        }
        
        #input_label, #search_label {
            color: #E0E0E0;
            font-size: 11px;
        }
        
        #field_label_title {
            color: #E0E0E0;
            font-weight: bold;
            font-size: 11px;
        }
        
        #page_label {
            color: #E0E0E0;
            font-size: 11px;
        }
        
        #page_size_label {
            color: #AAAAAA;
            font-size: 11px;
        }
        
        #input_field, #search_field {
            background-color: #2A2A2A;
            border: 1px solid #3A3A3A;
            border-radius: 6px;
            color: #E0E0E0;
            padding: 8px;
            font-size: 12px;
        }
        
        #readonly_field {
            background-color: #353535;
            border: 1px solid #454545;
            border-radius: 6px;
            color: #E0E0E0;
            padding: 8px;
            font-size: 11px;
        }
        
        #desc_field {
            background-color: #2A2A2A;
            border: 1px solid #3A3A3A;
            border-radius: 6px;
            color: #E0E0E0;
            padding: 8px;
            font-size: 12px;
        }
        
        #preview_text, #selected_preview_text {
            background-color: #1E1E1E;
            border: 1px solid #2D2D2D;
            border-radius: 8px;
            color: #E0E0E0;
            padding: 10px;
            font-family: Consolas;
            font-size: 11px;
        }
        
        #list_scroll {
            background-color: #1E1E1E;
            border: 1px solid #2D2D2D;
            border-radius: 8px;
        }
        
        #list_item[even="true"] {
            background-color: #252525;
            border: none;
        }
        
        #list_item[odd="true"] {
            background-color: #2A2A2A;
            border: none;
        }
        
        #list_item[selected="true"] {
            background-color: #333333;
            border: 1px solid #444444;
        }
        
        #list_index {
            color: #AAAAAA;
            font-family: Consolas;
            font-size: 10px;
        }
        
        #list_filename {
            color: #E0E0E0;
            font-family: Consolas;
            font-size: 10px;
        }
        
        #empty_list_label {
            color: #888888;
            padding: 10px;
            font-size: 11px;
            text-align: left;
        }
        
        #separator {
            background-color: #444444;
            border: none;
            height: 1px;
        }
        
        .QScrollArea {
            border: none;
            background-color: transparent;
        }
        
        .QScrollBar:vertical {
            background-color: #2A2A2A;
            width: 12px;
            border-radius: 6px;
        }
        
        .QScrollBar::handle:vertical {
            background-color: #444444;
            border-radius: 6px;
            min-height: 30px;
        }
        
        .QScrollBar::handle:vertical:hover {
            background-color: #555555;
        }
        
        .QScrollBar::add-line:vertical, .QScrollBar::sub-line:vertical {
            height: 0px;
        }
        """
        self.setStyleSheet(style)
            
    def load_window_state(self):
        """加载窗口状态"""
        try:
            with open("window_config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
                
            if "geometry" in config and len(config["geometry"]) == 4:
                self.setGeometry(QRect(*config["geometry"]))
                    
            if "data_dir" in config and config["data_dir"]:
                self.data_manager.set_data_dir(config["data_dir"])
                self.folder_label.setText(config["data_dir"])
                self.refresh_list()
                self.refresh_code()
                
            if "field_labels" in config:
                self.field_labels = config["field_labels"]
                if hasattr(self, 'actor_label_entry'):
                    self.actor_label_entry.setText(self.field_labels.get("actor", "主演"))
                if hasattr(self, 'source_label_entry'):
                    self.source_label_entry.setText(self.field_labels.get("source", "来源"))
                if hasattr(self, 'record_label_entry'):
                    self.record_label_entry.setText(self.field_labels.get("record", "记录"))
                    
            if "field_visibility" in config:
                self.field_visibility = config["field_visibility"]
                # 恢复字段显示状态
                for field, visible in self.field_visibility.items():
                    if not visible:
                        self.toggle_field_visibility(field)
                
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"加载配置失败: {e}")
            
    def save_window_state(self):
        """保存窗口状态"""
        try:
            config = {
                "geometry": [self.x(), self.y(), self.width(), self.height()],
                "theme": self.current_theme,
                "data_dir": self.data_manager.data_dir,
                "field_labels": self.field_labels,
                "field_visibility": self.field_visibility
            }
            with open("window_config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")
            
    def closeEvent(self, event):
        """窗口关闭事件"""
        self.save_window_state()
        event.accept()
        
    def keyPressEvent(self, event):
        """快捷键处理"""
        if event.key() == Qt.Key.Key_S and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.save_record_with_toast()
        elif event.key() == Qt.Key.Key_C and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.copy_preview_with_toast()
        elif event.key() == Qt.Key.Key_R and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.refresh_list()
        elif event.key() == Qt.Key.Key_Delete:
            self.delete_selected_record()
        else:
            super().keyPressEvent(event)
            
    def showEvent(self, event):
        """窗口显示事件"""
        super().showEvent(event)
        QTimer.singleShot(100, self.setup_enter_key_navigation)
        QTimer.singleShot(200, self.load_preset_combo)  # 延迟加载预设列表


# ========== 程序入口 ==========
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())
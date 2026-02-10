"""编号资料管理器 - PyQt6重构版
基于原customtkinter版本重构，保持所有功能完整
作者：Rylan
日期：2026年01月27日
PyQt6重构版本 - 添加Enter键跳转功能
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
                             QGroupBox, QRadioButton, QButtonGroup, QDialog, QProgressDialog)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize, QRect, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QPalette, QColor, QClipboard, QKeyEvent, QIcon, QPainter, QLinearGradient

# ========== 数据管理器类（保持不变）==========
class DataManager:
    """数据管理类 - 使用SQLite数据库优化搜索性能"""
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
        """初始化数据库"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            cursor = self.conn.cursor()
            
            # 创建记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS records (
                    code TEXT PRIMARY KEY,
                    actor TEXT,
                    source TEXT,
                    record_text TEXT,
                    resource TEXT,
                    tags TEXT,
                    description TEXT,
                    json_data TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建搜索索引
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_actor ON records(actor)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_source ON records(source)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_tags ON records(tags)
            ''')
            
            # 创建全文搜索虚拟表（用于快速搜索）
            cursor.execute('''
                CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
                    code, actor, source, record_text, resource, tags, description,
                    content='records', content_rowid='rowid'
                )
            ''')
            
            # 创建触发器：自动更新全文搜索表
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS records_ai AFTER INSERT ON records BEGIN
                    INSERT INTO records_fts(rowid, code, actor, source, record_text, resource, tags, description)
                    VALUES (new.rowid, new.code, new.actor, new.source, new.record_text, new.resource, new.tags, new.description);
                END
            ''')
            
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS records_ad AFTER DELETE ON records BEGIN
                    DELETE FROM records_fts WHERE rowid = old.rowid;
                END
            ''')
            
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS records_au AFTER UPDATE ON records BEGIN
                    UPDATE records_fts SET 
                        code = new.code,
                        actor = new.actor,
                        source = new.source,
                        record_text = new.record_text,
                        resource = new.resource,
                        tags = new.tags,
                        description = new.description
                    WHERE rowid = old.rowid;
                END
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

    def save_record(self, data: Dict) -> bool:
        """保存记录（同时保存到JSON和数据库）"""
        try:
            if not self.data_dir:
                return False
            
            code = data.get("编号", "")
            if not code:
                return False
            
            # 1. 保存到JSON文件（保持兼容性）
            file_path = os.path.join(self.data_dir, f"{code}.json")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 2. 保存到数据库
            if self.conn:
                cursor = self.conn.cursor()
                
                # 提取字段
                actor = data.get("主演", "")
                source = data.get("来源", "")
                record_text = data.get("记录", "")
                resource = data.get("资源", "")
                tags = " ".join(data.get("标签", []))  # 标签用空格连接
                description = data.get("简介", "")
                json_data = json.dumps(data, ensure_ascii=False)
                
                # 使用REPLACE实现插入或更新
                cursor.execute('''
                    REPLACE INTO records 
                    (code, actor, source, record_text, resource, tags, description, json_data, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (code, actor, source, record_text, resource, tags, description, json_data))
                
                self.conn.commit()
            
            # 3. 更新缓存
            self.file_cache[code] = data
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
        """搜索记录（使用数据库全文搜索，性能大幅提升）"""
        if not keyword:
            # 空搜索返回所有记录
            if self.conn:
                cursor = self.conn.cursor()
                cursor.execute('SELECT code FROM records ORDER BY code')
                return [row[0] for row in cursor.fetchall()]
            else:
                return sorted(self.file_cache.keys())
        
        keyword = keyword.lower()
        
        # 使用数据库全文搜索
        if self.conn:
            try:
                cursor = self.conn.cursor()
                # 使用LIKE搜索（兼容性更好）
                search_pattern = f'%{keyword}%'
                cursor.execute('''
                    SELECT code FROM records 
                    WHERE code LIKE ? 
                       OR actor LIKE ? 
                       OR source LIKE ? 
                       OR record_text LIKE ?
                       OR resource LIKE ?
                       OR tags LIKE ?
                       OR description LIKE ?
                    ORDER BY code
                ''', (search_pattern,) * 7)
                
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
                or any(keyword in tag.lower() for tag in data.get("标签", []))):
                results.append(name)
        return sorted(results)

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
    
    def sync_json_to_db(self, progress_callback=None) -> tuple:
        """同步JSON文件到数据库（数据迁移工具）
        返回: (成功数量, 失败数量, 总数)
        """
        if not self.data_dir or not self.conn:
            return (0, 0, 0)
        
        success_count = 0
        fail_count = 0
        total_count = 0
        
        try:
            # 获取所有JSON文件
            json_files = [f for f in os.listdir(self.data_dir) if f.endswith('.json')]
            total_count = len(json_files)
            
            for i, filename in enumerate(json_files):
                try:
                    file_path = os.path.join(self.data_dir, filename)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 保存到数据库
                    code = data.get("编号", "")
                    if code and self.conn:
                        cursor = self.conn.cursor()
                        actor = data.get("主演", "")
                        source = data.get("来源", "")
                        record_text = data.get("记录", "")
                        resource = data.get("资源", "")
                        tags = " ".join(data.get("标签", []))
                        description = data.get("简介", "")
                        json_data = json.dumps(data, ensure_ascii=False)
                        
                        cursor.execute('''
                            REPLACE INTO records 
                            (code, actor, source, record_text, resource, tags, description, json_data, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ''', (code, actor, source, record_text, resource, tags, description, json_data))
                        
                        success_count += 1
                    else:
                        fail_count += 1
                    
                    # 回调进度
                    if progress_callback:
                        progress_callback(i + 1, total_count)
                        
                except Exception as e:
                    print(f"导入文件 {filename} 失败: {e}")
                    fail_count += 1
            
            if self.conn:
                self.conn.commit()
            
            return (success_count, fail_count, total_count)
        except Exception as e:
            print(f"数据同步失败: {e}")
            return (success_count, fail_count, total_count)
    
    def __del__(self):
        """析构时关闭数据库连接"""
        if self.conn:
            self.conn.close()


# ========== 自定义组件 ==========
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
        
        # 使用柔和的颜色
        if self.message_type == "success":
            bg_color = "#4CAF50"  # 柔和的绿色
            border_color = "#388E3C"
        elif self.message_type == "warning":
            bg_color = "#FF9800"  # 柔和的橙色
            border_color = "#F57C00"
        elif self.message_type == "error":
            bg_color = "#F44336"  # 柔和的红色
            border_color = "#D32F2F"
        else:  # info
            bg_color = "#2196F3"  # 柔和的蓝色
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
        
        # 计算合适的大小
        self.adjustSize()
        
    def show_toast(self, duration=1800):
        """显示提示并自动关闭"""
        self.show()
        # 定位到父窗口右上角
        if self.parent():
            parent_rect = self.parent().geometry()
            x = parent_rect.x() + parent_rect.width() - self.width() - 20
            y = parent_rect.y() + 60  # 稍微靠下一点，避免被标题栏遮挡
            self.move(x, y)
        
        QTimer.singleShot(duration, self.close)


class StyledButton(QPushButton):
    """自定义样式按钮"""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setMinimumHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
    def set_style(self, bg_color, hover_color, text_color="#FFFFFF"):
        """设置按钮样式"""
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


# ========== 主窗口类 ==========
class MainWindow(QMainWindow):
    """主窗口 - PyQt6重构版"""
    
    def __init__(self):
        super().__init__()
        self.data_manager = DataManager()
        self.current_theme = "dark"
        self.field_labels = {
            "actor": "主演",
            "source": "来源",
            "record": "记录",
            "resource": "资源"
        }
        self.file_items = []  # 存储文件列表项
        self.current_selected_index = -1
        
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
        """创建顶部工具栏"""
        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("toolbar_frame")
        toolbar_frame.setFixedHeight(60)
        
        toolbar_layout = QHBoxLayout(toolbar_frame)
        toolbar_layout.setContentsMargins(20, 10, 20, 10)
        
        # 标题 - 去掉文件夹图标
        title_label = QLabel("编号资料管理器")
        title_label.setObjectName("title_label")
        title_font = QFont("Segoe UI", 15, QFont.Weight.Bold)
        title_label.setFont(title_font)
        
        # 右侧控制区域
        right_controls = QFrame()
        right_layout = QHBoxLayout(right_controls)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        
        # 目录选择区域
        dir_frame = QFrame()
        dir_layout = QHBoxLayout(dir_frame)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.setSpacing(10)
        
        # 选择目录按钮
        self.dir_button = StyledButton("📂 选择存储目录")
        self.dir_button.set_style("#555555", "#444444")
        self.dir_button.clicked.connect(self.choose_folder)
        
        # 目录标签
        self.folder_label = QLabel("未选择目录")
        self.folder_label.setObjectName("folder_label")
        
        dir_layout.addWidget(self.dir_button)
        dir_layout.addWidget(self.folder_label)
        
        # 添加到右侧控制区域
        right_layout.addWidget(dir_frame)
        
        # 添加到工具栏
        toolbar_layout.addWidget(title_label)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(right_controls)
        
        parent_layout.addWidget(toolbar_frame)
        
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
        left_layout.setContentsMargins(15, 15, 15, 15)  # 增加内边距，不紧贴边缘
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
        self.input_layout.setContentsMargins(5, 5, 5, 5)  # 增加容器内边距
        self.input_layout.setSpacing(10)  # 减少间距
        
        # 字段标签配置区域
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
        
        # 资源输入
        self.create_resource_input()
        
        # 简介输入
        self.create_description_section()
        
        # 按钮区域
        self.create_button_section()
        
        scroll_area.setWidget(input_container)
        scroll_area.setMinimumWidth(400)  # 设置最小宽度
        left_layout.addWidget(scroll_area)
        
        parent_layout.addWidget(left_frame, 1)  # 添加权重
        
    def create_field_labels_section(self):
        """创建字段标签配置区域 - 改为两行"""
        # 标题
        label_title = QLabel("⚙️ 字段标签设置：")
        label_title.setObjectName("field_label_title")
        self.input_layout.addWidget(label_title)
        
        # 第一行：主演和来源
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(5)
        
        # 主演字段
        actor_frame = QFrame()
        actor_layout = QHBoxLayout(actor_frame)
        actor_layout.setContentsMargins(0, 0, 0, 0)
        actor_layout.setSpacing(5)
        actor_layout.addWidget(QLabel("主演："))
        self.actor_label_entry = QLineEdit(self.field_labels["actor"])
        self.actor_label_entry.setPlaceholderText("主演")
        self.actor_label_entry.setFixedWidth(60)
        actor_layout.addWidget(self.actor_label_entry)
        self.actor_visibility_btn = StyledButton("显示")
        self.actor_visibility_btn.set_style("#666666", "#555555")
        self.actor_visibility_btn.clicked.connect(lambda: self.toggle_field_visibility("actor"))
        actor_layout.addWidget(self.actor_visibility_btn)
        row1_layout.addWidget(actor_frame)
        
        # 来源字段
        source_frame = QFrame()
        source_layout = QHBoxLayout(source_frame)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(5)
        source_layout.addWidget(QLabel("来源："))
        self.source_label_entry = QLineEdit(self.field_labels["source"])
        self.source_label_entry.setPlaceholderText("来源")
        self.source_label_entry.setFixedWidth(60)
        source_layout.addWidget(self.source_label_entry)
        self.source_visibility_btn = StyledButton("显示")
        self.source_visibility_btn.set_style("#666666", "#555555")
        self.source_visibility_btn.clicked.connect(lambda: self.toggle_field_visibility("source"))
        source_layout.addWidget(self.source_visibility_btn)
        row1_layout.addWidget(source_frame)
        
        row1_layout.addStretch()
        self.input_layout.addLayout(row1_layout)
        
        # 第二行：记录和资源
        row2_layout = QHBoxLayout()
        row2_layout.setSpacing(5)
        
        # 记录字段
        record_frame = QFrame()
        record_layout = QHBoxLayout(record_frame)
        record_layout.setContentsMargins(0, 0, 0, 0)
        record_layout.setSpacing(5)
        record_layout.addWidget(QLabel("记录："))
        self.record_label_entry = QLineEdit(self.field_labels["record"])
        self.record_label_entry.setPlaceholderText("记录")
        self.record_label_entry.setFixedWidth(60)
        record_layout.addWidget(self.record_label_entry)
        self.record_visibility_btn = StyledButton("显示")
        self.record_visibility_btn.set_style("#666666", "#555555")
        self.record_visibility_btn.clicked.connect(lambda: self.toggle_field_visibility("record"))
        record_layout.addWidget(self.record_visibility_btn)
        row2_layout.addWidget(record_frame)
        
        # 资源字段
        resource_frame = QFrame()
        resource_layout = QHBoxLayout(resource_frame)
        resource_layout.setContentsMargins(0, 0, 0, 0)
        resource_layout.setSpacing(5)
        resource_layout.addWidget(QLabel("资源："))
        self.resource_label_entry = QLineEdit(self.field_labels["resource"])
        self.resource_label_entry.setPlaceholderText("资源")
        self.resource_label_entry.setFixedWidth(60)
        resource_layout.addWidget(self.resource_label_entry)
        self.resource_visibility_btn = StyledButton("显示")
        self.resource_visibility_btn.set_style("#666666", "#555555")
        self.resource_visibility_btn.clicked.connect(lambda: self.toggle_field_visibility("resource"))
        resource_layout.addWidget(self.resource_visibility_btn)
        row2_layout.addWidget(resource_frame)
        
        row2_layout.addStretch()
        self.input_layout.addLayout(row2_layout)
        
        # 连接信号
        self.actor_label_entry.textChanged.connect(self.on_field_label_changed)
        self.source_label_entry.textChanged.connect(self.on_field_label_changed)
        self.record_label_entry.textChanged.connect(self.on_field_label_changed)
        self.resource_label_entry.textChanged.connect(self.on_field_label_changed)
        
    def create_prefix_input(self):
        """创建前缀输入"""
        row_layout = QHBoxLayout()
        
        label = QLabel("前缀：")
        label.setObjectName("input_label")
        label.setFixedWidth(60)
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
        label.setFixedWidth(60)
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
        self.actor_label.setFixedWidth(60)
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
        self.source_label.setFixedWidth(60)
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
        label.setFixedWidth(60)
        row_layout.addWidget(label)
        
        # 5个标签输入框
        self.tag_entries = []
        tag_container = QWidget()
        tag_layout = QHBoxLayout(tag_container)
        tag_layout.setContentsMargins(0, 0, 0, 0)
        tag_layout.setSpacing(5)
        
        for i in range(5):
            tag_entry = QLineEdit()
            tag_entry.setObjectName("input_field")
            tag_entry.setPlaceholderText(f"标签{i+1}")
            tag_entry.setMinimumWidth(70)  # 减小最小宽度
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
        self.record_label.setFixedWidth(60)
        row_layout.addWidget(self.record_label)
        
        self.record_entry = QLineEdit()
        self.record_entry.setObjectName("input_field")
        self.record_entry.setPlaceholderText(f"输入{self.field_labels['record']}")
        self.record_entry.textChanged.connect(self.update_preview)
        row_layout.addWidget(self.record_entry, 1)
        
        self.input_layout.addLayout(row_layout)
        
    def create_resource_input(self):
        """创建资源输入"""
        row_layout = QHBoxLayout()
        
        self.resource_label = QLabel(self.field_labels["resource"])
        self.resource_label.setObjectName("input_label")
        self.resource_label.setFixedWidth(60)
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
        label.setFixedWidth(60)
        row_layout.addWidget(label)
        
        self.desc_entry = QTextEdit()
        self.desc_entry.setObjectName("desc_field")
        self.desc_entry.setMinimumHeight(120)  # 增加高度
        self.desc_entry.textChanged.connect(self.update_preview)
        row_layout.addWidget(self.desc_entry, 1)
        
        self.input_layout.addLayout(row_layout)
        
    def create_button_section(self):
        """创建按钮区域"""
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        # 保存按钮
        self.save_button = StyledButton("💾 保存记录")
        self.save_button.set_style("#666666", "#555555")
        self.save_button.clicked.connect(self.save_record_with_toast)
        button_layout.addWidget(self.save_button)
        
        # 清空按钮
        self.clear_button = StyledButton("🗑️ 清空输入")
        self.clear_button.set_style("#888888", "#777777")
        self.clear_button.clicked.connect(self.clear_inputs)
        button_layout.addWidget(self.clear_button)
        
        self.input_layout.addLayout(button_layout)
        
    def create_right_panel(self, parent_layout):
        """创建右侧面板（预览区域）"""
        right_frame = QFrame()
        right_frame.setObjectName("right_frame")
        right_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(15, 15, 15, 15)  # 增加内边距，不紧贴边缘
        right_layout.setSpacing(12)  # 减少间距
        
        # 实时预览区域
        self.create_realtime_preview(right_layout)
        
        # 搜索区域
        self.create_search_section(right_layout)
        
        # 文件列表区域
        self.create_file_list(right_layout)
        
        # 选中记录预览区域
        self.create_selected_preview(right_layout)
        
        parent_layout.addWidget(right_frame, 1)  # 添加权重
        
    def create_realtime_preview(self, parent_layout):
        """创建实时预览区域"""
        # 标题和按钮
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
        
        parent_layout.addLayout(title_layout)
        
        # 预览文本框
        self.preview_text = QTextEdit()
        self.preview_text.setObjectName("preview_text")
        self.preview_text.setReadOnly(True)
        parent_layout.addWidget(self.preview_text, 2)  # 增加权重
        
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
        
        parent_layout.addLayout(search_layout)
        
    def create_file_list(self, parent_layout):
        """创建文件列表"""
        # 标题
        list_title = QLabel("📋 文件列表")
        list_title.setObjectName("section_title")
        parent_layout.addWidget(list_title)
        
        # 列表容器
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(2)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # 靠上对齐
        
        # 滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.list_container)
        scroll_area.setMaximumHeight(180)  # 限制最大高度
        scroll_area.setMinimumHeight(120)  # 设置最小高度
        scroll_area.setObjectName("list_scroll")
        
        parent_layout.addWidget(scroll_area, 1)  # 使用较小的权重
        
    def create_selected_preview(self, parent_layout):
        """创建选中记录预览区域"""
        # 标题
        preview_title = QLabel("📄 选中记录预览")
        preview_title.setObjectName("section_title")
        parent_layout.addWidget(preview_title)
        
        # 预览文本框
        self.selected_preview_text = QTextEdit()
        self.selected_preview_text.setObjectName("selected_preview_text")
        self.selected_preview_text.setReadOnly(True)
        parent_layout.addWidget(self.selected_preview_text, 2)  # 增加权重
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        # 恢复原来的颜色 - 编辑按钮用蓝色
        self.edit_button = StyledButton("✏️ 编辑")
        self.edit_button.set_style("#4A90D9", "#3A7BC8")
        self.edit_button.clicked.connect(self.edit_selected_record)
        self.edit_button.setEnabled(False)
        
        # 恢复原来的颜色 - 删除按钮用红色
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
        
        parent_layout.addLayout(button_layout)
        
    # ========== 新增：Enter键跳转功能 ==========
    def setup_enter_key_navigation(self):
        """设置Enter键导航功能"""
        # 字段标签设置区域的文本框
        field_label_entries = [
            self.actor_label_entry,    # 1. 主演标签
            self.source_label_entry,   # 2. 来源标签
            self.record_label_entry,   # 3. 记录标签
            self.resource_label_entry  # 4. 资源标签
        ]
        
        # 主要输入区域的文本框
        main_entries = [
            self.prefix_entry,         # 5. 前缀
            self.actor_entry,          # 6. 主演
            self.source_entry,         # 7. 来源
            *self.tag_entries,         # 8-12. 标签1-5
            self.record_entry,         # 13. 记录
            self.resource_entry        # 14. 资源
            # 简介文本框不包含在内（第15个）
        ]
        
        # 所有文本框列表（除了简介）
        all_entries = field_label_entries + main_entries
        
        # 为每个文本框设置Enter键跳转
        for i, entry in enumerate(all_entries):
            if i < len(all_entries) - 1:  # 不是最后一个文本框
                next_entry = all_entries[i + 1]
                entry.returnPressed.connect(lambda checked=False, ne=next_entry: ne.setFocus())
            else:  # 最后一个文本框（资源输入框）
                # 跳转到简介文本框
                entry.returnPressed.connect(lambda: self.desc_entry.setFocus())
        
        # 简介文本框的特殊处理：Ctrl+Enter保存记录
        self.desc_entry.keyPressEvent = self.desc_key_press_event
        
    def desc_key_press_event(self, event):
        """简介文本框的按键事件处理"""
        if event.key() == Qt.Key.Key_Return and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            # Ctrl+Enter 保存记录
            self.save_record_with_toast()
        else:
            # 调用原始的keyPressEvent
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
        # 清空现有列表
        for i in reversed(range(self.list_layout.count())):
            widget = self.list_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        self.file_items = []
        
        if not self.data_manager.data_dir:
            self.show_empty_list_message("请先选择存储目录")
            return
            
        keyword = self.search_entry.text()
        results = self.data_manager.search_records(keyword)
        
        if not results:
            self.show_empty_list_message("未找到匹配的记录")
            return
            
        for i, code in enumerate(results):
            self.create_list_item(i, code)
            
    def show_empty_list_message(self, message):
        """显示空列表提示"""
        label = QLabel(message)
        label.setObjectName("empty_list_label")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)  # 左对齐，垂直居中
        label.setContentsMargins(10, 5, 10, 5)
        self.list_layout.addWidget(label)
        
    def create_list_item(self, index, code):
        """创建列表项 - 固定高度"""
        item_frame = QFrame()
        item_frame.setObjectName("list_item")
        item_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        item_frame.setFixedHeight(28)  # 固定高度，不填充
        
        # 设置交替背景色
        if index % 2 == 0:
            item_frame.setProperty("even", True)
        else:
            item_frame.setProperty("odd", True)
            
        item_layout = QHBoxLayout(item_frame)
        item_layout.setContentsMargins(10, 0, 10, 0)  # 减少垂直边距
        
        # 序号
        index_label = QLabel(f"{index+1:03d}.")
        index_label.setObjectName("list_index")
        
        # 文件名
        file_label = QLabel(code)
        file_label.setObjectName("list_filename")
        
        item_layout.addWidget(index_label)
        item_layout.addWidget(file_label)
        item_layout.addStretch()
        
        # 点击事件
        item_frame.mousePressEvent = lambda e, idx=index: self.on_list_item_clicked(idx)
        
        self.list_layout.addWidget(item_frame)
        self.file_items.append(item_frame)
        
    def on_list_item_clicked(self, index):
        """列表项点击事件"""
        # 清除之前的选择
        for i, item in enumerate(self.file_items):
            if i == index:
                item.setProperty("selected", True)
            else:
                item.setProperty("selected", False)
            item.style().polish(item)
        
        self.current_selected_index = index
        
        # 启用按钮
        self.edit_button.setEnabled(True)
        self.delete_button.setEnabled(True)
        
        # 获取并显示记录
        keyword = self.search_entry.text()
        results = self.data_manager.search_records(keyword)
        if index < len(results):
            code = results[index]
            record = self.data_manager.get_record(code)
            if record:
                self.display_selected_record(record)
                
    def display_selected_record(self, record):
        """显示选中的记录"""
        # 构建预览内容
        tags_text = " ".join(f"#{tag}" for tag in record.get("标签", []) if tag)
        content = f"编号：#{record.get('编号', '')}\n"
        
        # 根据字段标签配置显示内容
        actor_label = self.actor_label_entry.text().strip() or self.field_labels["actor"]
        if actor_label and record.get('主演'):
            content += f"{actor_label}：#{record.get('主演', '')}\n"
            
        source_label = self.source_label_entry.text().strip() or self.field_labels["source"]
        if source_label and record.get('来源'):
            content += f"{source_label}：#{record.get('来源', '')}\n"
            
        if tags_text:
            content += f"标签：{tags_text}\n"
            
        record_label = self.record_label_entry.text().strip() or self.field_labels["record"]
        if record_label and record.get('记录'):
            content += f"{record_label}：{record.get('记录', '')}\n"
            
        resource_label = self.resource_label_entry.text().strip() or self.field_labels["resource"]
        if resource_label and record.get('资源'):
            content += f"\n{resource_label}：{record.get('资源', '')}\n"
            
        desc = record.get('简介', '')
        if desc:
            content += f"简介：{desc}"
            
        self.selected_preview_text.setText(content)
        
    def update_preview(self):
        """更新实时预览"""
        # 构建预览内容
        content = f"编号：#{self.code_entry.text()}\n"
        
        # 根据字段标签配置显示内容
        actor_label = self.actor_label_entry.text().strip() or self.field_labels["actor"]
        actor_value = self.actor_entry.text().strip()
        if actor_label and actor_value:
            content += f"{actor_label}：#{actor_value}\n"
            
        source_label = self.source_label_entry.text().strip() or self.field_labels["source"]
        source_value = self.source_entry.text().strip()
        if source_label and source_value:
            content += f"{source_label}：#{source_value}\n"
            
        # 标签
        tags = []
        for entry in self.tag_entries:
            tag = entry.text().strip()
            if tag:
                tags.append(f"#{tag}")
        if tags:
            content += f"标签：{' '.join(tags)}\n"
            
        # 记录
        record_label = self.record_label_entry.text().strip() or self.field_labels["record"]
        record_value = self.record_entry.text().strip()
        if record_label and record_value:
            content += f"{record_label}：{record_value}\n"
            
        # 资源
        resource_label = self.resource_label_entry.text().strip() or self.field_labels["resource"]
        resource_value = self.resource_entry.text().strip()
        if resource_label and resource_value:
            content += f"\n{resource_label}：{resource_value}\n"
            
        # 简介
        desc = self.desc_entry.toPlainText().strip()
        if desc:
            content += f"简介：{desc}"
            
        self.preview_text.setText(content)
        
    def save_record_with_toast(self):
        """保存记录"""
        if not self.data_manager.data_dir:
            self.show_warning_message("提示", "请先选择存储目录")
            return
            
        # 构建保存的数据
        data = {
            "编号": self.code_entry.text(),
            "创建时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # 根据字段标签配置添加数据
        actor_label = self.actor_label_entry.text().strip() or self.field_labels["actor"]
        if actor_label:
            data["主演"] = self.actor_entry.text()
            
        source_label = self.source_label_entry.text().strip() or self.field_labels["source"]
        if source_label:
            data["来源"] = self.source_entry.text()
            
        # 标签
        tags = [entry.text() for entry in self.tag_entries if entry.text().strip()]
        if tags:
            data["标签"] = tags
            
        # 记录
        record_label = self.record_label_entry.text().strip() or self.field_labels["record"]
        if record_label:
            data["记录"] = self.record_entry.text()
            
        # 资源
        resource_label = self.resource_label_entry.text().strip() or self.field_labels["resource"]
        if resource_label:
            data["资源"] = self.resource_entry.text()
            
        # 简介
        desc = self.desc_entry.toPlainText().strip()
        if desc:
            data["简介"] = desc
            
        if not data["编号"]:
            self.show_warning_message("提示", "编号不能为空")
            return
            
        if self.data_manager.save_record(data):
            self.show_toast_message("✅ 记录保存成功！", "success")
            self.refresh_list()
            self.refresh_code()
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
        """编辑选中的记录"""
        if self.current_selected_index == -1:
            self.show_warning_message("提示", "请先选择一个记录")
            return
            
        # 获取当前选中的记录
        keyword = self.search_entry.text()
        results = self.data_manager.search_records(keyword)
        if self.current_selected_index >= len(results):
            return
            
        code = results[self.current_selected_index]
        record = self.data_manager.get_record(code)
        
        if not record:
            self.show_error_message("错误", "无法加载记录数据")
            return
            
        # 将记录数据填充到输入区域
        # 编号（不可修改）
        self.code_entry.setText(record.get("编号", ""))
        
        # 主演
        self.actor_entry.setText(record.get("主演", ""))
        
        # 来源
        self.source_entry.setText(record.get("来源", ""))
        
        # 记录
        self.record_entry.setText(record.get("记录", ""))
        
        # 资源
        self.resource_entry.setText(record.get("资源", ""))
        
        # 标签
        tags = record.get("标签", [])
        for i, entry in enumerate(self.tag_entries):
            if i < len(tags):
                entry.setText(tags[i])
            else:
                entry.clear()
                
        # 简介
        self.desc_entry.setText(record.get("简介", ""))
        
        # 更新预览
        self.update_preview()
        
        self.show_toast_message("📝 记录加载成功", "info")
        
    def delete_selected_record(self):
        """删除选中的记录"""
        if self.current_selected_index == -1:
            self.show_warning_message("提示", "请先选择一个记录")
            return
            
        # 获取当前选中的记录
        keyword = self.search_entry.text()
        results = self.data_manager.search_records(keyword)
        if self.current_selected_index >= len(results):
            return
            
        code = results[self.current_selected_index]
        
        # 确认对话框
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
        
    def on_field_label_changed(self):
        """字段标签变化事件"""
        # 更新标签文本
        actor_label = self.actor_label_entry.text().strip()
        source_label = self.source_label_entry.text().strip()
        record_label = self.record_label_entry.text().strip()
        resource_label = self.resource_label_entry.text().strip()
        
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
            
        if resource_label:
            self.field_labels["resource"] = resource_label
            self.resource_label.setText(resource_label)
            self.resource_entry.setPlaceholderText(f"输入{resource_label}")
            
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
        elif field_type == "resource":
            btn = self.resource_visibility_btn
            label = self.resource_label
            entry = self.resource_entry
        else:
            return
            
        current_text = btn.text()
        
        if current_text == "显示":
            btn.setText("隐藏")
            label.hide()
            entry.hide()
            btn.set_style("#888888", "#777777")
        else:
            btn.setText("显示")
            label.show()
            entry.show()
            btn.set_style("#666666", "#555555")
            
    # ========== 工具方法 ==========
    def show_toast_message(self, message, msg_type="info"):
        """显示悬浮提示 - 使用柔和颜色"""
        toast = ToastMessage(self, message, msg_type)
        toast.show_toast()
        
    def show_warning_message(self, title, message):
        """显示警告消息 - 使用柔和颜色"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        # 应用自定义样式
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
        """显示错误消息 - 使用柔和颜色"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        # 应用自定义样式
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
            
        # 重新应用样式到所有子控件
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
        
        #input_field, #search_field {
            background-color: #2A2A2A;
            border: 1px solid #3A3A3A;
            border-radius: 6px;
            color: #E0E0E0;
            padding: 8px;
            font-size: 11px;
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
            font-size: 11px;
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
                # 自动刷新列表
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
                if hasattr(self, 'resource_label_entry'):
                    self.resource_label_entry.setText(self.field_labels.get("resource", "资源"))
                
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
                "field_labels": self.field_labels
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
        """窗口显示事件 - 初始化完成后设置Enter键导航"""
        super().showEvent(event)
        # 在窗口显示后设置Enter键导航
        QTimer.singleShot(100, self.setup_enter_key_navigation)


# ========== 程序入口 ==========
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())
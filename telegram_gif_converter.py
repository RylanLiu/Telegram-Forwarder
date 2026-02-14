#!/usr/bin/env python3
"""
Telegram GIF Converter
将短视频处理为 Telegram 可识别为 GIF 的 MP4 格式
"""

import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QProgressBar, QFileDialog,
    QGroupBox, QSpinBox, QCheckBox, QMessageBox, QAbstractItemView
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings, QSize
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QIcon
import subprocess
import json


class VideoProcessor(QThread):
    """视频处理线程"""
    progress = pyqtSignal(int)
    finished = pyqtSignal(str, bool, str)  # filepath, success, message
    
    def __init__(self, input_file, output_file, max_duration, remove_audio, target_size):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.max_duration = max_duration
        self.remove_audio = remove_audio
        self.target_size = target_size
    
    def run(self):
        try:
            # 获取视频信息
            duration = self.get_video_duration(self.input_file)
            
            if duration > self.max_duration:
                self.finished.emit(
                    self.input_file, 
                    False, 
                    f"视频时长 {duration:.1f}秒 超过限制 {self.max_duration}秒"
                )
                return
            
            # 构建 FFmpeg 命令
            cmd = self.build_ffmpeg_command()
            
            # 执行转换
            self.progress.emit(50)
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            _, stderr = process.communicate()
            
            if process.returncode == 0:
                file_size = os.path.getsize(self.output_file) / 1024 / 1024  # MB
                self.progress.emit(100)
                self.finished.emit(
                    self.input_file, 
                    True, 
                    f"成功！文件大小: {file_size:.2f} MB"
                )
            else:
                self.finished.emit(
                    self.input_file, 
                    False, 
                    f"FFmpeg 错误: {stderr[-200:]}"
                )
                
        except Exception as e:
            self.finished.emit(self.input_file, False, f"错误: {str(e)}")
    
    def get_video_duration(self, filepath):
        """获取视频时长"""
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'json',
            filepath
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        data = json.loads(result.stdout)
        return float(data['format']['duration'])
    
    def build_ffmpeg_command(self):
        """构建 FFmpeg 转换命令"""
        cmd = ['ffmpeg', '-i', self.input_file, '-y']
        
        # 视频编码设置 - 关键是使用 H.264 和优化参数
        cmd.extend([
            '-c:v', 'libx264',           # H.264 编码
            '-preset', 'slow',          # 编码速度预设
            '-crf', '20',                 # 质量控制 (18-28，越小质量越好)
            '-pix_fmt', 'yuv420p',        # 像素格式，兼容性好
            '-movflags', '+faststart',    # 优化流式传输
        ])
        
        # 音频处理
        if self.remove_audio:
            cmd.extend(['-an'])  # 移除音轨
        else:
            # 检查是否有音轨
            has_audio = self.check_has_audio(self.input_file)
            if not has_audio:
                cmd.extend(['-an'])
            else:
                cmd.extend(['-c:a', 'aac', '-b:a', '128k'])
        
        # 大小限制（可选）
        if self.target_size > 0:
            # 计算目标比特率
            duration = self.get_video_duration(self.input_file)
            target_bitrate = int((self.target_size * 8192) / duration)  # kbps
            cmd.extend(['-b:v', f'{target_bitrate}k', '-maxrate', f'{target_bitrate}k'])
        
        cmd.append(self.output_file)
        return cmd
    
    def check_has_audio(self, filepath):
        """检查视频是否有音轨"""
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'a',
            '-show_entries', 'stream=codec_type',
            '-of', 'json',
            filepath
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        data = json.loads(result.stdout)
        return len(data.get('streams', [])) > 0


class DropListWidget(QListWidget):
    """支持拖放的列表控件"""
    files_dropped = pyqtSignal(list)
    
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # 添加圆角样式
        self.setStyleSheet("""
            QListWidget {
                border: 1px solid #ccc;
                border-radius: 8px;
                padding: 5px;
            }
        """)
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    
    def dropEvent(self, event: QDropEvent):
        files = []
        for url in event.mimeData().urls():
            filepath = url.toLocalFile()
            if filepath.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
                files.append(filepath)
        
        if files:
            self.files_dropped.emit(files)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Telegram GIF 转换器")
        self.setMinimumSize(700, 600)
        
        # 设置窗口图标
        icon_path = "app.ico"
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self.video_queue = []
        self.processing = False
        self.current_processor = None
        
        # 加载窗口大小设置
        self.settings = QSettings("TelegramGIFConverter", "MainWindow")
        self.load_window_settings()
        
        self.init_ui()
        self.check_ffmpeg()
    
    def load_window_settings(self):
        """加载窗口大小和位置"""
        if self.settings.contains("geometry"):
            self.restoreGeometry(self.settings.value("geometry"))
        if self.settings.contains("windowState"):
            self.restoreState(self.settings.value("windowState"))
    
    def closeEvent(self, event):
        """保存窗口大小和位置"""
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        event.accept()
    
    def init_ui(self):
        """初始化界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        # 标题
        title = QLabel("📹 Telegram GIF 转换器")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        main_layout.addWidget(title)
        
        # 设置面板
        settings_group = QGroupBox("转换设置")
        settings_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #ccc;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        settings_layout = QVBoxLayout()
        
        # 最大时长
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("最大时长 (秒):"))
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 300)
        self.duration_spin.setValue(60)
        self.duration_spin.setStyleSheet("""
            QSpinBox {
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 3px;
            }
        """)
        duration_layout.addWidget(self.duration_spin)
        duration_layout.addStretch()
        settings_layout.addLayout(duration_layout)
        
        # 移除音轨选项
        self.remove_audio_check = QCheckBox("强制移除音轨 (推荐，Telegram 更可能识别为 GIF)")
        self.remove_audio_check.setChecked(True)
        settings_layout.addWidget(self.remove_audio_check)
        
        # 目标文件大小
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("目标大小限制 (MB, 0=不限制):"))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(0, 50)
        self.size_spin.setValue(0)
        self.size_spin.setStyleSheet("""
            QSpinBox {
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 3px;
            }
        """)
        size_layout.addWidget(self.size_spin)
        size_layout.addStretch()
        settings_layout.addLayout(size_layout)
        
        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)
        
        # 文件列表
        file_group = QGroupBox("视频文件")
        file_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #ccc;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        file_layout = QVBoxLayout()
        
        self.file_list = DropListWidget()
        self.file_list.files_dropped.connect(self.add_files)
        file_layout.addWidget(self.file_list)
        
        # 按钮行
        btn_layout = QHBoxLayout()
        
        add_btn = QPushButton("➕ 添加文件")
        add_btn.setStyleSheet("""
            QPushButton {
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                background-color: #66BB6A;
                color: white;
            }
            QPushButton:hover {
                background-color: #57AB5A;
            }
            QPushButton:pressed {
                background-color: #4CAF50;
            }
        """)
        add_btn.clicked.connect(self.browse_files)
        btn_layout.addWidget(add_btn)
        
        clear_btn = QPushButton("🗑️ 清空列表")
        clear_btn.setStyleSheet("""
            QPushButton {
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                background-color: #EF5350;
                color: white;
            }
            QPushButton:hover {
                background-color: #E53935;
            }
            QPushButton:pressed {
                background-color: #D32F2F;
            }
        """)
        clear_btn.clicked.connect(self.file_list.clear)
        btn_layout.addWidget(clear_btn)
        
        remove_btn = QPushButton("➖ 移除选中")
        remove_btn.setStyleSheet("""
            QPushButton {
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                background-color: #FFA726;
                color: white;
            }
            QPushButton:hover {
                background-color: #FB8C00;
            }
            QPushButton:pressed {
                background-color: #F57C00;
            }
        """)
        remove_btn.clicked.connect(self.remove_selected)
        btn_layout.addWidget(remove_btn)
        
        file_layout.addLayout(btn_layout)
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 8px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 7px;
            }
        """)
        main_layout.addWidget(self.progress_bar)
        
        # 状态标签
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("padding: 5px; color: #666666;")
        main_layout.addWidget(self.status_label)
        
        # 开始转换按钮
        self.convert_btn = QPushButton("🚀 开始转换")
        self.convert_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 16px;
                font-weight: bold;
                padding: 12px;
                border-radius: 10px;
                border: none;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.convert_btn.clicked.connect(self.start_conversion)
        main_layout.addWidget(self.convert_btn)
        
        # 提示信息
        tip = QLabel(
            "💡 提示：拖放视频文件到列表中，或点击\"添加文件\"按钮\n"
            "输出文件将保存在原文件同目录，文件名添加 _tg 后缀"
        )
        tip.setStyleSheet("color: gray; font-size: 11px; padding: 10px;")
        tip.setWordWrap(True)
        main_layout.addWidget(tip)
    
    def check_ffmpeg(self):
        """检查 FFmpeg 是否安装"""
        try:
            subprocess.run(
                ['ffmpeg', '-version'], 
                capture_output=True, 
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            QMessageBox.critical(
                self,
                "FFmpeg 未安装",
                "未检测到 FFmpeg！\n\n"
                "请安装 FFmpeg:\n"
                "• Ubuntu/Debian: sudo apt install ffmpeg\n"
                "• macOS: brew install ffmpeg\n"
                "• Windows: 从 ffmpeg.org 下载"
            )
            sys.exit(1)
    
    def browse_files(self):
        """浏览文件"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择视频文件",
            "",
            "视频文件 (*.mp4 *.mov *.avi *.mkv *.webm);;所有文件 (*.*)"
        )
        
        if files:
            self.add_files(files)
    
    def add_files(self, files):
        """添加文件到列表"""
        for filepath in files:
            # 检查是否已存在
            items = [self.file_list.item(i).text() for i in range(self.file_list.count())]
            if filepath not in items:
                self.file_list.addItem(filepath)
        
        self.status_label.setStyleSheet("padding: 5px; color: #2196F3;")
        self.status_label.setText(f"已添加 {len(files)} 个文件")
    
    def remove_selected(self):
        """移除选中的文件"""
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))
    
    def start_conversion(self):
        """开始转换"""
        if self.file_list.count() == 0:
            QMessageBox.warning(self, "提示", "请先添加视频文件！")
            return
        
        # 准备队列
        self.video_queue = [
            self.file_list.item(i).text() 
            for i in range(self.file_list.count())
        ]
        
        self.processing = True
        self.convert_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.process_next_video()
    
    def process_next_video(self):
        """处理下一个视频"""
        if not self.video_queue:
            # 全部完成
            self.processing = False
            self.convert_btn.setEnabled(True)
            self.progress_bar.setVisible(False)
            self.status_label.setStyleSheet("padding: 5px; color: #4CAF50;")
            self.status_label.setText("✅ 全部转换完成！")
            QMessageBox.information(self, "完成", "所有视频已转换完成！")
            return
        
        # 获取下一个文件
        input_file = self.video_queue.pop(0)
        
        # 生成输出文件名
        path = Path(input_file)
        output_file = str(path.parent / f"{path.stem}_tg.mp4")
        
        # 更新状态
        remaining = len(self.video_queue)
        self.status_label.setStyleSheet("padding: 5px; color: #FF9800;")
        self.status_label.setText(
            f"正在处理: {path.name} (剩余 {remaining} 个)"
        )
        
        # 创建处理线程
        self.current_processor = VideoProcessor(
            input_file,
            output_file,
            self.duration_spin.value(),
            self.remove_audio_check.isChecked(),
            self.size_spin.value()
        )
        
        self.current_processor.progress.connect(self.progress_bar.setValue)
        self.current_processor.finished.connect(self.on_video_finished)
        self.current_processor.start()
    
    def on_video_finished(self, filepath, success, message):
        """单个视频处理完成"""
        filename = Path(filepath).name
        
        if success:
            self.status_label.setStyleSheet("padding: 5px; color: #4CAF50;")
            self.status_label.setText(f"✅ {filename}: {message}")
        else:
            self.status_label.setStyleSheet("padding: 5px; color: #F44336;")
            self.status_label.setText(f"❌ {filename}: {message}")
            QMessageBox.warning(self, "转换失败", f"{filename}\n{message}")
        
        # 处理下一个
        self.process_next_video()


def main():
    app = QApplication(sys.argv)
    
    # 设置应用样式
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

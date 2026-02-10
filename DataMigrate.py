"""数据迁移工具 - 将现有JSON文件导入到SQLite数据库
作者：Rylan
日期：2026年02月10日
用途：一键将现有JSON格式的记录导入到数据库，提升搜索性能
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import json
import sqlite3
import threading

class DataMigrationTool:
    """数据迁移工具GUI"""
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("数据迁移工具")
        self.root.geometry("600x400")
        
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        
        self.data_dir = ""
        self.is_migrating = False
        
        self._create_ui()
    
    def _create_ui(self):
        """创建UI界面"""
        # 主标题
        title_label = ctk.CTkLabel(
            self.root,
            text="📦 数据迁移工具",
            font=("Segoe UI", 24, "bold")
        )
        title_label.pack(pady=20)
        
        # 说明文字
        desc_label = ctk.CTkLabel(
            self.root,
            text="将现有的JSON记录文件导入到SQLite数据库\n大幅提升搜索性能（10-100倍加速）",
            font=("Segoe UI", 12),
            text_color="#888888"
        )
        desc_label.pack(pady=10)
        
        # 选择目录框架
        dir_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        dir_frame.pack(pady=20, padx=40, fill="x")
        
        ctk.CTkLabel(
            dir_frame,
            text="数据目录:",
            font=("Segoe UI", 12)
        ).pack(side="left", padx=(0, 10))
        
        self.dir_label = ctk.CTkLabel(
            dir_frame,
            text="未选择",
            font=("Segoe UI", 11),
            text_color="#666666"
        )
        self.dir_label.pack(side="left", fill="x", expand=True)
        
        select_btn = ctk.CTkButton(
            dir_frame,
            text="选择目录",
            command=self._select_directory,
            width=100
        )
        select_btn.pack(side="right")
        
        # 进度框架
        progress_frame = ctk.CTkFrame(self.root)
        progress_frame.pack(pady=20, padx=40, fill="both", expand=True)
        
        self.status_label = ctk.CTkLabel(
            progress_frame,
            text="请选择数据目录",
            font=("Segoe UI", 11)
        )
        self.status_label.pack(pady=10)
        
        self.progress_bar = ctk.CTkProgressBar(progress_frame)
        self.progress_bar.pack(pady=10, padx=20, fill="x")
        self.progress_bar.set(0)
        
        self.detail_label = ctk.CTkLabel(
            progress_frame,
            text="",
            font=("Segoe UI", 10),
            text_color="#888888"
        )
        self.detail_label.pack(pady=5)
        
        # 操作按钮
        button_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        button_frame.pack(pady=20)
        
        self.migrate_btn = ctk.CTkButton(
            button_frame,
            text="🚀 开始迁移",
            command=self._start_migration,
            width=150,
            height=40,
            font=("Segoe UI", 13, "bold"),
            state="disabled"
        )
        self.migrate_btn.pack(side="left", padx=10)
        
        close_btn = ctk.CTkButton(
            button_frame,
            text="关闭",
            command=self.root.quit,
            width=100,
            height=40,
            fg_color="#555555",
            hover_color="#444444"
        )
        close_btn.pack(side="left", padx=10)
    
    def _select_directory(self):
        """选择数据目录"""
        directory = filedialog.askdirectory(title="选择数据目录")
        if directory:
            self.data_dir = directory
            self.dir_label.configure(text=directory)
            
            # 检查JSON文件数量
            json_count = len([f for f in os.listdir(directory) if f.endswith('.json')])
            
            if json_count > 0:
                self.status_label.configure(text=f"找到 {json_count} 个JSON文件")
                self.migrate_btn.configure(state="normal")
            else:
                self.status_label.configure(text="该目录下没有JSON文件")
                self.migrate_btn.configure(state="disabled")
    
    def _start_migration(self):
        """开始数据迁移"""
        if self.is_migrating:
            return
        
        self.is_migrating = True
        self.migrate_btn.configure(state="disabled", text="迁移中...")
        
        # 在新线程中执行迁移
        thread = threading.Thread(target=self._do_migration)
        thread.daemon = True
        thread.start()
    
    def _do_migration(self):
        """执行数据迁移（在线程中运行）"""
        try:
            db_path = os.path.join(self.data_dir, ".records.db")
            
            # 初始化数据库
            self._update_status("正在初始化数据库...")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # 创建表结构
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
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_actor ON records(actor)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_source ON records(source)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags ON records(tags)')
            
            conn.commit()
            
            # 获取所有JSON文件
            json_files = [f for f in os.listdir(self.data_dir) if f.endswith('.json')]
            total = len(json_files)
            
            success_count = 0
            fail_count = 0
            
            # 导入数据
            for i, filename in enumerate(json_files):
                try:
                    file_path = os.path.join(self.data_dir, filename)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    code = data.get("编号", "")
                    if code:
                        actor = data.get("主演", "")
                        source = data.get("来源", "")
                        record_text = data.get("记录", "")
                        resource = data.get("资源", "")
                        tags = " ".join(data.get("标签", []))
                        description = data.get("简介", "")
                        json_data = json.dumps(data, ensure_ascii=False)
                        
                        cursor.execute('''
                            REPLACE INTO records 
                            (code, actor, source, record_text, resource, tags, description, json_data)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (code, actor, source, record_text, resource, tags, description, json_data))
                        
                        success_count += 1
                    else:
                        fail_count += 1
                    
                    # 更新进度
                    progress = (i + 1) / total
                    self.root.after(0, lambda p=progress, c=i+1, t=total: self._update_progress(p, c, t))
                    
                except Exception as e:
                    print(f"导入文件 {filename} 失败: {e}")
                    fail_count += 1
            
            conn.commit()
            conn.close()
            
            # 完成
            self.root.after(0, lambda: self._migration_complete(success_count, fail_count, total))
            
        except Exception as e:
            self.root.after(0, lambda: self._migration_error(str(e)))
    
    def _update_status(self, text):
        """更新状态文字"""
        self.status_label.configure(text=text)
    
    def _update_progress(self, value, current, total):
        """更新进度条"""
        self.progress_bar.set(value)
        self.detail_label.configure(text=f"已处理: {current}/{total}")
    
    def _migration_complete(self, success, fail, total):
        """迁移完成"""
        self.is_migrating = False
        self.progress_bar.set(1.0)
        self.status_label.configure(text="✅ 迁移完成！")
        self.detail_label.configure(
            text=f"成功: {success}  失败: {fail}  总计: {total}"
        )
        self.migrate_btn.configure(state="normal", text="🚀 开始迁移")
        
        messagebox.showinfo(
            "迁移完成",
            f"数据迁移成功！\n\n成功导入: {success} 条记录\n失败: {fail} 条\n\n现在可以关闭此工具，重新打开主程序享受高速搜索！"
        )
    
    def _migration_error(self, error_msg):
        """迁移出错"""
        self.is_migrating = False
        self.status_label.configure(text="❌ 迁移失败")
        self.detail_label.configure(text=error_msg)
        self.migrate_btn.configure(state="normal", text="🚀 开始迁移")
        
        messagebox.showerror("错误", f"数据迁移失败:\n{error_msg}")
    
    def run(self):
        """运行程序"""
        self.root.mainloop()

if __name__ == "__main__":
    app = DataMigrationTool()
    app.run()

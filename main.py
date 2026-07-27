#!/usr/bin/env python3
"""
小说格式整理器 - 启动入口
"""
import sys
import os

# 把项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── 最先执行：把打包内的初始文件复制到 exe 旁边 ──────────────
from utils.paths import init_user_data
init_user_data()

# ── 依赖检查 ─────────────────────────────────────────────────
def check_deps():
    missing = []
    try: import customtkinter
    except ImportError: missing.append("customtkinter")
    try: from PIL import Image
    except ImportError: missing.append("Pillow")
    try: import chardet
    except ImportError: missing.append("chardet")
    try: import openpyxl
    except ImportError: missing.append("openpyxl")
    if missing:
        print("缺少依赖，请安装：")
        print(f"  py -m pip install {' '.join(missing)}")
        sys.exit(1)

check_deps()

from ui.app import main
main()

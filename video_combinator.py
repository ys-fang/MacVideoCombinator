#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
影片合併器 - VideoCombinator
將圖片和音檔按照檔名順序合併成影片
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import queue
import threading
import time
import tempfile
import shutil
from pathlib import Path
import re
from typing import List, Tuple, Optional
import logging
import platform
import subprocess
from moviepy import ImageClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips
from PIL import Image

class VideoJob:
    """影片處理工作類別"""
    def __init__(self, images_folder: str, audio_folder: str, output_path: str, group_size: int, job_id: int, merge_all: bool = False):
        self.images_folder = images_folder
        self.audio_folder = audio_folder
        self.output_path = output_path
        self.group_size = group_size
        self.job_id = job_id
        self.merge_all = merge_all  # 新增：是否合併為一個影片
        self.status = "等待中"
        self.progress = 0

class VideoCombinatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("影片合併器 VideoCombinator")
        self.root.geometry("800x750")  # 增加高度以容納新控件
        
        # 工作隊列
        self.job_queue = queue.Queue()
        self.current_job = None
        self.job_counter = 0
        self.is_processing = False
        self.stop_requested = False
        self.job_history = []  # 保存所有工作的歷史記錄
        
        # 編碼器效能記錄
        self.encoder_performance = {
            'hardware': {'total_time': 0, 'total_duration': 0, 'count': 0},
            'software': {'total_time': 0, 'total_duration': 0, 'count': 0}
        }
        
        # 路徑記憶功能
        self.last_images_path = os.path.expanduser("~")
        self.last_audio_path = os.path.expanduser("~")
        self.last_output_path = os.path.expanduser("~")
        
        # 設定臨時目錄（解決只讀文件系統問題）
        self.temp_dir = tempfile.mkdtemp(prefix="VideoCombinator_")
        
        # 檢查系統和硬體支援
        self.check_system_capabilities()
        
        # 設定logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        self.setup_ui()
        self.start_worker_thread()
    
    def check_system_capabilities(self):
        """檢查系統和硬體支援能力"""
        # 檢測系統類型和架構
        self.system_info = {
            'platform': platform.system(),
            'machine': platform.machine(),
            'is_apple_silicon': False,
            'ffmpeg_available': False,
            'hardware_encoders': [],
            'recommended_codec': 'libx264',
            'recommended_preset': 'medium'
        }
        
        # 檢測是否為Apple Silicon (Mac M系列)
        if (self.system_info['platform'] == 'Darwin' and 
            self.system_info['machine'] in ['arm64', 'aarch64']):
            self.system_info['is_apple_silicon'] = True
            print("🚀 偵測到 Apple Silicon (Mac M系列) 處理器")
        
        # 檢查FFmpeg及硬體編碼器支援
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self.system_info['ffmpeg_available'] = True
                print("✅ FFmpeg 可用")
                
                # 檢查硬體編碼器支援
                if self.system_info['is_apple_silicon']:
                    self._check_videotoolbox_support()
            else:
                print("⚠️ FFmpeg 可能有問題")
        except Exception as e:
            print(f"⚠️ FFmpeg 檢查失敗: {e}")
            
        try:
            # 測試 MoviePy 音訊功能
            from moviepy import AudioFileClip
            print("✅ MoviePy 音訊模組可用")
        except Exception as e:
            print(f"❌ MoviePy 音訊模組錯誤: {e}")
        
        # 顯示系統資訊
        self._print_system_info()
    
    def _check_videotoolbox_support(self):
        """檢查VideoToolbox硬體編碼器支援"""
        try:
            # 檢查h264_videotoolbox支援
            result = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                encoders_output = result.stdout
                
                if 'h264_videotoolbox' in encoders_output:
                    self.system_info['hardware_encoders'].append('h264_videotoolbox')
                    self.system_info['recommended_codec'] = 'h264_videotoolbox'
                    print("🎯 支援 H.264 VideoToolbox 硬體編碼")
                
                if 'hevc_videotoolbox' in encoders_output:
                    self.system_info['hardware_encoders'].append('hevc_videotoolbox')
                    print("🎯 支援 HEVC VideoToolbox 硬體編碼")
                
                # 如果有硬體編碼器，調整預設設定
                if self.system_info['hardware_encoders']:
                    self.system_info['recommended_preset'] = 'fast'
                    print("⚡ 將使用硬體加速編碼，預期效能提升約50%")
                    
        except Exception as e:
            print(f"⚠️ VideoToolbox 檢查失敗: {e}")
    
    def _print_system_info(self):
        """顯示系統資訊摘要"""
        print("\n📋 系統資訊摘要:")
        print(f"   平台: {self.system_info['platform']}")
        print(f"   架構: {self.system_info['machine']}")
        print(f"   Apple Silicon: {'是' if self.system_info['is_apple_silicon'] else '否'}")
        print(f"   建議編碼器: {self.system_info['recommended_codec']}")
        if self.system_info['hardware_encoders']:
            print(f"   硬體編碼器: {', '.join(self.system_info['hardware_encoders'])}")
        print()
    
    def _get_system_status_text(self):
        """取得系統狀態顯示文字"""
        if hasattr(self, 'system_info'):
            if self.system_info['is_apple_silicon']:
                codec = self.system_info.get('recommended_codec', 'libx264')
                if 'videotoolbox' in codec:
                    return f"🚀 Apple Silicon 偵測完成 - 已啟用硬體加速編碼 ({codec})"
                else:
                    return "🚀 Apple Silicon 偵測完成 - 硬體編碼器不可用，將使用軟體編碼"
            else:
                return f"💻 系統平台: {self.system_info.get('platform', 'Unknown')} - 使用軟體編碼"
        else:
            return "⏳ 正在檢測系統能力..."
    
    def setup_ui(self):
        """設置用戶界面"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置網格權重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # 標題
        title_label = ttk.Label(main_frame, text="影片合併器", font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 10))
        
        # 系統狀態顯示
        system_status_text = self._get_system_status_text()
        status_label = ttk.Label(main_frame, text=system_status_text, 
                                font=("Arial", 9), foreground="gray")
        status_label.grid(row=1, column=0, columnspan=3, pady=(0, 15))
        
        # 圖片資料夾選擇
        ttk.Label(main_frame, text="圖片資料夾:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.images_folder_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.images_folder_var, width=50).grid(row=2, column=1, sticky=(tk.W, tk.E), padx=(5, 5))
        ttk.Button(main_frame, text="瀏覽", command=self.select_images_folder).grid(row=2, column=2, padx=(5, 0))
        
        # 音檔資料夾選擇
        ttk.Label(main_frame, text="音檔資料夾:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.audio_folder_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.audio_folder_var, width=50).grid(row=3, column=1, sticky=(tk.W, tk.E), padx=(5, 5))
        ttk.Button(main_frame, text="瀏覽", command=self.select_audio_folder).grid(row=3, column=2, padx=(5, 0))
        
        # 輸出資料夾選擇
        ttk.Label(main_frame, text="輸出資料夾:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.output_folder_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.output_folder_var, width=50).grid(row=4, column=1, sticky=(tk.W, tk.E), padx=(5, 5))
        ttk.Button(main_frame, text="瀏覽", command=self.select_output_folder).grid(row=4, column=2, padx=(5, 0))
        
        # 群組大小設定
        ttk.Label(main_frame, text="每組數量:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.group_size_var = tk.IntVar(value=1)
        group_size_frame = ttk.Frame(main_frame)
        group_size_frame.grid(row=5, column=1, sticky=(tk.W, tk.E), padx=(5, 5))
        self.group_spinbox = ttk.Spinbox(group_size_frame, from_=1, to=100, textvariable=self.group_size_var, width=10)
        self.group_spinbox.pack(side=tk.LEFT)
        ttk.Label(group_size_frame, text="(多少個圖片和音檔為一組合併成一個影片)").pack(side=tk.LEFT, padx=(10, 0))
        
        # 全部合併選項
        self.merge_all_var = tk.BooleanVar(value=False)
        merge_all_frame = ttk.Frame(main_frame)
        merge_all_frame.grid(row=6, column=1, sticky=(tk.W, tk.E), padx=(5, 5), pady=(5, 0))
        self.merge_all_checkbox = ttk.Checkbutton(merge_all_frame, text="全部合併為一隻影片，不分組", 
                                                 variable=self.merge_all_var, command=self.on_merge_all_changed)
        self.merge_all_checkbox.pack(side=tk.LEFT)
        
        # 編碼器選擇選項
        encoder_frame = ttk.Frame(main_frame)
        encoder_frame.grid(row=7, column=1, sticky=(tk.W, tk.E), padx=(5, 5), pady=(5, 0))
        
        self.encoder_choice_var = tk.StringVar(value="auto")
        ttk.Label(encoder_frame, text="編碼器:").pack(side=tk.LEFT)
        encoder_combo = ttk.Combobox(encoder_frame, textvariable=self.encoder_choice_var, 
                                   values=["auto", "hardware", "software"], state="readonly", width=10)
        encoder_combo.pack(side=tk.LEFT, padx=(5, 10))
        
        # 說明文字
        encoder_help = ttk.Label(encoder_frame, text="auto=智能選擇, hardware=強制硬體, software=強制軟體", 
                               font=("Arial", 8), foreground="gray")
        encoder_help.pack(side=tk.LEFT)
        
        # 預覽和新增工作按鈕
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=8, column=0, columnspan=3, pady=20)
        ttk.Button(button_frame, text="預覽檔案", command=self.preview_files).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="新增工作", command=self.add_job).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="效能測試", command=self.run_benchmark).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="清除所有工作", command=self.clear_all_jobs).pack(side=tk.LEFT, padx=(0, 10))
        self.stop_button = ttk.Button(button_frame, text="停止處理", command=self.stop_processing, state='disabled')
        self.stop_button.pack(side=tk.LEFT)
        
        # 工作列表
        ttk.Label(main_frame, text="工作隊列:").grid(row=9, column=0, sticky=tk.W, pady=(20, 5))
        ttk.Label(main_frame, text="💡 提示：雙擊任一工作可開啟輸出資料夾", 
                 font=("Arial", 9), foreground="gray").grid(row=9, column=1, sticky=tk.W, padx=(5, 0), pady=(20, 5))
        
        # 工作列表框架
        jobs_frame = ttk.Frame(main_frame)
        jobs_frame.grid(row=10, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        jobs_frame.columnconfigure(0, weight=1)
        jobs_frame.rowconfigure(0, weight=1)
        
        # 工作列表樹狀視圖
        self.jobs_tree = ttk.Treeview(jobs_frame, columns=("狀態", "進度", "圖片資料夾", "音檔資料夾", "輸出資料夾"), show="tree headings", height=8)
        self.jobs_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 設定欄位標題和寬度
        self.jobs_tree.heading("#0", text="工作ID")
        self.jobs_tree.heading("狀態", text="狀態")
        self.jobs_tree.heading("進度", text="進度")
        self.jobs_tree.heading("圖片資料夾", text="圖片資料夾")
        self.jobs_tree.heading("音檔資料夾", text="音檔資料夾")
        self.jobs_tree.heading("輸出資料夾", text="輸出資料夾")
        
        self.jobs_tree.column("#0", width=80)
        self.jobs_tree.column("狀態", width=80)
        self.jobs_tree.column("進度", width=80)
        self.jobs_tree.column("圖片資料夾", width=150)
        self.jobs_tree.column("音檔資料夾", width=150)
        self.jobs_tree.column("輸出資料夾", width=150)
        
        # 綁定雙擊事件到輸出資料夾
        self.jobs_tree.bind("<Double-1>", self.on_tree_double_click)
        
        # 滾動條
        jobs_scrollbar = ttk.Scrollbar(jobs_frame, orient=tk.VERTICAL, command=self.jobs_tree.yview)
        jobs_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.jobs_tree.configure(yscrollcommand=jobs_scrollbar.set)
        
        # 日誌顯示
        ttk.Label(main_frame, text="處理日誌:").grid(row=11, column=0, sticky=tk.W, pady=(20, 5))
        
        log_frame = ttk.Frame(main_frame)
        log_frame.grid(row=12, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, width=80)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置主框架的行權重
        main_frame.rowconfigure(10, weight=1)
        main_frame.rowconfigure(12, weight=1)
    
    def on_merge_all_changed(self):
        """處理全部合併選項變化"""
        if self.merge_all_var.get():
            # 勾選時禁用群組設定
            self.group_spinbox.configure(state='disabled')
        else:
            # 取消勾選時啟用群組設定
            self.group_spinbox.configure(state='normal')
    
    def on_tree_double_click(self, event):
        """處理工作列表雙擊事件"""
        # 獲取點擊的項目
        item = self.jobs_tree.selection()[0] if self.jobs_tree.selection() else None
        if not item:
            return
        
        # 獲取該工作的輸出路徑
        try:
            job_id = int(self.jobs_tree.item(item, "text").replace("#", ""))
            
            # 從歷史記錄中找到對應的工作
            for job in self.job_history:
                if job.job_id == job_id:
                    if os.path.exists(job.output_path):
                        subprocess.Popen(['open', job.output_path])
                        self.log(f"已開啟輸出資料夾: {job.output_path}")
                    else:
                        messagebox.showwarning("警告", f"輸出資料夾不存在: {job.output_path}")
                    break
        except (ValueError, IndexError) as e:
            # 處理可能的錯誤
            self.log(f"無法開啟輸出資料夾: {e}")
    
    def select_images_folder(self):
        """選擇圖片資料夾"""
        folder = filedialog.askdirectory(title="選擇圖片資料夾", initialdir=self.last_images_path)
        if folder:
            self.images_folder_var.set(folder)
            self.last_images_path = folder
    
    def select_audio_folder(self):
        """選擇音檔資料夾"""
        folder = filedialog.askdirectory(title="選擇音檔資料夾", initialdir=self.last_audio_path)
        if folder:
            self.audio_folder_var.set(folder)
            self.last_audio_path = folder
    
    def select_output_folder(self):
        """選擇輸出資料夾"""
        folder = filedialog.askdirectory(title="選擇輸出資料夾", initialdir=self.last_output_path)
        if folder:
            self.output_folder_var.set(folder)
            self.last_output_path = folder
    
    def get_sorted_files(self, folder: str, extensions: List[str]) -> List[str]:
        """獲取資料夾中指定副檔名的檔案，並按檔名排序"""
        files = []
        if os.path.exists(folder):
            for file in os.listdir(folder):
                if any(file.lower().endswith(ext.lower()) for ext in extensions):
                    files.append(file)
        
        # 使用自然排序（考慮數字順序）
        def natural_sort_key(s):
            return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]
        
        return sorted(files, key=natural_sort_key)
    
    def preview_files(self):
        """預覽選中資料夾中的檔案"""
        images_folder = self.images_folder_var.get()
        audio_folder = self.audio_folder_var.get()
        
        if not images_folder or not audio_folder:
            messagebox.showwarning("警告", "請先選擇圖片和音檔資料夾")
            return
        
        # 獲取檔案列表
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.gif']
        audio_extensions = ['.mp3', '.wav', '.aac', '.m4a', '.flac', '.ogg']
        
        image_files = self.get_sorted_files(images_folder, image_extensions)
        audio_files = self.get_sorted_files(audio_folder, audio_extensions)
        
        # 顯示預覽視窗
        preview_window = tk.Toplevel(self.root)
        preview_window.title("檔案預覽")
        preview_window.geometry("600x400")
        
        # 建立筆記本頁籤
        notebook = ttk.Notebook(preview_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 圖片檔案頁籤
        image_frame = ttk.Frame(notebook)
        notebook.add(image_frame, text=f"圖片檔案 ({len(image_files)})")
        
        image_listbox = tk.Listbox(image_frame)
        image_listbox.pack(fill=tk.BOTH, expand=True)
        for img in image_files:
            image_listbox.insert(tk.END, img)
        
        # 音檔檔案頁籤
        audio_frame = ttk.Frame(notebook)
        notebook.add(audio_frame, text=f"音檔檔案 ({len(audio_files)})")
        
        audio_listbox = tk.Listbox(audio_frame)
        audio_listbox.pack(fill=tk.BOTH, expand=True)
        for audio in audio_files:
            audio_listbox.insert(tk.END, audio)
        
        # 對應關係頁籤
        mapping_frame = ttk.Frame(notebook)
        notebook.add(mapping_frame, text="對應關係")
        
        mapping_text = scrolledtext.ScrolledText(mapping_frame)
        mapping_text.pack(fill=tk.BOTH, expand=True)
        
        merge_all = self.merge_all_var.get()
        group_size = self.group_size_var.get()
        
        if merge_all:
            mapping_text.insert(tk.END, "模式: 全部合併為一隻影片\n\n")
            max_files = max(len(image_files), len(audio_files))
            for i in range(max_files):
                img_name = image_files[i] if i < len(image_files) else "無"
                audio_name = audio_files[i] if i < len(audio_files) else "無"
                mapping_text.insert(tk.END, f"  {i+1:2d}. {img_name} <-> {audio_name}\n")
        else:
            mapping_text.insert(tk.END, f"每組數量: {group_size}\n\n")
            max_files = max(len(image_files), len(audio_files))
            for i in range(0, max_files, group_size):
                group_num = i // group_size + 1
                mapping_text.insert(tk.END, f"第 {group_num} 組:\n")
                
                for j in range(i, min(i + group_size, max_files)):
                    img_name = image_files[j] if j < len(image_files) else "無"
                    audio_name = audio_files[j] if j < len(audio_files) else "無"
                    mapping_text.insert(tk.END, f"  {j+1:2d}. {img_name} <-> {audio_name}\n")
                
                mapping_text.insert(tk.END, "\n")
    
    def add_job(self):
        """新增工作到隊列"""
        images_folder = self.images_folder_var.get()
        audio_folder = self.audio_folder_var.get()
        output_folder = self.output_folder_var.get()
        group_size = self.group_size_var.get()
        
        # 驗證輸入
        if not images_folder or not os.path.exists(images_folder):
            messagebox.showerror("錯誤", "請選擇有效的圖片資料夾")
            return
        
        if not audio_folder or not os.path.exists(audio_folder):
            messagebox.showerror("錯誤", "請選擇有效的音檔資料夾")
            return
        
        if not output_folder:
            messagebox.showerror("錯誤", "請選擇輸出資料夾")
            return
        
        # 建立輸出資料夾
        os.makedirs(output_folder, exist_ok=True)
        
        # 建立工作
        self.job_counter += 1
        merge_all = self.merge_all_var.get()
        job = VideoJob(images_folder, audio_folder, output_folder, group_size, self.job_counter, merge_all)
        
        # 新增到隊列和歷史記錄
        self.job_queue.put(job)
        self.job_history.append(job)
        
        # 更新UI
        self.update_jobs_display()
        
        self.log(f"已新增工作 #{self.job_counter}")
    
    def clear_all_jobs(self):
        """清除所有工作"""
        # 清空隊列
        while not self.job_queue.empty():
            try:
                self.job_queue.get_nowait()
            except queue.Empty:
                break
        
        # 清空歷史記錄
        self.job_history.clear()
        
        # 清除顯示
        for item in self.jobs_tree.get_children():
            self.jobs_tree.delete(item)
        
        self.log("已清除所有工作")
    
    def stop_processing(self):
        """停止當前處理"""
        self.stop_requested = True
        self.stop_button.configure(state='disabled')
        self.log("🛑 已請求停止處理，等待當前工作完成...")
    
    def update_jobs_display(self):
        """更新工作顯示"""
        # 清除現有項目
        for item in self.jobs_tree.get_children():
            self.jobs_tree.delete(item)
        
        # 顯示所有工作歷史記錄
        for job in self.job_history:
            status_display = job.status
            if job == self.current_job:
                status_display = "處理中"
            
            self.jobs_tree.insert("", "end",
                                 text=f"#{job.job_id}",
                                 values=(status_display,
                                        f"{job.progress}%",
                                        os.path.basename(job.images_folder),
                                        os.path.basename(job.audio_folder),
                                        os.path.basename(job.output_path)))
    
    def start_worker_thread(self):
        """啟動工作處理執行緒"""
        worker_thread = threading.Thread(target=self.worker_loop, daemon=True)
        worker_thread.start()
    
    def worker_loop(self):
        """工作處理迴圈"""
        while True:
            try:
                if not self.is_processing and not self.job_queue.empty() and not self.stop_requested:
                    self.current_job = self.job_queue.get()
                    self.is_processing = True
                    
                    # 啟用停止按鈕
                    self.root.after(0, lambda: self.stop_button.configure(state='normal'))
                    
                    # 在主執行緒中更新UI
                    self.root.after(0, self.update_jobs_display)
                    
                    # 處理工作
                    if not self.stop_requested:
                        self.process_job(self.current_job)
                    
                    # 完成工作
                    self.current_job = None
                    self.is_processing = False
                    
                    # 禁用停止按鈕
                    self.root.after(0, lambda: self.stop_button.configure(state='disabled'))
                    
                    # 更新UI
                    self.root.after(0, self.update_jobs_display)
                
                elif self.stop_requested and not self.is_processing:
                    # 停止請求已處理完成
                    self.stop_requested = False
                    self.root.after(0, lambda: self.log("✅ 處理已停止"))
                
                time.sleep(0.1)  # 避免CPU占用過高
            except Exception as e:
                self.root.after(0, lambda: self.log(f"工作處理錯誤: {str(e)}"))
                self.is_processing = False
                self.current_job = None
                self.root.after(0, lambda: self.stop_button.configure(state='disabled'))
    
    def process_job(self, job: VideoJob):
        """處理單個工作"""
        try:
            self.root.after(0, lambda: self.log(f"開始處理工作 #{job.job_id}"))
            job.status = "處理中"
            
            # 獲取檔案列表
            image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']
            audio_extensions = ['.mp3', '.wav', '.aac', '.m4a', '.flac', '.ogg']
            
            image_files = self.get_sorted_files(job.images_folder, image_extensions)
            audio_files = self.get_sorted_files(job.audio_folder, audio_extensions)
            
            if not image_files:
                raise Exception("圖片資料夾中沒有找到支援的圖片檔案")
            
            if not audio_files:
                raise Exception("音檔資料夾中沒有找到支援的音檔檔案")
            
            # 計算需要建立的影片數量
            max_files = max(len(image_files), len(audio_files))
            
            if job.merge_all:
                # 全部合併為一個影片
                total_groups = 1
                self.root.after(0, lambda: self.log(f"將全部檔案合併為 1 個影片"))
                
                # 檢查是否需要停止
                if self.stop_requested:
                    self.root.after(0, lambda: self.log(f"🛑 收到停止請求，中斷處理"))
                    job.status = "已取消"
                    return
                
                # 建立包含所有檔案的影片
                self.create_video_for_group(job, 1, 0, max_files, image_files, audio_files)
                job.progress = 100
                self.root.after(0, self.update_jobs_display)
            else:
                # 分組處理
                total_groups = (max_files + job.group_size - 1) // job.group_size
                self.root.after(0, lambda: self.log(f"總共將建立 {total_groups} 個影片"))
                
                # 處理每個群組
                for group_idx in range(total_groups):
                    # 檢查是否需要停止
                    if self.stop_requested:
                        self.root.after(0, lambda: self.log(f"🛑 收到停止請求，中斷處理"))
                        job.status = "已取消"
                        return
                    
                    start_idx = group_idx * job.group_size
                    end_idx = min(start_idx + job.group_size, max_files)
                    
                    self.root.after(0, lambda g=group_idx+1: self.log(f"處理第 {g} 組..."))
                    
                    # 建立這個群組的影片
                    self.create_video_for_group(job, group_idx + 1, start_idx, end_idx, image_files, audio_files)
                    
                    # 更新進度
                    progress = int((group_idx + 1) / total_groups * 100)
                    job.progress = progress
                    self.root.after(0, self.update_jobs_display)
            
            job.status = "完成"
            job.progress = 100
            self.root.after(0, lambda: self.log(f"工作 #{job.job_id} 處理完成"))
            
        except Exception as e:
            job.status = "錯誤"
            error_msg = f"工作 #{job.job_id} 處理失敗: {str(e)}"
            self.root.after(0, lambda: self.log(error_msg))
            self.logger.error(error_msg)
    
    def create_video_for_group(self, job: VideoJob, group_num: int, start_idx: int, end_idx: int, 
                              image_files: List[str], audio_files: List[str]):
        """為一個群組建立影片"""
        try:
            clips = []
            
            for i in range(start_idx, end_idx):
                # 取得圖片和音檔
                img_path = None
                audio_path = None
                
                if i < len(image_files):
                    img_path = os.path.join(job.images_folder, image_files[i])
                
                if i < len(audio_files):
                    audio_path = os.path.join(job.audio_folder, audio_files[i])
                
                # 如果沒有圖片或音檔，跳過
                if not img_path or not audio_path or not os.path.exists(img_path) or not os.path.exists(audio_path):
                    self.root.after(0, lambda: self.log(f"跳過檔案：圖片={img_path}, 音檔={audio_path}"))
                    continue
                
                try:
                    # 載入音檔取得時長
                    self.root.after(0, lambda a=audio_path: self.log(f"載入音檔：{os.path.basename(a)}"))
                    audio_clip = AudioFileClip(audio_path)
                    duration = audio_clip.duration
                    self.root.after(0, lambda d=duration: self.log(f"音檔時長：{d:.2f}秒"))
                    
                    # 建立圖片剪輯
                    self.root.after(0, lambda i=img_path: self.log(f"載入圖片：{os.path.basename(i)}"))
                    img_clip = ImageClip(img_path, duration=duration)
                    
                    # 確認音訊資訊
                    if hasattr(audio_clip, 'fps') and audio_clip.fps:
                        self.root.after(0, lambda: self.log(f"音檔採樣率：{audio_clip.fps}Hz"))
                    if hasattr(audio_clip, 'nchannels') and audio_clip.nchannels:
                        self.root.after(0, lambda: self.log(f"音檔聲道數：{audio_clip.nchannels}"))
                    
                    # 合併音檔
                    video_clip = img_clip.with_audio(audio_clip)
                    
                    # 確認合併後的影片是否有音訊
                    if video_clip.audio is not None:
                        self.root.after(0, lambda: self.log(f"✅ 音訊成功附加到影片"))
                    else:
                        self.root.after(0, lambda: self.log(f"⚠️ 警告：影片沒有音訊"))
                    
                    clips.append(video_clip)
                    
                except Exception as e:
                    self.root.after(0, lambda err=str(e): self.log(f"處理音檔時發生錯誤: {err}"))
                    # 如果音檔處理失敗，至少創建無聲影片
                    img_clip = ImageClip(img_path, duration=2.0)  # 預設2秒
                    clips.append(img_clip)
            
            if clips:
                # 確認所有剪輯都有音訊
                audio_clips_count = sum(1 for clip in clips if clip.audio is not None)
                self.root.after(0, lambda count=audio_clips_count, total=len(clips): 
                               self.log(f"剪輯統計：總數={total}, 有音訊={count}"))
                
                # 合併所有剪輯
                if len(clips) == 1:
                    # 只有一個剪輯，直接使用
                    final_clip = clips[0]
                    self.root.after(0, lambda: self.log(f"使用單一剪輯"))
                else:
                    # 多個剪輯，需要串接
                    self.root.after(0, lambda: self.log(f"串接 {len(clips)} 個剪輯，方法: compose"))
                    final_clip = concatenate_videoclips(clips, method='compose')
                
                # 生成檔案名稱：[第一個圖片檔名]-[最後一個圖片檔名].mp4
                first_img_name = ""
                last_img_name = ""
                
                # 找到第一個和最後一個有效的圖片檔名
                for i in range(start_idx, end_idx):
                    if i < len(image_files):
                        img_name = os.path.splitext(image_files[i])[0]  # 去除副檔名
                        if not first_img_name:
                            first_img_name = img_name
                        last_img_name = img_name
                
                if first_img_name and last_img_name:
                    if first_img_name == last_img_name:
                        output_filename = f"{first_img_name}.mp4"
                    else:
                        output_filename = f"{first_img_name}-{last_img_name}.mp4"
                else:
                    # 備用檔名
                    output_filename = f"video_group_{group_num:03d}.mp4"
                
                output_path = os.path.join(job.output_path, output_filename)
                
                # 確認最終剪輯是否有音訊
                if final_clip.audio is not None:
                    self.root.after(0, lambda: self.log(f"✅ 最終影片包含音訊，準備輸出"))
                    self.root.after(0, lambda: self.log(f"   最終音頻時長: {final_clip.audio.duration:.2f}秒"))
                    self.root.after(0, lambda: self.log(f"   最終音頻採樣率: {final_clip.audio.fps}Hz"))
                else:
                    self.root.after(0, lambda: self.log(f"⚠️ 警告：最終影片沒有音訊"))
                
                # 設定 MoviePy 環境變數，強制使用我們的臨時目錄
                import os as os_module
                original_temp_dir = os_module.environ.get('TEMP', '')
                original_tmp_dir = os_module.environ.get('TMP', '')
                original_tmpdir = os_module.environ.get('TMPDIR', '')
                
                try:
                    # 設定環境變數指向我們的臨時目錄
                    os_module.environ['TEMP'] = self.temp_dir
                    os_module.environ['TMP'] = self.temp_dir
                    os_module.environ['TMPDIR'] = self.temp_dir
                    
                    self.root.after(0, lambda: self.log(f"🗂️ 臨時目錄設定為：{self.temp_dir}"))
                    
                    # 輸出影片 - 使用測試證明有效的基本AAC方法，並強制臨時檔案路徑
                    self.root.after(0, lambda: self.log(f"開始輸出影片：{output_filename}"))

                    # 創建一個唯一的臨時音頻檔案路徑
                    temp_audio_path = os.path.join(self.temp_dir, f"temp-audio-{int(time.time() * 1000)}.m4a")
                    self.root.after(0, lambda: self.log(f"🎧 強制臨時音頻路徑為: {temp_audio_path}"))
                    
                    # 效能監控：記錄編碼開始時間
                    encoding_start_time = time.time()
                    
                    # 根據用戶選擇和系統能力選擇編碼器
                    codec, encoder_type = self._smart_encoder_selection(final_clip.duration)
                    
                    # 準備編碼參數
                    write_params = {
                        'fps': 24,
                        'codec': codec,
                        'audio_codec': 'aac',
                        'temp_audiofile': temp_audio_path,
                        'remove_temp': True,
                        'write_logfile': False,
                        'logger': None
                    }
                    
                    # 針對不同編碼器優化參數
                    if codec == 'h264_videotoolbox':
                        # Apple Silicon VideoToolbox 優化參數
                        # 注意：VideoToolbox不支援preset參數，使用bitrate控制
                        write_params.update({
                            'bitrate': '2800k',  # 適中的位元率
                            'ffmpeg_params': ['-profile:v', 'main', '-level:v', '4.0'],  # 指定H.264配置
                        })
                        self.root.after(0, lambda: self.log(f"🚀 使用 Apple Silicon 硬體加速編碼"))
                    elif codec == 'hevc_videotoolbox':
                        # HEVC VideoToolbox 優化參數
                        write_params.update({
                            'bitrate': '2000k',  # HEVC 可用較低位元率
                            'ffmpeg_params': ['-profile:v', 'main'],  # HEVC配置
                        })
                        self.root.after(0, lambda: self.log(f"🎯 使用 HEVC 硬體加速編碼"))
                    else:
                        # 軟體編碼器回退參數
                        write_params.update({
                            'preset': 'medium',  # 平衡品質和速度
                        })
                        self.root.after(0, lambda: self.log(f"⚙️ 使用軟體編碼器: {codec}"))
                    
                    self.root.after(0, lambda: self.log(f"📹 編碼參數: {codec}, fps={write_params['fps']}"))
                    
                    # 安全的編碼過程，支援自動回退
                    success = self._safe_encode_video(final_clip, output_path, write_params, codec, encoder_type)
                    
                    if success:
                        # 效能監控：計算編碼時間
                        encoding_time = time.time() - encoding_start_time
                        video_duration = final_clip.duration
                        encoding_speed = video_duration / encoding_time if encoding_time > 0 else 0
                        
                        # 記錄編碼器效能
                        self._record_encoder_performance(encoder_type, encoding_time, video_duration)
                        
                        self.root.after(0, lambda: self.log(f"✅ 影片輸出成功"))
                        self.root.after(0, lambda: self.log(f"⏱️ 編碼時間: {encoding_time:.1f}秒, 影片時長: {video_duration:.1f}秒"))
                        self.root.after(0, lambda: self.log(f"🚀 編碼速度: {encoding_speed:.2f}x 實時速度 ({encoder_type}編碼)"))
                        
                        # 顯示效能建議
                        self._show_performance_advice()
                    else:
                        self.root.after(0, lambda: self.log(f"❌ 影片編碼失敗，跳過此檔案"))
                        # 清理可能存在的不完整檔案
                        if os.path.exists(output_path):
                            os.remove(output_path)
                            self.root.after(0, lambda: self.log(f"🗑️ 已清理不完整的輸出檔案"))
                    
                finally:
                    # 恢復原始環境變數
                    if original_temp_dir:
                        os_module.environ['TEMP'] = original_temp_dir
                    elif 'TEMP' in os_module.environ:
                        del os_module.environ['TEMP']
                        
                    if original_tmp_dir:
                        os_module.environ['TMP'] = original_tmp_dir
                    elif 'TMP' in os_module.environ:
                        del os_module.environ['TMP']
                        
                    if original_tmpdir:
                        os_module.environ['TMPDIR'] = original_tmpdir
                    elif 'TMPDIR' in os_module.environ:
                        del os_module.environ['TMPDIR']
                
                # 釋放資源
                final_clip.close()
                for clip in clips:
                    clip.close()
                
                self.root.after(0, lambda: self.log(f"第 {group_num} 組影片已儲存: {output_filename}"))
            else:
                self.root.after(0, lambda: self.log(f"第 {group_num} 組沒有有效的檔案配對"))
                
        except Exception as e:
            error_msg = f"建立第 {group_num} 組影片時發生錯誤: {str(e)}"
            self.root.after(0, lambda: self.log(error_msg))
            raise e
    
    def _safe_encode_video(self, final_clip, output_path, write_params, codec, encoder_type):
        """安全的影片編碼過程，支援超時和自動回退"""
        import threading
        import signal
        from threading import Event
        
        encoding_result = {'success': False, 'error': None}
        stop_event = Event()
        
        def encode_with_timeout():
            """在獨立執行緒中進行編碼，支援超時控制"""
            try:
                self.root.after(0, lambda: self.log(f"⏳ 開始編碼，使用編碼器: {codec}"))
                final_clip.write_videofile(output_path, **write_params)
                encoding_result['success'] = True
                self.root.after(0, lambda: self.log(f"✅ 編碼成功完成"))
            except Exception as e:
                encoding_result['error'] = str(e)
                self.root.after(0, lambda: self.log(f"❌ 編碼失敗: {str(e)}"))
        
        # 啟動編碼執行緒
        encode_thread = threading.Thread(target=encode_with_timeout, daemon=True)
        encode_thread.start()
        
        # 等待編碼完成，設定超時時間（根據影片時長調整）
        video_duration = final_clip.duration
        timeout_seconds = max(120, video_duration * 10)  # 至少2分鐘，或影片時長的10倍
        
        self.root.after(0, lambda: self.log(f"⏱️ 編碼超時設定: {timeout_seconds:.0f}秒"))
        
        encode_thread.join(timeout=timeout_seconds)
        
        if encode_thread.is_alive():
            # 編碼超時
            self.root.after(0, lambda: self.log(f"⚠️ 編碼超時，嘗試回退到軟體編碼"))
            
            # 如果是硬體編碼器，嘗試軟體編碼
            if 'videotoolbox' in codec:
                return self._fallback_to_software_encoding(final_clip, output_path, write_params)
            else:
                self.root.after(0, lambda: self.log(f"❌ 軟體編碼也超時，編碼失敗"))
                return False
        
        if not encoding_result['success'] and encoding_result['error']:
            # 編碼失敗
            self.root.after(0, lambda: self.log(f"⚠️ 編碼失敗，錯誤: {encoding_result['error']}"))
            
            # 如果是硬體編碼器，嘗試軟體編碼
            if 'videotoolbox' in codec:
                return self._fallback_to_software_encoding(final_clip, output_path, write_params)
            else:
                return False
        
        return encoding_result['success']
    
    def _fallback_to_software_encoding(self, final_clip, output_path, write_params):
        """回退到軟體編碼"""
        self.root.after(0, lambda: self.log(f"🔄 回退到軟體編碼器 (libx264)"))
        
        # 修改編碼參數為軟體編碼
        fallback_params = write_params.copy()
        fallback_params.update({
            'codec': 'libx264',
            'preset': 'medium',
            'bitrate': '2800k'
        })
        
        # 移除VideoToolbox特有的參數
        if 'ffmpeg_params' in fallback_params:
            del fallback_params['ffmpeg_params']
        
        try:
            self.root.after(0, lambda: self.log(f"⏳ 開始軟體編碼"))
            final_clip.write_videofile(output_path, **fallback_params)
            self.root.after(0, lambda: self.log(f"✅ 軟體編碼成功完成"))
            return True
        except Exception as e:
            self.root.after(0, lambda: self.log(f"❌ 軟體編碼也失敗: {str(e)}"))
            return False
    
    def _smart_encoder_selection(self, video_duration):
        """智能編碼器選擇"""
        user_choice = self.encoder_choice_var.get()
        
        if user_choice == "software":
            # 用戶強制軟體編碼
            self.root.after(0, lambda: self.log(f"🔧 用戶選擇：強制使用軟體編碼"))
            return 'libx264', 'software'
        
        elif user_choice == "hardware":
            # 用戶強制硬體編碼
            if self.system_info.get('hardware_encoders'):
                codec = self.system_info.get('recommended_codec', 'libx264')
                self.root.after(0, lambda: self.log(f"🔧 用戶選擇：強制使用硬體編碼"))
                return codec, 'hardware'
            else:
                self.root.after(0, lambda: self.log(f"⚠️ 硬體編碼不可用，回退到軟體編碼"))
                return 'libx264', 'software'
        
        else:  # user_choice == "auto"
            # 智能自動選擇
            return self._auto_select_encoder(video_duration)
    
    def _auto_select_encoder(self, video_duration):
        """自動選擇最佳編碼器"""
        # 如果沒有硬體編碼器，直接使用軟體
        if not self.system_info.get('hardware_encoders'):
            self.root.after(0, lambda: self.log(f"🤖 智能選擇：無硬體編碼器，使用軟體編碼"))
            return 'libx264', 'software'
        
        # 短影片偏好軟體編碼（避免硬體初始化開銷）
        if video_duration < 5.0:
            self.root.after(0, lambda: self.log(f"🤖 智能選擇：短影片({video_duration:.1f}s)，使用軟體編碼"))
            return 'libx264', 'software'
        
        # 基於歷史效能數據選擇
        hw_perf = self.encoder_performance['hardware']
        sw_perf = self.encoder_performance['software']
        
        if hw_perf['count'] > 0 and sw_perf['count'] > 0:
            # 計算平均編碼速度（影片時長/編碼時間）
            hw_speed = hw_perf['total_duration'] / hw_perf['total_time'] if hw_perf['total_time'] > 0 else 0
            sw_speed = sw_perf['total_duration'] / sw_perf['total_time'] if sw_perf['total_time'] > 0 else 0
            
            if hw_speed > sw_speed * 1.1:  # 硬體需要快10%以上才選用（考慮穩定性）
                self.root.after(0, lambda: self.log(f"🤖 智能選擇：硬體編碼較快({hw_speed:.2f}x vs {sw_speed:.2f}x)"))
                return self.system_info.get('recommended_codec', 'libx264'), 'hardware'
            else:
                self.root.after(0, lambda: self.log(f"🤖 智能選擇：軟體編碼較快({sw_speed:.2f}x vs {hw_speed:.2f}x)"))
                return 'libx264', 'software'
        
        # 預設策略：中等長度影片嘗試硬體編碼
        if video_duration >= 10.0:
            self.root.after(0, lambda: self.log(f"🤖 智能選擇：長影片({video_duration:.1f}s)，嘗試硬體編碼"))
            return self.system_info.get('recommended_codec', 'libx264'), 'hardware'
        else:
            self.root.after(0, lambda: self.log(f"🤖 智能選擇：中短影片({video_duration:.1f}s)，使用軟體編碼"))
            return 'libx264', 'software'
    
    def _record_encoder_performance(self, encoder_type, encoding_time, video_duration):
        """記錄編碼器效能"""
        if encoder_type in self.encoder_performance:
            perf = self.encoder_performance[encoder_type]
            perf['total_time'] += encoding_time
            perf['total_duration'] += video_duration
            perf['count'] += 1
            
            # 計算平均速度
            avg_speed = perf['total_duration'] / perf['total_time'] if perf['total_time'] > 0 else 0
            self.root.after(0, lambda: self.log(f"📊 {encoder_type}編碼平均速度: {avg_speed:.2f}x ({perf['count']}次)"))
    
    def _show_performance_advice(self):
        """顯示效能建議"""
        hw_perf = self.encoder_performance['hardware']
        sw_perf = self.encoder_performance['software']
        
        # 需要足夠的樣本才給建議
        if hw_perf['count'] >= 3 and sw_perf['count'] >= 3:
            hw_speed = hw_perf['total_duration'] / hw_perf['total_time'] if hw_perf['total_time'] > 0 else 0
            sw_speed = sw_perf['total_duration'] / sw_perf['total_time'] if sw_perf['total_time'] > 0 else 0
            
            speed_diff = abs(hw_speed - sw_speed) / max(hw_speed, sw_speed) * 100
            
            if speed_diff > 20:  # 超過20%差異才給建議
                if hw_speed > sw_speed:
                    self.root.after(0, lambda: self.log(f"💡 建議：硬體編碼比軟體快{speed_diff:.1f}%，建議使用硬體編碼"))
                else:
                    self.root.after(0, lambda: self.log(f"💡 建議：軟體編碼比硬體快{speed_diff:.1f}%，建議使用軟體編碼"))
    
    def run_benchmark(self):
        """執行編碼器效能基準測試"""
        if not self.images_folder_var.get() or not self.audio_folder_var.get():
            messagebox.showwarning("警告", "請先選擇圖片和音檔資料夾進行測試")
            return
        
        if self.is_processing:
            messagebox.showwarning("警告", "正在處理工作，無法進行測試")
            return
        
        # 詢問用戶是否要進行測試
        result = messagebox.askyesno("效能測試", 
                                   "將使用第一個圖片和音檔檔案進行編碼器效能測試。\n"
                                   "這會產生兩個測試影片檔案。\n\n"
                                   "是否繼續？")
        if not result:
            return
        
        # 啟動測試執行緒
        benchmark_thread = threading.Thread(target=self._run_benchmark_test, daemon=True)
        benchmark_thread.start()
    
    def _run_benchmark_test(self):
        """執行基準測試的核心邏輯"""
        try:
            self.root.after(0, lambda: self.log(f"🧪 開始編碼器效能基準測試"))
            
            # 獲取測試檔案
            images_folder = self.images_folder_var.get()
            audio_folder = self.audio_folder_var.get()
            
            image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']
            audio_extensions = ['.mp3', '.wav', '.aac', '.m4a', '.flac', '.ogg']
            
            image_files = self.get_sorted_files(images_folder, image_extensions)
            audio_files = self.get_sorted_files(audio_folder, audio_extensions)
            
            if not image_files or not audio_files:
                self.root.after(0, lambda: self.log(f"❌ 找不到測試檔案"))
                return
            
            # 使用第一個圖片和音檔
            test_image = os.path.join(images_folder, image_files[0])
            test_audio = os.path.join(audio_folder, audio_files[0])
            
            self.root.after(0, lambda: self.log(f"📷 測試圖片: {image_files[0]}"))
            self.root.after(0, lambda: self.log(f"🎵 測試音檔: {audio_files[0]}"))
            
            # 創建測試剪輯
            from moviepy import ImageClip, AudioFileClip
            audio_clip = AudioFileClip(test_audio)
            duration = min(audio_clip.duration, 10.0)  # 限制測試時長最多10秒
            
            img_clip = ImageClip(test_image, duration=duration)
            test_clip = img_clip.with_audio(audio_clip.subclipped(0, duration))
            
            self.root.after(0, lambda: self.log(f"⏱️ 測試影片時長: {duration:.1f}秒"))
            
            # 創建臨時測試目錄
            test_dir = os.path.join(self.temp_dir, "benchmark_test")
            os.makedirs(test_dir, exist_ok=True)
            
            # 測試軟體編碼
            if True:  # 總是測試軟體編碼
                self.root.after(0, lambda: self.log(f"🔬 測試軟體編碼器 (libx264)"))
                start_time = time.time()
                
                try:
                    software_output = os.path.join(test_dir, "test_software.mp4")
                    test_clip.write_videofile(software_output,
                                            fps=24,
                                            codec='libx264',
                                            preset='medium',
                                            audio_codec='aac',
                                            write_logfile=False,
                                            logger=None)
                    
                    sw_time = time.time() - start_time
                    sw_speed = duration / sw_time if sw_time > 0 else 0
                    self.root.after(0, lambda: self.log(f"✅ 軟體編碼完成: {sw_time:.1f}秒 ({sw_speed:.2f}x)"))
                    
                    # 記錄效能
                    self._record_encoder_performance('software', sw_time, duration)
                    
                except Exception as e:
                    self.root.after(0, lambda: self.log(f"❌ 軟體編碼測試失敗: {str(e)}"))
                    sw_time = None
            
            # 測試硬體編碼
            if self.system_info.get('hardware_encoders'):
                self.root.after(0, lambda: self.log(f"🔬 測試硬體編碼器 ({self.system_info['recommended_codec']})"))
                start_time = time.time()
                
                try:
                    hardware_output = os.path.join(test_dir, "test_hardware.mp4")
                    test_clip.write_videofile(hardware_output,
                                            fps=24,
                                            codec=self.system_info['recommended_codec'],
                                            bitrate='2800k',
                                            ffmpeg_params=['-profile:v', 'main', '-level:v', '4.0'],
                                            audio_codec='aac',
                                            write_logfile=False,
                                            logger=None)
                    
                    hw_time = time.time() - start_time
                    hw_speed = duration / hw_time if hw_time > 0 else 0
                    self.root.after(0, lambda: self.log(f"✅ 硬體編碼完成: {hw_time:.1f}秒 ({hw_speed:.2f}x)"))
                    
                    # 記錄效能
                    self._record_encoder_performance('hardware', hw_time, duration)
                    
                except Exception as e:
                    self.root.after(0, lambda: self.log(f"❌ 硬體編碼測試失敗: {str(e)}"))
                    hw_time = None
            else:
                self.root.after(0, lambda: self.log(f"⚠️ 無硬體編碼器可測試"))
                hw_time = None
            
            # 比較結果
            self.root.after(0, lambda: self.log(f"🏁 基準測試完成"))
            if sw_time and hw_time:
                if hw_time < sw_time:
                    improvement = (sw_time - hw_time) / sw_time * 100
                    self.root.after(0, lambda: self.log(f"🎯 硬體編碼快 {improvement:.1f}%"))
                else:
                    degradation = (hw_time - sw_time) / sw_time * 100
                    self.root.after(0, lambda: self.log(f"⚠️ 硬體編碼慢 {degradation:.1f}%"))
            
            # 清理測試檔案
            test_clip.close()
            audio_clip.close()
            img_clip.close()
            
            # 顯示效能建議
            self._show_performance_advice()
            
        except Exception as e:
            self.root.after(0, lambda: self.log(f"❌ 基準測試失敗: {str(e)}"))
    
    def log(self, message: str):
        """新增日誌訊息"""
        timestamp = time.strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        
        self.log_text.insert(tk.END, log_message)
        self.log_text.see(tk.END)
        
        # 限制日誌長度
        lines = self.log_text.get("1.0", tk.END).split("\n")
        if len(lines) > 1000:
            self.log_text.delete("1.0", f"{len(lines)-500}.0")

def main():
    """主程式進入點"""
    root = tk.Tk()
    app = VideoCombinatorApp(root)
    
    # 設定程式圖示（如果有的話）
    try:
        # root.iconbitmap("icon.ico")  # 取消註解並提供圖示檔案
        pass
    except:
        pass
    
    # 設定關閉事件
    def on_closing():
        if messagebox.askokcancel("退出", "確定要退出影片合併器嗎？"):
            # 清理臨時目錄
            try:
                if hasattr(app, 'temp_dir') and os.path.exists(app.temp_dir):
                    shutil.rmtree(app.temp_dir)
            except Exception as e:
                print(f"清理臨時目錄時發生錯誤: {e}")
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    # 啟動應用程式
    root.mainloop()

if __name__ == "__main__":
    main() 
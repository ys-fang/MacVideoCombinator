#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
影片合併器 - VideoCombinator2 (YouTube 友善 + Apple Silicon 最佳化)
核心改動：
- 改用 FFmpeg/FFprobe 子程序，避免 MoviePy 中介開銷
- 預設 H.264（High/4.2）與 24/30fps、BT.709、yuv420p，對 YouTube 友善
- 以「分段輸出 → concat -c copy」方式合併，零重編碼（快速穩定）
- 支援 Apple Silicon VideoToolbox（h264_videotoolbox），自動/強制/回退
- GUI 保留：資料夾選擇、群組/全部合併、編碼器選擇、FPS/解析度、預覽、工作隊列、日誌
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
from typing import List, Optional, Tuple
import logging
import platform
import subprocess
import sys


class VideoJob:
    """影片處理工作類別 (v2)"""
    def __init__(
        self,
        images_folder: str,
        audio_folder: str,
        output_path: str,
        group_size: int,
        job_id: int,
        merge_all: bool = False,
        encoder_choice: str = "auto",  # auto | hardware | software
        fps: int = 24,  # 24 | 30
        resolution: str = "1080p",  # 720p | 1080p | 1440p
        codec_preference: str = "h264",  # h264 | hevc (選配)
    ):
        self.images_folder = images_folder
        self.audio_folder = audio_folder
        self.output_path = output_path
        self.group_size = group_size
        self.job_id = job_id
        self.merge_all = merge_all
        self.encoder_choice = encoder_choice
        self.fps = fps
        self.resolution = resolution
        self.codec_preference = codec_preference
        self.status = "等待中"
        self.progress = 0


class VideoCombinator2App:
    def __init__(self, root):
        self.root = root
        self.root.title("影片合併器 VideoCombinator2")
        self.root.geometry("900x780")

        # 工作隊列
        self.job_queue = queue.Queue()
        self.current_job: Optional[VideoJob] = None
        self.job_counter = 0
        self.is_processing = False
        self.stop_requested = False
        self.job_history: List[VideoJob] = []

        # 設定臨時目錄
        self.temp_dir = tempfile.mkdtemp(prefix="VideoCombinator2_")

        # logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)

        # 檢查系統與 FFmpeg 能力
        self._init_system_info()

        # UI
        self._setup_ui()

        # 背景工作執行緒
        self._start_worker_thread()

    # --------------------- 系統偵測 ---------------------
    def _init_system_info(self):
        self.system_info = {
            'platform': platform.system(),
            'machine': platform.machine(),
            'is_apple_silicon': False,
            'ffmpeg_path': 'ffmpeg',
            'ffprobe_path': 'ffprobe',
            'ffmpeg_available': False,
            'hardware_encoders': [],
        }

        if self.system_info['platform'] == 'Darwin' and self.system_info['machine'] in ['arm64', 'aarch64']:
            self.system_info['is_apple_silicon'] = True

        # 優先使用 App 內嵌 ffmpeg/ffprobe，其次使用專案 assets/bin，最後才用系統 ffmpeg
        def ensure_executable(p: Path):
            try:
                mode = os.stat(p).st_mode
                # 設置 755 權限（若缺）
                os.chmod(p, mode | 0o755)
            except Exception:
                pass

        try:
            exe_path = Path(sys.executable).resolve()
            # PyInstaller .app 佈局：.../Contents/MacOS/<exe>
            resources_dir = exe_path.parents[1] / 'Resources'
            bin_dir = resources_dir / 'bin'
            ffm = bin_dir / 'ffmpeg'
            ffp = bin_dir / 'ffprobe'
            if ffm.exists() and ffp.exists():
                ensure_executable(ffm)
                ensure_executable(ffp)
                self.system_info['ffmpeg_path'] = str(ffm)
                self.system_info['ffprobe_path'] = str(ffp)
        except Exception:
            pass

        # 原始碼模式：使用 repo 內 assets/bin
        if self.system_info['ffmpeg_path'] == 'ffmpeg' or self.system_info['ffprobe_path'] == 'ffprobe':
            try:
                proj_bin = Path(__file__).resolve().parent / 'assets' / 'bin'
                ffm2 = proj_bin / 'ffmpeg'
                ffp2 = proj_bin / 'ffprobe'
                if ffm2.exists() and ffp2.exists():
                    ensure_executable(ffm2)
                    ensure_executable(ffp2)
                    self.system_info['ffmpeg_path'] = str(ffm2)
                    self.system_info['ffprobe_path'] = str(ffp2)
            except Exception:
                pass

        # 檢查 ffmpeg 可用性
        try:
            result = subprocess.run([self.system_info['ffmpeg_path'], '-version'], capture_output=True, text=True, timeout=5)
            self.system_info['ffmpeg_available'] = (result.returncode == 0)
        except Exception:
            self.system_info['ffmpeg_available'] = False

        # 檢查硬體編碼器 (VideoToolbox)
        if self.system_info['ffmpeg_available']:
            try:
                enc = subprocess.run([self.system_info['ffmpeg_path'], '-hide_banner', '-encoders'], capture_output=True, text=True, timeout=10)
                if enc.returncode == 0:
                    out = enc.stdout
                    if 'h264_videotoolbox' in out:
                        self.system_info['hardware_encoders'].append('h264_videotoolbox')
                    if 'hevc_videotoolbox' in out:
                        self.system_info['hardware_encoders'].append('hevc_videotoolbox')
            except Exception:
                pass

    def _system_status_text(self) -> str:
        if not self.system_info['ffmpeg_available']:
            return "❌ FFmpeg 不可用，請安裝 Homebrew ffmpeg"
        if self.system_info['is_apple_silicon']:
            if self.system_info['hardware_encoders']:
                return f"🚀 Apple Silicon 啟用硬體編碼: {', '.join(self.system_info['hardware_encoders'])}"
            return "🚀 Apple Silicon - 未檢測到硬體編碼器，使用軟體編碼"
        return f"💻 平台: {self.system_info['platform']} - 使用軟體編碼"

    # --------------------- UI ---------------------
    def _setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        title_label = ttk.Label(main_frame, text="影片合併器 (YouTube 最佳化)", font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 10))

        status_label = ttk.Label(main_frame, text=self._system_status_text(), font=("Arial", 9), foreground="gray")
        status_label.grid(row=1, column=0, columnspan=3, pady=(0, 15))

        # 資料夾選擇
        ttk.Label(main_frame, text="圖片資料夾:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.images_folder_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.images_folder_var, width=60).grid(row=2, column=1, sticky=(tk.W, tk.E), padx=(5, 5))
        ttk.Button(main_frame, text="瀏覽", command=self._select_images_folder).grid(row=2, column=2, padx=(5, 0))

        ttk.Label(main_frame, text="音檔資料夾:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.audio_folder_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.audio_folder_var, width=60).grid(row=3, column=1, sticky=(tk.W, tk.E), padx=(5, 5))
        ttk.Button(main_frame, text="瀏覽", command=self._select_audio_folder).grid(row=3, column=2, padx=(5, 0))

        ttk.Label(main_frame, text="輸出資料夾:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.output_folder_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.output_folder_var, width=60).grid(row=4, column=1, sticky=(tk.W, tk.E), padx=(5, 5))
        ttk.Button(main_frame, text="瀏覽", command=self._select_output_folder).grid(row=4, column=2, padx=(5, 0))

        # 群組與合併
        ttk.Label(main_frame, text="每組數量:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.group_size_var = tk.IntVar(value=1)
        group_size_frame = ttk.Frame(main_frame)
        group_size_frame.grid(row=5, column=1, sticky=(tk.W, tk.E), padx=(5, 5))
        self.group_spinbox = ttk.Spinbox(group_size_frame, from_=1, to=100, textvariable=self.group_size_var, width=10)
        self.group_spinbox.pack(side=tk.LEFT)
        ttk.Label(group_size_frame, text="(每組 圖片/音檔 對應為一支影片)").pack(side=tk.LEFT, padx=(10, 0))

        self.merge_all_var = tk.BooleanVar(value=False)
        merge_all_frame = ttk.Frame(main_frame)
        merge_all_frame.grid(row=6, column=1, sticky=(tk.W, tk.E), padx=(5, 5))
        self.merge_all_checkbox = ttk.Checkbutton(merge_all_frame, text="全部合併為一隻影片，不分組", variable=self.merge_all_var, command=self._on_merge_all_changed)
        self.merge_all_checkbox.pack(side=tk.LEFT)

        # 編碼與 YouTube 參數
        opts_frame = ttk.Frame(main_frame)
        opts_frame.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(5, 5))

        # 編碼器選擇
        self.encoder_choice_var = tk.StringVar(value="auto")
        ttk.Label(opts_frame, text="編碼器:").grid(row=0, column=0, sticky=tk.W)
        encoder_combo = ttk.Combobox(opts_frame, textvariable=self.encoder_choice_var, values=["auto", "hardware", "software"], state="readonly", width=10)
        encoder_combo.grid(row=0, column=1, sticky=tk.W, padx=(5, 15))

        # FPS
        self.fps_var = tk.IntVar(value=24)
        ttk.Label(opts_frame, text="FPS:").grid(row=0, column=2, sticky=tk.W)
        fps_combo = ttk.Combobox(opts_frame, textvariable=self.fps_var, values=[24, 30], state="readonly", width=10)
        fps_combo.grid(row=0, column=3, sticky=tk.W, padx=(5, 15))

        # 解析度
        self.resolution_var = tk.StringVar(value="1080p")
        ttk.Label(opts_frame, text="解析度:").grid(row=0, column=4, sticky=tk.W)
        reso_combo = ttk.Combobox(opts_frame, textvariable=self.resolution_var, values=["720p", "1080p", "1440p"], state="readonly", width=10)
        reso_combo.grid(row=0, column=5, sticky=tk.W, padx=(5, 15))

        # Codec 偏好（預設 H.264；HEVC 選配）
        self.codec_pref_var = tk.StringVar(value="h264")
        ttk.Label(opts_frame, text="Codec:").grid(row=0, column=6, sticky=tk.W)
        codec_combo = ttk.Combobox(opts_frame, textvariable=self.codec_pref_var, values=["h264", "hevc"], state="readonly", width=10)
        codec_combo.grid(row=0, column=7, sticky=tk.W, padx=(5, 15))

        # 說明
        ttk.Label(opts_frame, text="YouTube 建議：H.264 / 24fps / 1080p / yuv420p", foreground="gray").grid(row=1, column=0, columnspan=8, sticky=tk.W, pady=(4, 0))

        # 控制按鈕
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=8, column=0, columnspan=3, pady=12)
        ttk.Button(btn_frame, text="預覽檔案", command=self._preview_files).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="新增工作", command=self._add_job).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="清除所有工作", command=self._clear_all_jobs).pack(side=tk.LEFT, padx=(0, 10))
        self.stop_button = ttk.Button(btn_frame, text="停止處理", command=self._stop_processing, state='disabled')
        self.stop_button.pack(side=tk.LEFT)

        # 工作列表
        ttk.Label(main_frame, text="工作隊列:").grid(row=9, column=0, sticky=tk.W, pady=(12, 6))
        self.jobs_tree = ttk.Treeview(main_frame, columns=("狀態", "進度", "圖片資料夾", "音檔資料夾", "輸出資料夾"), show="tree headings", height=8)
        self.jobs_tree.grid(row=10, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.jobs_tree.heading("#0", text="工作ID")
        self.jobs_tree.heading("狀態", text="狀態")
        self.jobs_tree.heading("進度", text="進度")
        self.jobs_tree.heading("圖片資料夾", text="圖片資料夾")
        self.jobs_tree.heading("音檔資料夾", text="音檔資料夾")
        self.jobs_tree.heading("輸出資料夾", text="輸出資料夾")
        self.jobs_tree.column("#0", width=80)
        self.jobs_tree.column("狀態", width=80)
        self.jobs_tree.column("進度", width=80)
        self.jobs_tree.column("圖片資料夾", width=160)
        self.jobs_tree.column("音檔資料夾", width=160)
        self.jobs_tree.column("輸出資料夾", width=160)
        self.jobs_tree.bind("<Double-1>", self._on_tree_double_click)

        # 日誌
        ttk.Label(main_frame, text="處理日誌:").grid(row=11, column=0, sticky=tk.W, pady=(12, 6))
        log_frame = ttk.Frame(main_frame)
        log_frame.grid(row=12, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, width=90)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        main_frame.rowconfigure(10, weight=1)
        main_frame.rowconfigure(12, weight=1)

    # --------------------- UI handlers ---------------------
    def _on_merge_all_changed(self):
        if self.merge_all_var.get():
            self.group_spinbox.configure(state='disabled')
        else:
            self.group_spinbox.configure(state='normal')

    def _on_tree_double_click(self, event):
        item = self.jobs_tree.selection()[0] if self.jobs_tree.selection() else None
        if not item:
            return
        try:
            job_id = int(self.jobs_tree.item(item, "text").replace("#", ""))
            for job in self.job_history:
                if job.job_id == job_id:
                    if os.path.exists(job.output_path):
                        subprocess.Popen(['open', job.output_path])
                        self._log(f"已開啟輸出資料夾: {job.output_path}")
                    else:
                        messagebox.showwarning("警告", f"輸出資料夾不存在: {job.output_path}")
                    break
        except Exception as e:
            self._log(f"無法開啟輸出資料夾: {e}")

    def _select_images_folder(self):
        folder = filedialog.askdirectory(title="選擇圖片資料夾")
        if folder:
            self.images_folder_var.set(folder)

    def _select_audio_folder(self):
        folder = filedialog.askdirectory(title="選擇音檔資料夾")
        if folder:
            self.audio_folder_var.set(folder)

    def _select_output_folder(self):
        folder = filedialog.askdirectory(title="選擇輸出資料夾")
        if folder:
            self.output_folder_var.set(folder)

    # --------------------- 檔案與預覽 ---------------------
    def _get_sorted_files(self, folder: str, extensions: List[str]) -> List[str]:
        files: List[str] = []
        if os.path.exists(folder):
            for file in os.listdir(folder):
                if any(file.lower().endswith(ext) for ext in extensions):
                    files.append(file)

        def natural_sort_key(s: str):
            return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

        return sorted(files, key=natural_sort_key)

    def _preview_files(self):
        images_folder = self.images_folder_var.get()
        audio_folder = self.audio_folder_var.get()
        if not images_folder or not audio_folder:
            messagebox.showwarning("警告", "請先選擇圖片和音檔資料夾")
            return

        image_exts = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.gif']
        audio_exts = ['.mp3', '.wav', '.aac', '.m4a', '.flac', '.ogg']
        image_files = self._get_sorted_files(images_folder, image_exts)
        audio_files = self._get_sorted_files(audio_folder, audio_exts)

        preview_window = tk.Toplevel(self.root)
        preview_window.title("檔案預覽")
        preview_window.geometry("640x480")

        notebook = ttk.Notebook(preview_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        image_frame = ttk.Frame(notebook)
        notebook.add(image_frame, text=f"圖片檔案 ({len(image_files)})")
        image_listbox = tk.Listbox(image_frame)
        image_listbox.pack(fill=tk.BOTH, expand=True)
        for img in image_files:
            image_listbox.insert(tk.END, img)

        audio_frame = ttk.Frame(notebook)
        notebook.add(audio_frame, text=f"音檔檔案 ({len(audio_files)})")
        audio_listbox = tk.Listbox(audio_frame)
        audio_listbox.pack(fill=tk.BOTH, expand=True)
        for a in audio_files:
            audio_listbox.insert(tk.END, a)

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

    # --------------------- 工作管理 ---------------------
    def _add_job(self):
        images_folder = self.images_folder_var.get()
        audio_folder = self.audio_folder_var.get()
        output_folder = self.output_folder_var.get()
        group_size = self.group_size_var.get()

        if not images_folder or not os.path.exists(images_folder):
            messagebox.showerror("錯誤", "請選擇有效的圖片資料夾")
            return
        if not audio_folder or not os.path.exists(audio_folder):
            messagebox.showerror("錯誤", "請選擇有效的音檔資料夾")
            return
        if not output_folder:
            messagebox.showerror("錯誤", "請選擇輸出資料夾")
            return

        os.makedirs(output_folder, exist_ok=True)

        self.job_counter += 1
        job = VideoJob(
            images_folder=images_folder,
            audio_folder=audio_folder,
            output_path=output_folder,
            group_size=group_size,
            job_id=self.job_counter,
            merge_all=self.merge_all_var.get(),
            encoder_choice=self.encoder_choice_var.get(),
            fps=int(self.fps_var.get()),
            resolution=self.resolution_var.get(),
            codec_preference=self.codec_pref_var.get(),
        )

        self.job_queue.put(job)
        self.job_history.append(job)
        self._update_jobs_display()
        self._log(f"已新增工作 #{self.job_counter}")

    def _clear_all_jobs(self):
        while not self.job_queue.empty():
            try:
                self.job_queue.get_nowait()
            except queue.Empty:
                break
        self.job_history.clear()
        for item in self.jobs_tree.get_children():
            self.jobs_tree.delete(item)
        self._log("已清除所有工作")

    def _stop_processing(self):
        self.stop_requested = True
        self.stop_button.configure(state='disabled')
        self._log("🛑 已請求停止處理，等待當前工作完成...")

    def _update_jobs_display(self):
        for item in self.jobs_tree.get_children():
            self.jobs_tree.delete(item)
        for job in self.job_history:
            status_display = "處理中" if job == self.current_job else job.status
            self.jobs_tree.insert("", "end", text=f"#{job.job_id}", values=(
                status_display,
                f"{job.progress}%",
                os.path.basename(job.images_folder),
                os.path.basename(job.audio_folder),
                os.path.basename(job.output_path),
            ))

    def _start_worker_thread(self):
        t = threading.Thread(target=self._worker_loop, daemon=True)
        t.start()

    def _worker_loop(self):
        while True:
            try:
                if not self.is_processing and not self.job_queue.empty() and not self.stop_requested:
                    self.current_job = self.job_queue.get()
                    self.is_processing = True
                    self.root.after(0, lambda: self.stop_button.configure(state='normal'))
                    self.root.after(0, self._update_jobs_display)
                    if not self.stop_requested:
                        self._process_job(self.current_job)
                    self.current_job = None
                    self.is_processing = False
                    self.root.after(0, lambda: self.stop_button.configure(state='disabled'))
                    self.root.after(0, self._update_jobs_display)
                elif self.stop_requested and not self.is_processing:
                    self.stop_requested = False
                    self.root.after(0, lambda: self._log("✅ 處理已停止"))
                time.sleep(0.1)
            except Exception as e:
                self.root.after(0, lambda: self._log(f"工作處理錯誤: {e}"))
                self.is_processing = False
                self.current_job = None
                self.root.after(0, lambda: self.stop_button.configure(state='disabled'))

    # --------------------- 核心處理 ---------------------
    def _process_job(self, job: VideoJob):
        try:
            self.root.after(0, lambda: self._log(f"開始處理工作 #{job.job_id}"))
            job.status = "處理中"

            image_exts = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']
            audio_exts = ['.mp3', '.wav', '.aac', '.m4a', '.flac', '.ogg']
            image_files = self._get_sorted_files(job.images_folder, image_exts)
            audio_files = self._get_sorted_files(job.audio_folder, audio_exts)
            if not image_files:
                raise Exception("圖片資料夾中沒有找到支援的圖片檔案")
            if not audio_files:
                raise Exception("音檔資料夾中沒有找到支援的音檔檔案")

            max_files = max(len(image_files), len(audio_files))
            if job.merge_all:
                total_groups = 1
                self.root.after(0, lambda: self._log("將全部檔案合併為 1 個影片"))
                if self.stop_requested:
                    job.status = "已取消"
                    return
                self._create_video_for_range(job, 1, 0, max_files, image_files, audio_files)
                job.progress = 100
                self.root.after(0, self._update_jobs_display)
            else:
                total_groups = (max_files + job.group_size - 1) // job.group_size
                self.root.after(0, lambda: self._log(f"總共將建立 {total_groups} 個影片"))
                for group_idx in range(total_groups):
                    if self.stop_requested:
                        job.status = "已取消"
                        return
                    start_idx = group_idx * job.group_size
                    end_idx = min(start_idx + job.group_size, max_files)
                    self.root.after(0, lambda g=group_idx+1: self._log(f"處理第 {g} 組..."))
                    self._create_video_for_range(job, group_idx + 1, start_idx, end_idx, image_files, audio_files)
                    job.progress = int((group_idx + 1) / total_groups * 100)
                    self.root.after(0, self._update_jobs_display)

            job.status = "完成"
            job.progress = 100
            self.root.after(0, lambda: self._log(f"工作 #{job.job_id} 處理完成"))
        except Exception as e:
            job.status = "錯誤"
            self.root.after(0, lambda: self._log(f"工作 #{job.job_id} 處理失敗: {e}"))

    def _create_video_for_range(
        self,
        job: VideoJob,
        group_num: int,
        start_idx: int,
        end_idx: int,
        image_files: List[str],
        audio_files: List[str],
    ):
        # 決定輸出檔名
        first_img_name = ""
        last_img_name = ""
        for i in range(start_idx, end_idx):
            if i < len(image_files):
                img_name = os.path.splitext(image_files[i])[0]
                if not first_img_name:
                    first_img_name = img_name
                last_img_name = img_name

        if first_img_name and last_img_name:
            if first_img_name == last_img_name:
                output_filename = f"{first_img_name}.mp4"
            else:
                output_filename = f"{first_img_name}-{last_img_name}.mp4"
        else:
            output_filename = f"video_group_{group_num:03d}.mp4"
        output_path = os.path.join(job.output_path, output_filename)

        # 建立本組的暫存目錄
        group_tmp_dir = os.path.join(self.temp_dir, f"job_{job.job_id}_g{group_num}")
        os.makedirs(group_tmp_dir, exist_ok=True)

        # 蒐集本組段落
        seg_paths: List[str] = []
        for i in range(start_idx, end_idx):
            if self.stop_requested:
                self._log("🛑 已停止，略過後續段落")
                break

            img_path = os.path.join(job.images_folder, image_files[i]) if i < len(image_files) else None
            audio_path = os.path.join(job.audio_folder, audio_files[i]) if i < len(audio_files) else None
            if not img_path or not audio_path or not os.path.exists(img_path) or not os.path.exists(audio_path):
                self._log(f"跳過檔案：圖片={img_path}, 音檔={audio_path}")
                continue

            # 取得音訊時長（秒）
            duration = self._probe_audio_duration(audio_path)
            if duration is None:
                self._log("⚠️ 無法讀取音檔時長，預設 2 秒")
                duration = 2.0

            # 產生單段影片
            seg_out = os.path.join(group_tmp_dir, f"seg_{i:05d}.mp4")
            ok = self._encode_segment(
                image_path=img_path,
                audio_path=audio_path,
                duration=duration,
                fps=job.fps,
                resolution=job.resolution,
                codec_pref=job.codec_preference,
                encoder_choice=job.encoder_choice,
                seg_output=seg_out,
            )
            if not ok:
                self._log("❌ 段落編碼失敗，略過該段")
                continue
            seg_paths.append(seg_out)

        if not seg_paths:
            self._log(f"第 {group_num} 組沒有有效的段落可合併")
            return

        # concat list 檔案
        list_txt = os.path.join(group_tmp_dir, "mylist.txt")
        with open(list_txt, 'w', encoding='utf-8') as f:
            for p in seg_paths:
                # 使用單引號包覆，並允許 -safe 0
                f.write(f"file '{p}'\n")

        # 合併
        concat_cmd = [
            self.system_info['ffmpeg_path'], '-hide_banner', '-y',
            '-f', 'concat', '-safe', '0', '-i', list_txt,
            '-c', 'copy',
            '-movflags', '+faststart',
            output_path
        ]
        self._log("🔗 合併段落為最終影片 (0-copy concat)")
        ok = self._run_subprocess(concat_cmd, log_prefix="concat")
        if ok:
            self._log(f"✅ 第 {group_num} 組影片已儲存: {os.path.basename(output_path)}")
        else:
            self._log("❌ 合併失敗，將刪除不完整輸出")
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass

        # 清理段落檔案（保留以利問題追蹤可改成不刪）
        try:
            shutil.rmtree(group_tmp_dir)
        except Exception:
            pass

    # --------------------- FFmpeg helpers ---------------------
    def _probe_audio_duration(self, audio_path: str) -> Optional[float]:
        try:
            cmd = [
                self.system_info['ffprobe_path'], '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=nokey=1:noprint_wrappers=1',
                audio_path
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                val = res.stdout.strip()
                if val:
                    return float(val)
        except Exception as e:
            self._log(f"ffprobe 錯誤: {e}")
        return None

    def _resolution_to_scale_filter(self, resolution: str) -> str:
        # -2 以確保偶數寬度
        if resolution == "720p":
            return "scale=-2:720:flags=bicubic"
        if resolution == "1440p":
            return "scale=-2:1440:flags=lanczos"
        return "scale=-2:1080:flags=bicubic"

    def _choose_codec(self, encoder_choice: str, codec_pref: str) -> Tuple[str, str]:
        # 回傳 (codec, encoder_type) 其中 encoder_type: 'hardware'|'software'
        hw_available = len(self.system_info['hardware_encoders']) > 0
        if encoder_choice == "software":
            return ('libx264', 'software')
        if encoder_choice == "hardware":
            if hw_available:
                if codec_pref == 'hevc' and 'hevc_videotoolbox' in self.system_info['hardware_encoders']:
                    return ('hevc_videotoolbox', 'hardware')
                return ('h264_videotoolbox', 'hardware')
            return ('libx264', 'software')
        # auto
        if hw_available:
            if codec_pref == 'hevc' and 'hevc_videotoolbox' in self.system_info['hardware_encoders']:
                return ('hevc_videotoolbox', 'hardware')
            return ('h264_videotoolbox', 'hardware')
        return ('libx264', 'software')

    def _encode_segment(
        self,
        image_path: str,
        audio_path: str,
        duration: float,
        fps: int,
        resolution: str,
        codec_pref: str,
        encoder_choice: str,
        seg_output: str,
    ) -> bool:
        # 選擇編碼器
        codec, encoder_type = self._choose_codec(encoder_choice, codec_pref)
        scale_filter = self._resolution_to_scale_filter(resolution)

        # 共用參數（YouTube 友善）
        common_video_meta = [
            '-pix_fmt', 'yuv420p',
            '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
        ]

        # 指令
        cmd: List[str] = [
            self.system_info['ffmpeg_path'], '-hide_banner', '-y',
            '-loop', '1', '-framerate', str(fps), '-t', f"{duration:.3f}", '-i', image_path,
            '-i', audio_path,
            '-shortest', '-r', str(fps),
            '-vf', scale_filter,
        ]

        gop = fps * 2  # 2 秒 GOP

        if codec == 'h264_videotoolbox':
            cmd += [
                '-c:v', 'h264_videotoolbox', '-profile:v', 'high', '-level:v', '4.2',
                '-g', str(gop), '-sc_threshold', '0',
                '-b:v', '6M', '-maxrate', '8M', '-bufsize', '12M',
            ] + common_video_meta
        elif codec == 'hevc_videotoolbox':
            cmd += [
                '-c:v', 'hevc_videotoolbox', '-profile:v', 'main', '-g', str(gop), '-sc_threshold', '0',
                '-b:v', '5M', '-maxrate', '7M', '-bufsize', '10M', '-tag:v', 'hvc1',
            ] + common_video_meta
        else:
            # libx264
            cmd += [
                '-c:v', 'libx264', '-preset', 'medium', '-crf', '19',
                '-profile:v', 'high', '-level:v', '4.2', '-g', str(gop), '-sc_threshold', '0',
            ] + common_video_meta

        # 音訊 AAC-LC 48k 128k 立體聲
        cmd += [
            '-c:a', 'aac', '-b:a', '128k', '-ar', '48000', '-ac', '2',
            '-movflags', '+faststart',
            seg_output,
        ]

        self._log(f"🎬 產生段落: {os.path.basename(seg_output)} ({encoder_type}:{codec})")
        ok = self._run_subprocess(cmd, log_prefix="segment")
        if not ok and encoder_type == 'hardware':
            self._log("🔄 硬體編碼失敗，回退到軟體 libx264")
            # 回退到 libx264
            fallback_cmd = cmd[:]
            # 移除 video 編碼器相關段落，重建為 libx264
            # 找 '-c:v' 的位置重建比較複雜，改為重新組裝
            fallback_cmd = [
                self.system_info['ffmpeg_path'], '-hide_banner', '-y',
                '-loop', '1', '-framerate', str(fps), '-t', f"{duration:.3f}", '-i', image_path,
                '-i', audio_path,
                '-shortest', '-r', str(fps),
                '-vf', scale_filter,
                '-c:v', 'libx264', '-preset', 'medium', '-crf', '19',
                '-profile:v', 'high', '-level:v', '4.2', '-g', str(gop), '-sc_threshold', '0',
            ] + common_video_meta + [
                '-c:a', 'aac', '-b:a', '128k', '-ar', '48000', '-ac', '2',
                '-movflags', '+faststart',
                seg_output,
            ]
            ok = self._run_subprocess(fallback_cmd, log_prefix="segment-fallback")
        return ok

    def _run_subprocess(self, cmd: List[str], log_prefix: str = "proc", timeout: Optional[int] = None) -> bool:
        # 避免卡住：給一個寬鬆超時（每段通常 < 2 分鐘，視音檔長度）
        if timeout is None:
            timeout = 60 * 10
        self._log(f"▶️ 執行: {' '.join(cmd[:8])} ...")  # 只顯示前段，避免太長
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
            if proc.stdout:
                # 只擷取最後數十行避免 UI 過載
                tail = '\n'.join(proc.stdout.splitlines()[-10:])
                if tail.strip():
                    self._log(f"{log_prefix}: {tail}")
            if proc.returncode != 0:
                self._log(f"{log_prefix}: 退出碼 {proc.returncode}")
                return False
            return True
        except subprocess.TimeoutExpired:
            self._log(f"{log_prefix}: ⏱️ 超時")
            return False
        except Exception as e:
            self._log(f"{log_prefix}: 錯誤 {e}")
            return False

    # --------------------- 日誌 ---------------------
    def _log(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        try:
            self.log_text.insert(tk.END, log_message)
            self.log_text.see(tk.END)
            # 控制日誌長度
            lines = self.log_text.get("1.0", tk.END).split("\n")
            if len(lines) > 1200:
                self.log_text.delete("1.0", f"{len(lines)-600}.0")
        except Exception:
            # 在非 GUI 情境下（單元測試）避免崩潰
            print(log_message, end="")


def main():
    root = tk.Tk()
    app = VideoCombinator2App(root)

    def on_closing():
        if messagebox.askokcancel("退出", "確定要退出影片合併器嗎？"):
            try:
                if hasattr(app, 'temp_dir') and os.path.exists(app.temp_dir):
                    shutil.rmtree(app.temp_dir)
            except Exception as e:
                print(f"清理臨時目錄時發生錯誤: {e}")
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()



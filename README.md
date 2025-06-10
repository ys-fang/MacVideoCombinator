# 影片合併器 VideoCombinator

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/Platform-macOS-lightgrey.svg)](https://www.apple.com/macos/)

一個功能強大的 Python 應用程式，可以將圖片和音檔按照檔名順序合併成影片。支援批次處理和工作隊列管理，具備現代化的圖形使用者介面。

## 🖼️ 預覽

![VideoCombinator](icon.png)

> **📱 完整的 macOS 原生應用程式**：支援打包為獨立的 .app 檔案，無需安裝 Python 環境即可運行。

## ✨ 主要功能

- 📁 **資料夾選擇**：選擇包含圖片和音檔的資料夾
- 🔢 **群組設定**：設定多少個檔案為一組合併成一個影片
- 🎬 **全部合併**：可選擇將所有檔案合併為一隻影片，不分組
- 📝 **檔案預覽**：預覽檔案對應關係
- 🚀 **工作隊列**：支援新增多個工作，按序列處理
- 📊 **進度顯示**：即時顯示處理進度和狀態
- 📋 **工作歷史**：保留所有工作記錄，包括已完成的工作
- 📂 **快速開啟**：雙擊輸出資料夾欄位可直接開啟檔案位置
- 💾 **智慧檔名**：自動使用圖片檔名生成有意義的影片檔名
- 🗂️ **路徑記憶**：記住上次使用的資料夾路徑
- 📱 **獨立應用**：可打包成 macOS 獨立應用程式

## 🎯 工作原理

1. **檔案排序**：按照檔名進行自然排序（支援數字順序）
2. **配對合併**：每個圖片對應一個音檔
3. **群組處理**：將指定數量的配對合併成一個影片
4. **序列執行**：工作隊列確保每次只處理一個工作

## 📋 系統需求

- macOS 10.14 或更高版本
- Python 3.8 或更高版本
- FFmpeg（用於影片處理）

## 🚀 快速開始

### 1. 安裝依賴

```bash
# 賦予腳本執行權限
chmod +x setup.sh run.sh build_app.sh

# 運行設置腳本
./setup.sh
```

### 2. 安裝 FFmpeg

```bash
# 使用 Homebrew 安裝 FFmpeg
brew install ffmpeg
```

### 3. 運行應用程式

```bash
# 使用便捷腳本運行
./run.sh

# 或手動運行
source venv/bin/activate
python video_combinator.py
```

## 📦 打包成獨立應用程式

```bash
# 打包成 macOS 應用程式
./build_app.sh
```

打包完成後，應用程式將位於 `dist/VideoCombinator.app`

## 🎮 使用說明

### 基本操作

1. **選擇資料夾**
   - 點擊「瀏覽」按鈕選擇圖片資料夾
   - 點擊「瀏覽」按鈕選擇音檔資料夾
   - 選擇輸出資料夾

2. **設定參數**
   - 調整「每組數量」設定合併規模
   - 可勾選「全部合併為一隻影片，不分組」跳過分組
   - 預覽檔案對應關係

3. **新增工作**
   - 點擊「新增工作」將當前設定加入隊列
   - 可以重複新增多個不同的工作

4. **開始處理**
   - 工作會自動按順序執行
   - 可在日誌區域查看處理進度
   - 已完成的工作會保留在工作隊列中
   
5. **查看結果**
   - 雙擊工作隊列中的「輸出資料夾」欄位可直接開啟檔案位置
   - 所有工作狀態和進度都會永久保留

### 檔案命名建議

為了獲得最佳的排序效果，建議使用以下命名方式：

```
圖片檔案：
001.jpg, 002.jpg, 003.jpg, ...
或
image_001.png, image_002.png, ...

音檔檔案：
001.mp3, 002.mp3, 003.mp3, ...
或
audio_001.wav, audio_002.wav, ...
```

## 🎵 支援格式

### 圖片格式
- JPEG (.jpg, .jpeg)
- PNG (.png)
- BMP (.bmp)
- TIFF (.tiff)
- GIF (.gif)

### 音檔格式
- MP3 (.mp3)
- WAV (.wav)
- AAC (.aac)
- M4A (.m4a)
- FLAC (.flac)
- OGG (.ogg)

### 輸出格式
- MP4 (H.264 + AAC)

### 檔案命名規則
- **分組模式**：`第一個圖片檔名-最後一個圖片檔名.mp4`
  - 例如：`001-003.mp4`（包含001.jpg到003.jpg）
  - 單一檔案：`001.mp4`（只包含001.jpg）
- **全部合併模式**：`第一個圖片檔名-最後一個圖片檔名.mp4`
  - 例如：`001-010.mp4`（包含所有圖片）

## 🛠️ 開發資訊

### 專案結構

```
VideoCombinator/
├── video_combinator.py    # 主程式
├── requirements.txt       # Python 依賴
├── setup.sh              # 設置腳本
├── run.sh                # 運行腳本
├── build_app.sh          # 打包腳本
├── icon.png              # 應用程式圖標 (1024x1024)
├── icon.icns             # macOS 圖標文件
└── README.md             # 說明文件
```

### 核心依賴

- **tkinter**：GUI 界面
- **moviepy**：影片處理
- **PIL/Pillow**：圖片處理
- **opencv-python**：影像處理
- **numpy**：數值運算
- **pyinstaller**：應用程式打包

## 🔧 故障排除

### 常見問題

1. **FFmpeg 未找到**
   ```bash
   brew install ffmpeg
   ```

2. **虛擬環境問題**
   ```bash
   rm -rf venv
   ./setup.sh
   ```

3. **依賴安裝失敗**
   ```bash
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **打包失敗**
   - 確保所有依賴都已正確安裝
   - 檢查 Python 版本是否支援
   - 查看終端錯誤訊息

### 效能最佳化

- 使用 SSD 硬碟可提升處理速度
- 較大的 RAM 有助於處理大型檔案
- 將輸入和輸出資料夾放在同一磁碟可減少複製時間

## 🤝 貢獻

歡迎各種形式的貢獻！請參閱以下方式：

1. **回報問題**：在 [Issues](https://github.com/您的用戶名/VideoCombinator/issues) 中回報 Bug 或提出功能建議
2. **提交代碼**：Fork 專案並提交 Pull Request
3. **改進文件**：幫助完善使用說明和技術文件
4. **分享想法**：在 Discussions 中分享使用心得和改進建議

### 開發環境設置

```bash
# 1. Clone 專案
git clone https://github.com/您的用戶名/VideoCombinator.git
cd VideoCombinator

# 2. 設置開發環境
./setup.sh

# 3. 運行專案
./run.sh
```

## 🐛 問題回報

如果您遇到任何問題，請在 [GitHub Issues](https://github.com/您的用戶名/VideoCombinator/issues) 中回報，並包含：

- 您的 macOS 版本
- Python 版本
- 錯誤訊息的完整內容
- 重現問題的步驟

## 📄 授權條款

本專案採用 [MIT 授權條款](LICENSE)。

## ⭐ 支持專案

如果這個專案對您有幫助，請給我們一個 Star ⭐！

---

**Made with ❤️ for the macOS community** 
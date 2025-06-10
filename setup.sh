#!/bin/bash

# VideoCombinator 設置腳本
echo "=== 影片合併器 VideoCombinator 設置腳本 ==="

# 檢查Python是否安裝
if ! command -v python3 &> /dev/null; then
    echo "❌ 錯誤: 未找到 Python3，請先安裝 Python 3.8 或更高版本"
    exit 1
fi

# 顯示Python版本
echo "✅ Python版本: $(python3 --version)"

# 建立虛擬環境
if [ ! -d "venv" ]; then
    echo "📦 建立虛擬環境..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "❌ 建立虛擬環境失敗"
        exit 1
    fi
    echo "✅ 虛擬環境建立完成"
else
    echo "ℹ️  虛擬環境已存在"
fi

# 啟動虛擬環境
echo "🔄 啟動虛擬環境..."
source venv/bin/activate

# 升級pip
echo "⬆️  升級 pip..."
pip install --upgrade pip

# 安裝依賴
echo "📥 安裝依賴套件..."
pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✅ 所有依賴套件安裝完成"
else
    echo "❌ 安裝依賴套件時發生錯誤"
    exit 1
fi

# 檢查是否需要安裝額外的系統依賴
echo "🔍 檢查系統依賴..."

# 檢查ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  警告: 未找到 ffmpeg，這是處理影片所必需的"
    echo "   請使用以下命令安裝 ffmpeg:"
    echo "   brew install ffmpeg"
    echo ""
fi

echo "🎉 設置完成！"
echo ""
echo "使用方法："
echo "1. 啟動虛擬環境: source venv/bin/activate"
echo "2. 運行應用程式: python video_combinator.py"
echo "3. 或使用便捷腳本: ./run.sh"
echo "" 
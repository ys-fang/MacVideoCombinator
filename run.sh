#!/bin/bash

# VideoCombinator 運行腳本
echo "🚀 啟動影片合併器 VideoCombinator..."

# 檢查虛擬環境是否存在
if [ ! -d "venv" ]; then
    echo "❌ 虛擬環境不存在，請先運行 ./setup.sh"
    exit 1
fi

# 啟動虛擬環境
source venv/bin/activate

# 檢查主程式檔案是否存在
if [ ! -f "video_combinator.py" ]; then
    echo "❌ 主程式檔案 video_combinator.py 不存在"
    exit 1
fi

# 運行應用程式
echo "▶️  運行影片合併器..."
python video_combinator.py

echo "👋 程式已結束" 
#!/bin/bash

# VideoCombinator 演示腳本
echo "🎬 影片合併器演示腳本"

# 創建測試資料夾
echo "📁 創建測試資料夾..."
mkdir -p demo_data/images
mkdir -p demo_data/audio
mkdir -p demo_data/output

echo "ℹ️  測試資料夾已創建在 demo_data/ 中"
echo ""
echo "📝 使用說明："
echo "1. 將您的圖片檔案放入 demo_data/images/"
echo "2. 將您的音檔檔案放入 demo_data/audio/"
echo "3. 運行應用程式: ./run.sh"
echo "4. 在應用程式中選擇對應的資料夾"
echo "5. 輸出檔案將儲存在 demo_data/output/"
echo ""
echo "💡 建議檔案命名格式："
echo "   圖片: 001.jpg, 002.jpg, 003.jpg, ..."
echo "   音檔: 001.mp3, 002.mp3, 003.mp3, ..."
echo ""

# 可選：開啟 demo_data 資料夾
read -p "是否要開啟測試資料夾? (y/n): " open_demo
if [ "$open_demo" = "y" ] || [ "$open_demo" = "Y" ]; then
    open demo_data/
fi

echo "🚀 準備完成！現在可以運行 ./run.sh 啟動應用程式" 
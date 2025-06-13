#!/bin/bash

# VideoCombinator PyInstaller 打包腳本
echo "📦 開始打包影片合併器為獨立的 macOS 應用程式..."

# 檢查虛擬環境是否存在
if [ ! -d "venv" ]; then
    echo "❌ 虛擬環境不存在，請先運行 ./setup.sh"
    exit 1
fi

# 啟動虛擬環境
source venv/bin/activate

# 檢查PyInstaller是否安裝
if ! python -c "import PyInstaller" &> /dev/null; then
    echo "📥 安裝 PyInstaller..."
    pip install pyinstaller
fi

# 清理之前的建置
echo "🗑️  清理之前的建置檔案..."
rm -rf build/
rm -rf dist/
rm -f *.spec

# 建立 PyInstaller 規格檔案
echo "📝 建立 PyInstaller 規格檔案..."
cat > VideoCombinator.spec << 'EOF'
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['video_combinator.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.scrolledtext',
        'PIL',
        'PIL.Image',
        'moviepy',
        'imageio',
        'imageio_ffmpeg',
        'proglog',
        'decorator',
        'requests',
        'numpy'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VideoCombinator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VideoCombinator',
)

app = BUNDLE(
    coll,
    name='VideoCombinator.app',
    icon='icon.icns',
    bundle_identifier='com.videocombinator.app',
    info_plist={
        'CFBundleDisplayName': '影片合併器',
        'CFBundleIdentifier': 'com.videocombinator.app',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
    },
)
EOF

# 使用 PyInstaller 打包
echo "🔨 開始打包應用程式..."
pyinstaller VideoCombinator.spec

# 檢查打包結果
if [ -d "dist/VideoCombinator.app" ]; then
    echo "✅ 打包成功！"
    echo "📱 應用程式位置: dist/VideoCombinator.app"
    echo ""
    echo "使用方法："
    echo "1. 在 Finder 中開啟 dist 資料夾"
    echo "2. 將 VideoCombinator.app 拖拽到應用程式資料夾"
    echo "3. 從 Launchpad 或應用程式資料夾啟動"
    echo ""
    echo "⚠️  注意：首次運行時 macOS 可能會要求安全權限確認"
    
    # 可選：自動開啟 dist 資料夾
    read -p "是否要開啟 dist 資料夾? (y/n): " open_dist
    if [ "$open_dist" = "y" ] || [ "$open_dist" = "Y" ]; then
        open dist/
    fi
else
    echo "❌ 打包失敗，請檢查錯誤訊息"
    exit 1
fi 
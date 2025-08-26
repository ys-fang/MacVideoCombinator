#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -x "assets/bin/ffmpeg" || ! -x "assets/bin/ffprobe" ]]; then
  echo "[錯誤] 找不到 assets/bin/ffmpeg 或 ffprobe。請先執行 setup_ffmpeg_assets.sh 並放置 arm64 版二進位。"
  exit 1
fi

# 使用 venv python 如有
PY="$ROOT_DIR/venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

echo "==> 安裝/更新 PyInstaller"
"$PY" -m pip install --upgrade pip pyinstaller >/dev/null

echo "==> 以 spec 打包 .app (arm64 環境)"
"$ROOT_DIR/venv/bin/pyinstaller" VideoCombinator2.spec 2>/dev/null || pyinstaller VideoCombinator2.spec

echo "==> 產出檔案在 dist/VideoCombinator2.app"
echo "   首次啟動若遇 Gatekeeper：右鍵→打開；或移除隔離："
echo "   xattr -dr com.apple.quarantine \"$ROOT_DIR/dist/VideoCombinator2.app\""



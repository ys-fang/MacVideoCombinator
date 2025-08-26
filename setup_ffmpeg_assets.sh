#!/bin/zsh
set -euo pipefail

# 準備目錄
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
ASSETS_BIN="$ROOT_DIR/assets/bin"
ASSETS_LICENSES="$ROOT_DIR/assets/licenses"
mkdir -p "$ASSETS_BIN" "$ASSETS_LICENSES"

echo "==> 下載或複製 arm64 版 ffmpeg/ffprobe (含 libx264 + videotoolbox 建議用內部來源)"
echo "    注意：請依內部指引提供已編譯的 ffmpeg/ffprobe；此腳本預留手動放置的流程。"

# 若你已有內部提供的 ffmpeg binaries, 請放入 _downloads 目錄後再複製
DL_DIR="$ROOT_DIR/_downloads"
mkdir -p "$DL_DIR"

if [[ -x "$DL_DIR/ffmpeg" && -x "$DL_DIR/ffprobe" ]]; then
  cp "$DL_DIR/ffmpeg" "$ASSETS_BIN/ffmpeg"
  cp "$DL_DIR/ffprobe" "$ASSETS_BIN/ffprobe"
  chmod 755 "$ASSETS_BIN/ffmpeg" "$ASSETS_BIN/ffprobe"
  echo "已將 _downloads/ffmpeg(ffprobe) 複製到 assets/bin"
else
  echo "[提示] 請將 arm64 ffmpeg 與 ffprobe 放入 $DL_DIR 並命名為 ffmpeg/ffprobe 後重跑此腳本。"
fi

# 複製 FFmpeg 授權文本（請依內部來源放置）
if [[ -f "$DL_DIR/LICENSE.ffmpeg" ]]; then
  cp "$DL_DIR/LICENSE.ffmpeg" "$ASSETS_LICENSES/"
fi

echo "完成。資產路徑：$ASSETS_BIN"



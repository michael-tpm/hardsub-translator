#!/bin/zsh
# hardsub-translator — run the 4 steps / chạy 4 bước. Work dir: <out_dir>/<video_name>_work
#   ./dich.sh detect <video.mp4> [out_dir]    (do)   1. find Chinese subtitles → captions.json, review/, dich.tsv
#   ./dich.sh import <work_dir>                (nhap) 2. load your translations from dich.tsv
#   ./dich.sh render <work_dir> <out.mp4>      (xuat) 3. erase Chinese, draw new text, export video
#   ./dich.sh verify <work_dir> <out.mp4>      (kiem) 4. check nothing Chinese is left + before/after sheets
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/.venv/bin/python"
[ -x "$PY" ] && [ -x "$HERE/ocr_vision" ] || { echo "Not installed / chưa cài → run: $HERE/setup.sh"; exit 1; }

case "$1" in
  detect|do)
    OUT="${3:-$(dirname "$2")}"
    WORK="$OUT/$(basename "${2%.*}")_work"
    "$PY" -I "$HERE/detect.py" "$2" "$WORK" ${FPS:+--fps=$FPS}
    "$PY" -I "$HERE/dich_tsv.py" export "$WORK/captions.json"
    echo "→ Review / soát: $WORK/review/sheet_*.jpg ; translate in / điền bản dịch: $WORK/dich.tsv" ;;
  import|nhap) "$PY" -I "$HERE/dich_tsv.py" import "$2/captions.json" ;;
  render|xuat) "$PY" -I "$HERE/render.py" "$2/captions.json" "$3" --style "${STYLE:-hop}" ;;
  verify|kiem) "$PY" -I "$HERE/verify.py" "$3" "$2/captions.json" "$2" ;;
  *) sed -n '2,6p' "$0"; exit 1 ;;
esac

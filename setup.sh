#!/bin/zsh
# One-time setup / cài 1 lần: Python env + Apple Vision OCR helper (macOS).
set -e
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || { echo "ffmpeg missing / thiếu ffmpeg → brew install ffmpeg"; exit 1; }
command -v swiftc >/dev/null || { echo "Swift missing / thiếu Swift → xcode-select --install"; exit 1; }
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/pip install -q --disable-pip-version-check -r requirements.txt
swiftc -O ocr_vision.swift -o ocr_vision
echo "Done / xong → ./dich.sh"

---
description: Translate burned-in Chinese subtitles in a video (erase Chinese, draw translated text at the same place and time), self-verify before delivering
argument-hint: <video.mp4> [out_dir] [target language, default Vietnamese]
---

# /hardsub

Input: $ARGUMENTS

Run from the repository root. Work straight through; only stop if blocked.

1. **Setup** — if `.venv/` or `ocr_vision` is missing, run `./setup.sh`.
2. **Detect** — `./dich.sh detect <video> <out_dir>` (default out_dir: next to the video; run in background for long videos). Look at **every** `review/sheet_*.jpg`: confirm the Chinese text, spot lines that are not subtitles (text printed on objects), emoji next to text, text that fades out. Sample a few frames in the gaps between captions and the last second of the video to make sure nothing was missed.
3. **Translate** — fill the `vi` column of `<work>/dich.tsv` with natural, concise translations in the target language (use `\n` to wrap only the last line of a caption). Mark `bo_qua = x` for non-subtitle lines, `xoa_vung = x` for fading/animated/emoji lines; if text fades until the end, set `end` to the video duration. Then `./dich.sh import <work>`.
4. **Render** — `./dich.sh render <work> <out.mp4>` (default style: black text on white rounded box; `STYLE=vien` for white outlined text).
5. **Verify (mandatory)** — `./dich.sh verify <work> <out.mp4>` and read `<work>/verify/report.txt`. Required: per-frame check **0 frames** with original strokes and OCR **0 leftover lines** (text on objects is informational). Look at every `verify/compare_*.jpg`. Fix and re-render until it passes.
6. **Deliver** — report the output path, the caption table (time, Chinese, translation) and any Chinese text intentionally left on objects.

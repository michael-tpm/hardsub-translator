"""Bước 4 — Kiểm tra video kết quả: còn sót chữ Trung không + ảnh so sánh trước/sau.

Dùng: python verify.py <video_ra.mp4> <captions.json> <thư_mục_làm_việc> [--fps 6]
- OCR lại video kết quả (mặc định 6 khung/giây, lệch nhịp với bước dò) + khung đầu/cuối từng câu.
- Dòng chữ Trung có viền tối (kiểu phụ đề) → báo "CÒN SÓT". Chữ in trên đồ vật → chỉ liệt kê.
- Ảnh so sánh: <thư_mục>/verify/compare_XX.jpg (trái: gốc, phải: kết quả).
"""
import argparse, json, os, shutil, subprocess, sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detect import CJK, FONT, run_ocr, text_feat, white_mask  # noqa: E402


def grab(video, t, path):
    tail = ["-frames:v", "1", "-q:v", "2", "-strict", "unofficial", path]
    r = subprocess.run(["ffmpeg", "-v", "quiet", "-y", "-ss", f"{max(0, t):.3f}", "-i", video, *tail])
    if r.returncode or not os.path.exists(path):  # t vượt quá khung cuối → lấy khung cuối
        subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.3", "-i", video, *tail])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_video")
    ap.add_argument("captions")
    ap.add_argument("work")
    ap.add_argument("--fps", type=float, default=6)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()

    cfg = json.load(open(a.captions, encoding="utf-8"))
    W, H, FPS = cfg["width"], cfg["height"], cfg["fps"]
    caps = [c for c in cfg["captions"] if not c.get("skip")]
    vdir = os.path.join(a.work, "verify")
    shutil.rmtree(vdir, ignore_errors=True)
    os.makedirs(os.path.join(vdir, "f"))

    # 1) khung đều + khung đầu/cuối của mỗi câu
    subprocess.check_call(["ffmpeg", "-v", "error", "-i", a.out_video, "-vf", f"fps={a.fps}",
                           "-q:v", "2", os.path.join(vdir, "f", "s_%05d.jpg")])
    times = {}
    for f in os.listdir(os.path.join(vdir, "f")):
        times[os.path.join(vdir, "f", f)] = (int(f[2:7]) - 1) / a.fps
    for c in caps:
        for tag, t in (("a", c["start"] + 0.5 / FPS), ("b", min(c["end"], cfg["duration"]) - 1.5 / FPS)):
            p = os.path.join(vdir, "f", f"e{c['id']:03d}{tag}.jpg")
            grab(a.out_video, t, p)
            times[p] = t
    files = sorted(times)
    print(f"OCR {len(files)} khung của video kết quả…", flush=True)
    ocr = run_ocr(files, a.jobs)

    left, bg = [], []
    for f in files:
        img = None
        for ln in ocr.get(f, []):
            # ≥2 chữ Hán: 1 chữ lẻ thường là OCR đọc nhầm chữ Việt
            if len(CJK.findall(ln["text"])) < 2:
                continue
            if img is None:
                img = np.asarray(Image.open(f).convert("RGB"))
            b = [max(0, ln["box"][0]), max(0, ln["box"][1]), min(W, ln["box"][2]), min(H, ln["box"][3])]
            white = white_mask(img, b)
            outline = text_feat(img, b).sum() / max(1, white.sum())
            rec = (round(times[f], 2), ln["text"], b, round(float(outline), 2))
            (left if outline >= 0.2 and white.mean() >= 0.04 else bg).append(rec)

    # 2) Soát TỪNG khung: nét chữ Trung gốc còn xuất hiện trong video kết quả không
    print("Soát từng khung bằng mẫu nét chữ gốc…", flush=True)
    refs = []
    for c in caps:
        img = np.asarray(Image.open(c["frame"]).convert("RGB"))
        for l in c["lines"]:
            if not l.get("skip"):
                refs.append((l, text_feat(img, l["box"]), round(l["start"] * FPS), round(l["end"] * FPS)))
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", a.out_video, "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    n, fsz, hits = 0, W * H * 3, []
    while True:
        buf = dec.stdout.read(fsz)
        if len(buf) < fsz:
            break
        img = None
        for l, ref, n0, n1 in refs:
            if n0 - 45 <= n < n1 + 45:
                img = img if img is not None else np.frombuffer(buf, np.uint8).reshape(H, W, 3)
                cur = text_feat(img, l["box"])
                u = (cur | ref).sum()
                if u and (cur & ref).sum() / u > 0.35:
                    hits.append((round(n / FPS, 3), n, l["zh"], l["box"]))
        n += 1
    dec.wait()

    report = os.path.join(vdir, "report.txt")
    with open(report, "w", encoding="utf-8") as fo:
        fo.write(f"Soát từng khung: {n} khung, {len(refs)} dòng — khung còn nét chữ gốc: {len(hits)}\n")
        for h_ in hits:
            fo.write(f"  {h_[0]:7.3f}s (khung {h_[1]})  {h_[2]}  box={h_[3]}\n")
        fo.write(f"Khung đã OCR: {len(files)}\n")
        fo.write(f"CÒN SÓT chữ Trung kiểu phụ đề: {len(left)}\n")
        for r in sorted(left):
            fo.write(f"  {r[0]:7.2f}s  {r[1]}  box={r[2]}  viền={r[3]}\n")
        fo.write(f"Chữ Trung trên đồ vật/nền (không phải phụ đề, bỏ qua): {len(bg)}\n")
        for r in sorted(bg):
            fo.write(f"  {r[0]:7.2f}s  {r[1]}  box={r[2]}  viền={r[3]}\n")
    print(open(report, encoding="utf-8").read())

    # 3) ảnh so sánh trước/sau giữa mỗi câu
    font = ImageFont.truetype(FONT, 22)
    strips = []
    for c in caps:
        t = (c["start"] + min(c["end"], cfg["duration"])) / 2
        pa, pb = os.path.join(vdir, "a.jpg"), os.path.join(vdir, "b.jpg")
        grab(cfg["video"], t, pa)
        grab(a.out_video, t, pb)
        ls = [l for l in c["lines"] if not l.get("skip")]
        y0 = max(0, min(l["box"][1] for l in ls) - 20)
        y1 = min(H, max(l["box"][3] for l in ls) + 50)
        A = Image.open(pa).convert("RGB").crop((0, y0, W, y1))
        B = Image.open(pb).convert("RGB").crop((0, y0, W, y1))
        s = Image.new("RGB", (W * 2 + 6, A.height + 30), (40, 40, 40))
        s.paste(A, (0, 30))
        s.paste(B, (W + 6, 30))
        ImageDraw.Draw(s).text((6, 3), f"#{c['id']}  {c['start']:.2f}-{c['end']:.2f}s", font=font, fill=(255, 220, 0))
        strips.append(s)
    page, h, k = [], 0, 0
    for s in strips + [None]:
        if s is None or (page and h + s.height > 1600):
            sheet = Image.new("RGB", (W * 2 + 6, sum(p.height + 4 for p in page)), (0, 0, 0))
            y = 0
            for p in page:
                sheet.paste(p, (0, y))
                y += p.height + 4
            sheet.save(os.path.join(vdir, f"compare_{k:02d}.jpg"), quality=88)
            page, h, k = [], 0, k + 1
        if s is not None:
            page.append(s)
            h += s.height + 4
    print(f"Ảnh so sánh: {vdir}/compare_*.jpg ({k} trang)")
    sys.exit(1 if left or hits else 0)


if __name__ == "__main__":
    main()

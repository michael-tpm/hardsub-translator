"""Bước 1 — Dò chữ Trung trong video: thời điểm + vị trí từng dòng.

Dùng: python detect.py <video.mp4> <thư_mục_làm_việc> [--fps 5] [--jobs 4]
Ra:   <thư_mục>/captions.json   (danh sách câu, cột "vi" để trống chờ dịch)
      <thư_mục>/review/sheet_XX.jpg  (ảnh cắt từng câu, đánh số, để soát chữ)
"""
import argparse, difflib, json, os, re, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OCR_BIN = os.path.join(HERE, "ocr_vision")
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
CJK = re.compile(r"[㐀-鿿]")


def probe(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                   "-show_entries", "stream=width,height,r_frame_rate:format=duration",
                                   "-of", "json", path])
    j = json.loads(out)
    s = j["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return s["width"], s["height"], float(num) / float(den), float(j["format"]["duration"])


def white_mask(img, box):
    """Điểm ảnh trắng (chữ phụ đề) trong box."""
    x0, y0, x1, y1 = box
    roi = img[y0:y1, x0:x1].astype(np.int16)
    mx, mn = roi.max(axis=2), roi.min(axis=2)
    return (mn > 200) & (mx - mn < 50)


def text_feat(img, box):
    """Nét chữ phụ đề: điểm trắng nằm sát viền tối (bỏ qua nền trắng như đĩa, khay)."""
    x0, y0, x1, y1 = box
    roi = img[y0:y1, x0:x1].astype(np.int16)
    white = (roi.min(axis=2) > 200) & (roi.max(axis=2) - roi.min(axis=2) < 50)
    dark = cv2.dilate((roi.max(axis=2) < 100).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    return white & dark


def iou(cur, ref):
    """Trùng khớp nét chữ: thấp khi mất chữ HOẶC khi là câu khác cùng chỗ."""
    u = (cur | ref).sum()
    return (cur & ref).sum() / u if u else 0.0


def box_iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    area = lambda r: (r[2] - r[0]) * (r[3] - r[1])
    return inter / (area(a) + area(b) - inter) if inter else 0.0


def run_ocr(files, jobs):
    chunks = [files[i::jobs] for i in range(jobs)]
    def work(chunk):
        if not chunk:
            return []
        out = subprocess.check_output([OCR_BIN, *chunk], text=True)
        return [json.loads(l) for l in out.splitlines() if l.strip()]
    res = {}
    with ThreadPoolExecutor(jobs) as ex:
        for part in ex.map(work, chunks):
            for r in part:
                res[r["file"]] = r["lines"]
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("work")
    ap.add_argument("--fps", type=float, default=5, help="số khung/giây đem đi OCR")
    ap.add_argument("--jobs", type=int, default=4, help="số tiến trình OCR song song")
    ap.add_argument("--min-dur", type=float, default=0.3, help="bỏ dòng hiện ngắn hơn (giây)")
    a = ap.parse_args()
    a.work = os.path.abspath(a.work)

    W, H, VFPS, DUR = probe(a.video)
    fdir = os.path.join(a.work, "frames")
    shutil.rmtree(fdir, ignore_errors=True)
    os.makedirs(fdir)
    print(f"Video {W}x{H} {VFPS:.2f}fps {DUR:.1f}s — tách khung {a.fps}/giây…", flush=True)
    subprocess.check_call(["ffmpeg", "-v", "error", "-i", a.video, "-vf", f"fps={a.fps}",
                           "-q:v", "2", os.path.join(fdir, "s_%05d.jpg")])
    files = sorted(os.path.join(fdir, f) for f in os.listdir(fdir))
    print(f"OCR {len(files)} khung, {a.jobs} tiến trình song song…", flush=True)
    ocr = run_ocr(files, a.jobs)

    # Gom dòng chữ Trung thành "vệt" theo thời gian (cùng vị trí + chữ gần giống)
    step = 1 / a.fps
    tracks = []
    for i, f in enumerate(files):
        t = i * step  # khung fps=N lấy tại t = i/N (xấp xỉ)
        for ln in ocr.get(f, []):
            if not CJK.search(ln["text"]):
                continue
            b = [max(0, ln["box"][0]), max(0, ln["box"][1]), min(W, ln["box"][2]), min(H, ln["box"][3])]
            best = None
            for tr in tracks:
                if i - tr["last"] > 3:
                    continue
                if box_iou(b, tr["box"]) > 0.5 and \
                        difflib.SequenceMatcher(None, ln["text"], tr["texts"][-1][0]).ratio() >= 0.4:
                    best = tr
                    break
            if best is None:
                best = {"first": i, "last": i, "box": b, "texts": [], "boxes": [], "frames": []}
                tracks.append(best)
            best["last"] = i
            best["texts"].append((ln["text"], ln["conf"]))
            best["boxes"].append(b)
            best["frames"].append(f)

    # Lọc: phải là chữ trắng (phụ đề), không phải chữ in trên bao bì
    keep = []
    for tr in tracks:
        bx = np.array(tr["boxes"])
        tr["box"] = [int(np.median(bx[:, 0])), int(np.median(bx[:, 1])),
                     int(np.median(bx[:, 2])), int(np.median(bx[:, 3]))]
        mid = tr["frames"][len(tr["frames"]) // 2]
        mid_img = np.asarray(Image.open(mid).convert("RGB"))
        white = white_mask(mid_img, tr["box"])
        tr["white"] = float(white.mean())
        # Phụ đề có viền tối quanh chữ trắng; chữ in nổi trên khay/nồi thì không
        tr["ref"] = text_feat(mid_img, tr["box"])
        tr["outline"] = float(tr["ref"].sum() / max(1, white.sum()))
        tr["mid_frame"] = mid
        cnt = {}
        for txt, c in tr["texts"]:
            cnt[txt] = cnt.get(txt, 0) + 1 + c
        tr["zh"] = max(cnt, key=cnt.get)
        if tr["white"] < 0.04:
            print(f"  bỏ (không phải chữ trắng): {tr['zh']}  t={tr['first']*step:.1f}s", flush=True)
            continue
        keep.append(tr)
    tracks = keep

    # Tinh chỉnh mốc đầu/cuối theo từng khung gốc bằng so khớp mặt nạ chữ trắng
    print("Tinh chỉnh mốc thời gian theo từng khung…", flush=True)
    for tr in tracks:
        tr["s0"], tr["e0"] = tr["first"] * step, tr["last"] * step
        tr["score"] = {}
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", a.video, "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    n = 0
    fsz = W * H * 3
    while True:
        buf = dec.stdout.read(fsz)
        if len(buf) < fsz:
            break
        t = n / VFPS
        img = None
        for tr in tracks:
            if tr["s0"] - 1.5 <= t <= tr["e0"] + 1.5:  # OCR có thể sót vài khung đầu/cuối
                if img is None:
                    img = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
                tr["score"][n] = iou(text_feat(img, tr["box"]), tr["ref"])
        n += 1
    dec.wait()

    for tr in tracks:
        sc = tr["score"]
        n0 = int(round(tr["s0"] * VFPS))
        n1 = int(round(tr["e0"] * VFPS))
        thr = 0.5
        s = n0
        while s - 1 in sc and sc[s - 1] > thr:
            s -= 1
        while s < n1 and sc.get(s, 1) <= thr:  # khung lấy mẫu lệch nhẹ
            s += 1
        e = n1
        while e + 1 in sc and sc[e + 1] > thr:
            e += 1
        while e > s and sc.get(e, 1) <= thr:
            e -= 1
        tr["start"], tr["end"] = round(s / VFPS, 3), round((e + 1) / VFPS, 3)

    tracks = [tr for tr in tracks if tr["end"] - tr["start"] >= a.min_dur]
    tracks.sort(key=lambda tr: (tr["start"], tr["box"][1]))

    # Gom các dòng cùng lúc thành 1 câu
    caps = []
    for tr in tracks:
        line = {"zh": tr["zh"], "vi": "", "box": tr["box"], "start": tr["start"], "end": tr["end"],
                "outline": round(tr["outline"], 2)}
        if tr["outline"] < 0.2:
            line["nghi_ngo"] = True  # có thể không phải phụ đề → soát kỹ
        if caps and abs(caps[-1]["start"] - tr["start"]) < 0.25 and abs(caps[-1]["end"] - tr["end"]) < 0.25:
            caps[-1]["lines"].append(line)
            caps[-1]["end"] = max(caps[-1]["end"], tr["end"])
        else:
            caps.append({"id": len(caps) + 1, "start": tr["start"], "end": tr["end"],
                         "frame": tr["mid_frame"], "lines": [line]})
    for c in caps:
        c["lines"].sort(key=lambda l: l["box"][1])

    with open(os.path.join(a.work, "captions.json"), "w", encoding="utf-8") as f:
        json.dump({"video": os.path.abspath(a.video), "width": W, "height": H, "fps": VFPS,
                   "duration": DUR, "captions": caps}, f, ensure_ascii=False, indent=1)

    # Ảnh soát chữ: mỗi câu 1 dải cắt, có số thứ tự
    rdir = os.path.join(a.work, "review")
    shutil.rmtree(rdir, ignore_errors=True)
    os.makedirs(rdir)
    font = ImageFont.truetype(FONT, 22)
    strips = []
    for c in caps:
        im = Image.open(c["frame"]).convert("RGB")
        y0 = max(0, min(l["box"][1] for l in c["lines"]) - 8)
        y1 = min(H, max(l["box"][3] for l in c["lines"]) + 8)
        crop = im.crop((0, y0, W, y1))
        strip = Image.new("RGB", (W + 110, crop.height), (40, 40, 40))
        strip.paste(crop, (110, 0))
        ImageDraw.Draw(strip).text((8, 4), f"#{c['id']}\n{c['start']:.1f}s", font=font, fill=(255, 220, 0))
        strips.append(strip)
    page, k = [], 0
    def flush(page, k):
        h = sum(s.height for s in page) + 4 * len(page)
        sheet = Image.new("RGB", (W + 110, h), (0, 0, 0))
        y = 0
        for s in page:
            sheet.paste(s, (0, y))
            y += s.height + 4
        sheet.save(os.path.join(rdir, f"sheet_{k:02d}.jpg"), quality=90)
    hsum = 0
    for s in strips:
        if page and hsum + s.height > 1400:
            flush(page, k)
            page, hsum, k = [], 0, k + 1
        page.append(s)
        hsum += s.height + 4
    if page:
        flush(page, k)

    print(f"Xong: {len(caps)} câu, {len(tracks)} dòng → {os.path.join(a.work, 'captions.json')}")
    for c in caps:
        flag = " [NGHI NGỜ]" if any(l.get("nghi_ngo") for l in c["lines"]) else ""
        print(f"  #{c['id']:>2} {c['start']:6.2f}-{c['end']:6.2f}  "
              + " / ".join(f"{l['zh']}({l['outline']})" for l in c["lines"]) + flag)


if __name__ == "__main__":
    main()

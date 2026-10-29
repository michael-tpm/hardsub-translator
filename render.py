"""Bước 3 — Xóa chữ Trung và ghi chữ Việt, xuất video MỘT lần (giữ âm thanh gốc).

Dùng: python render.py <captions.json> <video_ra.mp4> [--style hop|vien] [--from 0 --to 5]
  --style hop  (mặc định) chữ đen trên nền trắng bo góc, kiểu phụ đề TikTok; nền trắng che kín chỗ chữ Trung cũ
  --style vien chữ trắng viền đen, đặt thẳng lên hình
Mỗi dòng trong captions.json:
  "vi":    chữ Việt ("\n" để xuống dòng; chuỗi rỗng = chỉ xóa, không ghi)
  "skip":  true → bỏ qua dòng này (không phải phụ đề)
  "erase": [[x0,y0,x1,y1], ...] → xóa trắng thêm vùng này (vd: emoji ✅ cạnh chữ)
"""
import argparse, json, subprocess

import cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont

FONTS = {  # (file, index) — cả 2 đều đủ dấu tiếng Việt
    "hop": ("/System/Library/Fonts/Avenir Next.ttc", 2),  # Avenir Next Demi Bold
    "vien": ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
}
MARGIN = 16
SS = 2  # vẽ to gấp đôi rồi thu nhỏ → chữ và góc bo mịn
_fonts = {}


def font(style, size):
    k = (style, size)
    if k not in _fonts:
        path, idx = FONTS[style]
        _fonts[k] = ImageFont.truetype(path, size, index=idx)
    return _fonts[k]


def white_mask(frame, box, W, H, pad=6):
    x0, y0 = max(0, box[0] - pad), max(0, box[1] - pad)
    x1, y1 = min(W, box[2] + pad), min(H, box[3] + pad)
    roi = frame[y0:y1, x0:x1].astype(np.int16)
    mx, mn = roi.max(axis=2), roi.min(axis=2)
    m = np.zeros(frame.shape[:2], np.uint8)
    m[y0:y1, x0:x1] = ((mn > 200) & (mx - mn < 50)).astype(np.uint8) * 255
    return m


def text_w(style, size, s):
    return font(style, size).getlength(s) + (4 if style == "vien" else 0)


def pad_x(size):
    return round(size * 0.5)


def fit_size(style, line, W, size):
    """Cỡ chữ lớn nhất ≤ size mà dòng Việt (kể cả nền) vừa khung hình."""
    extra = 2 * pad_x(size) if style == "hop" else 0
    while size > 16 and max(text_w(style, size, s) for s in line["vi"].split("\n")) + extra > W - 2 * MARGIN:
        size -= 1
        extra = 2 * pad_x(size) if style == "hop" else 0
    return size


def rects(style, line, W, size):
    """Khung (x0,y0,x1,y1) + chữ cho từng dòng con; khung đầu phủ kín chữ Trung gốc."""
    x0, y0, x1, y1 = line["box"]
    cx = (x0 + x1) / 2
    if abs(cx - W / 2) < W * 0.08:  # phụ đề canh giữa
        cx = W / 2
    bh = round(size * 1.55)
    out, top = [], None
    for i, s in enumerate(line["vi"].split("\n")):
        rw = text_w(style, size, s) + (2 * pad_x(size) if style == "hop" else 0)
        rh = bh
        if i == 0 and style == "hop":
            rw, rh = max(rw, x1 - x0 + 12), max(rh, y1 - y0 + 8)
        if i == 0:
            top = (y0 + y1) / 2 - rh / 2
        left = min(max(cx - rw / 2, MARGIN / 2), W - MARGIN / 2 - rw)
        out.append(((round(left), round(top), round(left + rw), round(top + rh)), s))
        top += rh - 2  # dòng con dính liền khung trên
    return out


def patches(style, line, W, H, size):
    """Ảnh phủ (BGR, alpha) vẽ sẵn 1 lần: (nền, chữ) — nền mọi dòng vẽ trước, chữ vẽ sau."""
    rs = rects(style, line, W, size)
    pad = 6
    X0 = max(0, min(r[0] for r, _ in rs) - pad)
    Y0 = max(0, min(r[1] for r, _ in rs) - pad)
    X1 = min(W, max(r[2] for r, _ in rs) + pad)
    Y1 = min(H, max(r[3] for r, _ in rs) + pad)
    w, h = X1 - X0, Y1 - Y0
    f = font(style, size * SS)

    def finish(img):
        a = np.asarray(img.resize((w, h), Image.LANCZOS)).astype(np.float32) / 255
        return X0, Y0, a[..., [2, 1, 0]], a[..., 3:4]  # RGBA → BGR + alpha

    box = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    txt = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    db, dt = ImageDraw.Draw(box), ImageDraw.Draw(txt)
    for (rx0, ry0, rx1, ry1), s in rs:
        bx = [(rx0 - X0) * SS, (ry0 - Y0) * SS, (rx1 - X0) * SS, (ry1 - Y0) * SS]
        c = ((bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2)
        if style == "hop":
            db.rounded_rectangle(bx, radius=round(size * 0.3) * SS, fill=(255, 255, 255, 255))
            dt.text(c, s, font=f, anchor="mm", fill=(18, 18, 18, 255))
        else:
            sw = 2 * SS
            dt.text((c[0] + 2 * SS, c[1] + 2 * SS), s, font=f, anchor="mm", fill=(0, 0, 0, 110),
                    stroke_width=sw, stroke_fill=(0, 0, 0, 110))
            dt.text(c, s, font=f, anchor="mm", fill=(255, 255, 255, 255), stroke_width=sw, stroke_fill=(20, 20, 20, 255))
    return (finish(box) if style == "hop" else None), finish(txt)


def blend(frame, p):
    x, y, rgb, a = p
    h, w = a.shape[:2]
    roi = frame[y:y + h, x:x + w].astype(np.float32)
    frame[y:y + h, x:x + w] = (rgb * 255 * a + roi * (1 - a) + 0.5).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("captions")
    ap.add_argument("out")
    ap.add_argument("--style", choices=["hop", "vien"], default="hop")
    ap.add_argument("--from", dest="t0", type=float, default=0)
    ap.add_argument("--to", dest="t1", type=float, default=None)
    a = ap.parse_args()

    cfg = json.load(open(a.captions, encoding="utf-8"))
    W, H, FPS, src = cfg["width"], cfg["height"], cfg["fps"], cfg["video"]
    lines = [l for c in cfg["captions"] if not c.get("skip")
             for l in c["lines"] if not l.get("skip")]
    missing = [l["zh"] for l in lines if "vi" not in l or l["vi"] is None]
    if missing:
        raise SystemExit(f"Còn {len(missing)} dòng chưa có 'vi': {missing[:3]}")

    # Cỡ chữ chung cả video (theo chiều cao chữ Trung gốc); câu nào dòng quá dài thì thu nhỏ cả câu
    base = int(min(40, max(20, round(np.median([l["box"][3] - l["box"][1] for l in lines]) * 0.75))))
    print(f"Kiểu: {a.style}, cỡ chữ chung: {base}px")
    for c in cfg["captions"]:
        ls = [l for l in c["lines"] if not l.get("skip") and l.get("vi")]
        if c.get("skip") or not ls:
            continue
        size = min(fit_size(a.style, l, W, base) for l in ls)
        for l in ls:
            l["_box"], l["_txt"] = patches(a.style, l, W, H, size)
    for l in lines:
        l.setdefault("_box", None)
        l.setdefault("_txt", None)
        # So theo số khung (mốc giây trong json đã làm tròn 3 số lẻ)
        l["_n0"], l["_n1"] = round(l["start"] * FPS), round(l["end"] * FPS)
    n_off = round(a.t0 * FPS)

    seek = ["-ss", str(a.t0)] if a.t0 else []
    dur = ["-t", str(a.t1 - a.t0)] if a.t1 else []
    dec = subprocess.Popen(["ffmpeg", "-v", "error", *seek, "-i", src, *dur,
                            "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y",
                            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                            *seek, *dur, "-i", src,
                            "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-crf", "16", "-preset", "medium",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                            "-shortest", a.out], stdin=subprocess.PIPE)
    fsz, n = W * H * 3, 0
    while True:
        buf = dec.stdout.read(fsz)
        if len(buf) < fsz:
            break
        act = [l for l in lines if l["_n0"] <= n + n_off < l["_n1"]]
        frame = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        if act:
            mask = np.zeros((H, W), np.uint8)
            for l in act:
                mask |= white_mask(frame, l["box"], W, H)
            mask = cv2.dilate(mask, np.ones((7, 7), np.uint8))
            for l in act:
                for x0, y0, x1, y1 in l.get("erase", []):
                    mask[y0:y1, x0:x1] = 255
            frame = cv2.inpaint(frame, mask, 5, cv2.INPAINT_TELEA)
            for key in ("_box", "_txt"):
                for l in act:
                    if l[key] is not None:
                        blend(frame, l[key])
        enc.stdin.write(frame.tobytes())
        n += 1
    enc.stdin.close()
    enc.wait()
    dec.wait()
    print(f"Xong {n} khung → {a.out}")


if __name__ == "__main__":
    main()

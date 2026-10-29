"""Bước 2 — Xuất / nhập bảng dịch (TSV, mở được bằng Excel/Numbers).

Xuất:  python dich_tsv.py export <captions.json>   → <cùng thư mục>/dich.tsv
Nhập:  python dich_tsv.py import <captions.json>   ← đọc dich.tsv, ghi vào captions.json

Cột trong dich.tsv:
  cau, dong, start, end : số câu, số dòng, mốc giây (sửa được nếu cần)
  zh                    : chữ Trung OCR đọc được (chỉ để tham khảo)
  vi                    : điền tiếng Việt; "\\n" = xuống dòng; để trống = chỉ xóa chữ Trung
  bo_qua                : x = không phải phụ đề, giữ nguyên (đã tự đánh x cho dòng nghi ngờ)
  xoa_vung              : x = xóa trắng cả khung chữ (chữ mờ dần / có hiệu ứng / emoji)
"""
import csv, json, os, sys

COLS = ["cau", "dong", "start", "end", "zh", "vi", "bo_qua", "xoa_vung"]


def main():
    mode, path = sys.argv[1], sys.argv[2]
    tsv = os.path.join(os.path.dirname(os.path.abspath(path)), "dich.tsv")
    d = json.load(open(path, encoding="utf-8"))

    if mode == "export":
        with open(tsv, "w", encoding="utf-8-sig", newline="") as f:  # BOM → Excel hiển thị đúng tiếng Việt
            w = csv.writer(f, delimiter="\t")
            w.writerow(COLS)
            for c in d["captions"]:
                for i, l in enumerate(c["lines"], 1):
                    skip = l.get("skip", l.get("nghi_ngo", False)) or c.get("skip")
                    w.writerow([c["id"], i, l["start"], l["end"], l["zh"], l.get("vi", "").replace("\n", "\\n"),
                                "x" if skip else "", "x" if l.get("erase") else ""])
        print(f"Đã xuất {tsv}")
        return

    rows = {(int(r["cau"]), int(r["dong"])): r
            for r in csv.DictReader(open(tsv, encoding="utf-8-sig"), delimiter="\t")}
    for c in d["captions"]:
        for i, l in enumerate(c["lines"], 1):
            r = rows.get((c["id"], i))
            if r is None:
                continue
            l["vi"] = r["vi"].replace("\\n", "\n").strip()
            l["skip"] = r["bo_qua"].strip().lower() == "x"
            l["start"], l["end"] = float(r["start"]), float(r["end"])
            if r["xoa_vung"].strip().lower() == "x":
                x0, y0, x1, y1 = l["box"]
                l["erase"] = [[max(0, x0 - 6), max(0, y0 - 4), min(d["width"], x1 + 6), min(d["height"], y1 + 4)]]
            else:
                l.pop("erase", None)
        live = [l for l in c["lines"] if not l["skip"]]
        c["skip"] = not live
        if live:
            c["start"], c["end"] = min(l["start"] for l in live), max(l["end"] for l in live)
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    todo = [(c["id"], l["zh"]) for c in d["captions"] for l in c["lines"] if not l["skip"] and not l["vi"]]
    print(f"Đã nhập vào {path}. Dòng chưa có tiếng Việt (sẽ chỉ xóa chữ): {len(todo)}")
    for t in todo:
        print("  ", t)


if __name__ == "__main__":
    main()

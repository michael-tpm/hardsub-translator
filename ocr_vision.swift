// OCR ảnh bằng Apple Vision (tiếng Trung giản thể + phồn thể).
// Dùng: ocr_vision <ảnh1> [ảnh2 ...]  → mỗi dòng 1 JSON: {"file","lines":[{"text","conf","box":[x0,y0,x1,y1]}]}
// box tính theo pixel, gốc trên-trái.
import Foundation
import Vision
import AppKit

func ocr(_ path: String) -> [[String: Any]] {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return [] }
    let W = Double(cg.width), H = Double(cg.height)
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US"]
    req.usesLanguageCorrection = true
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    try? handler.perform([req])
    var out: [[String: Any]] = []
    for o in req.results ?? [] {
        guard let c = o.topCandidates(1).first else { continue }
        let b = o.boundingBox
        out.append(["text": c.string, "conf": Double(c.confidence),
                    "box": [Int(b.minX * W), Int((1 - b.maxY) * H), Int(b.maxX * W), Int((1 - b.minY) * H)]])
    }
    return out
}

for p in CommandLine.arguments.dropFirst() {
    let rec: [String: Any] = ["file": p, "lines": ocr(p)]
    if let d = try? JSONSerialization.data(withJSONObject: rec), let s = String(data: d, encoding: .utf8) {
        print(s)
        fflush(stdout)
    }
}

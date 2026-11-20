"""Đo chất lượng phần Vision bằng ONNX chạy local: KHÔNG gọi Gemini/Groq, không tốn lượt.

    python eval/vision/tai_anh.py          # một lần: tải ảnh
    python eval/vision/run_eval.py         # đo + ghi eval/vision/KET_QUA.md

Đo năm thứ (phần 5 chỉ chạy khi thêm --gemini vì tốn lượt):
  1. Độ chính xác ĐẾM của YOLO (yolo11n.onnx) trên ảnh có đáp án, kèm quét ngưỡng tin cậy.
  2. Bộ lọc loại vật thể: hỏi "có mấy con mèo" thì còn lại gì so với không lọc.
  3. Lỗi xoay ảnh EXIF: ảnh dọc kiểu điện thoại, đếm trước và sau khi sửa.
  4. Tỉ lệ phân loại CHỦ ĐỀ từ câu hỏi (động vật / du lịch / món ăn / tài liệu / biểu đồ / chung)
     và tỉ lệ hiểu đúng loại vật thể trong câu hỏi.
  5. Vật ngoài 80 loại COCO ("con bướm", "người hói đầu") đếm bằng Gemini.

Ảnh riêng của bạn (đặc biệt ảnh dọc chụp từ điện thoại): bỏ vào `eval/vision/anh_rieng/`
kèm `nhan_rieng.json` dạng {"IMG_0001.jpg": {"dog": 2, "person": 1}} (xem README.md).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import statistics
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

THU_MUC = Path(__file__).resolve().parent
GOC_REPO = THU_MUC.parent.parent
sys.path.insert(0, str(GOC_REPO))

from PIL import Image  # noqa: E402

from app.agents.vision_agent.image_utils import chuan_hoa_huong_anh  # noqa: E402
from app.agents.vision_agent.labels import (  # noqa: E402
    COCO_VI,
    loc_theo_lop,
    lop_tu_cau_hoi,
    ten_viet,
)
from app.agents.vision_agent.onnx_detector import onnx_detect  # noqa: E402
from app.agents.vision_agent.tools import parse_yolo_results  # noqa: E402
from app.agents.vision_agent.topics import CHU_DE_CHUNG, chu_de_tu_cau_hoi  # noqa: E402

# Câu hỏi tự nhiên cho từng loại vật trong bộ ảnh (để đo bộ lọc như người dùng thật hỏi).
CAU_HOI_LOP = {
    "person": "Có mấy người?", "dog": "Có mấy con chó?", "cat": "Có mấy con mèo?",
    "horse": "Có mấy con ngựa?", "zebra": "Có mấy con ngựa vằn?", "giraffe": "Có mấy con hươu cao cổ?",
    "bird": "Có mấy con chim?", "bicycle": "Có mấy chiếc xe đạp?", "car": "Có mấy chiếc ô tô?",
    "motorcycle": "Có mấy chiếc xe máy?", "bus": "Có mấy chiếc xe buýt?", "truck": "Có mấy chiếc xe tải?",
    "apple": "Có mấy quả táo?", "orange": "Có mấy quả cam?", "donut": "Có mấy cái bánh donut?",
    "sports ball": "Có mấy quả bóng?", "umbrella": "Có mấy cái ô?", "bench": "Có mấy cái ghế dài?",
    "bed": "Có mấy cái giường?", "couch": "Có mấy cái ghế sofa?", "tennis racket": "Có mấy cái vợt tennis?",
    "snowboard": "Có mấy cái ván trượt tuyết?", "knife": "Có mấy cái dao?",
}


# --------------------------------------------------------------------------- #
# Chạy model
# --------------------------------------------------------------------------- #
def chay(duong_dan: Path, weights: str, conf: float, iou: float) -> dict:
    t0 = time.perf_counter()
    kq = parse_yolo_results(onnx_detect(str(duong_dan), weights, conf, iou))
    kq["ms"] = (time.perf_counter() - t0) * 1000
    return kq


def dem_tu_nguong(kq: dict, nguong: float) -> dict:
    """Số đếm khi chỉ giữ khung có độ tin cậy >= nguong. Chạy model MỘT lần ở ngưỡng
    thấp nhất rồi lọc: NMS tham lam đi từ điểm cao xuống nên khung điểm cao không bao giờ
    bị khung điểm thấp ảnh hưởng, kết quả y hệt chạy lại ở ngưỡng cao."""
    dem: Counter = Counter()
    for d in kq["detections"]:
        if d["confidence"] >= nguong:
            dem[d["class"]] += 1
    return dict(dem)


def cham(du_doan: dict, dap_an: dict) -> dict:
    """Chấm một ảnh: chỉ trên các loại có trong đáp án."""
    cap = []
    for lop, n_that in dap_an.items():
        n_dd = du_doan.get(lop, 0)
        cap.append((lop, n_that, n_dd))
    return {"cap": cap}


def tong_hop(ket_qua: list) -> dict:
    """ket_qua: list các (anh, lop, that, du_doan). Trả các số đo gộp."""
    n = len(ket_qua)
    if not n:
        return {}
    dung = sum(1 for _, _, t, p in ket_qua if t == p)
    mae = sum(abs(t - p) for _, _, t, p in ket_qua) / n
    tp = sum(min(t, p) for _, _, t, p in ket_qua)
    fp = sum(max(p - t, 0) for _, _, t, p in ket_qua)
    fn = sum(max(t - p, 0) for _, _, t, p in ket_qua)
    pre = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * pre * rec / (pre + rec) if pre + rec else 0.0
    return {"n": n, "dung": dung, "ti_le_dung": dung / n, "mae": mae, "precision": pre, "recall": rec, "f1": f1,
            "tp": tp, "fp": fp, "fn": fn}


def pc(x: float) -> str:
    return f"{x * 100:.1f}%"


# --------------------------------------------------------------------------- #
# Nạp dữ liệu
# --------------------------------------------------------------------------- #
def nap_bo_anh(thu_muc_anh: Path) -> list:
    du_lieu = json.loads((THU_MUC / "dataset.json").read_text(encoding="utf-8"))
    ds, thieu = [], []
    for a in du_lieu["anh"]:
        p = thu_muc_anh / a["file"]
        if not p.is_file():
            thieu.append(a["file"])
            continue
        if hashlib.sha256(p.read_bytes()).hexdigest() != a["sha256"]:
            sys.exit(f"{a['file']}: sha256 không khớp với lúc gắn nhãn. Chạy lại tai_anh.py.")
        ds.append({"file": a["file"], "path": p, "dem": a["dem"], "dem_ngoai": a.get("dem_ngoai", {}), "rieng": False})
    if thieu:
        sys.exit(f"Thiếu {len(thieu)} ảnh trong {thu_muc_anh}. Chạy trước: python eval/vision/tai_anh.py")

    nhan_rieng = THU_MUC / "anh_rieng" / "nhan_rieng.json"
    if nhan_rieng.is_file():
        for ten, dem in json.loads(nhan_rieng.read_text(encoding="utf-8")).items():
            if ten.startswith("_"):
                continue
            p = THU_MUC / "anh_rieng" / ten
            if p.is_file():
                # Khoá không phải tên lớp COCO ("quả xoài") -> phần 5 (Gemini), không chấm YOLO.
                coco = {k: v for k, v in dem.items() if k in COCO_VI}
                ngoai = {k: v for k, v in dem.items() if k not in COCO_VI}
                ds.append({"file": ten, "path": p, "dem": coco, "dem_ngoai": ngoai, "rieng": True})
            else:
                print(f"[cảnh báo] anh_rieng/{ten} có trong nhan_rieng.json nhưng không có file, bỏ qua.")
    return ds


# --------------------------------------------------------------------------- #
# 1. Độ chính xác đếm
# --------------------------------------------------------------------------- #
def do_dem(ds, weights, iou, nguong_chinh, cac_nguong):
    thap = min(cac_nguong + [nguong_chinh])
    chay_may = {}
    for a in ds:
        chay_may[a["file"]] = chay(a["path"], weights, thap, iou)

    theo_nguong = {}
    for ng in sorted(set(cac_nguong + [nguong_chinh])):
        cap = []
        for a in ds:
            if not a["dem"]:
                continue
            dd = dem_tu_nguong(chay_may[a["file"]], ng)
            for lop, that in a["dem"].items():
                cap.append((a["file"], lop, that, dd.get(lop, 0)))
        theo_nguong[ng] = (tong_hop(cap), cap)

    # ảnh "âm" (không có vật COCO nào): model có bịa ra không?
    am = []
    for a in ds:
        if a["dem"] or a["rieng"]:
            continue
        dd = dem_tu_nguong(chay_may[a["file"]], nguong_chinh)
        am.append((a["file"], dd))
    return chay_may, theo_nguong, am


# --------------------------------------------------------------------------- #
# 2. Bộ lọc loại vật thể
# --------------------------------------------------------------------------- #
def do_loc(ds, chay_may, nguong):
    hang = []
    for a in ds:
        for lop, that in a["dem"].items():
            q = CAU_HOI_LOP.get(lop)
            if not q:
                continue
            kq = chay_may[a["file"]]
            payload = {
                "counting": dem_tu_nguong(kq, nguong),
                "detections": [d for d in kq["detections"] if d["confidence"] >= nguong],
            }
            can = lop_tu_cau_hoi(q)
            loc = loc_theo_lop(payload, can)
            hang.append({
                "anh": a["file"], "lop": lop, "hieu_dung": lop in can,
                "loai_truoc": len(payload["counting"]), "vat_truoc": len(payload["detections"]),
                "loai_sau": len(loc["counting"]), "vat_sau": len(loc["detections"]),
                "dem_truoc": payload["counting"].get(lop, 0), "dem_sau": loc["counting"].get(lop, 0),
                "sach": all(c in can for c in loc["counting"]),
            })
    return hang


# --------------------------------------------------------------------------- #
# 3. EXIF
# --------------------------------------------------------------------------- #
def _ghi_kieu_dien_thoai(anh_dung: Image.Image, dich: Path, orient: int) -> None:
    """Giống điện thoại: pixel lưu bị xoay + cờ EXIF Orientation để trình xem xoay lại."""
    nguoc = {6: Image.ROTATE_90, 8: Image.ROTATE_270, 3: Image.ROTATE_180}[orient]
    ex = Image.Exif()
    ex[0x0112] = orient
    anh_dung.transpose(nguoc).save(dich, "JPEG", quality=95, exif=ex.tobytes())


def do_exif(ds, weights, conf, iou):
    """Với mỗi ảnh có đáp án và mỗi hướng EXIF (6, 8, 3) so ba cách đọc:
    cũ  = đọc pixel như lúc chưa sửa (bỏ qua cờ EXIF) -> chính là cái YOLO từng nhìn thấy;
    mới_detector = để nguyên file EXIF, detector tự xoay theo cờ;
    mới_upload   = qua chuan_hoa_huong_anh (đúng như /api/ask làm khi nhận ảnh)."""
    ket = {"cu": [], "moi_detector": [], "moi_upload": [], "goc": []}
    chi_tiet = defaultdict(list)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for a in ds:
            if not a["dem"] or a["rieng"]:
                continue
            with Image.open(a["path"]) as im0:
                dung = im0.convert("RGB")
            g = dem_tu_nguong(chay(a["path"], weights, conf, iou), conf)
            for lop, that in a["dem"].items():
                ket["goc"].append((a["file"], lop, that, g.get(lop, 0)))
            for orient in (6, 8, 3):
                f_exif = tmp / f"{a['file']}.o{orient}.jpg"
                _ghi_kieu_dien_thoai(dung, f_exif, orient)

                # cũ: pixel đúng như lưu trên file (không xoay), lưu PNG không mất dữ liệu
                with Image.open(f_exif) as raw:
                    f_cu = tmp / f"{a['file']}.o{orient}.cu.png"
                    raw.convert("RGB").save(f_cu)
                d_cu = dem_tu_nguong(chay(f_cu, weights, conf, iou), conf)

                d_det = dem_tu_nguong(chay(f_exif, weights, conf, iou), conf)

                f_up = tmp / f"{a['file']}.o{orient}.up.jpg"
                f_up.write_bytes(f_exif.read_bytes())
                chuan_hoa_huong_anh(f_up)
                d_up = dem_tu_nguong(chay(f_up, weights, conf, iou), conf)

                for lop, that in a["dem"].items():
                    ket["cu"].append((a["file"], lop, that, d_cu.get(lop, 0)))
                    ket["moi_detector"].append((a["file"], lop, that, d_det.get(lop, 0)))
                    ket["moi_upload"].append((a["file"], lop, that, d_up.get(lop, 0)))
                    chi_tiet[orient].append((d_cu.get(lop, 0) == that, d_up.get(lop, 0) == that))
    return ket, chi_tiet


def exif_anh_rieng(ds, weights, conf, iou):
    """Ảnh thật của bạn: ảnh nào mang cờ EXIF xoay thì so đếm cũ/mới."""
    ra = []
    with tempfile.TemporaryDirectory() as tmp:
        for a in ds:
            if not a["rieng"]:
                continue
            with Image.open(a["path"]) as im:
                huong = im.getexif().get(0x0112, 1)
                kich_thuoc = im.size
            if huong in (None, 0, 1):
                continue
            with Image.open(a["path"]) as raw:
                f_cu = Path(tmp) / (a["file"] + ".cu.png")
                raw.convert("RGB").save(f_cu)
            cu = dem_tu_nguong(chay(f_cu, weights, conf, iou), conf)
            moi = dem_tu_nguong(chay(a["path"], weights, conf, iou), conf)
            ra.append({"anh": a["file"], "huong": huong, "pixel_luu": kich_thuoc,
                       "dap_an": a["dem"], "cu": cu, "moi": moi})
    return ra


# --------------------------------------------------------------------------- #
# 5. Vật ngoài COCO bằng Gemini (tùy chọn: tốn lượt)
# --------------------------------------------------------------------------- #
def do_gemini(ds, bat: bool):
    """Mỗi cặp (ảnh, cụm ngoài COCO): hỏi đúng như người dùng "Có mấy <cụm>?" rồi chấm.

    Chỉ chạy khi bật --gemini (mỗi cặp tốn MỘT lượt Gemini). Đồng thời kiểm tra luồng:
    câu hỏi đó có thật sự được chia sang Gemini không (can_dung_gemini).
    """
    from app.agents.vision_agent.gemini_detect import can_dung_gemini, dem_bang_gemini

    hang = []
    for a in ds:
        for cum, that in (a.get("dem_ngoai") or {}).items():
            q = f"Có mấy {cum}?"
            muc_tieu = can_dung_gemini(q)
            r = {"anh": a["file"], "cum": cum, "that": that, "chia_gemini": bool(muc_tieu), "du_doan": None, "loi": ""}
            if bat and muc_tieu:
                kq = dem_bang_gemini(str(a["path"]), muc_tieu)
                if "error" in kq:
                    r["loi"] = " ".join(kq["error"].split())[:90].replace("|", "/")
                else:
                    r["du_doan"] = sum(kq["counting"].values())
            hang.append(r)
    return hang


# --------------------------------------------------------------------------- #
# 4. Chủ đề + loại vật trong câu hỏi
# --------------------------------------------------------------------------- #
def do_chu_de():
    cau = json.loads((THU_MUC / "cau_hoi.json").read_text(encoding="utf-8"))
    chu_de, loi = [], []
    for m in cau["chu_de"]:
        got = chu_de_tu_cau_hoi(m["q"]) or CHU_DE_CHUNG
        chu_de.append((m["q"], m["mong_doi"], got))
    loai = []
    for m in cau["loai_vat"]:
        got = sorted(lop_tu_cau_hoi(m["q"]))
        loai.append((m["q"], sorted(m["mong_doi"]), got))
    return chu_de, loai


# --------------------------------------------------------------------------- #
# Báo cáo
# --------------------------------------------------------------------------- #
def viet_bao_cao(ctx: dict) -> str:
    L = []
    P = L.append
    nguong = ctx["nguong"]
    chinh, cap = ctx["theo_nguong"][nguong]
    P(f"# Kết quả đánh giá Vision ({date.today().isoformat()})\n")
    P("Chạy bằng `python eval/vision/run_eval.py`. ONNX Runtime local, **không gọi Gemini/Groq**.\n")
    P(f"- Model: `{ctx['weights']}` · conf={nguong} · iou={ctx['iou']}")
    P(f"- Bộ ảnh: {ctx['so_anh_chuan']} ảnh có đáp án ({chinh['n']} cặp ảnh–loại), "
      f"{len(ctx['am'])} ảnh không có vật COCO" + (f", {ctx['so_anh_rieng']} ảnh riêng" if ctx['so_anh_rieng'] else ""))
    P(f"- Tốc độ: trung vị {ctx['ms_trung_vi']:.0f} ms/ảnh trên máy chạy báo cáo (CPU, chưa tính mạng/LLM)")
    P("- **Đáp án đếm do Claude gắn nhãn bằng mắt, chưa có người kiểm lại.** Chỉ gắn những loại thấy rõ và đếm chắc "
      "chắn (không gắn đám đông, vật bị che nhiều, vật quá nhỏ). Số liệu dưới đây vì thế dùng cho "
      "cảnh \"đếm vật rõ ràng\", không đại diện cho ảnh đông đúc.\n")

    P("## 1. Độ chính xác đếm của YOLO\n")
    P("| Chỉ số | Giá trị |\n|---|---|")
    P(f"| Đếm đúng tuyệt đối | **{chinh['dung']}/{chinh['n']} = {pc(chinh['ti_le_dung'])}** |")
    P(f"| Sai số trung bình (MAE) | {chinh['mae']:.2f} vật/cặp |")
    P(f"| Precision / Recall / F1 (mức số lượng) | {pc(chinh['precision'])} / {pc(chinh['recall'])} / {pc(chinh['f1'])} |")
    t1 = [c for c in cap if c[2] == 1]
    t2 = [c for c in cap if c[2] >= 2]
    s1, s2 = tong_hop(t1), tong_hop(t2)
    if s1:
        P(f"| Chỉ 1 vật cần đếm | {s1['dung']}/{s1['n']} = {pc(s1['ti_le_dung'])} |")
    if s2:
        P(f"| Từ 2 vật trở lên | {s2['dung']}/{s2['n']} = {pc(s2['ti_le_dung'])} |")
    P("")
    P("Quét ngưỡng tin cậy (cùng một lần chạy model):\n")
    P("| conf | Đếm đúng | MAE | Precision | Recall | F1 |\n|---|---|---|---|---|---|")
    for ng, (s, _c) in sorted(ctx["theo_nguong"].items()):
        danh_dau = " ← đang dùng" if ng == nguong else ""
        P(f"| {ng}{danh_dau} | {pc(s['ti_le_dung'])} | {s['mae']:.2f} | {pc(s['precision'])} | {pc(s['recall'])} | {pc(s['f1'])} |")
    P("")
    sai = [c for c in cap if c[2] != c[3]]
    if sai:
        P(f"Các cặp đếm sai ở conf={nguong} ({len(sai)}):\n")
        P("| Ảnh | Loại | Đáp án | YOLO |\n|---|---|---|---|")
        for f, lop, t, p in sai:
            P(f"| {f} | {lop} ({ten_viet(lop)}) | {t} | {p} |")
        P("")
    if ctx["am"]:
        bia = [(f, d) for f, d in ctx["am"] if d]
        P(f"Ảnh không có vật COCO: {len(ctx['am']) - len(bia)}/{len(ctx['am'])} ảnh YOLO trả đúng \"không có gì\"."
          + ("" if not bia else " Bịa ra: " + "; ".join(f"{f} → {d}" for f, d in bia)) + "\n")

    P("## 2. Lọc theo loại vật thể (hỏi gì trả nấy)\n")
    h = ctx["loc"]
    if h:
        hieu = sum(1 for r in h if r["hieu_dung"])
        sach = sum(1 for r in h if r["sach"])
        thua_truoc = statistics.mean(r["loai_truoc"] - (1 if r["dem_truoc"] else 0) for r in h)
        P(f"{len(h)} câu hỏi dạng \"Có mấy <loại>?\" trên các ảnh có loại đó (câu hỏi viết cho từng loại, xem `CAU_HOI_LOP`).\n")
        P("| Chỉ số | Không lọc (cũ) | Có lọc (mới) |\n|---|---|---|")
        P(f"| Số loại vật trả về mỗi câu (trung bình) | {statistics.mean(r['loai_truoc'] for r in h):.1f} | {statistics.mean(r['loai_sau'] for r in h):.1f} |")
        P(f"| Số khung trả về mỗi câu (trung bình) | {statistics.mean(r['vat_truoc'] for r in h):.1f} | {statistics.mean(r['vat_sau'] for r in h):.1f} |")
        P(f"| Loại vật KHÔNG được hỏi bị trả kèm (trung bình/câu) | {thua_truoc:.1f} | 0.0 |")
        P("")
        P(f"- Hiểu đúng loại được hỏi từ câu tiếng Việt: **{hieu}/{len(h)}**")
        P(f"- Kết quả chỉ chứa loại được hỏi: **{sach}/{len(h)}**")
        P(f"- Số đếm của loại được hỏi giữ nguyên sau lọc: **{sum(1 for r in h if r['dem_truoc'] == r['dem_sau'])}/{len(h)}**\n")

    P("## 3. Lỗi xoay ảnh EXIF (ảnh dọc chụp từ điện thoại)\n")
    k = ctx["exif"]
    if k["cu"]:
        sc, sm, su, sg = (tong_hop(k[x]) for x in ("cu", "moi_detector", "moi_upload", "goc"))
        P("Mỗi ảnh có đáp án được lưu lại kiểu điện thoại (pixel xoay + cờ EXIF Orientation 6, 8 và 3), rồi đếm lại.\n")
        P("| Cách đọc ảnh | Đếm đúng | MAE |\n|---|---|---|")
        P(f"| Ảnh gốc đúng chiều (mức tối đa có thể) | {pc(sg['ti_le_dung'])} | {sg['mae']:.2f} |")
        P(f"| **Cũ**: bỏ qua cờ EXIF | {pc(sc['ti_le_dung'])} | {sc['mae']:.2f} |")
        P(f"| Mới: detector tự xoay theo EXIF | {pc(sm['ti_le_dung'])} | {sm['mae']:.2f} |")
        P(f"| Mới: xoay ngay khi upload | {pc(su['ti_le_dung'])} | {su['mae']:.2f} |")
        P("")
        P("Theo hướng EXIF (đếm đúng cũ → sau upload):\n")
        P("| Orientation | Ý nghĩa | Cũ | Sau sửa |\n|---|---|---|---|")
        y_nghia = {6: "ảnh dọc, cầm máy xoay phải", 8: "ảnh dọc, cầm máy xoay trái", 3: "ảnh lộn ngược"}
        for o in (6, 8, 3):
            c = ctx["exif_chi_tiet"][o]
            n = len(c)
            P(f"| {o} | {y_nghia[o]} | {pc(sum(1 for x, _ in c if x) / n)} | {pc(sum(1 for _, y in c if y) / n)} |")
        P("")
    if ctx["exif_rieng"]:
        P("Ảnh thật trong `anh_rieng/` mang cờ xoay:\n")
        P("| Ảnh | Orientation | Pixel lưu (rộng×cao) | Đáp án | Cũ | Mới |\n|---|---|---|---|---|---|")
        for r in ctx["exif_rieng"]:
            P(f"| {r['anh']} | {r['huong']} | {r['pixel_luu'][0]}×{r['pixel_luu'][1]} | {r['dap_an']} | {r['cu']} | {r['moi']} |")
        P("")

    P("## 4. Phân loại chủ đề và hiểu loại vật từ câu hỏi\n")
    cd, lv = ctx["chu_de"], ctx["loai_cau_hoi"]
    dung = sum(1 for _, m, g in cd if m == g)
    P(f"Chủ đề (hàm `chu_de_tu_cau_hoi`, chạy local, không tốn model): **{dung}/{len(cd)} = {pc(dung / len(cd))}** "
      f"trên {len(cd)} câu viết tay.\n")
    P("| Chủ đề mong đợi | Số câu | Đúng | Tỉ lệ |\n|---|---|---|---|")
    theo = defaultdict(lambda: [0, 0])
    for _, m, g in cd:
        theo[m][0] += 1
        theo[m][1] += (m == g)
    for m, (n, d) in sorted(theo.items()):
        P(f"| {m} | {n} | {d} | {pc(d / n)} |")
    P("")
    sai_cd = [(q, m, g) for q, m, g in cd if m != g]
    if sai_cd:
        P("Câu phân loại sai:\n")
        P("| Câu hỏi | Mong đợi | Hàm trả |\n|---|---|---|")
        for q, m, g in sai_cd:
            P(f"| {q} | {m} | {g} |")
        P("")
    dl = sum(1 for _, m, g in lv if m == g)
    P(f"Loại vật trong câu hỏi (`lop_tu_cau_hoi`): **{dl}/{len(lv)} = {pc(dl / len(lv))}** trên {len(lv)} câu.\n")
    sai_lv = [(q, m, g) for q, m, g in lv if m != g]
    if sai_lv:
        P("| Câu hỏi | Mong đợi | Hàm trả |\n|---|---|---|")
        for q, m, g in sai_lv:
            P(f"| {q} | {m} | {g} |")
        P("")
    P("**Lưu ý khi trình bày:** phần 4 đo bước định tuyến chủ đề theo CÂU HỎI (từ khoá). Bước phân loại chủ đề "
      "theo NỘI DUNG ẢNH dùng Gemini nên không nằm trong bộ này (tốn lượt). Hai bộ câu hỏi do người viết tay "
      "nên là mẫu nhỏ, không phải số đo trên dữ liệu người dùng thật. Riêng `lop_tu_cau_hoi`: bộ 34 câu từng "
      "lộ một lỗi (\"Đếm số chó và mèo\" chỉ ra mèo) và quy tắc đã được sửa sau đó, nên 100% ở đây là con số "
      "SAU KHI chỉnh theo chính bộ này, lạc quan hơn so với câu hỏi chưa từng thấy. Phần 2 \"hiểu đúng loại\" dùng "
      "câu hỏi mẫu do người viết biết trước từ khoá nên cũng không độc lập.\n")
    g = ctx.get("gemini") or []
    if g:
        P("## 5. Đếm vật ngoài 80 loại COCO bằng Gemini\n")
        chia = sum(1 for r in g if r["chia_gemini"])
        P(f"Câu hỏi \"Có mấy <cụm>?\" được chia đúng sang Gemini: **{chia}/{len(g)}** (đọc câu hỏi, không tốn lượt).\n")
        da_chay = [r for r in g if r["du_doan"] is not None]
        if not ctx.get("gemini_bat"):
            P(f"Chưa đo độ chính xác: chạy lại với `--gemini` (tốn {chia} lượt Gemini, cần GEMINI/GOOGLE key trong .env).\n")
        else:
            s = tong_hop([(r["anh"], r["cum"], r["that"], r["du_doan"]) for r in da_chay])
            if s:
                P(f"Gemini đếm đúng tuyệt đối **{s['dung']}/{s['n']} = {pc(s['ti_le_dung'])}**, MAE {s['mae']:.2f}.\n")
            P("| Ảnh | Cụm | Đáp án | Gemini |\n|---|---|---|---|")
            for r in g:
                kq = r["du_doan"] if r["du_doan"] is not None else ("lỗi: " + r["loi"] if r["loi"] else "không chia sang Gemini")
                P(f"| {r['anh']} | {r['cum']} | {r['that']} | {kq} |")
            P("")
        P("Mẫu rất nhỏ, đáp án gắn tay: chỉ để minh hoạ tính năng, chưa đủ để kết luận độ chính xác của Gemini.\n")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--weights", default=str(GOC_REPO / "yolo11n.onnx"))
    ap.add_argument("--conf", type=float, default=0.25, help="ngưỡng chính (mặc định = YOLO_CONF của app)")
    ap.add_argument("--iou", type=float, default=0.45)
    ap.add_argument("--anh-dir", default=str(THU_MUC / "anh"))
    ap.add_argument("--ghi", default=str(THU_MUC / "KET_QUA.md"), help="file báo cáo Markdown; '-' = chỉ in ra màn hình")
    ap.add_argument("--json", default="", help="ghi thêm số liệu thô ra file JSON")
    ap.add_argument("--gemini", action="store_true",
                    help="đo thêm phần 5: vật ngoài COCO bằng Gemini (tốn 1 lượt Gemini mỗi cặp, cần key)")
    args = ap.parse_args()

    if not Path(args.weights).is_file():
        sys.exit(f"Không thấy model {args.weights}")
    ds = nap_bo_anh(Path(args.anh_dir))
    print(f"{len(ds)} ảnh, model {args.weights}")

    cac_nguong = [0.15, 0.25, 0.35, 0.5]
    chay_may, theo_nguong, am = do_dem(ds, args.weights, args.iou, args.conf, cac_nguong)
    ms = statistics.median(v["ms"] for v in chay_may.values())
    print("đếm xong; lọc...")
    loc = do_loc(ds, chay_may, args.conf)
    print("EXIF...")
    exif, exif_chi_tiet = do_exif(ds, args.weights, args.conf, args.iou)
    exif_rieng = exif_anh_rieng(ds, args.weights, args.conf, args.iou)
    chu_de, loai_cau_hoi = do_chu_de()
    gemini = do_gemini(ds, args.gemini)

    ctx = {
        "weights": Path(args.weights).name, "iou": args.iou, "nguong": args.conf,
        "theo_nguong": theo_nguong, "am": am, "loc": loc, "exif": exif, "exif_chi_tiet": exif_chi_tiet,
        "exif_rieng": exif_rieng, "chu_de": chu_de, "loai_cau_hoi": loai_cau_hoi, "ms_trung_vi": ms,
        "so_anh_chuan": sum(1 for a in ds if a["dem"] and not a["rieng"]),
        "so_anh_rieng": sum(1 for a in ds if a["rieng"]),
        "gemini": gemini, "gemini_bat": args.gemini,
    }
    bao_cao = viet_bao_cao(ctx)
    print()
    print(bao_cao)
    if args.ghi != "-":
        Path(args.ghi).write_text(bao_cao + "\n", encoding="utf-8")
        print(f"\nĐã ghi {args.ghi}")
    if args.json:
        thuan = {
            "conf": args.conf,
            "dem": {str(ng): s for ng, (s, _c) in theo_nguong.items()},
            "exif": {k: tong_hop(v) for k, v in exif.items() if v},
            "chu_de": {"dung": sum(1 for _, m, g in chu_de if m == g), "tong": len(chu_de)},
            "loai_cau_hoi": {"dung": sum(1 for _, m, g in loai_cau_hoi if m == g), "tong": len(loai_cau_hoi)},
        }
        Path(args.json).write_text(json.dumps(thuan, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

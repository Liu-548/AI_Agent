"""Nhóm C-7: phân tích video ngắn bằng cách đếm vật thể trên từng khung hình.

Khung hình được TRÌNH DUYỆT tách sẵn (thẻ <video> + canvas, tối đa 8 khung rải đều;
video tới 30 giây nên khung có thể cách nhau tới ~4 giây) rồi
gửi lên như các ảnh JPEG nhỏ. Lý do không giải mã video trên server:
  - repo chưa có thư viện đọc video (opencv/ffmpeg), thêm vào là đổi bộ phụ thuộc đã
    khoá của nhóm (QUY_TAC_THIET_KE.md, MT-03) và nặng thêm vài chục MB;
  - giải mã video tốn RAM, mà gói Free của Render chỉ có 512MB cho CẢ tiến trình.

Ở đây chỉ còn việc nhẹ: YOLO (ONNX, ~55ms/khung) đếm từng khung, gom thành dòng thời
gian và một bản tóm tắt bằng chữ cho supervisor. Không tốn lượt Gemini nào.

Lưu ý quan trọng khi diễn giải: đếm theo KHUNG, không theo dõi từng cá thể. "Nhiều nhất
3 người cùng lúc" là đúng; "video có tổng cộng 3 người" thì không suy ra được (một người
đi ra rồi người khác đi vào vẫn là 1 mỗi khung).
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from app.agents.vision_agent.labels import loc_theo_lop, lop_tu_cau_hoi, ten_viet

SO_KHUNG_TOI_DA = 8
THOI_LUONG_TOI_DA = 30.0  # giây. Luôn tối đa 8 khung: video dài thì khung thưa hơn.


def _giay(t: float) -> str:
    """2.1 -> "2,1s"; 3.0 -> "3s" (dấu phẩy thập phân kiểu Việt)."""
    return f"{t:.1f}".rstrip("0").rstrip(".").replace(".", ",") + "s"


def phan_tich_khung_hinh(
    duong_dan: List[str],
    thoi_diem: List[float],
    cau_hoi: str = "",
    detector: Optional[Callable] = None,
) -> dict:
    """YOLO từng khung -> {"frames": [...], "classes": {...}, "summary": "..."}.

    Câu hỏi nêu loại vật ("có mấy con chó") thì chỉ giữ loại đó (labels.py), như ảnh.
    """
    from app.agents.vision_agent.tools import default_detector, parse_yolo_results

    chay = detector or default_detector
    loai = lop_tu_cau_hoi(cau_hoi)
    frames: List[dict] = []
    for p, t in zip(duong_dan[:SO_KHUNG_TOI_DA], thoi_diem[:SO_KHUNG_TOI_DA]):
        kq = loc_theo_lop(parse_yolo_results(chay(p)), loai)
        frames.append({"t": round(float(t), 2), "counting": kq["counting"], "detections": kq["detections"]})

    cac_lop = sorted({c for f in frames for c in f["counting"]})
    lop: Dict[str, dict] = {}
    for c in cac_lop:
        dem = [f["counting"].get(c, 0) for f in frames]
        co_mat = [f["t"] for f in frames if f["counting"].get(c)]
        cao_nhat = max(dem)
        lop[c] = {
            "ten": ten_viet(c),
            "counts": dem,
            "max": cao_nhat,
            "max_at": [f["t"] for f in frames if f["counting"].get(c, 0) == cao_nhat],
            "frames_present": len(co_mat),
            "first": co_mat[0],
            "last": co_mat[-1],
        }
    return {
        "frames": frames,
        "classes": lop,
        "filtered_by": sorted(loai),
        "summary": tom_tat(frames, lop),
    }


def tom_tat(frames: List[dict], lop: Dict[str, dict]) -> str:
    """Tóm tắt bằng chữ, tiếng Việt, xác định (không gọi model)."""
    if not frames:
        return "Không có khung hình nào."
    n = len(frames)
    if not lop:
        return f"YOLO không phát hiện vật thể nào trong {n} khung hình."
    dong = []
    for c, v in sorted(lop.items(), key=lambda kv: -kv[1]["max"]):
        luc = ", ".join(_giay(t) for t in v["max_at"][:3])
        if v["frames_present"] == n:
            co_mat = f"có mặt cả {n}/{n} khung"
        else:
            co_mat = f"có mặt {v['frames_present']}/{n} khung (từ {_giay(v['first'])} đến {_giay(v['last'])})"
        dau, cuoi = v["counts"][0], v["counts"][-1]
        xu_huong = "tăng" if cuoi > dau else "giảm" if cuoi < dau else "không đổi"
        dong.append(
            f"- {v['ten']}: nhiều nhất {v['max']} cùng lúc (lúc {luc}); {co_mat}; "
            f"đầu video {dau}, cuối video {cuoi} ({xu_huong})."
        )
    return "\n".join(dong)


def khoi_cho_supervisor(ket: dict, thoi_luong: float) -> str:
    """Khối chữ gửi kèm câu hỏi: số đếm từng khung + tóm tắt + cách diễn giải đúng."""
    frames = ket["frames"]
    cach = thoi_luong / max(1, len(frames))
    dong = [
        f"[VIDEO] {_giay(thoi_luong)} video, {len(frames)} frames sampled evenly "
        f"(about one every {_giay(cach)}; anything shorter than that may be missed). "
        "Object counts by the detector (YOLO) in EACH frame:"
    ]
    for f in frames:
        ta = ", ".join(f"{ten_viet(c)} {k}" for c, k in f["counting"].items()) or "không có gì"
        dong.append(f"t={_giay(f['t'])}: {ta}")
    dong += [
        "Summary (Vietnamese):",
        ket["summary"],
        "Counts are PER FRAME, not tracked individuals: say 'nhiều nhất N cùng lúc', never claim "
        "a total number of different individuals in the whole video.",
        "[END VIDEO]",
    ]
    return "\n".join(dong)

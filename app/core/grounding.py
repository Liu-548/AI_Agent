"""Kiểm tra một câu trả lời có bám vào kết quả tool hay không (grounding).

Vì sao cần: model trả lời rất trôi chảy bằng trí nhớ của nó. Trong một lần chạy
thử, Research Agent viết "RoPE được dùng trong GPT-4, LLaMA-2" — LLaMA thì đúng,
còn GPT-4 thì OpenAI chưa từng công bố kiến trúc, và KHÔNG kết quả tool nào nhắc
tới cả hai. Với một agent tìm tài liệu khoa học thì đây là lỗi nặng: câu văn đúng
ngữ pháp, nghe hợp lý, và không ai soi ra khi chấm.

Cách chặn gồm hai nửa, cố tình tách rời:
- Nửa mềm (prompt): bắt model gắn NHÃN NGUỒN vào cuối mỗi câu.
- Nửa cứng (file này): đối chiếu nhãn với văn bản tool đã trả về. Thuần Python,
  không gọi LLM, nên chạy được offline và không tốn hạn mức.

Module này chỉ TỐ CÁO, không sửa câu trả lời. Sửa hộ model là che mất lỗi.
"""

from __future__ import annotations

import re
from typing import Iterable, List

# Nhãn nguồn model phải gắn cuối câu: [http://arxiv.org/abs/...] hoặc [wikipedia: Tên trang]
NHAN_RE = re.compile(r"\[([^\[\]\n]{3,300})\]")

# Mã bài báo arXiv dưới mọi dạng model hay viết.
MA_ARXIV_RE = re.compile(r"(?:arxiv\.org/abs/|arxiv:\s*)(\d{4}\.\d{4,5})", re.IGNORECASE)

# Dòng "Page: ..." trong kết quả wikipedia_search — nguồn hợp lệ duy nhất cho nhãn wikipedia.
TRANG_WIKI_RE = re.compile(r"^Page:\s*(.+)$", re.MULTILINE)

# Câu ngắn hơn ngần này coi như tiêu đề/gạch đầu dòng cấu trúc, không bắt gắn nhãn.
SO_TU_TOI_THIEU = 6

DAU_HIEU_TU_CHOI = ("KHONG DU DU LIEU", "KHÔNG ĐỦ DỮ LIỆU")


def _chuan_hoa(s: str) -> str:
    return " ".join((s or "").lower().split())


def _bo_nhan(cau: str) -> str:
    return NHAN_RE.sub(" ", cau)


def tach_cau(answer: str) -> List[str]:
    """Tách câu trả lời thành từng câu. Cắt theo xuống dòng rồi tới dấu kết câu."""
    cau = []
    for dong in (answer or "").splitlines():
        dong = dong.strip()
        if not dong:
            continue
        # Bỏ ký hiệu markdown đầu dòng để đếm từ cho đúng.
        dong = re.sub(r"^\s*(?:[-*+]|\d+[.)]|#{1,6}|\|)\s*", "", dong)
        for phan in re.split(r"(?<=[.!?])\s+", dong):
            phan = phan.strip()
            if not phan:
                continue
            # Nhãn nguồn đứng SAU dấu chấm nên bị regex trên tách thành một "câu"
            # riêng, làm câu thật phía trước trông như không có nguồn. Dán nó trả
            # về câu trước. Đây là lỗi đã làm bộ kiểm tra báo sai toàn bộ 4 câu
            # trong một lần chạy thử, dù model gắn nhãn hoàn toàn đúng.
            if cau and not _bo_nhan(phan).strip():
                cau[-1] = cau[-1] + " " + phan
                continue
            cau.append(phan)
    return cau


def ma_arxiv_trong(text: str) -> List[str]:
    """Mọi mã arXiv xuất hiện trong một đoạn văn bản, đã bỏ hậu tố phiên bản."""
    return [m.group(1) for m in MA_ARXIV_RE.finditer(text or "")]


def kiem_tra_grounding(answer: str, tool_texts: Iterable[str]) -> List[str]:
    """Trả về danh sách vi phạm. Rỗng = mọi khẳng định đều truy được về kết quả tool.

    Ba loại vi phạm, xếp theo mức nguy hiểm giảm dần:
      1. MA_BIA      — mã arXiv không có trong bất kỳ kết quả tool nào.
      2. NHAN_BIA    — nhãn nguồn trỏ tới thứ tool chưa từng trả về.
      3. THIEU_NGUON — câu khẳng định không gắn nhãn nào.
    """
    kho = "\n".join(t or "" for t in tool_texts)
    kho_chuan = _chuan_hoa(kho)
    ma_that = set(ma_arxiv_trong(kho))

    vi_pham: List[str] = []

    if any(d in (answer or "") for d in DAU_HIEU_TU_CHOI):
        return vi_pham  # model đã tự khai là không đủ dữ liệu, không bắt lỗi thêm

    for ma in dict.fromkeys(ma_arxiv_trong(answer)):
        if ma not in ma_that:
            vi_pham.append(f"MA_BIA: arXiv {ma} không có trong bất kỳ kết quả tool nào")

    trang_wiki = {_chuan_hoa(t) for t in TRANG_WIKI_RE.findall(kho)}

    for nhan in dict.fromkeys(m.group(1).strip() for m in NHAN_RE.finditer(answer or "")):
        if ma_arxiv_trong(nhan):
            continue  # mã arXiv đã xét ở vòng trên, không tố cáo hai lần
        khop_wiki = re.match(r"^wikipedia\s*:\s*(.+)$", nhan, flags=re.IGNORECASE)
        if khop_wiki:
            # Nhãn wikipedia phải trỏ tới đúng một dòng "Page:" tool đã trả về.
            # Không đối chiếu kiểu "có xuất hiện đâu đó" được: tên trang bịa vẫn
            # có thể trùng một cụm trong tiêu đề bài báo.
            ten_trang = _chuan_hoa(khop_wiki.group(1))
            if not any(ten_trang == t or ten_trang in t for t in trang_wiki):
                vi_pham.append(
                    f"NHAN_BIA: không có trang Wikipedia {khop_wiki.group(1).strip()!r} trong kết quả tool"
                )
            continue
        noi_dung = nhan.strip()
        if noi_dung and _chuan_hoa(noi_dung) not in kho_chuan:
            vi_pham.append(f"NHAN_BIA: nguồn {nhan!r} không xuất hiện trong kết quả tool")

    for cau in tach_cau(answer):
        if NHAN_RE.search(cau):
            continue
        if len(_bo_nhan(cau).split()) < SO_TU_TOI_THIEU:
            continue
        vi_pham.append(f"THIEU_NGUON: {cau[:110]}")

    return vi_pham


def bao_cao(vi_pham: List[str]) -> str:
    """Khối văn bản in ra sau câu trả lời."""
    if not vi_pham:
        return "=== KIEM TRA NGUON ===\nOK — mọi khẳng định đều truy được về kết quả tool."
    dong = ["=== KIEM TRA NGUON ===", f"{len(vi_pham)} chỗ chưa có nguồn kiểm chứng được:"]
    dong += [f"  - {v}" for v in vi_pham]
    dong.append("")
    if any(v.startswith("MA_BIA") for v in vi_pham):
        dong.append("MA_BIA là lỗi nặng nhất: mã đó không tồn tại trong dữ liệu đã tra.")
    if any(v.startswith("THIEU_NGUON") for v in vi_pham):
        dong.append("THIEU_NGUON: câu không gắn nhãn. Nhãn phải nằm CUỐI câu, dạng")
        dong.append("  [http://arxiv.org/abs/...] hoặc [wikipedia: Tên trang].")
    dong.append("Lưu ý: bộ này chỉ kiểm tra nguồn CÓ TỒN TẠI trong kết quả tool,")
    dong.append("không kiểm tra được nguồn đó có thật sự nói điều đang trích hay không.")
    return "\n".join(dong)

"""Kiểm tra TÍNH XÁC THỰC của nguồn — khác với grounding.py.

`grounding.py` chỉ trả lời câu hỏi "nguồn này có tồn tại trong kết quả tool
không". Nó KHÔNG trả lời được câu hỏi khác, cũng quan trọng không kém với một
Research Agent: "nguồn tồn tại thật, nhưng nó còn ĐÁNG TIN không?". Một bài báo
có thể có thật, có Entry ID/DOI thật, và vẫn không nên dùng để trả lời — vì nó
đã bị RÚT (retracted) sau khi công bố, hoặc tác giả tự rút lại (withdrawn).

Cách làm, để KHÔNG tốn thêm một lượt gọi API/LLM nào:
- OpenAlex đã trả sẵn field `is_retracted` trong CHÍNH response tìm kiếm (xem
  tools.tim_openalex) — chỉ cần xin thêm field đó qua `select=`, không phải
  gọi thêm request.
- arXiv không có field retraction, nhưng quy ước của họ là ghi thẳng chữ
  "withdrawn" vào `comment` hoặc đầu `summary` khi tác giả rút bài (xem
  https://info.arxiv.org/help/withdraw.html) — cũng đã có sẵn trong response.

Module này chỉ ĐỌC LẠI hai cờ đó từ văn bản tool đã trả về (không gọi mạng,
không gọi LLM) rồi đối chiếu với những nguồn THỰC SỰ được câu trả lời trích
dẫn. Giống grounding.py: chỉ tố cáo, không tự sửa câu trả lời.

Hạn chế cần biết: đây KHÔNG phải một bộ phát hiện "predatory journal" hay xác
minh danh tính tác giả — nó chỉ bắt được đúng hai cờ retracted/withdrawn mà
OpenAlex/arXiv tự công bố. Nguồn giả mạo tinh vi hơn (DOI thật nhưng nội dung
bị bóp méo, tạp chí dỏm...) nằm ngoài phạm vi của bộ kiểm tra rẻ tiền này.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List

from app.core.grounding import ma_arxiv_trong, ma_openalex_trong

# Một khối kết quả tool là đoạn văn bản giữa hai dòng trống -- đúng khuôn
# format_arxiv_docs()/format_openalex_docs() dùng để nối các mục lại với nhau.
_KHOI_RE = re.compile(r"\n\s*\n")

_CO_RUT_RE = re.compile(r"^(?:Retracted|Withdrawn):\s*CÓ", re.IGNORECASE | re.MULTILINE)


def nguon_da_rut(tool_texts: Iterable[str]) -> Dict[str, str]:
    """{mã_định_danh: lý do} cho mọi nguồn tool đã tự gắn cờ retracted/withdrawn.

    Mã định danh dùng CHUNG khuôn với grounding.py (mã arXiv bỏ hậu tố phiên
    bản, Work ID của OpenAlex) để hai module đối chiếu được với nhau.
    """
    ket_qua: Dict[str, str] = {}
    for text in tool_texts:
        for khoi in _KHOI_RE.split(text or ""):
            if not _CO_RUT_RE.search(khoi):
                continue
            for ma in ma_openalex_trong(khoi):
                ket_qua[ma] = "OpenAlex đánh dấu is_retracted = true"
            for ma in ma_arxiv_trong(khoi):
                ket_qua[ma] = "tác giả đã rút bài (withdrawn) trên arXiv"
    return ket_qua


def kiem_tra_xac_thuc(answer: str, tool_texts: Iterable[str]) -> List[str]:
    """Trả về danh sách vi phạm NGUON_RUT. Rỗng = không nguồn bị rút nào được trích dẫn.

    Chỉ bắt lỗi khi nguồn bị rút THỰC SỰ xuất hiện trong câu trả lời — một
    nguồn bị rút nằm trong kết quả tool nhưng model không dùng tới thì không
    phải lỗi của câu trả lời.
    """
    rut = nguon_da_rut(tool_texts)
    if not rut:
        return []
    ma_duoc_trich = set(ma_arxiv_trong(answer)) | set(ma_openalex_trong(answer))
    return [
        f"NGUON_RUT: {ma} — {rut[ma]}, không nên dùng làm căn cứ trả lời"
        for ma in sorted(ma_duoc_trich)
        if ma in rut
    ]


def bao_cao_xac_thuc(vi_pham: List[str]) -> str:
    """Khối văn bản in ra sau bao_cao() của grounding.py."""
    if not vi_pham:
        return (
            "=== KIEM TRA XAC THUC NGUON ===\n"
            "OK — không nguồn nào bị OpenAlex/arXiv gắn cờ retracted/withdrawn."
        )
    dong = [
        "=== KIEM TRA XAC THUC NGUON ===",
        f"{len(vi_pham)} nguồn ĐÃ BỊ RÚT nhưng vẫn được dùng làm căn cứ trả lời:",
    ]
    dong += [f"  - {v}" for v in vi_pham]
    dong.append("")
    dong.append(
        "Lưu ý: bộ này chỉ đọc lại cờ retracted/withdrawn mà OpenAlex/arXiv tự công bố,"
    )
    dong.append("không phát hiện được nguồn giả mạo tinh vi hơn (tạp chí dỏm, DOI bị bóp méo...).")
    return "\n".join(dong)

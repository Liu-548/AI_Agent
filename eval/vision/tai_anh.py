"""Tải ảnh của bộ đánh giá Vision về `eval/vision/anh/` và kiểm sha256.

    python eval/vision/tai_anh.py

Ảnh KHÔNG nằm trong repo (mỗi nguồn có giấy phép riêng) mà tải từ GitHub raw theo
`dataset.json`. Mỗi file được kiểm sha256: nếu nguồn đổi ảnh thì báo lỗi thay vì âm
thầm chấm điểm trên một ảnh khác với ảnh đã gắn nhãn.

Chạy lại bao nhiêu lần cũng được: ảnh đã tải đúng sha256 thì bỏ qua.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import requests

THU_MUC = Path(__file__).resolve().parent
ANH = THU_MUC / "anh"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    du_lieu = json.loads((THU_MUC / "dataset.json").read_text(encoding="utf-8"))
    ANH.mkdir(exist_ok=True)
    ok = hong = 0
    for a in du_lieu["anh"]:
        dich = ANH / a["file"]
        if dich.is_file() and _sha(dich.read_bytes()) == a["sha256"]:
            ok += 1
            continue
        try:
            r = requests.get(a["url"], timeout=30)
            r.raise_for_status()
        except requests.RequestException as exc:
            print(f"LỖI tải {a['file']}: {exc}")
            hong += 1
            continue
        if _sha(r.content) != a["sha256"]:
            print(f"LỖI {a['file']}: nội dung đã đổi so với lúc gắn nhãn (sha256 không khớp), bỏ qua.")
            hong += 1
            continue
        dich.write_bytes(r.content)
        ok += 1
        print(f"đã tải {a['file']}")
    print(f"\n{ok}/{len(du_lieu['anh'])} ảnh sẵn sàng" + (f", {hong} lỗi" if hong else ""))
    return 1 if hong else 0


if __name__ == "__main__":
    sys.exit(main())

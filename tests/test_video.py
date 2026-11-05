"""Nhóm C-7: video ngắn. Trình duyệt tách khung, server đếm từng khung bằng YOLO.

Lời hứa:
  - Dòng thời gian số đếm đúng từng khung, tóm tắt nêu "nhiều nhất N cùng lúc", lúc nào,
    có mặt bao nhiêu khung, tăng/giảm. Câu hỏi nêu loại vật thì chỉ giữ loại đó.
  - Supervisor nhận khối [VIDEO] (đếm theo KHUNG, không phải cá thể) và mã khung chính.
  - Câu hỏi cần "nhìn" -> MỘT lượt model xem các khung chính như một cảnh.
  - Giới hạn: tối đa 8 khung, video tối đa 10 giây.
Không cần mạng/API key: YOLO và model đều giả.
"""

from __future__ import annotations

import io
import json

from langchain_core.messages import AIMessage
from PIL import Image

from app.agents.vision_agent.video import khoi_cho_supervisor, phan_tich_khung_hinh
from tests.fakes import fake_detector_factory
from tests.test_image_memory import he  # noqa: F401

# số chó / người theo từng khung (giả)
KICH_BAN = [
    [("dog", 0.9, (1, 1, 5, 5))],
    [("dog", 0.9, (1, 1, 5, 5)), ("dog", 0.8, (6, 6, 9, 9)), ("person", 0.9, (1, 1, 9, 9))],
    [("dog", 0.9, (1, 1, 5, 5)), ("dog", 0.8, (6, 6, 9, 9)), ("dog", 0.7, (2, 2, 3, 3))],
    [("person", 0.9, (1, 1, 9, 9))],
]


def _detector_theo_thu_tu():
    i = {"n": 0}

    def _chay(_ref):
        kq = fake_detector_factory(KICH_BAN[i["n"] % len(KICH_BAN)])(_ref)
        i["n"] += 1
        return kq

    return _chay


def test_dong_thoi_gian_va_tom_tat():
    ket = phan_tich_khung_hinh(["a", "b", "c", "d"], [0, 1, 2, 3], "", detector=_detector_theo_thu_tu())
    assert [f["counting"].get("dog", 0) for f in ket["frames"]] == [1, 2, 3, 0]
    cho = ket["classes"]["dog"]
    assert cho["max"] == 3 and cho["max_at"] == [2] and cho["frames_present"] == 3
    assert cho["first"] == 0 and cho["last"] == 2
    assert "chó: nhiều nhất 3 cùng lúc (lúc 2s)" in ket["summary"]
    assert "có mặt 3/4 khung (từ 0s đến 2s)" in ket["summary"]
    assert "đầu video 1, cuối video 0 (giảm)" in ket["summary"]


def test_cau_hoi_neu_loai_thi_chi_giu_loai_do():
    ket = phan_tich_khung_hinh(["a", "b", "c", "d"], [0, 1, 2, 3], "Có mấy người?", detector=_detector_theo_thu_tu())
    assert set(ket["classes"]) == {"person"}
    assert ket["filtered_by"] == ["person"]


def test_khong_thay_gi():
    ket = phan_tich_khung_hinh(["a"], [0], "", detector=fake_detector_factory([]))
    assert "không phát hiện" in ket["summary"]


def test_khoi_cho_supervisor_noi_ro_dem_theo_khung():
    ket = phan_tich_khung_hinh(["a", "b"], [0, 1.5], "", detector=_detector_theo_thu_tu())
    khoi = khoi_cho_supervisor(ket, 2.0)
    assert khoi.startswith("[VIDEO] 2s video, 2 frames") and khoi.endswith("[END VIDEO]")
    assert "t=0s: chó 1" in khoi and "t=1,5s: chó 2, người 1" in khoi
    assert "PER FRAME" in khoi


# ------------------------------- qua API ----------------------------------- #
def _khung(mau):
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), mau).save(buf, "JPEG")
    return buf.getvalue()


def _gui_video(he, so_khung=4, thoi_luong=4.0, cau_hoi="Trong video có mấy con chó?"):  # noqa: F811
    files = [("video_frames", (f"k{i}.jpg", _khung((i * 40, 80, 80)), "image/jpeg")) for i in range(so_khung)]
    data = {"question": cau_hoi, "video_times": json.dumps(list(range(so_khung))), "video_duration": str(thoi_luong)}
    return he.client.post("/api/ask", data=data, files=files, headers=he.headers)


def test_api_video_tra_dong_thoi_gian(he, monkeypatch):  # noqa: F811
    monkeypatch.setattr("app.agents.vision_agent.tools.default_detector", _detector_theo_thu_tu())
    he.model.kich_ban(AIMessage(content="Nhiều nhất 3 con chó cùng lúc, lúc 2 giây."))
    r = _gui_video(he)
    assert r.status_code == 200, r.text
    v = r.json()["video"]
    assert len(v["frames"]) == 4 and len(v["thumbs"]) == 4 and v["image_size"] == [64, 48]
    assert v["classes"]["dog"]["max"] == 3 and v["duration"] == 4.0
    tin = he.model.tin_nguoi_dung_cuoi
    assert "[VIDEO]" in tin and "t=2s: chó 3" in tin
    assert "Video keyframes: IMG901 (t=0s), IMG902 (t=2s), IMG903 (t=3s)" in tin
    # lịch sử giữ ảnh nhỏ khung đầu cho bong bóng tin nhắn
    cid = r.json()["conversation_id"]
    assert he.store.lay_tin_nhan(cid)[0]["extras"]["video_thumb_base64"]


def test_api_video_qua_dai_hoac_qua_nhieu_khung(he):  # noqa: F811
    assert _gui_video(he, so_khung=9).status_code == 400
    assert _gui_video(he, so_khung=3, thoi_luong=30).status_code == 400


def test_xem_khung_video_mot_luot(monkeypatch, tmp_path):
    import app.agents.supervisor.tools as sup
    from app.agents.vision_agent.prompts import VIDEO_FRAMES_SYSTEM_PROMPT

    goi = []

    class _Llm:
        def invoke(self, m):
            goi.append(m)
            return AIMessage(content="Một con chó chạy qua sân.")

    monkeypatch.setattr("app.core.llm.get_llm", lambda role, *a, **k: _Llm())
    anh = {}
    for so in (901, 902, 903):
        p = tmp_path / f"{so}.jpg"
        Image.new("RGB", (8, 8)).save(p)
        anh[so] = str(p)
    tin = sup.vision_tool.invoke(
        {"type": "tool_call", "id": "t", "name": "vision_agent_tool",
         "args": {"query": "Video này về gì?", "image_path": "IMG901,IMG902,IMG903"}},
        config={"configurable": {"image_resolver": lambda so: anh.get(int(so))}},
    )
    assert tin.content == "Một con chó chạy qua sân."
    assert len(goi) == 1 and goi[0][0].content.startswith(VIDEO_FRAMES_SYSTEM_PROMPT)
    nhan = [p["text"] for p in goi[0][1].content if p.get("type") == "text"]
    assert "Khung 1:" in nhan and "Khung 3:" in nhan

"""Test phần giao diện báo "agent nào đã làm việc" (agents_used / agent_answers).

Lỗi đã gặp: supervisor gọi vision/research qua tool `vision_agent_tool` /
`research_agent_tool`, nhưng `_extract_agent_trace` chỉ tìm tên `transfer_to_*` của
thiết kế cũ nên luôn trả rỗng -> giao diện luôn hiện "Supervisor -> Tự trả lời" dù
vision đã chạy thật.

Không gọi mạng: supervisor là model giả theo kịch bản (dùng lại fixture của test
bộ nhớ ảnh), vision / research agent là đối tượng giả.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402

from tests.fakes import tool_call  # noqa: E402
from tests.test_image_memory import he  # noqa: E402,F401


class _ResearchGia:
    def __init__(self, tra_loi="Mi Quang va banh trang cuon thit heo."):
        self.tra_loi = tra_loi

    def invoke(self, state, config=None):
        return {"messages": [AIMessage(content=self.tra_loi)]}


def _kich_ban(he, *goi_tool):
    """Supervisor gọi lần lượt các tool đã cho (cùng một lượt), rồi trả lời."""
    he.model.kich_ban(
        AIMessage(
            content="",
            tool_calls=[
                tool_call(ten, args, call_id=f"c{i}") for i, (ten, args) in enumerate(goi_tool)
            ],
        ),
        AIMessage(content="Cau tra loi tong hop."),
    )


@pytest.fixture()
def tn(he, monkeypatch):  # noqa: F811
    import app.agents.supervisor.tools as sup

    monkeypatch.setattr(sup, "_research_agent_instance", _ResearchGia())
    return he


def test_goi_vision_thi_giao_dien_biet_vision_da_lam_viec(tn):
    tra_loi = tn.gui_anh("meo_cam", 1)

    assert tra_loi["agents_used"] == ["vision_agent"]
    # Câu trả lời riêng của vision agent đi kèm để giao diện hiện đúng thẻ của nó.
    assert tra_loi["agent_answers"] == {"vision_agent": "Day la anh meo_cam."}


def test_goi_research_thi_giao_dien_biet_research_da_lam_viec(tn):
    _kich_ban(tn, ("research_agent_tool", {"query": "Da Nang cuisine"}))

    tra_loi = tn.gui("Mon an noi tieng o Da Nang")

    assert tra_loi["agents_used"] == ["research_agent"]
    assert tra_loi["agent_answers"] == {"research_agent": "Mi Quang va banh trang cuon thit heo."}


def test_goi_ca_hai_thi_giu_dung_thu_tu_goi(tn):
    tn.gui_anh("meo_cam", 1)
    _kich_ban(
        tn,
        ("research_agent_tool", {"query": "Da Nang"}),
        ("vision_agent_tool", {"query": "Mo ta", "image_path": "IMG1"}),
    )

    tra_loi = tn.gui("Ke them ve anh 1 va noi do")

    assert tra_loi["agents_used"] == ["research_agent", "vision_agent"]


def test_goi_cung_mot_agent_hai_lan_chi_liet_ke_mot_lan(tn):
    tn.gui_anh("meo_cam", 1)
    tn.gui_anh("meo_den", 2)
    _kich_ban(
        tn,
        ("vision_agent_tool", {"query": "Mo ta", "image_path": "IMG1"}),
        ("vision_agent_tool", {"query": "Mo ta", "image_path": "IMG2"}),
    )

    tra_loi = tn.gui("So sanh anh 1 va anh 2")

    assert tra_loi["agents_used"] == ["vision_agent"]
    # Cùng một agent gọi hai lần: giữ câu trả lời của lần SAU (mới nhất).
    assert tra_loi["agent_answers"] == {"vision_agent": "Day la anh meo_den."}


def test_khong_goi_agent_nao_thi_la_tu_tra_loi(tn):
    tn.model.kich_ban(AIMessage(content="Chao ban."))

    tra_loi = tn.gui("Xin chao")

    assert tra_loi["agents_used"] == []
    assert "agent_answers" not in tra_loi


def test_agent_tra_loi_loi_van_duoc_liet_ke_nhung_khong_hien_cau_loi_tho(tn):
    # Câu hỏi về IMG9 không tồn tại -> vision_tool trả ERROR: IMAGE_NOT_IN_MEMORY.
    tn.gui_anh("meo_cam", 1)
    _kich_ban(tn, ("vision_agent_tool", {"query": "Mo ta", "image_path": "IMG9"}))

    tra_loi = tn.gui("Anh 9 co gi")

    assert tra_loi["agents_used"] == ["vision_agent"]
    # Dòng "ERROR: ..." không được hiện thành thẻ trả lời của agent; đã có warnings lo.
    assert "agent_answers" not in tra_loi
    assert tra_loi["warnings"]


def test_giao_dien_chi_duoc_nhan_ten_agent_da_biet(tn):
    # Tool lạ (ví dụ do model bịa) không được lọt vào danh sách agent của giao diện.
    from app.api import _extract_agent_trace

    ket_qua = {
        "messages": [
            ToolMessage(content="x", name="tool_la_hoac", tool_call_id="1"),
            ToolMessage(content="y", name="vision_agent_tool", tool_call_id="2"),
        ]
    }
    agents, tra_loi = _extract_agent_trace(ket_qua)

    assert agents == ["vision_agent"]
    assert tra_loi == {"vision_agent": "y"}


def test_van_nhan_ra_cach_dat_ten_cu_transfer_to(tn):
    """Giữ tương thích với kiểu handoff cũ (transfer_to_<agent>) cho ai còn dùng."""
    from app.api import _extract_agent_trace

    ket_qua = {
        "messages": [
            ToolMessage(content="ok", name="transfer_to_research_agent", tool_call_id="1"),
            AIMessage(content="noi dung nghien cuu", name="research_agent"),
        ]
    }
    agents, tra_loi = _extract_agent_trace(ket_qua)

    assert agents == ["research_agent"]
    assert tra_loi == {"research_agent": "noi dung nghien cuu"}


# ---------------- kết quả YOLO của agent con phải tới được giao diện ---------------- #
class _Tensor:
    """Giả một giá trị dạng tensor của ultralytics: box.cls[0], box.conf[0], box.xyxy[0]."""

    def __init__(self, gia_tri):
        self._v = gia_tri

    def __getitem__(self, i):
        return self._v


class _Hop:
    def __init__(self, ten_lop, do_tin_cay=0.9, toa_do=(1, 2, 30, 40)):
        self.cls, self.conf, self.xyxy = _Tensor(ten_lop), _Tensor(do_tin_cay), _Tensor(toa_do)


class _KetQuaYolo:
    names = {0: "cat", 1: "dog"}

    def __init__(self, *lop):
        self.boxes = [_Hop(c) for c in lop]


@pytest.fixture()
def vision_that(tn, monkeypatch):
    """Vision agent THẬT (ReAct + tool đếm), chỉ model và detector là giả."""
    import app.agents.supervisor.tools as sup
    from app.agents.vision_agent.agent import build_vision_agent
    from app.agents.vision_agent.tools import make_detect_and_count_tool
    from tests.fakes import FakeToolCallingModel

    def dung(loi_tool=None):
        def detector(ref):
            if loi_tool:
                raise ImportError("thieu goi")
            return [_KetQuaYolo(0, 0, 1)]

        model = FakeToolCallingModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[tool_call("detect_and_count_objects", {"text": "dem Image: x.png"})],
                ),
                AIMessage(content="Co 2 con meo va 1 con cho."),
            ]
        )
        agent = build_vision_agent(model=model, tools=[make_detect_and_count_tool(detector=detector)])
        monkeypatch.setattr(sup, "_vision_agent_instance", agent)

    return dung


def test_so_dem_cua_yolo_toi_duoc_giao_dien(tn, vision_that):
    tn.gui_anh("meo_cam", 1)  # gui anh bang vision gia truoc
    vision_that()  # roi doi sang vision that: kich ban cua no chi du cho MOT luot
    _kich_ban(tn, ("vision_agent_tool", {"query": "Co bao nhieu con vat?", "image_path": "IMG1"}))

    tra_loi = tn.gui("Co bao nhieu con vat?")

    assert tra_loi["counting"] == {"cat": 2, "dog": 1}
    assert tra_loi["agents_used"] == ["vision_agent"]


def test_loi_cua_tool_ben_trong_agent_con_hien_thanh_canh_bao(tn, vision_that):
    tn.gui_anh("meo_cam", 1)
    vision_that(loi_tool=True)
    _kich_ban(tn, ("vision_agent_tool", {"query": "Dem so con vat", "image_path": "IMG1"}))

    tra_loi = tn.gui("Dem so con vat")

    assert any("YOLO" in c or "dem vat the" in c.lower() for c in tra_loi["warnings"])

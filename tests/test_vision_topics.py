"""Test chủ đề ảnh của Vision Agent (app/agents/vision_agent/topics.py + phần nối).

Lời hứa của tính năng:
  - Ảnh có chủ đề (động vật, du lịch, món ăn, tài liệu, chung); lượt NHÌN ẢNH nhận
    lời dặn riêng của chủ đề đó, ngay từ lượt đầu tiên của ảnh mới.
  - Câu hỏi chỉ thẳng tới một chủ đề thì thắng chủ đề ghi trong hồ sơ ảnh.
  - Không biết chủ đề thì dùng chủ đề chung; VISION_TOPICS=false thì y như cũ.
  - Mỗi ảnh mới vẫn chỉ tốn MỘT lượt lập hồ sơ (chỉ đổi thời điểm: trước khi trả lời).

Không gọi mạng. Điều KHÔNG test được ở đây: model thật có tuân theo lời dặn hay
nhận đúng loài / địa điểm hay không — phải thử bằng key thật.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.runnables import RunnableLambda  # noqa: E402

from app.agents.vision_agent import topics  # noqa: E402
from app.agents.vision_agent.prompts import IMAGE_DESCRIBER_SYSTEM_PROMPT  # noqa: E402
from tests.fakes import FakeToolCallingModel, tool_call  # noqa: E402
from tests.test_image_memory import HO_SO, _ten_theo_mau, he  # noqa: E402,F401

CHU_DE_ANH = {
    "meo_cam": "animal",
    "meo_den": "animal",
    "cho_trang": "travel",
    "cho_nau": "food",
    "cho_xam": "document",
}


# ------------------------------ topics.py --------------------------------- #
def test_cac_chu_de_co_san_va_chung_la_du_phong():
    assert topics.CHU_DE_IDS == ("animal", "travel", "food", "document", "general")
    assert topics.CHU_DE[topics.CHU_DE_CHUNG].loi_dan == ""
    for c in topics.CHU_DE.values():
        if c.id != topics.CHU_DE_CHUNG:
            assert c.loi_dan.startswith("TOPIC FOCUS"), c.id
            assert c.tu_khoa, c.id


@pytest.mark.parametrize(
    "gia_tri, mong_doi",
    [("animal", "animal"), ("  Travel ", "travel"), ("GENERAL", "general"),
     ("xyz", None), ("", None), (None, None), (3, None)],
)
def test_chu_de_hop_le(gia_tri, mong_doi):
    assert topics.chu_de_hop_le(gia_tri) == mong_doi


@pytest.mark.parametrize(
    "cau_hoi, mong_doi",
    [
        ("Đây là con gì?", "animal"),
        ("day la con gi vay", "animal"),
        ("Con chó này giống gì?", "animal"),
        # "chó này" và "chỗ này" cùng thành "cho nay" khi bỏ dấu: không được ép du lịch.
        ("Chó này dễ thương quá", None),
        ("Chỗ này thì sao", None),
        ("Đây là ở đâu?", "travel"),
        ("day la o dau", "travel"),
        ("Địa điểm này có gì hay?", "travel"),
        ("Món gì đây?", "food"),
        ("Nguyên liệu của món này", "food"),
        ("Đọc chữ trên ảnh giúp mình", "document"),
        ("Chép lại hóa đơn này", "document"),
        # Không có tín hiệu rõ -> không ép chủ đề.
        ("Mô tả ảnh này", None),
        ("Con mèo ở đâu trong ảnh?", None),
        ("", None),
        # Hai chủ đề cùng khớp -> mơ hồ -> không ép.
        ("Đọc chữ trên biển ở địa điểm này", None),
        # Khớp theo TỪ, không khớp một phần của từ khác.
        ("Họ nói 'ocrea' là gì", None),
    ],
)
def test_chu_de_tu_cau_hoi(cau_hoi, mong_doi):
    assert topics.chu_de_tu_cau_hoi(cau_hoi) == mong_doi


def test_thu_tu_uu_tien_cau_hoi_roi_ho_so_roi_chung():
    # Ảnh con chó, nhưng hỏi đọc chữ trên áo -> câu hỏi thắng.
    assert topics.chon_chu_de("Đọc chữ trên áo nó", "animal") == "document"
    # Câu hỏi không nói gì thêm -> theo hồ sơ ảnh.
    assert topics.chon_chu_de("Kể thêm đi", "travel") == "travel"
    # Không biết gì -> chung. Hồ sơ ghi chủ đề lạ cũng thành chung.
    assert topics.chon_chu_de("Kể thêm đi", None) == "general"
    assert topics.chon_chu_de("Kể thêm đi", "xyz") == "general"


def test_dung_chu_de_tu_tra_ve_nhu_cu_khi_ra_khoi_khoi_with():
    assert topics.chu_de_hien_tai() is None and topics.loi_dan_hien_tai() == ""
    with topics.dung_chu_de("animal"):
        assert topics.chu_de_hien_tai() == "animal"
        assert "animals" in topics.loi_dan_hien_tai()
        with topics.dung_chu_de("food"):
            assert topics.chu_de_hien_tai() == "food"
        assert topics.chu_de_hien_tai() == "animal"
    assert topics.chu_de_hien_tai() is None
    # Lỗi bên trong khối with cũng không để lại chủ đề dính lại.
    with pytest.raises(RuntimeError):
        with topics.dung_chu_de("travel"):
            raise RuntimeError("boom")
    assert topics.chu_de_hien_tai() is None
    # Chủ đề lạ bị bỏ, không làm hỏng gì.
    with topics.dung_chu_de("xyz"):
        assert topics.chu_de_hien_tai() is None


# ------------- lời dặn thật sự tới lượt nhìn ảnh (qua LangGraph) ------------ #
class _LlmNhinAnh:
    """Đứng thay model "describe": ghi lại system prompt của lượt nhìn ảnh."""

    def __init__(self):
        self.system_prompts = []

    def with_structured_output(self, schema, **kwargs):
        def _goi(messages):
            self.system_prompts.append(messages[0].content)
            return schema(image_description="mo ta gia")

        return RunnableLambda(_goi)


def _chay_vision_agent_that(tmp_path, chu_de):
    """Chạy Vision Agent THẬT (ReAct + ToolNode của LangGraph), chỉ model là giả."""
    from PIL import Image

    from app.agents.vision_agent.agent import build_vision_agent
    from app.agents.vision_agent.tools import make_image_describer_tool

    anh = tmp_path / "a.png"
    Image.new("RGB", (32, 32), (200, 10, 10)).save(anh)
    llm = _LlmNhinAnh()
    model = FakeToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[tool_call("image_describer", {"text": f"Mo ta Image: {anh}"})],
            ),
            AIMessage(content="xong"),
        ]
    )
    agent = build_vision_agent(
        model=model, tools=[make_image_describer_tool(vision_llm=llm, return_direct=False)]
    )
    with topics.dung_chu_de(chu_de):
        agent.invoke({"messages": [("user", f"Mo ta anh Image: {anh}")]})
    return llm.system_prompts


def test_loi_dan_chu_de_toi_duoc_system_prompt_cua_luot_nhin_anh(tmp_path):
    prompts = _chay_vision_agent_that(tmp_path, "animal")

    assert len(prompts) == 1
    assert prompts[0].startswith(IMAGE_DESCRIBER_SYSTEM_PROMPT)  # phần cũ còn nguyên
    assert topics.CHU_DE["animal"].loi_dan in prompts[0]


@pytest.mark.parametrize("chu_de", [None, "general"])
def test_khong_co_chu_de_thi_system_prompt_y_nhu_cu(tmp_path, chu_de):
    assert _chay_vision_agent_that(tmp_path, chu_de) == [IMAGE_DESCRIBER_SYSTEM_PROMPT]


# ------------------------- nối vào API + vision_tool ------------------------ #
@pytest.fixture()
def tn(he, monkeypatch):  # noqa: F811
    """`he` của test bộ nhớ ảnh + hồ sơ có chủ đề + vision giả ghi lại chủ đề nó thấy."""
    he.so_lan_lap_ho_so = 0

    def ho_so_co_chu_de(path):
        he.so_lan_lap_ho_so += 1
        ten = _ten_theo_mau(path)
        return {**HO_SO[ten], "topic": CHU_DE_ANH[ten]}

    monkeypatch.setattr(he.mem, "_goi_llm_ho_so", ho_so_co_chu_de)

    he.chu_de_vision = []
    goc = he.vision.invoke

    def ghi_chu_de(state, config=None):
        he.chu_de_vision.append(topics.chu_de_hien_tai())
        return goc(state, config)

    monkeypatch.setattr(he.vision, "invoke", ghi_chu_de)

    def hoi(cau_hoi_supervisor: str, so: int, cau_hoi_user: str):
        he.model.kich_ban(
            AIMessage(
                content="",
                tool_calls=[
                    tool_call(
                        "vision_agent_tool",
                        {"query": cau_hoi_supervisor, "image_path": f"IMG{so}"},
                    )
                ],
            ),
            AIMessage(content="ok"),
        )
        return he.gui(cau_hoi_user)

    he.hoi = hoi
    return he


def test_anh_moi_co_chu_de_ngay_o_luot_dau_tien(tn):
    tn.gui_anh("meo_cam", 1)

    assert tn.chu_de_vision == ["animal"]
    # Mỗi ảnh mới vẫn chỉ tốn đúng MỘT lượt lập hồ sơ (không lặp lại sau khi trả lời).
    assert tn.so_lan_lap_ho_so == 1
    # Chủ đề được lưu vào hồ sơ ảnh trong database.
    assert tn.store.danh_sach_anh(tn.cid, 20)[0]["profile"]["topic"] == "animal"


def test_danh_muc_cho_supervisor_ghi_chu_de(tn):
    tn.gui_anh("meo_cam", 1)
    tn.gui_anh("cho_trang", 2)
    tn.hoi("Mo ta them", 1, "Cho minh biet them")

    dong = {d.split(" | ")[0]: d for d in tn.model.tin_nguoi_dung_cuoi.splitlines() if d.startswith("IMG")}
    assert "topic: animal" in dong["IMG1"]
    assert "topic: travel" in dong["IMG2"]


def test_hoi_lai_anh_cu_dung_chu_de_da_luu(tn):
    tn.gui_anh("meo_cam", 1)
    tn.gui_anh("cho_trang", 2)
    tn.chu_de_vision.clear()

    tn.hoi("Mo ta them", 2, "Kể thêm về ảnh 2")
    tn.hoi("Mo ta them", 1, "Kể thêm về ảnh 1")

    assert tn.chu_de_vision == ["travel", "animal"]


def test_cau_hoi_chi_thang_chu_de_khac_thang_ho_so_anh(tn):
    tn.gui_anh("meo_cam", 1)  # hồ sơ: animal
    tn.chu_de_vision.clear()

    tn.hoi("Doc chu tren ao con meo", 1, "Đọc chữ trên áo con mèo")

    assert tn.chu_de_vision == ["document"]


def test_ho_so_khong_co_chu_de_thi_dung_chung(tn, monkeypatch):
    monkeypatch.setattr(
        tn.mem, "_goi_llm_ho_so", lambda path: {**HO_SO[_ten_theo_mau(path)], "topic": "xyz"}
    )
    tn.gui_anh("meo_cam", 1)

    assert tn.chu_de_vision == ["general"]
    assert "topic" not in tn.store.danh_sach_anh(tn.cid, 20)[0]["profile"]


def test_lap_ho_so_hong_van_tra_loi_duoc(tn, monkeypatch):
    def hong(path):
        raise RuntimeError("het han muc")

    monkeypatch.setattr(tn.mem, "_goi_llm_ho_so", hong)
    tra_loi = tn.gui_anh("meo_cam", 1)

    assert tra_loi["image_no"] == 1
    assert tn.chu_de_vision == ["general"]


def test_khach_vang_lai_chu_de_chi_theo_cau_hoi(tn, monkeypatch):
    tn.model.kich_ban(
        AIMessage(
            content="",
            tool_calls=[
                tool_call(
                    "vision_agent_tool",
                    {"query": "Day la con gi", "image_path": "unused"},
                )
            ],
        ),
        AIMessage(content="ok"),
    )
    # Khách: không header -> không bộ nhớ ảnh, ảnh đi theo đường dẫn như cũ.
    from tests.test_image_memory import _anh

    def vision_khong_doc_file(state, config=None):
        tn.chu_de_vision.append(topics.chu_de_hien_tai())
        return {"messages": [AIMessage(content="ok")]}

    monkeypatch.setattr(tn.vision, "invoke", vision_khong_doc_file)

    r = tn.client.post(
        "/api/ask",
        data={"question": "Day la con gi"},
        files={"file": ("a.png", _anh("meo_cam"), "image/png")},
    )
    assert r.status_code == 200, r.text
    assert tn.chu_de_vision == ["animal"]
    assert tn.so_lan_lap_ho_so == 0


@pytest.mark.parametrize("he", [{"VISION_TOPICS": "false"}], indirect=True)
def test_tat_vision_topics_thi_chay_y_nhu_cu(tn):
    tn.gui_anh("meo_cam", 1)
    tn.chu_de_vision.clear()
    tn.hoi("Doc chu tren ao", 1, "Đọc chữ trên áo")

    assert tn.chu_de_vision and set(tn.chu_de_vision) == {None}
    # Hồ sơ vẫn được lập (sau khi trả lời) đúng một lần cho ảnh mới.
    assert tn.so_lan_lap_ho_so == 1

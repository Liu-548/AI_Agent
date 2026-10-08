"""Test bộ nhớ ảnh theo hội thoại (app/image_memory.py + phần liên quan).

Lời hứa của tính năng:
  - Gửi nhiều ảnh rồi quay lại hỏi một ảnh cũ thì ĐÚNG ảnh đó được đưa cho vision
    agent, kể cả khi ảnh đã trôi khỏi HISTORY_MAX_TURNS lượt gần nhất.
  - File ảnh trên đĩa bị dọn (24 giờ, server restart) thì dựng lại được từ database.
  - Mỗi hội thoại chỉ nhớ IMAGE_MEMORY_MAX ảnh gần nhất.
  - Khách vãng lai không có bộ nhớ ảnh, hành vi y như cũ.

Không gọi mạng, không cần API key: supervisor chạy bằng model giả theo kịch bản,
vision agent là một đối tượng giả ghi lại câu hỏi nó nhận được.

Điều KHÔNG test được ở đây: việc model thật có chọn đúng ảnh từ lời mô tả ("con
mèo cam") hay không — đó là hành vi của LLM, phải thử bằng key thật.
"""

from __future__ import annotations

import importlib
import io
import re
from typing import Any, List

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from PIL import Image  # noqa: E402

from tests.fakes import FakeToolCallingModel, tool_call  # noqa: E402

CLIENT_ID = "123456789-test.apps.googleusercontent.com"
BI_MAT = "bi_mat_test_" + "0123456789abcdef"
A = {"sub": "sub_A", "email": "a@gmail.com", "name": "Ban A", "picture": ""}

# Mỗi ảnh test là một màu đặc -> nhìn pixel là biết đang cầm ảnh nào.
MAU = {
    "meo_cam": (240, 140, 20),
    "meo_den": (20, 20, 20),
    "cho_trang": (245, 245, 245),
    "cho_nau": (120, 70, 30),
    "cho_xam": (128, 128, 128),
}
HO_SO = {
    "meo_cam": {"subject": "mèo", "count": 1, "colors": "cam", "scene": "trên sofa"},
    "meo_den": {"subject": "mèo", "count": 2, "colors": "đen", "scene": "ngoài sân"},
    "cho_trang": {"subject": "chó", "count": 1, "colors": "trắng"},
    "cho_nau": {"subject": "chó", "count": 3, "colors": "nâu"},
    "cho_xam": {"subject": "chó", "count": 1, "colors": "xám"},
}


def _anh(ten: str, kich_thuoc=(64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", kich_thuoc, MAU[ten]).save(buf, "PNG")
    return buf.getvalue()


def _ten_theo_mau(path) -> str:
    with Image.open(path) as im:
        diem = im.convert("RGB").getpixel((2, 2))
    return min(MAU, key=lambda t: sum(abs(a - b) for a, b in zip(MAU[t], diem)))


class _ModelGhiLai(FakeToolCallingModel):
    """Model giả phát kịch bản, đồng thời ghi lại mọi tin nhắn nó nhận được."""

    da_nhan: List[Any] = []

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.da_nhan.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def kich_ban(self, *tra_loi: AIMessage) -> None:
        self.responses = list(tra_loi)
        self._cursor = 0
        self.da_nhan.clear()

    @property
    def tin_nguoi_dung_cuoi(self) -> str:
        """Tin nhắn người dùng mới nhất mà supervisor nhìn thấy ở lượt gọi đầu."""
        nguoi_dung = [m for m in self.da_nhan[0] if m.type == "human"]
        return nguoi_dung[-1].content

    @property
    def toan_bo_lan_goi_dau(self) -> str:
        return "\n".join(str(m.content) for m in self.da_nhan[0])


class _VisionGia:
    """Đứng thay vision agent: ghi lại câu hỏi, trả lời theo màu ảnh nó được đưa."""

    def __init__(self):
        self.cau_hoi: List[str] = []

    def invoke(self, state, config=None):
        cau = state["messages"][0][1]
        self.cau_hoi.append(cau)
        khop = re.search(r"Image: (\S.*)$", cau)
        ten = _ten_theo_mau(khop.group(1).strip()) if khop else "?"
        return {"messages": [AIMessage(content=f"Day la anh {ten}.")]}

    @property
    def anh_cuoi(self) -> str:
        """Tên (theo màu) của ảnh mà lần gọi vision gần nhất thực sự nhận được."""
        duong_dan = re.search(r"Image: (\S.*)$", self.cau_hoi[-1]).group(1).strip()
        return _ten_theo_mau(duong_dan)

    @property
    def duong_dan_cuoi(self) -> str:
        return re.search(r"Image: (\S.*)$", self.cau_hoi[-1]).group(1).strip()


@pytest.fixture()
def he(monkeypatch, tmp_path, request):
    """API thật + supervisor thật (model giả) + vision agent giả + SQLite tạm.

    Muốn đổi biến môi trường cho một test: tham số hoá gián tiếp, ví dụ
    `@pytest.mark.parametrize("he", [{"IMAGE_MEMORY_MAX": "3"}], indirect=True)`.
    Phải đặt TRƯỚC khi reload config, vì `settings` chỉ đọc env một lần lúc import.
    """
    # Mặc định TẮT đường nhìn ảnh nhanh: các test ở đây kiểm tra việc chọn ảnh qua
    # vision agent giả, và đường nhanh sẽ đi gọi model thật (get_llm). Test đường
    # nhanh nằm ở test_vision_direct.py và tự bật lại bằng tham số.
    monkeypatch.setenv("VISION_DIRECT", "false")
    for ten, gia_tri in getattr(request, "param", {}).items():
        monkeypatch.setenv(ten, gia_tri)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'web.db'}")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("SESSION_SECRET", BI_MAT)

    import app.core.config as cfg

    importlib.reload(cfg)
    import app.store as store_mod
    import app.auth as auth_mod
    import app.image_memory as mem_mod
    import app.api as api_mod

    for mod in (store_mod, auth_mod, mem_mod, api_mod):
        importlib.reload(mod)

    import app.agents.supervisor.tools as sup_tools
    from app.agents.supervisor import build_supervisor

    monkeypatch.setattr(api_mod, "UPLOAD_DIR", tmp_path / "uploads")
    api_mod.UPLOAD_DIR.mkdir()

    vision = _VisionGia()
    monkeypatch.setattr(sup_tools, "_vision_agent_instance", vision)
    model = _ModelGhiLai()
    graph = build_supervisor(model=model)
    monkeypatch.setattr(api_mod, "_get_supervisor_graph", lambda: graph)
    # Hồ sơ ảnh: thay lượt gọi LLM bằng bảng tra theo màu.
    monkeypatch.setattr(mem_mod, "_goi_llm_ho_so", lambda path: HO_SO[_ten_theo_mau(path)])

    class He:
        pass

    he = He()
    he.api, he.store, he.mem, he.model, he.vision = api_mod, store_mod, mem_mod, model, vision
    he.client = TestClient(api_mod.app)
    he.headers = {"Authorization": "Bearer " + auth_mod.tao_phieu(A)}
    he.cid = ""

    def gui(cau_hoi: str, anh: str = "", headers=he.headers, **data):
        files = {"file": (f"{anh}.png", _anh(anh), "image/png")} if anh else None
        du_lieu = {"question": cau_hoi, **data}
        if he.cid and headers:
            du_lieu["conversation_id"] = he.cid
        r = he.client.post("/api/ask", data=du_lieu, files=files, headers=headers or {})
        assert r.status_code == 200, r.text
        if "conversation_id" in r.json():
            he.cid = r.json()["conversation_id"]
        return r.json()

    def gui_anh(ten: str, so: int):
        """Gửi một ảnh mới; supervisor (kịch bản) chuyển nó cho vision rồi trả lời."""
        model.kich_ban(
            AIMessage(
                content="",
                tool_calls=[
                    tool_call(
                        "vision_agent_tool",
                        {"query": "Mo ta anh", "image_path": f"IMG{so}"},
                        call_id=f"c{so}",
                    )
                ],
            ),
            AIMessage(content=f"Da xem anh {ten}."),
        )
        return gui(f"Anh nay la gi? ({ten})", anh=ten)

    def hoi_anh_cu(cau_hoi: str, so: int):
        model.kich_ban(
            AIMessage(
                content="",
                tool_calls=[
                    tool_call(
                        "vision_agent_tool",
                        {"query": cau_hoi, "image_path": f"IMG{so}"},
                        call_id=f"q{so}",
                    )
                ],
            ),
            AIMessage(content="Tra loi ve anh cu."),
        )
        return gui(cau_hoi)

    he.gui, he.gui_anh, he.hoi_anh_cu = gui, gui_anh, hoi_anh_cu
    return he


THU_TU = ["meo_cam", "cho_trang", "meo_den", "cho_nau", "cho_xam"]


def _gui_nam_anh(he):
    for i, ten in enumerate(THU_TU, start=1):
        assert he.gui_anh(ten, i)["image_no"] == i


# ------------------------------ ca chính ---------------------------------- #
def test_anh_moi_duoc_dua_dung_cho_vision_va_duoc_danh_so(he):
    tra_loi = he.gui_anh("meo_cam", 1)

    assert tra_loi["image_no"] == 1
    assert he.vision.anh_cuoi == "meo_cam"
    # Supervisor thấy bí danh, không thấy đường dẫn file trên server.
    assert "Image: IMG1" in he.model.tin_nguoi_dung_cuoi
    assert str(he.api.UPLOAD_DIR) not in he.model.tin_nguoi_dung_cuoi


def test_hai_meo_ba_cho_quay_lai_hoi_dung_anh_cu(he):
    """Ca của người dùng: 2 ảnh mèo + 3 ảnh chó, rồi quay lại hỏi từng ảnh cũ."""
    _gui_nam_anh(he)

    he.hoi_anh_cu("Con meo cam mau gi?", 1)
    assert he.vision.anh_cuoi == "meo_cam"

    he.hoi_anh_cu("Dem lai so cho trong anh cho nau", 4)
    assert he.vision.anh_cuoi == "cho_nau"

    he.hoi_anh_cu("Con hai con meo den thi sao?", 3)
    assert he.vision.anh_cuoi == "meo_den"


def test_danh_muc_co_ho_so_de_phan_biet_anh_cung_loai(he):
    _gui_nam_anh(he)
    he.hoi_anh_cu("Con meo cam mau gi?", 1)

    khoi = he.model.tin_nguoi_dung_cuoi
    assert khoi.startswith("[IMAGE MEMORY]")
    dong = {d.split(" | ")[0]: d for d in khoi.splitlines() if d.startswith("IMG")}
    assert list(dong) == ["IMG1", "IMG2", "IMG3", "IMG4", "IMG5"]
    # Hai ảnh mèo phải khác nhau ở màu / số lượng / bối cảnh.
    assert "subject: mèo" in dong["IMG1"] and "colors: cam" in dong["IMG1"]
    assert "subject: mèo" in dong["IMG3"] and "colors: đen" in dong["IMG3"]
    assert "count: 2" in dong["IMG3"] and "scene: ngoài sân" in dong["IMG3"]
    assert "subject: chó" in dong["IMG4"] and "count: 3" in dong["IMG4"]
    # Câu hỏi thật của người dùng nằm SAU khối danh mục, không bị trộn vào.
    assert khoi.rstrip().endswith("Con meo cam mau gi?")


def test_anh_dau_van_goi_lai_duoc_khi_da_troi_khoi_lich_su(he):
    """HISTORY_MAX_TURNS = 6: sau 8 lượt chữ, tin nhắn kèm ảnh 1 không còn được
    gửi lại, nhưng danh mục ảnh vẫn có nó."""
    he.gui_anh("meo_cam", 1)
    for i in range(8):
        he.model.kich_ban(AIMessage(content=f"Tra loi {i}"))
        he.gui(f"Cau hoi chu so {i}")

    he.hoi_anh_cu("Quay lai anh con meo luc dau", 1)

    assert "(meo_cam)" not in he.model.toan_bo_lan_goi_dau  # tin nhắn gốc đã trôi
    assert "IMG1 | subject: mèo" in he.model.tin_nguoi_dung_cuoi
    assert he.vision.anh_cuoi == "meo_cam"


def test_file_bi_don_thi_dung_lai_tu_database(he):
    """Giả lập bỏ 2-3 ngày / server restart: mọi file ảnh tạm biến mất."""
    _gui_nam_anh(he)
    for f in he.api.UPLOAD_DIR.glob("*"):
        f.unlink()

    he.hoi_anh_cu("Con meo den dang lam gi?", 3)

    assert he.vision.anh_cuoi == "meo_den"
    # Chỉ ảnh được hỏi mới bị dựng lại, không phải cả 5.
    assert len(list(he.api.UPLOAD_DIR.glob("*"))) == 1


def test_ban_luu_trong_database_duoc_thu_nho(he):
    he.model.kich_ban(AIMessage(content="ok"))
    files = {"file": ("to.png", _anh("cho_nau", (3000, 2000)), "image/png")}
    r = he.client.post("/api/ask", data={"question": "anh to"}, files=files, headers=he.headers)
    cid = r.json()["conversation_id"]

    du_lieu = he.store.lay_du_lieu_anh(cid, 1)
    with Image.open(io.BytesIO(du_lieu)) as im:
        assert max(im.size) == he.mem.CANH_DAI_LUU_PX
        assert im.format == "JPEG"


def test_hoi_lai_anh_cu_thi_ghi_them_dieu_da_biet(he):
    _gui_nam_anh(he)
    he.hoi_anh_cu("Con meo cam mau gi?", 1)

    ho_so = he.store.danh_sach_anh(he.cid)[0]["profile"]
    assert ho_so["subject"] == "mèo"
    assert "Day la anh meo_cam." in ho_so["notes"]


def test_tin_nhan_cu_trong_lich_su_mang_bi_danh_anh(he):
    he.gui_anh("meo_cam", 1)
    he.model.kich_ban(AIMessage(content="ok"))
    he.gui("Cam on")

    lan_goi = he.model.da_nhan[0]
    cu = [m.content for m in lan_goi if m.type == "human"][0]
    assert cu.endswith("Image: IMG1")


# ------------------------------ giới hạn ---------------------------------- #
@pytest.mark.parametrize("he", [{"IMAGE_MEMORY_MAX": "3"}], indirect=True)
def test_chi_nho_so_anh_gan_nhat_theo_gioi_han(he):
    for i, ten in enumerate(THU_TU[:4], start=1):
        he.gui_anh(ten, i)

    con_nho = he.store.danh_sach_anh(he.cid, 3)
    assert [a["stt"] for a in con_nho] == [2, 3, 4]
    assert he.store.lay_du_lieu_anh(he.cid, 1) is None  # bản ảnh cũ nhất đã bị xoá
    assert he.store.lay_du_lieu_anh(he.cid, 2) is not None

    # Supervisor lỡ gọi ảnh đã hết được nhớ -> lỗi rõ ràng, không đoán ảnh khác.
    so_lan_goi_vision = len(he.vision.cau_hoi)
    tra_loi = he.hoi_anh_cu("Anh dau tien", 1)
    assert len(he.vision.cau_hoi) == so_lan_goi_vision
    assert any("bo nho" in c for c in tra_loi.get("warnings", []))
    assert "IMG1" not in he.model.tin_nguoi_dung_cuoi.split("[END IMAGE MEMORY]")[0]


def test_xoa_hoi_thoai_thi_xoa_luon_anh(he):
    he.gui_anh("meo_cam", 1)
    cid = he.cid
    assert he.client.delete(f"/api/conversations/{cid}", headers=he.headers).status_code == 200
    assert he.store.danh_sach_anh(cid) == []
    assert he.store.lay_du_lieu_anh(cid, 1) is None


def test_moi_hoi_thoai_danh_so_anh_rieng(he):
    he.gui_anh("meo_cam", 1)
    he.cid = ""
    assert he.gui_anh("cho_nau", 1)["image_no"] == 1


# ------------------------------ khách ------------------------------------- #
def test_khach_khong_co_bo_nho_anh_va_van_dung_duong_dan(he):
    he.model.kich_ban(AIMessage(content="ok"))
    tra_loi = he.gui("Anh gi day?", anh="meo_cam", headers=None)

    assert "image_no" not in tra_loi and "conversation_id" not in tra_loi
    tin = he.model.tin_nguoi_dung_cuoi
    assert "[IMAGE MEMORY]" not in tin
    assert str(he.api.UPLOAD_DIR) in tin


# ------------------------- hồ sơ ảnh: đường lùi ---------------------------- #
def test_ho_so_van_co_khi_luot_goi_llm_hong(he, monkeypatch):
    def hong(path):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(he.mem, "_goi_llm_ho_so", hong)
    he.gui_anh("meo_cam", 1)

    ho_so = he.store.danh_sach_anh(he.cid)[0]["profile"]
    assert "subject" not in ho_so
    assert ho_so["notes"] == ["Day la anh meo_cam."]


@pytest.mark.parametrize("he", [{"IMAGE_PROFILE_LLM": "false"}], indirect=True)
def test_tat_image_profile_llm_thi_khong_goi_model(he, monkeypatch):
    def khong_duoc_goi(path):
        raise AssertionError("IMAGE_PROFILE_LLM=false ma van goi model")

    monkeypatch.setattr(he.mem, "_goi_llm_ho_so", khong_duoc_goi)
    he.gui_anh("meo_cam", 1)
    assert he.store.danh_sach_anh(he.cid)[0]["profile"]["notes"]


def test_ghi_chu_chi_giu_vai_cai_gan_nhat(he):
    ho_so = {}
    for i in range(6):
        ho_so = he.mem.them_ghi_chu(ho_so, f"ghi chu {i}")
    assert ho_so["notes"] == ["ghi chu 3", "ghi chu 4", "ghi chu 5"]
    # Chuỗi lỗi của tool không phải là "điều đã biết" về ảnh.
    assert he.mem.them_ghi_chu({}, "ERROR: VISION_LLM_FAILED | x") == {}


def test_lam_sach_ho_so_bo_truong_la(he):
    sach = he.mem.lam_sach_ho_so(
        {"subject": " mèo ", "count": 2, "colors": None, "bay_ba": "x", "scene": "null"}
    )
    assert sach == {"subject": "mèo", "count": "2"}


# ------------------------- tool vision của supervisor ---------------------- #
def test_giai_bi_danh_anh():
    from app.agents.supervisor.tools import giai_bi_danh_anh

    bang = {3: "/tmp/ba.jpg"}
    config = {"configurable": {"image_resolver": bang.get}}

    for cach_viet in ("IMG3", "img 3", "IMG#3", "3", "#3", "Ảnh 3", "anh 3"):
        assert giai_bi_danh_anh("dem", cach_viet, config) == ("/tmp/ba.jpg", None)
    # Bí danh nằm trong câu hỏi, không truyền image_path.
    assert giai_bi_danh_anh("dem cho trong IMG3", None, config) == ("/tmp/ba.jpg", None)
    # Đường dẫn / URL thật đi qua nguyên vẹn.
    assert giai_bi_danh_anh("dem", "C:\\x\\cho.jpg", config) == ("C:\\x\\cho.jpg", None)
    assert giai_bi_danh_anh("dem", "https://a.b/c.png", config) == ("https://a.b/c.png", None)
    # Không có bộ giải (CLI, khách) -> hành vi cũ.
    assert giai_bi_danh_anh("dem", "IMG3", None) == ("IMG3", None)
    # Số không có trong bộ nhớ -> lỗi theo hợp đồng tool, không raise.
    duong_dan, loi = giai_bi_danh_anh("dem", "IMG9", config)
    assert duong_dan is None and loi.startswith("ERROR: IMAGE_NOT_IN_MEMORY |")


def test_prompt_supervisor_co_quy_tac_chon_anh():
    from app.agents.supervisor.prompts import SUPERVISOR_PROMPT_TEMPLATE as p

    assert "IMAGE MEMORY" in p and "clarifying question" in p
    assert "vision_agent_tool" in p and "`vision_tool`" not in p
    # Template vẫn format được (không có ngoặc nhọn lạc).
    assert "{agent_catalog}" in p and p.format(agent_catalog="x")

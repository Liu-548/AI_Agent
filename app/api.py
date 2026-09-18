"""HTTP API cho web UI - boc quanh cac agent con bang FastAPI.

Khong dong gi trong app/agents/** hay app/core/**: endpoint chi goi lai dung
nhung ham CLI (app/main.py) da dung - build_vision_agent(), graph.invoke(),
final_text(), tool_error contract, ...  Neu QUY_TAC_THIET_KE.md doi cach cac
ham do hoat dong thi file nay cung phai doi theo, khong tu y sua logic agent.

LUU TRU HOI THOAI (tang nay tu quan ly, agent khong biet gi ve no):
mot cau hoi khong con dung mot minh. /api/ask nhan them conversation_id, doc
lai vai luot gan nhat tu database (app/store.py) roi gui kem cho graph -> nguoi
dung bam vao hoi thoai cu hoi tiep thi agent van hieu "con ben trai" hay "bai
bao do" dang noi ve cai gi.

Chay thu (tu goc repo, sau khi da kich hoat .venv):

    pip install -r requirements.txt
    uvicorn app.api:app --reload --port 8000

Mo http://127.0.0.1:8000 de dung web UI, hoac /docs de test bang Swagger UI.
"""

from __future__ import annotations

import base64
import io
import json
import re
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app import auth, store
from app.core.config import settings
from app.core.pretty import message_text

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Mo ket noi database + tao bang ngay luc khoi dong.

    Lam o day thay vi doi request dau tien: neu chuoi DATABASE_URL sai thi log
    bao ngay luc deploy, khong phai doi den luc nguoi dung bam gui roi moi thay
    loi 500 kho hieu. Loi khong lam sap app - cac endpoint khong dung lich su
    (vd /api/vision) van chay duoc.
    """
    try:
        store.get_engine()
        print(f"[store] san sang: {settings.mo_ta_database()}")
    except Exception as exc:  # noqa: BLE001
        print(f"[store] KHONG ket noi duoc database: {exc}")
    yield


app = FastAPI(title="Visual Agentic AI - API", version="0.2.0", lifespan=lifespan)

# Web UI duoc chinh FastAPI phuc vu (xem endpoint "/" o cuoi file) nen thuc te
# la cung origin, khong can CORS. Van giu "*" de ai muon mo file HTML truc tiep
# tu o dia hay host frontend rieng van goi duoc.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8MB - tu choi truoc khi ton luot goi LLM
UPLOAD_DIR = Path(tempfile.gettempdir()) / "visual_agentic_ai_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Anh upload KHONG bi xoa ngay sau request nua: nguoi dung con hoi tiep ve dung
# buc anh do o luot sau. Doi lai phai tu don, neu khong o dia server day dan.
GIU_ANH_GIAY = 24 * 3600
# Anh thu nho luu kem tin nhan de mo lai hoi thoai cu van thay anh da gui.
THUMBNAIL_MAX_PX = 360

# Build agent DUNG MOT LAN cho ca tien trinh uvicorn, khong build lai moi
# request - YOLO/LLM client se duoc tai su dung giua cac request thay vi nap
# lai tu dau (dieu khong the co duoc voi CLI vi CLI thoat sau moi lan chay).
_vision_graph = None
_research_graph = None
_supervisor_graph = None


def _get_vision_graph():
    global _vision_graph
    if _vision_graph is None:
        from app.agents.vision_agent import build_vision_agent

        _vision_graph = build_vision_agent()
    return _vision_graph


def _get_research_graph():
    global _research_graph
    if _research_graph is None:
        from app.agents.research_agent import build_research_agent

        _research_graph = build_research_agent()
    return _research_graph


def _get_supervisor_graph():
    """Supervisor build_all_agents() ben trong no, KHONG dung chung cache
    _vision_graph/_research_graph o tren - hai bo nho doc lap, binh thuong,
    chi ton them mot lan build LLM client cho cac agent con cua supervisor."""
    global _supervisor_graph
    if _supervisor_graph is None:
        from app.agents.supervisor import build_supervisor

        _supervisor_graph = build_supervisor()
    return _supervisor_graph


# --------------------------------------------------------------------------- #
# Anh upload
# --------------------------------------------------------------------------- #
def _don_anh_cu() -> None:
    """Xoa anh qua han. Goi moi lan co upload moi - du de o dia khong phinh."""
    han = time.time() - GIU_ANH_GIAY
    for f in UPLOAD_DIR.glob("*"):
        try:
            if f.is_file() and f.stat().st_mtime < han:
                f.unlink(missing_ok=True)
        except OSError:
            pass  # file dang bi tien trinh khac giu - bo qua, lan sau don tiep


def _save_upload(file: UploadFile) -> Path:
    """Luu file upload vao thu muc tam, kiem tra duoi va dung luong truoc."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Dinh dang {ext or '(khong ro)'} khong duoc ho tro. "
            f"Chi nhan: {sorted(ALLOWED_EXTS)}",
        )

    _don_anh_cu()
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    size = 0
    with dest.open("wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"Anh vuot qua {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.",
                )
            out.write(chunk)
    return dest


def _thumbnail_base64(path: Path) -> str:
    """Anh thu nho dang base64 de luu kem tin nhan.

    Khong luu anh goc: mot anh dien thoai 4MB nhan doi thanh ~5.5MB base64,
    vai chuc cau hoi la day database mien phi. Ban thu nho ~20-40KB.
    """
    try:
        from PIL import Image

        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((THUMBNAIL_MAX_PX, THUMBNAIL_MAX_PX))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=72)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:  # noqa: BLE001 - thieu anh xem truoc khong dang lam hong request
        return ""


# --------------------------------------------------------------------------- #
# Doc ket qua graph
# --------------------------------------------------------------------------- #
def _final_answer(result: dict) -> str:
    """Cau tra loi cuoi cung tu ket qua graph.invoke().

    KHONG dung duoc app.core.pretty.final_text() o day: ham do doc chunk cua
    .stream() (dict {ten_node: {...}}), con .invoke() tra thang {"messages":
    [...]}} - dung nham se luon ra chuoi rong (da phat hien bang test tay
    truoc khi giao file nay).
    """
    messages = result.get("messages") if isinstance(result, dict) else None
    if not messages:
        return ""
    last = messages[-1]
    content = last.get("content") if isinstance(last, dict) else getattr(last, "content", None)
    return message_text(content)


def _collect_tool_outputs(result: dict) -> Dict[str, str]:
    """Gom noi dung ToolMessage theo ten tool - cung logic voi _gom_ket_qua_tool
    trong app/main.py, chi khac la lam viec tren ket qua .invoke() (dict) thay
    vi tung chunk cua .stream()."""
    out: Dict[str, str] = {}
    messages = result.get("messages") if isinstance(result, dict) else None
    for m in messages or []:
        get = m.get if isinstance(m, dict) else (lambda k, d=None: getattr(m, k, d))
        if get("type", None) != "tool":
            continue
        name = get("name", "") or ""
        if name:
            out[name] = message_text(get("content", None))
    return out


def _extract_vision_extras(tool_outputs: Dict[str, str], response: dict) -> None:
    """Doc ket qua cua detect_and_count_objects (neu co trong tool_outputs) va
    them counting/detections/annotated_image_base64 vao response, sua truc
    tiep tren dict truyen vao. Dung chung cho ca /api/vision va /api/ask (vi
    supervisor cung co the goi toi vision_agent)."""
    detect_raw = tool_outputs.get("detect_and_count_objects")
    if not detect_raw or detect_raw.startswith("ERROR:"):
        return
    try:
        payload = json.loads(detect_raw)
    except json.JSONDecodeError:
        return
    response["counting"] = payload.get("counting", {})
    response["detections"] = payload.get("detections", [])
    annotated = payload.get("annotated_image")
    if annotated and Path(annotated).exists():
        response["annotated_image_base64"] = base64.b64encode(
            Path(annotated).read_bytes()
        ).decode("ascii")
        Path(annotated).unlink(missing_ok=True)


def _extract_agent_trace(result: dict):
    """Doc trace cua Supervisor de biet: (1) agent con nao da duoc goi, theo
    dung thu tu; (2) cau tra loi rieng cua tung agent con truoc khi no
    "Transferring back to supervisor". Dung de UI hien thi dung con nao lam
    viec, thay vi chi thay 1 cau tra loi tong hop duy nhat."""
    KNOWN_AGENTS = {"research_agent", "vision_agent"}
    TRANSFER_BACK_TEXT = "Transferring back to supervisor"

    agents_used: list[str] = []
    agent_answers: Dict[str, str] = {}

    messages = result.get("messages") if isinstance(result, dict) else None
    for m in messages or []:
        get = m.get if isinstance(m, dict) else (lambda k, d=None: getattr(m, k, d))
        mtype = get("type", None)
        name = get("name", None) or ""

        if mtype == "tool" and name.startswith("transfer_to_"):
            agent_name = name[len("transfer_to_") :]
            if agent_name in KNOWN_AGENTS and agent_name not in agents_used:
                agents_used.append(agent_name)

        if mtype == "ai" and name in KNOWN_AGENTS:
            text = message_text(get("content", None)).strip()
            if text and text != TRANSFER_BACK_TEXT:
                agent_answers[name] = text

    return agents_used, agent_answers


# Ma loi -> cau tieng Viet nguoi dung cuoi doc hieu ngay, khong can biet ten tool.
# Dong bo voi ma loi that su duoc tra ve trong app/agents/*/tools.py.
_TEN_LOI_DE_HIEU = {
    "YOLO_NOT_INSTALLED": "Server chua cai thu vien dem vat the (YOLO)",
    "NO_IMAGE_REF": "Khong tim thay duong dan/URL anh trong cau hoi",
    "IMAGE_UNREADABLE": "Khong doc duoc anh (sai duong dan, URL hong, hoac khong phai file anh)",
    "YOLO_INFERENCE_FAILED": "Model dem vat the xu ly anh bi loi",
    "VISION_LLM_FAILED": "Model doc anh gap loi",
    "VISION_EMPTY": "Model doc anh khong tra ve noi dung",
    "ARXIV_UNAVAILABLE": "Khong tra cuu duoc arXiv luc nay",
    "WIKIPEDIA_UNAVAILABLE": "Khong tra cuu duoc Wikipedia luc nay",
    "EMPTY_QUERY": "Thieu noi dung de tim kiem",
}
_MA_LOI_RE = re.compile(r"^ERROR:\s*([A-Z_]+)\s*\|\s*(.*)$", re.DOTALL)


def _canh_bao_de_doc(ten_tool: str, text: str) -> str:
    """Doi 'ERROR: MA | chi tiet' (dinh dang noi bo cua tool_error) thanh cau
    nguoi dung cuoi doc hieu ngay tren giao dien, khong phai dan ky thuat vien.
    Khong doi GI trong contract cua tool (van la tool_error() nhu cu) - day chi
    la lop hien thi rieng cua API, giu nguyen o app/api.py."""
    khop = _MA_LOI_RE.match(text or "")
    if not khop:
        return f"{ten_tool}: {text}"
    ma, chi_tiet = khop.groups()
    tieu_de = _TEN_LOI_DE_HIEU.get(ma, ma)
    return f"{tieu_de}: {chi_tiet}" if chi_tiet else tieu_de


def _loi_ro_rang(exc: Exception) -> str:
    """Rut gon cac loi hay gap thanh cau tra ve doc duoc cho frontend, cung
    nhom loi voi _giai_thich_loi trong app/main.py nhung ngan hon vi day la
    JSON tra ve API chu khong phai text in ra console."""
    msg = str(exc)
    # 503/UNAVAILABLE/overloaded = may chu cua nha cung cap dang qua tai, KHONG
    # phai loi cua nguoi dung va cung khong phai het han muc. SDK cua Google da
    # tu thu lai 6 lan (1s -> 16s) truoc khi nem ra den day, nen khong retry
    # them o server nua: bao that ro va de nguoi dung bam "Thu lai" khi muon.
    if "503" in msg or "UNAVAILABLE" in msg or "overloaded" in msg.lower():
        return (
            "May chu cua model dang qua tai (bao loi 503). Day la su co tam thoi "
            "ben phia nha cung cap, khong phai loi cau hoi cua ban - bam Thu lai "
            "sau vai giay."
        )
    if "RESOURCE_EXHAUSTED" in msg or "rate_limit" in msg or "429" in msg:
        return "Da het han muc mien phi cua model hom nay. Thu lai sau hoac doi model trong .env."
    if "API key not valid" in msg or "API_KEY_INVALID" in msg or "invalid_api_key" in msg:
        return "API key khong hop le. Kiem tra GROQ_API_KEY / GEMINI_API_KEY trong .env."
    if "recursion" in msg.lower():
        return "Agent lap qua nhieu buoc (recursion limit). Thu cau hoi ro rang/ngan hon."
    return f"Loi khi chay agent: {msg}"


# --------------------------------------------------------------------------- #
# Lich su -> ngu canh cho graph
# --------------------------------------------------------------------------- #
def _lich_su_cho_graph(conversation_id: str) -> List[dict]:
    """Vai luot hoi-dap gan nhat, dang message de ghep vao dau graph.invoke().

    Day la thu lam nen "hoi tiep khong bi gian doan". Ba diem can luu y:

    1. CHI lay phan chu. Anh thu nho, so lieu dem, trace agent nam trong
       `extras` va bi bo lai - nhoi anh base64 vao lich su la cach nhanh nhat
       de no gioi han token va an loi 400 cua Groq.
    2. Duong dan anh cu duoc gan lai vao cau hoi NEU file con ton tai, de agent
       co the nhin lai dung buc anh do. File da bi don (hoac server vua restart)
       thi bo qua - agent van con phan mo ta chinh no viet o luot truoc.
    3. So luot bi chan boi HISTORY_MAX_TURNS. Moi luot gui lai lam tang token
       cho MOI lan goi LLM cua luot moi, khong phai chi mot lan.
    """
    so_luot = settings.history_max_turns
    if so_luot <= 0:
        return []

    tat_ca = store.lay_tin_nhan(conversation_id)
    gan_nhat = tat_ca[-(so_luot * 2) :]

    ket_qua: List[dict] = []
    for m in gan_nhat:
        noi_dung = (m.get("content") or "").strip()
        if not noi_dung:
            continue
        if m.get("role") == "user":
            duong_dan = (m.get("extras") or {}).get("image_path")
            if duong_dan and Path(duong_dan).exists():
                noi_dung = f"{noi_dung}\nImage: {duong_dan}"
        ket_qua.append({"role": m["role"], "content": noi_dung})
    return ket_qua


def _kiem_tra_user(user_id: str) -> str:
    uid = (user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="Thieu user_id.")
    return uid[:64]


def _lay_phieu(authorization: Optional[str]) -> str:
    """Tach phan phieu ra khoi header `Authorization: Bearer <phieu>`."""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def _danh_tinh_tuy_chon(authorization: Optional[str], user_id: str = "") -> str:
    """Ai dang goi? Tra ve chuoi RONG neu la khach chua dang nhap.

    Hai che do, quyet dinh boi cau hinh cua server chu KHONG phai boi client:

      - Da bat dang nhap (co GOOGLE_CLIENT_ID + SESSION_SECRET): danh tinh LUON
        lay tu phieu trong header Authorization. `user_id` client gui len bi bo
        qua hoan toan - neu tin no thi ai cung doc duoc lich su nguoi khac chi
        bang cach doi mot chuoi.
      - Chua bat dang nhap: giu nguyen kieu cu, moi trinh duyet mot ma ngau
        nhien. Nho vay ai trong nhom chua cau hinh OAuth van chay duoc local.

    Chuoi rong co nghia "khach vang lai": van hoi agent duoc, nhung khong co cho
    nao de luu lich su, va cung khong doc duoc lich su cua ai.
    """
    if not settings.dang_nhap_bat():
        return (user_id or "").strip()[:64]

    ruot = auth.doc_phieu(_lay_phieu(authorization))
    return str(ruot["sub"])[:64] if ruot else ""


def _danh_tinh(authorization: Optional[str], user_id: str = "") -> str:
    """Nhu tren nhung BAT BUOC phai co danh tinh.

    Dung cho cac endpoint dong vao mot hoi thoai co that (mo, doi ten, ghim,
    xoa) - nhung viec ma khach vang lai khong the lam vi ho khong so huu hoi
    thoai nao.
    """
    uid = _danh_tinh_tuy_chon(authorization, user_id)
    if not uid:
        if settings.dang_nhap_bat():
            raise HTTPException(status_code=401, detail="Can dang nhap lai.")
        raise HTTPException(status_code=400, detail="Thieu user_id.")
    return uid


def _bat_buoc_co_hoi_thoai(conversation_id: str, user_id: str) -> dict:
    hoi_thoai = store.lay_hoi_thoai(conversation_id, user_id)
    if hoi_thoai is None:
        raise HTTPException(status_code=404, detail="Khong tim thay hoi thoai.")
    return hoi_thoai


# --------------------------------------------------------------------------- #
# Endpoint - tien ich
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def config():
    """Vai tro -> provider/model, KHONG lo API key. Dung de debug tu Swagger/Postman."""
    return {"config": settings.mo_ta_cau_hinh()}


# --------------------------------------------------------------------------- #
# Endpoint - lich su hoi thoai
# --------------------------------------------------------------------------- #
@app.post("/api/auth/google")
def dang_nhap_google(credential: str = Form(..., description="ID token tu nut Google")):
    """Doi ID token cua Google lay phieu dang nhap cua he thong nay."""
    if not settings.dang_nhap_bat():
        raise HTTPException(status_code=400, detail="Server chua bat dang nhap Google.")
    try:
        ho_so = auth.xac_minh_google(credential)
    except auth.LoiDangNhap as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    store.luu_nguoi_dung(ho_so)
    return {"token": auth.tao_phieu(ho_so), "user": ho_so}


@app.get("/api/me")
def toi_la_ai(authorization: Optional[str] = Header(None)):
    """Trang web goi dau tien: can dang nhap khong, va dang la ai?

    Tra ve ca `client_id` de trang tu dung nut dang nhap - nho vay doi Client ID
    chi phai sua .env, khong phai sua lai HTML.
    """
    if not settings.dang_nhap_bat():
        return {"login_required": False, "client_id": "", "user": None}

    phieu = ""
    if authorization and authorization.lower().startswith("bearer "):
        phieu = authorization[7:].strip()
    ruot = auth.doc_phieu(phieu)
    nguoi_dung = None
    if ruot:
        nguoi_dung = {
            "sub": ruot["sub"],
            "email": ruot.get("email", ""),
            "name": ruot.get("name", ""),
            "picture": ruot.get("picture", ""),
        }
    return {
        "login_required": True,
        "client_id": settings.google_client_id,
        "user": nguoi_dung,
    }


@app.get("/api/conversations")
def list_conversations(user_id: str = "", authorization: Optional[str] = Header(None)):
    """Danh sach hoi thoai cua mot nguoi: ghim len truoc, roi toi moi nhat.

    Khach chua dang nhap khong co hoi thoai nao -> tra danh sach rong. Tra rong
    thay vi bao loi de giao dien cua khach khong phai hien mot thong bao do ma
    ho chang lam gi duoc.
    """
    uid = _danh_tinh_tuy_chon(authorization, user_id)
    if not uid:
        return {"conversations": []}
    return {"conversations": store.danh_sach_hoi_thoai(uid)}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    user_id: str = "",
    authorization: Optional[str] = Header(None),
):
    """Toan bo tin nhan cua mot hoi thoai - dung khi bam vao no o sidebar."""
    uid = _danh_tinh(authorization, user_id)
    hoi_thoai = _bat_buoc_co_hoi_thoai(conversation_id, uid)
    hoi_thoai["messages"] = store.lay_tin_nhan(conversation_id)
    return hoi_thoai


@app.patch("/api/conversations/{conversation_id}")
def update_conversation(
    conversation_id: str,
    user_id: str = Form(""),
    title: Optional[str] = Form(None),
    pinned: Optional[bool] = Form(None),
    authorization: Optional[str] = Header(None),
):
    """Doi ten hoac ghim/bo ghim mot hoi thoai."""
    uid = _danh_tinh(authorization, user_id)
    _bat_buoc_co_hoi_thoai(conversation_id, uid)
    if title is not None:
        ten = title.strip()
        if not ten:
            raise HTTPException(status_code=400, detail="Tieu de khong duoc de trong.")
        store.doi_ten_hoi_thoai(conversation_id, uid, ten)
    if pinned is not None:
        store.ghim_hoi_thoai(conversation_id, uid, pinned)
    return store.lay_hoi_thoai(conversation_id, uid)


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    user_id: str = "",
    authorization: Optional[str] = Header(None),
):
    uid = _danh_tinh(authorization, user_id)
    if not store.xoa_hoi_thoai(conversation_id, uid):
        raise HTTPException(status_code=404, detail="Khong tim thay hoi thoai.")
    return {"deleted": conversation_id}


# --------------------------------------------------------------------------- #
# Endpoint - chay agent
# --------------------------------------------------------------------------- #
@app.post("/api/vision")
def ask_vision(
    file: UploadFile = File(..., description="Anh PNG/JPG/JPEG/WEBP/BMP"),
    question: str = Form(
        "Describe this image and count the objects in it.",
        description="Cau hoi ve buc anh, vd 'Co may con cho trong anh?'",
    ),
):
    """Nhan 1 anh upload + 1 cau hoi -> chay thang vision_agent, tra JSON.

    Co y KHONG di qua supervisor de tiet kiem luot Groq + Gemini, va co y KHONG
    luu lich su - day la endpoint de debug rieng vision agent.

    Ham nay khai bao `def` (khong phai `async def`) CO CHU DICH: graph.invoke()
    va doc/ghi file la cac thao tac dong (blocking), FastAPI se tu chay no
    trong threadpool rieng thay vi chan luon vong lap su kien - neu doi sang
    `async def` ma khong await dung cho thi moi request khac se bi treo theo.
    """
    saved_path = _save_upload(file)
    try:
        graph = _get_vision_graph()
        message = f"{question}\nImage: {saved_path}"
        run_config = {"recursion_limit": settings.recursion_limit}

        result = graph.invoke(
            {"messages": [{"role": "user", "content": message}]}, config=run_config
        )
        answer = _final_answer(result)
        tool_outputs = _collect_tool_outputs(result)

        response: dict = {"answer": answer}
        # Tra anh da khoanh vung ve thang trong JSON (base64) thay vi mot duong
        # dan tren dia server - trinh duyet cua nguoi dung khac khong doc duoc
        # "C:/..." hay "/tmp/..." cua server.
        _extract_vision_extras(tool_outputs, response)

        warnings = [
            _canh_bao_de_doc(name, text)
            for name, text in tool_outputs.items()
            if text.startswith("ERROR:")
        ]
        if warnings:
            response["warnings"] = warnings

        return response
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - doi loi ky thuat thanh message doc duoc
        raise HTTPException(status_code=502, detail=_loi_ro_rang(exc)) from exc
    finally:
        saved_path.unlink(missing_ok=True)


@app.post("/api/research")
def ask_research(
    question: str = Form(..., description="Cau hoi tim kiem hoc thuat, vd 'rotary positional encoding'"),
):
    """Chay thang research_agent (arXiv + Wikipedia), khong qua supervisor -
    tiet kiem 2 luot dieu phoi cho moi cau hoi. Khong luu lich su."""
    try:
        graph = _get_research_graph()
        run_config = {"recursion_limit": settings.recursion_limit}
        result = graph.invoke(
            {"messages": [{"role": "user", "content": question}]}, config=run_config
        )
        answer = _final_answer(result)
        tool_outputs = _collect_tool_outputs(result)

        response: dict = {"answer": answer}
        warnings = [
            _canh_bao_de_doc(name, text)
            for name, text in tool_outputs.items()
            if text.startswith("ERROR:")
        ]
        if warnings:
            response["warnings"] = warnings
        return response
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=_loi_ro_rang(exc)) from exc


@app.post("/api/ask")
def ask_supervisor(
    question: str = Form(..., description="Cau hoi bat ky - supervisor tu chon agent con phu hop"),
    user_id: str = Form("", description="Id ngau nhien trinh duyet tu sinh, de tach lich su"),
    conversation_id: str = Form("", description="De trong = mo hoi thoai moi"),
    file: UploadFile = File(
        None, description="Anh (tuy chon) - chi can khi cau hoi lien quan toi hinh anh"
    ),
    authorization: Optional[str] = Header(None),
):
    """Di qua Supervisor, co nho ngu canh cua chinh hoi thoai do.

    Luong chay:
      1. Khong co conversation_id -> tao hoi thoai moi, dat ten theo cau hoi dau.
      2. Doc vai luot gan nhat cua hoi thoai do tu database.
      3. Ghep lich su + cau hoi moi roi dua vao graph -> agent hieu ngu canh.
      4. Luu ca cau hoi lan cau tra loi xuong database.

    user_id de trong -> van tra loi binh thuong nhung KHONG luu gi (giu tuong
    thich cho ai dang goi API kieu cu).
    """
    # Khach vang lai (uid rong) VAN hoi duoc agent, chi khong luu lai gi. Day la
    # cho duy nhat trong ca file cho phep goi ma khong co danh tinh: dung thu
    # phai de dang, con lich su thi phai co chu.
    uid = _danh_tinh_tuy_chon(authorization, user_id)
    luu_lich_su = bool(uid)
    saved_path: Optional[Path] = None
    hoi_thoai: Optional[dict] = None

    try:
        if file is not None and file.filename:
            saved_path = _save_upload(file)
            message = f"{question}\nImage: {saved_path}"
        else:
            message = question

        lich_su: List[dict] = []
        if luu_lich_su:
            if conversation_id:
                hoi_thoai = _bat_buoc_co_hoi_thoai(conversation_id, uid)
                lich_su = _lich_su_cho_graph(conversation_id)
            # Hoi thoai moi: CHUA tao trong database o day. Tao som roi lo agent
            # loi giua chung (vd Gemini qua tai 503) se de lai mot hoi thoai
            # rong khong co tin nhan nao, hien trong sidebar nhung mo ra trong
            # trơn. Doi den luc chac chan co cau tra loi moi tao (xem ben duoi).

        graph = _get_supervisor_graph()
        run_config = {"recursion_limit": settings.recursion_limit}
        result = graph.invoke(
            {"messages": lich_su + [{"role": "user", "content": message}]},
            config=run_config,
        )
        answer = _final_answer(result)
        tool_outputs = _collect_tool_outputs(result)
        agents_used, agent_answers = _extract_agent_trace(result)

        response: dict = {"answer": answer, "agents_used": agents_used}
        if agent_answers:
            response["agent_answers"] = agent_answers
        _extract_vision_extras(tool_outputs, response)

        warnings = [
            _canh_bao_de_doc(name, text)
            for name, text in tool_outputs.items()
            if text.startswith("ERROR:")
        ]
        if warnings:
            response["warnings"] = warnings

        if luu_lich_su:
            if hoi_thoai is None:
                # Hoi thoai moi: chi tao khi da chac chan co cau tra loi de luu.
                hoi_thoai = store.tao_hoi_thoai(uid, store.dat_tieu_de(question))
            cid = hoi_thoai["id"]
            extras_user: dict = {}
            if saved_path is not None:
                # image_path de luot sau con nhin lai dung buc anh;
                # image_thumb_base64 de mo lai hoi thoai cu van thay anh da gui.
                extras_user["image_path"] = str(saved_path)
                anh_nho = _thumbnail_base64(saved_path)
                if anh_nho:
                    extras_user["image_thumb_base64"] = anh_nho
            store.them_tin_nhan(cid, "user", question, extras_user)
            store.them_tin_nhan(
                cid,
                "assistant",
                answer,
                {k: v for k, v in response.items() if k != "answer"},
            )
            response["conversation_id"] = cid
            response["title"] = hoi_thoai["title"]

        return response
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=_loi_ro_rang(exc)) from exc


# --------------------------------------------------------------------------- #
# Web UI - de FastAPI phuc vu luon trang web
# --------------------------------------------------------------------------- #
# Mot dia chi duy nhat cho ca API lan giao dien: gui mot link la ca lop vao test
# duoc, va vi cung origin nen khong con chuyen trinh duyet chan CORS.
@app.get("/", include_in_schema=False)
def trang_chu():
    trang = WEB_DIR / "UI_style.html"
    if not trang.is_file():
        raise HTTPException(status_code=404, detail="Chua co web/UI_style.html")
    return FileResponse(trang)

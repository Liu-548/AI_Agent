"""HTTP API cho web UI - boc quanh cac agent con bang FastAPI.

Khong dong gi trong app/agents/** hay app/core/**: endpoint chi goi lai dung
nhung ham CLI (app/main.py) da dung - build_vision_agent(), graph.invoke(),
final_text(), tool_error contract, ...  Neu QUY_TAC_THIET_KE.md doi cach cac
ham do hoat dong thi file nay cung phai doi theo, khong tu y sua logic agent.

Chay thu (tu goc repo, sau khi da kich hoat .venv):

    pip install fastapi "uvicorn[standard]" python-multipart
    uvicorn app.api:app --reload --port 8000

Sau do mo http://127.0.0.1:8000/docs de test bang Swagger UI truoc khi noi
frontend that vao.
"""

from __future__ import annotations

import base64
import json
import tempfile
import uuid
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.pretty import message_text

app = FastAPI(title="Visual Agentic AI - API", version="0.1.0")

# TODO: sieet lai allow_origins khi trien khai that (vd domain cua frontend),
# "*" chi de tien phat trien cuc bo.
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

# Build agent DUNG MOT LAN cho ca tien trinh uvicorn, khong build lai moi
# request - YOLO/LLM client se duoc tai su dung giua cac request thay vi nap
# lai tu dau (dieu khong the co duoc voi CLI vi CLI thoat sau moi lan chay).
# Ca 3 agent (vision, research, supervisor) deu duoc cache rieng - endpoint
# nao khong bi goi thi khong bi build, dung 1 lan cho cai dau tien can den.
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


def _save_upload(file: UploadFile) -> Path:
    """Luu file upload vao thu muc tam, kiem tra duoi va dung luong truoc."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Dinh dang {ext or '(khong ro)'} khong duoc ho tro. "
            f"Chi nhan: {sorted(ALLOWED_EXTS)}",
        )

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


def _loi_ro_rang(exc: Exception) -> str:
    """Rut gon cac loi hay gap thanh cau tra ve doc duoc cho frontend, cung
    nhom loi voi _giai_thich_loi trong app/main.py nhung ngan hon vi day la
    JSON tra ve API chu khong phai text in ra console."""
    msg = str(exc)
    if "RESOURCE_EXHAUSTED" in msg or "rate_limit" in msg or "429" in msg:
        return "Da het han muc mien phi cua model hom nay. Thu lai sau hoac doi model trong .env."
    if "API key not valid" in msg or "API_KEY_INVALID" in msg or "invalid_api_key" in msg:
        return "API key khong hop le. Kiem tra GROQ_API_KEY / GEMINI_API_KEY trong .env."
    if "recursion" in msg.lower():
        return "Agent lap qua nhieu buoc (recursion limit). Thu cau hoi ro rang/ngan hon."
    return f"Loi khi chay agent: {msg}"


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def config():
    """Vai tro -> provider/model, KHONG lo API key. Dung de debug tu Swagger/Postman."""
    return {"config": settings.mo_ta_cau_hinh()}


@app.post("/api/vision")
def ask_vision(
    file: UploadFile = File(..., description="Anh PNG/JPG/JPEG/WEBP/BMP"),
    question: str = Form(
        "Describe this image and count the objects in it.",
        description="Cau hoi ve buc anh, vd 'Co may con cho trong anh?'",
    ),
):
    """Nhan 1 anh upload + 1 cau hoi -> chay thang vision_agent, tra JSON.

    Co y KHONG di qua supervisor de tiet kiem luot Groq + Gemini (xem README,
    muc "Dang sua code thi chay -v thay vi qua supervisor").

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
            f"{name}: {text}" for name, text in tool_outputs.items() if text.startswith("ERROR:")
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
    """Chay thang research_agent (arXiv + OpenAlex + Wikipedia), khong qua
    supervisor - tiet kiem 2 luot dieu phoi cho moi cau hoi (xem README, muc
    "Dang sua code thi chay -r/-v thay vi qua supervisor")."""
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
            f"{name}: {text}" for name, text in tool_outputs.items() if text.startswith("ERROR:")
        ]
        if warnings:
            response["warnings"] = warnings
        return response
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=_loi_ro_rang(exc)) from exc


@app.post("/api/ask")
def ask_supervisor(
    question: str = Form(..., description="Cau hoi bat ky - supervisor tu chon agent con phu hop"),
    file: UploadFile = File(
        None, description="Anh (tuy chon) - chi can khi cau hoi lien quan toi hinh anh"
    ),
):
    """Di qua Supervisor: LLM tu quyet dinh giao viec cho vision_agent va/hoac
    research_agent, roi tong hop cau tra loi. Ton nhieu luot goi LLM hon 2
    endpoint tren (xem README, bang "Luot LLM") - dung khi cau hoi thuc su can
    ca 2 agent (vd: hoi ve mot khai niem duoc minh hoa trong anh)."""
    saved_path = None
    try:
        if file is not None and file.filename:
            saved_path = _save_upload(file)
            message = f"{question}\nImage: {saved_path}"
        else:
            message = question

        graph = _get_supervisor_graph()
        run_config = {"recursion_limit": settings.recursion_limit}
        result = graph.invoke(
            {"messages": [{"role": "user", "content": message}]}, config=run_config
        )
        answer = _final_answer(result)
        tool_outputs = _collect_tool_outputs(result)
        agents_used, agent_answers = _extract_agent_trace(result)

        response: dict = {"answer": answer, "agents_used": agents_used}
        if agent_answers:
            response["agent_answers"] = agent_answers
        _extract_vision_extras(tool_outputs, response)

        warnings = [
            f"{name}: {text}" for name, text in tool_outputs.items() if text.startswith("ERROR:")
        ]
        if warnings:
            response["warnings"] = warnings
        return response
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=_loi_ro_rang(exc)) from exc
    finally:
        if saved_path is not None:
            saved_path.unlink(missing_ok=True)
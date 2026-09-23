"""Giao diện web (Streamlit) cho Visual Agentic AI.

Lớp MỎNG bọc quanh app/main.py: gọi lại đúng hàm build-graph + stream mà CLI
dùng, nên hành vi (grounding, kiểm tra xác thực nguồn, lời giải thích lỗi) giữ
nguyên giữa 2 giao diện — không có logic agent nào lặp lại ở đây.

Chạy:
    streamlit run streamlit_app.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from app.agents import AGENT_SPECS_BY_NAME
from app.core.authenticity import bao_cao_xac_thuc, kiem_tra_xac_thuc
from app.core.config import DOTENV_LOADED, DOTENV_PROBLEM, settings
from app.core.grounding import bao_cao, kiem_tra_grounding
from app.core.pretty import final_text
from app.main import _giai_thich_loi, _gom_ket_qua_tool

SUPERVISOR_KEY = "__supervisor__"
AGENT_LABELS = {SUPERVISOR_KEY: "Supervisor (tự động chọn agent)"}
AGENT_LABELS.update({name: name for name in AGENT_SPECS_BY_NAME})

st.set_page_config(page_title="Visual Agentic AI", page_icon="🔎")


@st.cache_resource(show_spinner="Đang khởi tạo agent...")
def _get_graph(agent_key: str):
    if agent_key == SUPERVISOR_KEY:
        from app.agents.supervisor import build_supervisor

        return build_supervisor()
    return AGENT_SPECS_BY_NAME[agent_key].builder()


st.title("Visual Agentic AI")
st.caption("Research + Vision agent — trả lời có dẫn nguồn, kèm kiểm tra grounding.")

with st.sidebar:
    agent_key = st.selectbox(
        "Chế độ", options=list(AGENT_LABELS), format_func=lambda k: AGENT_LABELS[k]
    )
    uploaded = st.file_uploader(
        "Ảnh (tuỳ chọn — cho Vision Agent)",
        type=["png", "jpg", "jpeg", "webp", "bmp"],
    )
    if not DOTENV_LOADED and DOTENV_PROBLEM:
        st.warning(f"Chưa nạp được .env: {DOTENV_PROBLEM}")

question = st.text_area("Câu hỏi", placeholder="Ví dụ: rotary positional encoding là gì?")
submit = st.button("Gửi", type="primary")

if submit:
    if not question.strip():
        st.warning("Cần nhập câu hỏi.")
        st.stop()

    full_question = question.strip()
    if uploaded is not None:
        suffix = Path(uploaded.name).suffix or ".jpg"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(uploaded.getbuffer())
        tmp.close()
        full_question += f"\nImage: {tmp.name}"

    graph = _get_graph(agent_key)
    config = {"recursion_limit": settings.recursion_limit}
    tool_texts: list[str] = []
    tool_names: set[str] = set()
    last_chunk = None

    with st.spinner("Đang xử lý — có thể mất vài chục giây..."):
        try:
            for chunk in graph.stream(
                {"messages": [{"role": "user", "content": full_question}]}, config=config
            ):
                last_chunk = chunk
                _gom_ket_qua_tool(chunk, tool_texts, tool_names)
        except Exception as exc:  # noqa: BLE001 - đổi traceback thành lời khuyên, giống CLI
            loi = _giai_thich_loi(exc)
            if loi is None:
                st.exception(exc)
                st.stop()
            st.error(loi)
            if last_chunk is not None:
                st.markdown("**Phần đã chạy được trước khi dừng:**")
                st.write(final_text(last_chunk) or "(chưa có nội dung)")
            st.stop()

    cau_tra_loi = final_text(last_chunk)
    st.markdown("### Câu trả lời")
    st.write(cau_tra_loi or "(rỗng)")

    can_kiem_tra = bool(tool_names & {"arxiv_search", "openalex_search", "wikipedia_search"})
    if cau_tra_loi and can_kiem_tra:
        with st.expander("Kiểm tra nguồn (grounding + xác thực)"):
            st.text(bao_cao(kiem_tra_grounding(cau_tra_loi, tool_texts)))
            st.text(bao_cao_xac_thuc(kiem_tra_xac_thuc(cau_tra_loi, tool_texts)))

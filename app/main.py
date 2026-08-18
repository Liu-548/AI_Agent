"""CLI chạy thử hệ thống.

    python -m app.main "What is the latest research on positional embeddings?"
    python -m app.main "How many dogs are there in the image? Image: ./assets/dogs.jpg"
    python -m app.main --agent research_agent "rotary positional encoding"
    python -m app.main --graph        # in sơ đồ state graph dạng mermaid
"""

from __future__ import annotations

import argparse
import sys

from app.core.config import settings
from app.core.grounding import bao_cao, kiem_tra_grounding
from app.core.pretty import final_text, message_text, pretty_print_messages


def _build(agent_name: str | None):
    if agent_name:
        from app.agents import AGENT_SPECS_BY_NAME

        spec = AGENT_SPECS_BY_NAME.get(agent_name)
        if spec is None:
            available = ", ".join(AGENT_SPECS_BY_NAME) or "(rỗng)"
            raise SystemExit(f"Không có agent {agent_name!r}. Hiện có: {available}")
        return spec.builder()
    from app.agents.supervisor import build_supervisor

    return build_supervisor()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Visual Agentic AI — Supervisor demo")
    parser.add_argument("question", nargs="*", help="Câu hỏi gửi cho hệ thống")
    parser.add_argument("--agent", default=None, help="Chạy thẳng một agent con")
    parser.add_argument("--quiet", action="store_true", help="Chỉ in câu trả lời cuối")
    parser.add_argument("--graph", action="store_true", help="In state graph (mermaid)")
    parser.add_argument(
        "--skip-source-check",
        action="store_true",
        help="Bỏ qua bước đối chiếu câu trả lời với kết quả tool",
    )
    parser.add_argument("--config", action="store_true", help="In cấu hình model/provider")
    parser.add_argument(
        "--models",
        nargs="?",
        const="all",
        default=None,
        help="Liệt kê model mà key của bạn dùng được (groq|google|openai)",
    )
    args = parser.parse_args(argv)

    if args.models:
        return _in_danh_sach_model(args.models)

    if args.config:
        print("Cấu hình LLM (vai trò -> nhà cung cấp / model):")
        print(settings.mo_ta_cau_hinh())
        return 0

    graph = _build(args.agent)

    if args.graph:
        print(graph.get_graph().draw_mermaid())
        return 0

    question = " ".join(args.question).strip()
    if not question:
        parser.error("Cần một câu hỏi. Ví dụ: python -m app.main \"machine learning\"")

    config = {"recursion_limit": settings.recursion_limit}
    last_chunk = None
    tool_texts: list[str] = []
    tool_names: set[str] = set()
    try:
        for chunk in graph.stream(
            {"messages": [{"role": "user", "content": question}]}, config=config
        ):
            last_chunk = chunk
            _gom_ket_qua_tool(chunk, tool_texts, tool_names)
            if not args.quiet:
                pretty_print_messages(chunk, last_message=True)
    except Exception as exc:  # noqa: BLE001 - CLI: đổi traceback thành lời khuyên
        loi = _giai_thich_loi(exc)
        if loi is None:
            raise
        print(f"\n=== DUNG GIUA CHUNG ===\n{loi}")
        if last_chunk is not None:
            print("\n--- Phần đã chạy được trước khi dừng ---")
            print(final_text(last_chunk) or "(chưa có nội dung)")
        return 1

    cau_tra_loi = final_text(last_chunk)
    print("\n=== FINAL ANSWER ===")
    print(cau_tra_loi or "(rỗng)")

    # Chỉ đối chiếu khi câu trả lời thực sự dựa trên tool tra cứu tài liệu.
    # Vision Agent mô tả ảnh, nguồn của nó là chính bức ảnh, không có nhãn để đối chiếu.
    can_kiem_tra = bool(tool_names & {"arxiv_search", "wikipedia_search"})
    if cau_tra_loi and can_kiem_tra and not args.skip_source_check:
        print()
        print(bao_cao(kiem_tra_grounding(cau_tra_loi, tool_texts)))
    return 0


def _gom_ket_qua_tool(chunk, tool_texts: list, tool_names: set) -> None:
    """Nhặt nội dung mọi ToolMessage đi qua stream — đây là 'sự thật' để đối chiếu."""
    if isinstance(chunk, tuple):
        _, chunk = chunk
    if not isinstance(chunk, dict):
        return
    for node_update in chunk.values():
        if not isinstance(node_update, dict) or "messages" not in node_update:
            continue
        for m in node_update["messages"] or []:
            lay = m.get if isinstance(m, dict) else (lambda k, d=None: getattr(m, k, d))
            if lay("type", None) != "tool":
                continue
            ten = lay("name", "") or ""
            if ten:
                tool_names.add(ten)
            tool_texts.append(message_text(lay("content", None)))


def _in_danh_sach_model(chon: str) -> int:
    """Hỏi nhà cung cấp xem key hiện tại dùng được model nào."""
    from app.core.config import PROVIDERS
    from app.core.llm import list_models

    if chon == "all":
        dang_dung = {
            settings.split_model(spec)[0]
            for spec in (
                settings.model_supervisor, settings.model_research, settings.model_vision,
                settings.model_describe, settings.model_utility,
            )
        }
        providers = sorted(dang_dung)
    elif chon in PROVIDERS:
        providers = [chon]
    else:
        print(f"Nhà cung cấp {chon!r} không hợp lệ. Chọn trong {list(PROVIDERS)}.")
        return 1

    for p in providers:
        print(f"\n=== {p} ===")
        try:
            ten = list_models(p)
        except Exception as exc:  # noqa: BLE001
            print(f"  không lấy được danh sách: {exc}")
            continue
        if not ten:
            print("  (rỗng)")
        for t in ten:
            print(f"  {t}")
    print("\nDùng tên ở trên để điền vào MODEL_* trong .env, dạng provider:model")
    return 0


def _giai_thich_loi(exc: Exception) -> str | None:
    """Đổi các lỗi hay gặp thành thông điệp đọc được. None = không nhận ra, để nguyên."""
    msg = str(exc)

    dau_hieu_parse = (
        "output_parse_failed", "tool_use_failed", "Parsing failed", "failed_generation",
    )
    if any(d in msg for d in dau_hieu_parse):
        return (
            "Groq không dựng lại được câu trả lời của model (400 output_parse_failed).\n"
            "Đây là lỗi phía nhà cung cấp, KHÔNG phải sai key và KHÔNG phải hết hạn mức;\n"
            "retry cũng không cứu được vì 400 là lỗi không thể thử lại.\n"
            "\n"
            "Nó gần như luôn nổ ra SAU khi agent gọi lặp nhiều lượt tool làm hội thoại\n"
            "phình to. Cách xử lý, theo thứ tự nên thử:\n"
            "  1. Siết lượt tìm kiếm:  thêm RESEARCH_MAX_SEARCHES=4 vào .env\n"
            "  2. Đổi model của vai trò đang lỗi sang họ khác — gpt-oss gọi tool hay hỏng:\n"
            "       MODEL_RESEARCH=groq:qwen/qwen3.6-27b\n"
            "     Xem model dùng được:  python -m app.main --models\n"
            "  3. Khoanh vùng bằng cách chạy thẳng agent con:\n"
            "       python -m app.main --agent research_agent \"câu hỏi\"\n"
        )

    if "recursion" in msg.lower():
        return (
            "Graph chạy quá số bước cho phép — gần như chắc chắn là agent gọi lặp tool.\n"
            "  1. Xem agent lặp ở đâu trong log phía trên (cùng một tool, cùng một tham số).\n"
            "  2. Siết lượt tìm kiếm:  RESEARCH_MAX_SEARCHES=4 trong .env\n"
            "  3. Chỉ khi thật cần mới nới:  RECURSION_LIMIT=... trong .env\n"
        )

    if "RESOURCE_EXHAUSTED" in msg or "rate_limit" in msg or "429" in msg:
        return (
            "Hết hạn mức của MỘT model (mỗi model một sổ riêng, tính theo tài khoản/project).\n"
            "\n"
            "Cách xử lý, theo thứ tự nên thử:\n"
            "  1. Xem vai trò nào đang dùng model nào:  python -m app.main --config\n"
            "  2. Đổi MODEL_* trong .env sang model còn hạn mức.\n"
            "     Xem model dùng được:  python -m app.main --models\n"
            "     Hạn mức: https://console.groq.com/docs/rate-limits · https://aistudio.google.com/rate-limit\n"
            "  3. Chạy thẳng một agent con để đỡ tốn lượt của supervisor:\n"
            "       python -m app.main --agent research_agent \"câu hỏi\"\n"
            "  4. Test không tốn hạn mức: python -m pytest -m \"not network\"\n"
        )

    if "thought_signature" in msg:
        return (
            "Thư viện Google quá cũ so với model Gemini 3 (không giữ được chữ ký suy luận).\n"
            "  Sửa: python -m pip install -r requirements.txt\n"
            "  (cần langchain-google-genai >= 3.0, xem QUY_TAC_THIET_KE.md, MT-08)"
        )

    if "API key not valid" in msg or "API_KEY_INVALID" in msg or "invalid_api_key" in msg:
        return (
            "API key bị từ chối.\n"
            "  1. Xem vai trò nào dùng key nào:  python -m app.main --config\n"
            "  2. Key Gemini (AQ.) chỉ chạy với tiền tố google: trong MODEL_*\n"
            "  3. Key Groq bắt đầu bằng gsk_ — lấy tại https://console.groq.com/keys\n"
            "     Key Gemini lấy tại https://aistudio.google.com/apikey"
        )

    dau_hieu_model = ("model_not_found", "does not exist", "was not found", "is not found")
    if any(d in msg for d in dau_hieu_model):
        return (
            "Tên model không tồn tại, đã bị khai tử, hoặc tài khoản không truy cập được.\n"
            "  1. Xem model key của bạn dùng được:  python -m app.main --models\n"
            "  2. Sửa dòng MODEL_* tương ứng trong .env (dạng provider:model)\n"
            "  3. Xem vai trò nào đang dùng model nào:  python -m app.main --config\n"
            "  Lưu ý: nhà cung cấp có khai tử model theo lịch — tài liệu của họ\n"
            "  thường lạc hậu hơn thực tế, cứ tin --models."
        )

    return None


if __name__ == "__main__":
    sys.exit(main())

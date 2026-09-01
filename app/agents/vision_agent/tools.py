"""Tool của Vision Agent: image_describer + detect_and_count_objects.

Cả hai tool đều nhận đúng một tham số `text` (câu hỏi tự do có chứa đường dẫn/URL
ảnh) và trả về `str`, đúng hợp đồng ở app/contracts.py.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Callable, List, Optional

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.contracts import tool_error
from app.agents.vision_agent.prompts import IMAGE_DESCRIBER_SYSTEM_PROMPT
from app.agents.vision_agent.image_utils import draw_detections, encode_image, extract_image_ref


class ImageToolInput(BaseModel):
    text: str = Field(
        description="Path or URL to the image (PNG/JPG/JPEG/WEBP), optionally inside a sentence."
    )


class ImageDescription(BaseModel):
    image_description: str = Field(description="Detailed description of the image")


def _message_content_text(result: Any) -> str:
    content = getattr(result, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("text"):
                parts.append(str(block["text"]))
        return "\n".join(parts).strip()
    return str(content).strip() if content else ""


# --------------------------------------------------------------------------- #
# Tool 1: image_describer
# --------------------------------------------------------------------------- #
def describe_image(image_path_or_url: str, vision_llm) -> str:
    """Gửi ảnh (base64) kèm system prompt tới vision LLM, nhận mô tả có cấu trúc."""
    from langchain_core.messages import HumanMessage, SystemMessage

    b64, mime = encode_image(image_path_or_url, get_mime_type=True)
    if not b64 or not mime:
        return tool_error(
            "IMAGE_UNREADABLE",
            f"Không đọc được ảnh từ {image_path_or_url!r} "
            "(sai đường dẫn, URL hỏng, hoặc không phải file ảnh).",
        )

    image_url: dict = {"url": f"data:{mime};base64,{b64}"}
    # `detail` là tham số riêng của OpenAI. Một số endpoint tương thích (Gemini,
    # Groq...) không hiểu nó — để VISION_DETAIL rỗng trong .env là bỏ hẳn trường này.
    if settings.vision_detail:
        image_url["detail"] = settings.vision_detail

    messages = [
        SystemMessage(content=IMAGE_DESCRIBER_SYSTEM_PROMPT),
        HumanMessage(
            content=[
                {"type": "text", "text": "Describe the following image for me:"},
                {"type": "image_url", "image_url": image_url},
            ]
        ),
    ]
    try:
        result = vision_llm.with_structured_output(ImageDescription).invoke(messages)
        description = getattr(result, "image_description", None)
    except Exception as structured_exc:
        try:
            description = _message_content_text(vision_llm.invoke(messages))
        except Exception as plain_exc:
            return tool_error("VISION_LLM_FAILED", str(plain_exc or structured_exc))
        if not description:
            return tool_error("VISION_LLM_FAILED", str(structured_exc))
    if not description:
        return tool_error("VISION_EMPTY", "Vision model không trả về mô tả.")
    return description


def make_image_describer_tool(
    vision_llm=None,
    extractor_llm=None,
    return_direct: Optional[bool] = None,
):
    """Tạo tool mô tả ảnh.

    vision_llm / extractor_llm để None -> lấy từ app.llm (cần API key).
    Truyền model giả vào đây để test mà không tốn tiền.
    """
    from langchain_core.tools import StructuredTool

    if return_direct is None:
        return_direct = settings.image_describer_return_direct

    def _run(text: str) -> str:
        llm = vision_llm
        if llm is None:
            from app.core.llm import get_llm

            llm = get_llm("describe")
        ref = extract_image_ref(text, llm=extractor_llm)
        if not ref:
            return tool_error(
                "NO_IMAGE_REF", f"Không tìm thấy đường dẫn hay URL ảnh trong: {text!r}"
            )
        return describe_image(ref, llm)

    return StructuredTool.from_function(
        func=_run,
        name="image_describer",
        description=(
            "Describe the visible content of an image in detail: objects, colors, "
            "composition, actions, and any text present. Input is the image path or "
            "URL. Use this for 'what is in the image', colors, or context questions."
        ),
        args_schema=ImageToolInput,
        return_direct=return_direct,
    )


# --------------------------------------------------------------------------- #
# Tool 2: detect_and_count_objects
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _load_yolo(weights: str):
    """Nạp YOLO một lần duy nhất. Import trễ để ai không làm vision khỏi phải cài torch."""
    from ultralytics import YOLO

    return YOLO(weights)


def default_detector(image_ref: str) -> Any:
    model = _load_yolo(settings.yolo_weights)
    return model(image_ref, conf=settings.yolo_conf, iou=settings.yolo_iou, verbose=False)


def parse_yolo_results(results: Any) -> dict:
    """Chuyển kết quả ultralytics -> dict thuần Python (JSON-serializable)."""
    detections: List[dict] = []
    counting: dict = {}
    for result in results:
        boxes, class_names = result.boxes, result.names
        for box in boxes:
            class_id = int(box.cls[0])
            class_name = class_names[class_id]
            confidence = round(float(box.conf[0]), 3)
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
            detections.append(
                {
                    "class": class_name,
                    "confidence": confidence,
                    "bbox": [x1, y1, x2, y2],  # x1,y1 góc trên-trái; x2,y2 góc dưới-phải
                }
            )
            counting[class_name] = counting.get(class_name, 0) + 1
    return {"counting": counting, "detections": detections}


def make_detect_and_count_tool(
    detector: Optional[Callable[[str], Any]] = None,
    extractor_llm=None,
):
    """Tạo tool phát hiện + đếm vật thể.

    detector: callable(image_ref) -> kết quả kiểu ultralytics. Mặc định là YOLOv11.
    Cho phép truyền detector giả để test không cần tải model 100MB.
    """
    from langchain_core.tools import StructuredTool

    run_detector = detector or default_detector

    def _run(text: str) -> str:
        ref = extract_image_ref(text, llm=extractor_llm)
        if not ref:
            return tool_error(
                "NO_IMAGE_REF", f"Không tìm thấy đường dẫn hay URL ảnh trong: {text!r}"
            )
        try:
            results = run_detector(ref)
        except ImportError:
            return tool_error(
                "YOLO_NOT_INSTALLED",
                "Chưa cài ultralytics. Chạy: pip install ultralytics==8.3.108",
            )
        except Exception as exc:
            return tool_error("YOLO_INFERENCE_FAILED", str(exc))
        payload = parse_yolo_results(results)
        if not payload["counting"]:
            return json.dumps(
                {"counting": {}, "detections": [], "note": "No object detected."},
                ensure_ascii=False,
            )
        # Vẽ khung lên ảnh gốc chỉ khi bật DRAW_DETECTIONS=1 trong .env -- mặc định
        # TẮT để không sinh file "_detected.jpg" rác mỗi lần đếm vật thể.
        if settings.draw_detections_enabled:
            annotated_path = draw_detections(ref, payload["detections"])
            if annotated_path:
                payload["annotated_image"] = annotated_path
        return json.dumps(payload, ensure_ascii=False)

    return StructuredTool.from_function(
        func=_run,
        name="detect_and_count_objects",
        description=(
            "Detect and count objects inside an image using an object detector. "
            "Input is the image path or URL. Returns JSON with `counting` (how many "
            "instances of each class), `detections` (class, confidence, bbox in "
            "x1,y1,x2,y2 format), and `annotated_image` (path to a copy of the image "
            "with boxes drawn on it, when available). Use this for any 'how many' "
            "question about an image, and mention the annotated_image path to the user "
            "if present so they can open it and see the boxes."
        ),
        args_schema=ImageToolInput,
    )


def default_vision_tools() -> List:
    return [make_image_describer_tool(), make_detect_and_count_tool()]
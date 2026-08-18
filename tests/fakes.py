"""Model giả + detector giả để test toàn hệ thống mà KHÔNG cần API key, không tốn tiền.

Đây là lý do hợp đồng bắt buộc mọi factory phải có tham số `model=` và `tools=`:
không có DI thì không test được, không test được thì hôm merge mới biết hỏng.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, PrivateAttr


class FakeToolCallingModel(BaseChatModel):
    """Phát lại một kịch bản AIMessage định sẵn, hỗ trợ bind_tools()."""

    responses: List[AIMessage] = Field(default_factory=list)
    _cursor: int = PrivateAttr(default=0)
    _bound_tools: List[Any] = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake-tool-calling"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "FakeToolCallingModel":
        self._bound_tools = list(tools)
        return self

    @property
    def bound_tool_names(self) -> List[str]:
        names = []
        for t in self._bound_tools:
            name = getattr(t, "name", None) or getattr(t, "__name__", None)
            if name:
                names.append(name)
        return names

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        if not self.responses:
            msg = AIMessage(content="")
        else:
            idx = min(self._cursor, len(self.responses) - 1)
            msg = self.responses[idx].model_copy()
            self._cursor += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])


class FakeStructuredModel(BaseChatModel):
    """Model giả cho with_structured_output() — dùng test image_describer."""

    payload: dict = Field(default_factory=dict)
    should_fail: bool = False

    @property
    def _llm_type(self) -> str:
        return "fake-structured"

    def with_structured_output(self, schema: Any, **kwargs: Any):
        from langchain_core.runnables import RunnableLambda

        payload, should_fail = self.payload, self.should_fail

        def _call(_messages: Any):
            if should_fail:
                raise RuntimeError("vision provider is down")
            return schema(**payload)

        return RunnableLambda(_call)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=""))])


# --------------------------------------------------------------------------- #
# Detector giả — bắt chước đúng API của ultralytics (results[i].boxes / .names)
# --------------------------------------------------------------------------- #
class _FakeBox:
    def __init__(self, cls_id: int, conf: float, xyxy):
        self.cls = [cls_id]
        self.conf = [conf]
        self.xyxy = [list(xyxy)]


class _FakeResult:
    def __init__(self, boxes, names):
        self.boxes = boxes
        self.names = names


def fake_detector_factory(detections):
    """detections: list các (class_name, confidence, (x1,y1,x2,y2))."""
    names = {}
    boxes = []
    for cls_name, conf, box in detections:
        if cls_name not in names.values():
            names[len(names)] = cls_name
        cls_id = [k for k, v in names.items() if v == cls_name][0]
        boxes.append(_FakeBox(cls_id, conf, box))

    def _detect(_image_ref: str):
        return [_FakeResult(boxes, names)]

    return _detect


def tool_call(name: str, args: dict, call_id: str = "call_1") -> dict:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}

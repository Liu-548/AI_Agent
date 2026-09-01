"""Hợp đồng giao diện giữa các agent — phần MÁY KIỂM TRA ĐƯỢC của bảng quy tắc.

`tests/test_contract.py` gọi các hàm ở đây. Nếu một thành viên đổi tên agent, đổi
chữ ký factory, hoặc đổi tên tool thì test đỏ NGAY trên máy người đó, không đợi
đến hôm merge mới phát hiện.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable

# Tên agent: snake_case, vì langgraph-supervisor sinh handoff tool
# `transfer_to_<AGENT_NAME>` — tên sai chính tả = supervisor không route được.
AGENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*_agent$")
TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Tham số bắt buộc của mọi factory build_*_agent.
REQUIRED_BUILDER_PARAMS = ("model", "tools")

# Trường input chuẩn của mọi tool: đúng 1 trường tên `text`, kiểu str.
STANDARD_TOOL_INPUT_FIELD = "text"

ERROR_PREFIX = "ERROR:"


@dataclass(frozen=True)
class AgentSpec:
    """Mô tả một agent trong registry."""

    name: str
    description: str
    builder: Callable[..., Any]

    def validate(self) -> None:
        if not AGENT_NAME_RE.match(self.name):
            raise AssertionError(
                f"Tên agent {self.name!r} sai quy tắc: snake_case và kết thúc bằng '_agent'."
            )
        if not self.description or len(self.description) > 300:
            raise AssertionError(
                f"[{self.name}] description phải có và ngắn (<=300 ký tự) vì supervisor đọc nó để route."
            )
        if not callable(self.builder):
            raise AssertionError(f"[{self.name}] builder phải là callable.")
        expected = f"build_{self.name}"
        if self.builder.__name__ != expected:
            raise AssertionError(
                f"[{self.name}] factory phải tên {expected}(), đang là {self.builder.__name__}()."
            )
        params = inspect.signature(self.builder).parameters
        for p in REQUIRED_BUILDER_PARAMS:
            if p not in params:
                raise AssertionError(
                    f"[{self.name}] factory thiếu tham số bắt buộc {p!r} "
                    f"(cần cho việc test bằng model/tool giả)."
                )
            if params[p].default is inspect.Parameter.empty:
                raise AssertionError(
                    f"[{self.name}] tham số {p!r} phải có giá trị mặc định (None)."
                )


def validate_tool(tool: Any) -> None:
    """Kiểm tra một LangChain tool có tuân thủ hợp đồng tool không."""
    name = getattr(tool, "name", None)
    if not name or not TOOL_NAME_RE.match(name):
        raise AssertionError(f"Tên tool {name!r} phải là snake_case, không dấu.")
    desc = getattr(tool, "description", "")
    if not desc or len(desc) < 20:
        raise AssertionError(
            f"[{name}] description quá ngắn — LLM dựa vào đây để quyết định gọi tool."
        )
    schema = getattr(tool, "args", None) or {}
    if list(schema.keys()) != [STANDARD_TOOL_INPUT_FIELD]:
        raise AssertionError(
            f"[{name}] tool phải nhận đúng một tham số {STANDARD_TOOL_INPUT_FIELD!r}, "
            f"đang nhận {list(schema.keys())}."
        )


def validate_agent_layout(spec: AgentSpec) -> None:
    """Mỗi agent phải là một GÓI tự chứa, tên thư mục trùng AGENT_NAME (quy tắc CT-05).

    Nhờ ràng buộc này mà "một người = một thư mục" luôn đúng: nhìn tên thư mục là
    biết ai sở hữu, và không ai phải sửa file nằm ngoài thư mục của mình.
    """
    from pathlib import Path

    agents_root = Path(__file__).resolve().parent.parent / "agents"
    pkg_dir = agents_root / spec.name
    if not pkg_dir.is_dir():
        raise AssertionError(
            f"[{spec.name}] phải là một thư mục {pkg_dir.relative_to(agents_root.parent.parent)}/, "
            "không phải một file .py rời."
        )
    for required in ("__init__.py", "agent.py", "prompts.py"):
        if not (pkg_dir / required).is_file():
            raise AssertionError(f"[{spec.name}] thiếu file bắt buộc {required} trong gói.")


def validate_registry(specs: Iterable[AgentSpec]) -> None:
    seen: set[str] = set()
    for spec in specs:
        spec.validate()
        if spec.name in seen:
            raise AssertionError(f"Trùng tên agent: {spec.name!r}")
        seen.add(spec.name)


def tool_error(code: str, message: str) -> str:
    """Định dạng lỗi thống nhất cho mọi tool: tool KHÔNG raise, chỉ trả chuỗi."""
    return f"{ERROR_PREFIX} {code} | {message}"

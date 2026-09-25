"""SearchProfile — MỘT chỗ duy nhất chứa mọi giới hạn tìm kiếm của chế độ "topics".

Vì sao gom lại: muốn tiết kiệm token thì chỉ cần đổi RESEARCH_MODE (eco/standard/
full), không phải sửa code ở nhiều nơi. Mọi con số giới hạn ở paper_tools, topic
tool và lead đều LẤY từ profile, không viết cứng ở chỗ khác.

Các con số dưới đây là tạm thời; Phase 2 sẽ đo token thật rồi chỉnh lại.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class SearchProfile:
    name: str                        # "eco" | "standard" | "full"
    paper_sources: Tuple[str, ...]   # nguồn mà paper_search gọi, theo thứ tự
    per_source_limit: int            # số kết quả xin từ MỖI nguồn
    max_results: int                 # số bài giữ lại sau khi khử trùng + xếp hạng
    abstract_chars: int              # cắt abstract trước khi đưa cho LLM
    max_searches_per_topic: int      # trần lượt tìm kiếm cho MỘT lần gọi agent chủ đề
    max_lookups_per_topic: int       # trần doi_lookup cho MỘT lần gọi agent chủ đề
    max_topic_calls: int             # trần số lần lead gọi agent chủ đề cho MỘT câu hỏi
    inner_recursion_limit: int       # recursion_limit khi invoke agent chủ đề


PROFILES: Dict[str, SearchProfile] = {
    "eco": SearchProfile(
        name="eco",
        paper_sources=("arxiv", "openalex"),
        per_source_limit=2,
        max_results=3,
        abstract_chars=300,
        max_searches_per_topic=2,
        max_lookups_per_topic=1,
        max_topic_calls=1,
        inner_recursion_limit=12,
    ),
    "standard": SearchProfile(
        name="standard",
        paper_sources=("arxiv", "openalex", "semantic_scholar"),
        per_source_limit=3,
        max_results=5,
        abstract_chars=600,
        max_searches_per_topic=3,
        max_lookups_per_topic=3,
        max_topic_calls=2,
        inner_recursion_limit=20,
    ),
    "full": SearchProfile(
        name="full",
        paper_sources=("arxiv", "openalex", "semantic_scholar"),
        per_source_limit=5,
        max_results=8,
        abstract_chars=1000,
        max_searches_per_topic=5,
        max_lookups_per_topic=5,
        max_topic_calls=3,
        inner_recursion_limit=30,
    ),
}


def get_profile(name: Optional[str] = None) -> SearchProfile:
    """Profile theo RESEARCH_MODE (hoặc theo `name` nếu truyền vào).

    RESEARCH_MAX_SEARCHES, nếu được đặt thật, ghi đè max_searches_per_topic.
    Giá trị RESEARCH_MODE lạ -> RuntimeError rõ ràng (do config báo).
    """
    # Đọc settings lúc gọi (không import ở đầu file) để test đổi được cấu hình.
    from app.core import config

    cfg = config.settings
    ten = name or cfg.research_mode_hop_le()
    if ten not in PROFILES:
        raise RuntimeError(f"Profile {ten!r} không tồn tại. Chọn trong {list(PROFILES)}.")
    profile = PROFILES[ten]
    if cfg.research_max_searches_set:
        profile = replace(profile, max_searches_per_topic=cfg.research_max_searches)
    return profile

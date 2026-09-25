"""Các nguồn dữ liệu học thuật. File này CHỈ re-export (quy tắc CT-04)."""

from app.agents.research_agent.sources.base import (
    PaperRecord,
    SourceError,
    dedupe_records,
    http_get,
    rank_records,
)

__all__ = ["PaperRecord", "SourceError", "dedupe_records", "http_get", "rank_records"]

"""Ngân sách gọi agent con trong một lượt chạy Supervisor."""

from __future__ import annotations

import logging
from threading import Lock

CALL_BUDGET_CONFIG_KEY = "supervisor_call_budget"

_LOGGER = logging.getLogger(__name__)


class CallBudget:
    """Đếm lượt gọi agent con, an toàn khi các tool chạy song song."""

    def __init__(self, max_calls_per_agent: int, max_total_calls: int):
        self.max_calls_per_agent = max(0, int(max_calls_per_agent))
        self.max_total_calls = max(0, int(max_total_calls))
        self._calls_by_agent: dict[str, int] = {}
        self._total_calls = 0
        self._lock = Lock()

    @classmethod
    def from_settings(cls) -> CallBudget:
        """Tạo ngân sách theo cấu hình ứng dụng."""
        from app.core.config import settings

        return cls(
            max_calls_per_agent=settings.supervisor_max_calls_per_agent,
            max_total_calls=settings.supervisor_max_total_calls,
        )

    def reserve(self, agent_name: str) -> tuple[bool, str, int, int]:
        """Giữ một lượt gọi hoặc trả lý do vượt giới hạn."""
        with self._lock:
            agent_calls = self._calls_by_agent.get(agent_name, 0)
            if agent_calls >= self.max_calls_per_agent:
                reason = "agent"
            elif self._total_calls >= self.max_total_calls:
                reason = "total"
            else:
                agent_calls += 1
                self._total_calls += 1
                self._calls_by_agent[agent_name] = agent_calls
                _LOGGER.info(
                    "Supervisor agent call reserved: agent=%s agent_calls=%d total_calls=%d",
                    agent_name,
                    agent_calls,
                    self._total_calls,
                )
                if (
                    agent_calls == self.max_calls_per_agent
                    or self._total_calls == self.max_total_calls
                ):
                    _LOGGER.warning(
                        "Supervisor call budget reached: agent=%s agent_calls=%d "
                        "total_calls=%d error_type=CallBudgetLimit",
                        agent_name,
                        agent_calls,
                        self._total_calls,
                    )
                return True, "", agent_calls, self._total_calls

            _LOGGER.warning(
                "Supervisor call budget exceeded: agent=%s limit=%s agent_calls=%d "
                "total_calls=%d error_type=CallBudgetLimit",
                agent_name,
                reason,
                agent_calls,
                self._total_calls,
            )
            return False, reason, agent_calls, self._total_calls


def budget_from_config(config: dict | None) -> CallBudget:
    """Lấy budget từ configurable; tạo budget cục bộ cho lời gọi tool độc lập."""
    configurable = (config or {}).get("configurable")
    if isinstance(configurable, dict):
        budget = configurable.get(CALL_BUDGET_CONFIG_KEY)
        if isinstance(budget, CallBudget):
            return budget
        budget = CallBudget.from_settings()
        configurable[CALL_BUDGET_CONFIG_KEY] = budget
        return budget
    return CallBudget.from_settings()


__all__ = ["CALL_BUDGET_CONFIG_KEY", "CallBudget", "budget_from_config"]

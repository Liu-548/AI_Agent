from __future__ import annotations

import asyncio
from threading import Lock

from langchain_core.messages import AIMessage

from app.agents.supervisor import build_supervisor
from app.agents.supervisor.budget import CALL_BUDGET_CONFIG_KEY, CallBudget
from app.agents.supervisor.prompts import SUPERVISOR_PROMPT_TEMPLATE
from app.agents.supervisor.tools import SUPERVISOR_TOOLS, _chay_agent_con
from app.core.config import Settings
from tests.fakes import FakeToolCallingModel, tool_call


class _FakeAgent:
    name = "research_agent"

    def __init__(self, result=None, errors=None):
        self.result = result or {"messages": [AIMessage(content="agent answer")]}
        self.errors = list(errors or [])
        self.calls = 0
        self.configs = []
        self._lock = Lock()

    def invoke(self, state, config=None):
        with self._lock:
            self.calls += 1
            self.configs.append(config)
            if self.errors:
                error = self.errors.pop(0)
                raise error
        return self.result


def _config(budget: CallBudget) -> dict:
    return {"configurable": {CALL_BUDGET_CONFIG_KEY: budget}}


def test_agent_con_nhan_config_tu_supervisor_graph():
    agent = _FakeAgent()
    model = FakeToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    tool_call("transfer_to_research_agent", {"query": "question"})
                ],
            ),
            AIMessage(content="done"),
        ]
    )
    graph = build_supervisor(model=model, agents=[agent])
    graph.invoke(
        {"messages": [{"role": "user", "content": "question"}]},
        config={"recursion_limit": 19, "configurable": {"trace_marker": "kept"}},
    )

    child_config = agent.configs[0]
    assert child_config["recursion_limit"] == 19
    assert child_config["configurable"]["trace_marker"] == "kept"
    assert isinstance(child_config["configurable"][CALL_BUDGET_CONFIG_KEY], CallBudget)


def test_prompt_chi_nhac_ten_tool_da_dang_ky():
    registered = {sub_agent_tool.name for sub_agent_tool in SUPERVISOR_TOOLS}
    named_tools = {"research_agent_tool", "vision_agent_tool"}
    assert named_tools <= registered
    assert "`research_agent_tool`" in SUPERVISOR_PROMPT_TEMPLATE
    assert "`vision_agent_tool`" in SUPERVISOR_PROMPT_TEMPLATE
    assert "`research_tool`" not in SUPERVISOR_PROMPT_TEMPLATE


def test_loi_tam_thoi_retry_dung_mot_lan_roi_tra_loi_co_cau_truc(monkeypatch):
    agent = _FakeAgent(errors=[TimeoutError(), TimeoutError()])
    monkeypatch.setattr("app.agents.supervisor.tools.time.sleep", lambda _seconds: None)

    answer, _ = _chay_agent_con(agent, "question", _config(CallBudget(3, 6)))

    assert agent.calls == 2
    assert answer.startswith("ERROR: SUB_AGENT_ERROR")
    assert "TimeoutError" in answer


def test_agent_tra_state_rong_khong_gay_index_error():
    agent = _FakeAgent(result={"messages": []})

    answer, _ = _chay_agent_con(agent, "question", _config(CallBudget(3, 6)))

    assert answer.startswith("ERROR: SUB_AGENT_EMPTY_STATE")
    assert agent.calls == 1


def test_agent_khong_hop_le_tra_loi_co_cau_truc():
    answer, _ = _chay_agent_con(object(), "question", _config(CallBudget(3, 6)))

    assert answer.startswith("ERROR: SUB_AGENT_INVALID")


def test_loi_khong_tam_thoi_khong_retry(monkeypatch):
    agent = _FakeAgent(errors=[RuntimeError("configuration error")])
    monkeypatch.setattr("app.agents.supervisor.tools.time.sleep", lambda _seconds: None)

    answer, _ = _chay_agent_con(agent, "question", _config(CallBudget(3, 6)))

    assert agent.calls == 1
    assert answer.startswith("ERROR: SUB_AGENT_ERROR")
    assert "RuntimeError" in answer


def test_goi_agent_duoi_nguong_duoc_thuc_thi_day_du():
    agent = _FakeAgent()
    config = _config(CallBudget(max_calls_per_agent=3, max_total_calls=6))

    answers = [_chay_agent_con(agent, f"question {index}", config)[0] for index in range(3)]

    assert answers == ["agent answer"] * 3
    assert agent.calls == 3


def test_lan_goi_thu_tu_cung_agent_bi_chan():
    agent = _FakeAgent()
    config = _config(CallBudget(max_calls_per_agent=3, max_total_calls=6))

    for index in range(3):
        assert _chay_agent_con(agent, f"question {index}", config)[0] == "agent answer"
    answer, _ = _chay_agent_con(agent, "question 4", config)

    assert answer.startswith("ERROR: CALL_BUDGET_AGENT_LIMIT")
    assert "research_agent" in answer
    assert agent.calls == 3


def test_vuot_tong_so_luot_chan_agent_khac_nhau():
    budget = CallBudget(max_calls_per_agent=3, max_total_calls=2)
    first = _FakeAgent()
    second = _FakeAgent()
    third = _FakeAgent()
    third.name = "vision_agent"
    config = _config(budget)

    assert _chay_agent_con(first, "one", config)[0] == "agent answer"
    assert _chay_agent_con(second, "two", config)[0] == "agent answer"
    answer, _ = _chay_agent_con(third, "three", config)

    assert answer.startswith("ERROR: CALL_BUDGET_TOTAL_LIMIT")
    assert first.calls == second.calls == 1
    assert third.calls == 0


def test_hai_luot_dong_thoi_co_ngan_sach_doc_lap(monkeypatch):
    monkeypatch.setattr(
        CallBudget,
        "from_settings",
        classmethod(lambda cls: cls(max_calls_per_agent=1, max_total_calls=1)),
    )
    agents = [_FakeAgent(), _FakeAgent()]
    graphs = [
        build_supervisor(
            model=FakeToolCallingModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            tool_call(
                                "transfer_to_research_agent",
                                {"query": "question"},
                            )
                        ],
                    ),
                    AIMessage(content="done"),
                ]
            ),
            agents=[agent],
        )
        for agent in agents
    ]
    state = {"messages": [{"role": "user", "content": "question"}]}
    shared_config = {
        "configurable": {CALL_BUDGET_CONFIG_KEY: CallBudget(1, 1)}
    }

    async def run_concurrently():
        await asyncio.gather(
            *(asyncio.to_thread(graph.invoke, state, shared_config) for graph in graphs)
        )

    asyncio.run(run_concurrently())

    assert [agent.calls for agent in agents] == [1, 1]
    assert all(
        isinstance(config["configurable"][CALL_BUDGET_CONFIG_KEY], CallBudget)
        for agent in agents
        for config in agent.configs
    )
    budgets = [
        agent.configs[0]["configurable"][CALL_BUDGET_CONFIG_KEY] for agent in agents
    ]
    assert budgets[0] is not budgets[1]


def test_cau_hinh_ngan_sach_doc_env_va_ghi_de_duoc(monkeypatch):
    import app.core.config as config_module

    monkeypatch.setenv("SUPERVISOR_MAX_CALLS_PER_AGENT", "2")
    monkeypatch.setenv("SUPERVISOR_MAX_TOTAL_CALLS", "4")

    settings = Settings()
    monkeypatch.setattr(config_module, "settings", settings)
    budget = CallBudget.from_settings()

    assert settings.supervisor_max_calls_per_agent == 2
    assert settings.supervisor_max_total_calls == 4
    assert budget.max_calls_per_agent == 2
    assert budget.max_total_calls == 4


def test_cau_hinh_ngan_sach_mac_dinh(monkeypatch):
    import app.core.config as config_module

    monkeypatch.delenv("SUPERVISOR_MAX_CALLS_PER_AGENT", raising=False)
    monkeypatch.delenv("SUPERVISOR_MAX_TOTAL_CALLS", raising=False)

    settings = Settings()
    monkeypatch.setattr(config_module, "settings", settings)
    budget = CallBudget.from_settings()

    assert settings.supervisor_max_calls_per_agent == 3
    assert settings.supervisor_max_total_calls == 6
    assert budget.max_calls_per_agent == 3
    assert budget.max_total_calls == 6

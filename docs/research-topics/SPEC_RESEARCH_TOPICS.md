# SPEC — Research Agent phân chủ đề (Topic Agents) · Phase 1

> **Dành cho:** Claude Code (người thực thi) và Tuấn (chủ vùng Research, người duyệt).
> **Soạn:** 25/09/2026 · **Phiên bản:** 1.0 · **Trạng thái:** đã chốt với chủ dự án, sẵn sàng thực thi.
> **Vị trí trong repo:** `docs/research-topics/SPEC_RESEARCH_TOPICS.md` (repo `visual-agentic-ai/`).
> **Hạn Phase 1:** 2–3 tuần → mốc mục tiêu **09/10/2026**, muộn nhất **16/10/2026**.

---

## 0. Claude Code đọc phần này trước tiên

### 0.1 Thứ tự đọc

1. `C:\CTK47C\DoAnChuyenNganh\CLAUDE.md` — guardrails chung của dự án.
2. `QUY_TAC_THIET_KE.md` — luật nhóm (Bảng 1–11). Mọi mã quy tắc trong spec này (IF-xx, CH-xx, TS-xx…) trỏ về file đó.
3. `TRUOC_KHI_CHAY.md` — kích hoạt venv, các lệnh kiểm tra không tốn hạn mức.
4. Spec này.

Khi mâu thuẫn, thứ tự ưu tiên là: **luật nhóm > CLAUDE.md > spec này > phán đoán của bạn.** Mâu thuẫn thật thì xử lý theo §0.4.

### 0.2 Nhịp thực thi

Làm **liền mạch toàn bộ Phase 1** theo các bước ở §9, không chờ duyệt giữa các bước. Sau mỗi bước:

1. `python -m pytest -q -m "not network"` phải xanh.
2. Commit (có thể tách nhiều commit nhỏ trong một bước, mỗi commit ≤ ~200 dòng — GIT-06).
3. Sang bước tiếp.

Kết thúc khi đạt DoD tự động ở §10.1, viết báo cáo theo §11, rồi **dừng**. Phần nghiệm thu có gọi LLM thật (§10.2) là việc của Tuấn.

Trong code: comment và docstring bằng **tiếng Việt** (DT-02, để Tuấn đọc học), tên biến/hàm/tool bằng **tiếng Anh snake_case** (DT-01), prompt gửi LLM bằng **tiếng Anh** (DT-02).

### 0.3 Những việc KHÔNG được làm

- **Không gọi LLM thật.** Không chạy `python -m app.main "<câu hỏi>"`, không chạy `--agent`, không chạy test nào cần key LLM. Hạn mức là của Tuấn. Được phép chạy: `pytest -m "not network"`, `--config`, `--graph`, và **một lần** `pytest -m network -k research_sources` ở cuối (chỉ gọi API học thuật miễn phí, không gọi LLM).
- Không `git push`, không commit vào `main`/`develop`, không rewrite history, không `--force`, không `git reset --hard`.
- Không sửa file trong **danh sách cấm** ở §4.3 — đặc biệt `tests/test_contract.py` (TS-05).
- Không thêm, nâng hay hạ thư viện; không sửa `requirements.txt` (MT-03, MT-04). Phase 1 chỉ dùng `requests` (đã ghim) và thư viện chuẩn (`json`, `xml.etree.ElementTree`, `dataclasses`, `re`, `logging`, `time`).
- Không `print()` trong `app/` (LX-03) — dùng `logging`.
- Không hard-code key (CH-01); không đọc biến môi trường ngoài `app/core/config.py` (CH-02); không khởi tạo ChatModel ngoài `app.core.llm.get_llm()` (CH-03).
- Không commit `.env`, `*.ipynb`, `*.pt`, `__pycache__/`, `.venv/` (GIT-05).
- Không log hay in API key, kể cả một phần.

### 0.4 Điều kiện DỪNG HẲN

Gặp một trong các tình huống dưới đây thì **dừng, không tự xoay xở**:

1. Muốn test xanh mà buộc phải sửa một file trong danh sách cấm (§4.3).
2. Cần thêm hoặc đổi phiên bản thư viện.
3. Test đã **đỏ ngay từ đầu** (baseline ở B0) — không sửa code của người khác.
4. Phiên bản LangGraph/LangChain đang cài thiếu một tính năng spec dựa vào (§5.10, §5.7), và phương án dự phòng được ghi trong spec cũng không dùng được.
5. API thật của một nguồn dữ liệu khác spec **ở mức thiết kế** (ví dụ endpoint bị bỏ, bắt buộc trả phí). Khác biệt nhỏ (tên tham số, tên trường) thì cứ thích nghi và ghi vào báo cáo.
6. Cần một hành động không đảo ngược được, hoặc thao tác ngoài thư mục repo.
7. Cần tiêu hạn mức LLM để đi tiếp.

Khi dừng, ghi vào `docs/research-topics/PHASE1_REPORT.md` một mục **"ĐÃ DỪNG"** gồm:
- chuyện gì xảy ra, ở bước nào, file và dòng nào;
- 2–3 phương án;
- phương án bạn khuyến nghị kèm lý do.

---

## 1. Bối cảnh

**Hiện trạng.** `research_agent` là **một** ReAct agent với hai tool `arxiv_search`, `wikipedia_search`. Các cơ chế đang có:
- phanh `SearchBudget` (từ chối truy vấn trùng + trần tổng lượt, siết thêm bằng `RESEARCH_MAX_SEARCHES`);
- hàm `tim_arxiv()` in cả `Published` lẫn `Last updated`;
- hợp đồng chống bịa (prompt GROUNDING + `app/core/grounding.py` với `MA_BIA`, `NHAN_BIA`, `THIEU_NGUON`).

Supervisor của nhóm gọi nó qua `transfer_to_research_agent`.

**Vấn đề.** Một prompt duy nhất phải xử lý mọi kiểu câu hỏi: vừa tìm bài báo, vừa giải thích khái niệm. Nếu thêm nguồn (OpenAlex, Semantic Scholar, PubMed, Crossref) thẳng vào agent này, nó sẽ quá tải tool — đúng giới hạn "tool overload" ở §I tài liệu gốc. Về lâu dài, dự án còn muốn thêm các chủ đề khác như code, du lịch, văn hoá–nghệ thuật.

**Hướng giải.** Biến `research_agent` thành một **research lead**. Lead điều phối các **agent chủ đề**, mỗi agent chuyên một loại việc và được gói thành một tool. Nhìn từ supervisor, mọi thứ vẫn là một node `research_agent` như cũ.

## 2. Mục tiêu và ngoài phạm vi

**Mục tiêu Phase 1**

- G1. Khung agent chủ đề: thêm một chủ đề mới = thêm một thư mục con + **một dòng** đăng ký.
- G2. Hai agent chủ đề đầu tiên: `scholar_agent` (học thuật) và `explainer_agent` (khoa học phổ thông).
- G3. Bốn nguồn mới — OpenAlex, Semantic Scholar, PubMed, Crossref — cạnh arXiv và Wikipedia, có khử trùng tài liệu.
- G4. Grounding bắt buộc cho mọi agent chủ đề, chạy **hai tầng**: trong từng agent chủ đề, và trên câu trả lời tổng hợp của lead.
- G5. Mọi giới hạn tìm kiếm đi qua **một** `SearchProfile`, sẵn chỗ cắm cho chế độ tiết kiệm token (`RESEARCH_MODE=eco|standard|full`).
- G6. Vết thực thi đầy đủ của từng agent chủ đề được giữ lại cho phần trực quan hoá sau này.
- G7. Không phá hợp đồng nhóm: `test_contract.py` xanh mà không sửa; chế độ cũ vẫn chạy y nguyên qua công tắc `RESEARCH_ARCH=single`.

**Ngoài phạm vi Phase 1** (xem lộ trình ở §13)

- Tinh chỉnh số liệu cho eco/full, đo token thực tế, cache kết quả tìm kiếm → Phase 2.
- Xếp hạng bằng embedding.
- Giao diện UI.
- Các chủ đề Code, Du lịch, Văn hoá & Nghệ thuật → Phase 3–5.
- Sửa `app/main.py`, supervisor hay vision agent.

## 3. Quyết định đã chốt

| Mã | Quyết định | Lý do |
|---|---|---|
| D1 | **Phân cấp bên ngoài, agents-as-tools bên trong.** Supervisor vẫn chỉ thấy `research_agent`. Bên trong, lead là một ReAct agent có các tool là agent chủ đề. | Hợp đồng ngoài (`AGENT_NAME`, factory, tên handoff) không đổi → merge không đụng registry hay file của người khác. Rẻ hơn lồng `create_supervisor` (không có lượt handoff qua lại). Tái dùng được `SearchBudget` và `recursion_limit`. Đây là hướng "Hierarchical là hướng mở rộng" đã ghi trong bản thiết kế. |
| D2 | **Chia chủ đề theo loại việc, không theo lĩnh vực.** `scholar_agent` tìm, lọc và trích bài báo. `explainer_agent` giải thích khái niệm. Lĩnh vực là tham số bên trong `scholar_agent` (y sinh thì gọi thêm PubMed). | Ranh giới "tìm bài báo" và "giải thích" rõ ràng. Ranh giới lĩnh vực (CS hay Y sinh…) thì mờ, dễ route sai. |
| D3 | **Câu hỏi đa chủ đề:** lead tách thành câu con tự đủ nghĩa, gọi **tuần tự** từng agent chủ đề, rồi tổng hợp. Có trần số lần gọi (`max_topic_calls`, mặc định 2) và từ chối gọi trùng. Chỉ hỏi lại người dùng khi câu hỏi mơ hồ thật sự (`CAN_LAM_RO:`, tương ứng UC02.E1). | Khớp quy tắc "không song song" của nhóm, không đụng trần 8K TPM của Groq. Trần số lần gọi đặt trong **code** (bài học số 2 ở TRUOC_KHI_CHAY §7). |
| D4 | **Grounding bắt buộc cho mọi agent chủ đề, hai tầng.** Vi phạm `MA_BIA`/`NHAN_BIA` → **xoá câu** đó. `THIEU_NGUON` → chỉ đếm và báo cáo, không xoá. | Bịa mã hay bịa nhãn là lỗi nặng và được so khớp chính xác, nên gần như không có báo động giả. `THIEU_NGUON` dễ báo động giả hơn (bài học số 5), xoá câu đúng thì còn hại hơn. |
| D5 | **Mở rộng `app/core/grounding.py` ngay trên nhánh** để nhận các loại nhãn mới (DOI, PMID, OpenAlex, Semantic Scholar). Mở rộng qua một bảng pattern; báo nhóm khi merge. | Grounding là tài sản chung; các chủ đề tương lai cũng cần thêm nhãn. Một bảng pattern giúp lần sau chỉ phải thêm một mục. |
| D6 | **Không thêm thư viện.** Gọi API bằng `requests` và thư viện chuẩn. | MT-03/MT-04. `requirements.txt` là tài sản chung. |
| D7 | **Một `SearchProfile` duy nhất** chứa mọi giới hạn. Phase 1 định nghĩa sẵn `eco`/`standard`/`full`, mặc định `standard`; tinh chỉnh số liệu để Phase 2. | Chế độ tiết kiệm token về sau chỉ còn là việc cấu hình, không phải sửa code. |
| D8 | **Lead dùng vai trò model `research` (giữ nguyên); agent chủ đề dùng vai trò mới `research_topic`.** | Hạn mức Groq tính theo từng model (CH-06). Tách sổ giúp lead và agent chủ đề không ăn chung 200K token/ngày. |
| D9 | **Dữ liệu đầy đủ (bằng chứng, vết thực thi) đi qua `ToolMessage.artifact`.** Chỉ bản rút gọn được đưa vào context LLM của lead (`response_format="content_and_artifact"`). | Chống context overload, chống `400 output_parse_failed`, và giữ dưới 8K TPM. Artifact không gửi cho LLM nhưng vẫn nằm trong state → dùng được cho grounding tầng 2 và cho UI sau này. |
| D10 | **Công tắc `RESEARCH_ARCH=single\|topics`, mặc định `single` ở Phase 1.** | Test hiện có (kể cả e2e của nhóm) vẫn chạy trên đường cũ. Merge an toàn. Demo được so sánh một agent với nhiều agent — trả lời câu vấn đáp "tại sao phải nhiều agent". |

## 4. Kiến trúc

### 4.1 Sơ đồ

```
Người dùng
   │
   ▼
Supervisor (của nhóm — KHÔNG ĐỔI)
   │  transfer_to_research_agent
   ▼
research_agent ──(RESEARCH_ARCH=single)──► agent cũ: arxiv_search + wikipedia_search  (giữ nguyên)
   │
   └──(RESEARCH_ARCH=topics)──► RESEARCH LEAD  (ReAct, model vai trò "research")
          │   tool: scholar_agent(text)          tool: explainer_agent(text)
          │   [TopicBudget: ≤ max_topic_calls, không gọi trùng — đếm trong code]
          ▼                                        ▼
   scholar_agent (ReAct con,               explainer_agent (ReAct con,
   model "research_topic")                  model "research_topic")
     ├ paper_search ─► arXiv │ OpenAlex │ Semantic Scholar  (khử trùng, xếp hạng)
     ├ pubmed_search ─► PubMed               ├ wikipedia_search  (tool cũ)
     └ doi_lookup ─► Crossref                └ arxiv_search      (tool cũ)
          │                                        │
          └──── GROUNDING TẦNG 1 (trong topic tool): xoá câu MA_BIA/NHAN_BIA ────┘
                 content rút gọn → LLM của lead  |  artifact đầy đủ → state
          │
   Lead tổng hợp (ngôn ngữ người dùng, giữ nguyên nhãn)
          │
   GROUNDING TẦNG 2 (post_model_hook): đối chiếu với bằng chứng trong artifact
          │
          ▼
   trả về Supervisor
```

### 4.2 Cây thư mục (chỉ phần thay đổi)

```
app/agents/research_agent/
├── __init__.py            # CHỈ re-export (CT-04). Giữ mọi export cũ.                  [SỬA NHẸ]
├── agent.py               # AGENT_NAME, AGENT_DESCRIPTION (KHÔNG ĐỔI) + build_research_agent rẽ nhánh [SỬA NHẸ]
├── prompts.py             # RESEARCH_AGENT_PROMPT (giữ nguyên từng byte) + RESEARCH_LEAD_PROMPT_TEMPLATE
│                          #   + GROUNDING_RULES (khối quy tắc dùng chung cho agent chủ đề)  [THÊM]
├── tools.py               # arxiv_search, wikipedia_search, SearchBudget, tim_arxiv — GIỮ HÀNH VI [HẠN CHẾ SỬA]
├── lead.py                # build_research_lead() + hook grounding tầng 2                 [MỚI]
├── profiles.py            # SearchProfile, PROFILES, get_profile()                        [MỚI]
├── grounding_policy.py    # apply_grounding_policy(): xoá câu vi phạm nặng, dựng báo cáo  [MỚI]
├── paper_tools.py         # make_paper_tools(budget, profile) → paper_search, pubmed_search, doi_lookup [MỚI]
├── sources/                                                                               [MỚI]
│   ├── __init__.py        # re-export
│   ├── base.py            # PaperRecord, SourceError, http_get(), dedupe_records(), rank_records()
│   ├── arxiv_source.py    # bọc tim_arxiv() → PaperRecord (KHÔNG sửa tim_arxiv)
│   ├── openalex_source.py
│   ├── semantic_scholar_source.py
│   ├── pubmed_source.py
│   └── crossref_source.py
└── topics/                                                                                [MỚI]
    ├── __init__.py        # re-export
    ├── registry.py        # TopicSpec, TOPIC_SPECS, build_topic_tools()  ← thêm chủ đề = thêm 1 dòng
    ├── topic_tool.py      # make_topic_tool(): gói agent con thành tool + grounding tầng 1 + artifact
    ├── budget.py          # check_topic_budget(): đếm lượt gọi chủ đề từ state
    ├── scholar_agent/
    │   ├── __init__.py    # re-export
    │   ├── agent.py       # TOPIC_NAME, TOPIC_DESCRIPTION, build_scholar_agent(model=None, tools=None, prompt=None)
    │   ├── tools.py       # default_scholar_tools(budget, profile)
    │   └── prompts.py     # SCHOLAR_AGENT_PROMPT
    └── explainer_agent/
        ├── __init__.py
        ├── agent.py       # TOPIC_NAME, TOPIC_DESCRIPTION, build_explainer_agent(...)
        ├── tools.py       # default_explainer_tools(budget, profile)
        └── prompts.py     # EXPLAINER_AGENT_PROMPT

tests/
├── test_research_sources.py          # [MỚI] parser + lỗi HTTP + khử trùng + tool lá (offline)
├── test_research_sources_network.py  # [MỚI] @pytest.mark.network, skip khi mất mạng/thiếu key
├── test_research_topics.py           # [MỚI] registry, topic tool, budget, grounding tầng 1, lead e2e
├── test_grounding_labels.py          # [MỚI] nhãn mới trong core/grounding.py (vùng chung)
├── research_fakes.py                 # [MỚI, chỉ khi tests/fakes.py không đủ] helper model giả riêng
└── fixtures/research/                # [MỚI] JSON/XML mẫu đã cắt gọn, mỗi file < 20KB, không chứa key

docs/research-topics/
├── SPEC_RESEARCH_TOPICS.md           # file này
└── PHASE1_REPORT.md                  # [MỚI] Claude Code viết ở cuối (§11)
```

Quy ước đặt tên agent chủ đề giống CT-05: **tên thư mục = `TOPIC_NAME` = tên tool = `name=` truyền vào `create_react_agent`** (ví dụ `scholar_agent`).

### 4.3 Phạm vi file được sửa

**Vùng của Research — sửa tự do:**
- `app/agents/research_agent/**`
- `tests/test_research_*.py`, `tests/research_fakes.py`, `tests/fixtures/research/**`
- Riêng `tests/test_research_tools.py` (test cũ): chỉ được **thêm** test, không xoá hay nới assert cũ. Mọi test cũ trong file này phải xanh nguyên trạng.
- `docs/research-topics/**`

**Vùng chung — được sửa tối thiểu, mọi thay đổi phải liệt kê trong báo cáo mục "Thay đổi vùng chung":**

| File | Được làm gì |
|---|---|
| `app/core/grounding.py` | Thêm bảng pattern nhãn mới (§5.6). **Không đổi chữ ký** hàm công khai hiện có; test grounding cũ phải xanh nguyên trạng. |
| `app/core/config.py` | Thêm các biến ở §5.12, theo đúng kiểu khai báo đang có. |
| `app/core/llm.py` | **Chỉ khi bắt buộc** để đăng ký vai trò `research_topic`. Nếu vai trò được đăng ký hoàn toàn trong `config.py` thì không đụng file này. |
| `.env.example` | Thêm biến mới, **chỉ ASCII**, giá trị trống hoặc ví dụ (DT-06, CH-04). |
| `tests/conftest.py` | **Chỉ** thêm tên biến mới vào `APP_ENV_VARS` (TS-06). |
| `tests/test_grounding_labels.py` | File test mới cho phần core. |

**CẤM sửa:**
- `tests/test_contract.py`, `tests/fakes.py`, `tests/test_agents_e2e.py`;
- `app/agents/__init__.py`, `app/agents/supervisor/**`, `app/agents/vision_agent/**`;
- `app/main.py`, `app/core/pretty.py` (được **import**, không được sửa), `app/core/contracts.py` (được import);
- `requirements.txt`, `pyproject.toml`, `.gitignore`, `README.md`, `QUY_TAC_THIET_KE.md`, `TRUOC_KHI_CHAY.md`, `CLAUDE.md`.

---

## 5. Đặc tả chi tiết

### 5.1 Công tắc kiến trúc và factory ngoài

`app/core/config.py` thêm thiết lập `RESEARCH_ARCH` ∈ {`single`, `topics`}, mặc định `single`. Giá trị khác → báo lỗi cấu hình rõ ràng, theo cách `config.py` đang báo lỗi.

`app/agents/research_agent/agent.py`:

```python
AGENT_NAME = "research_agent"        # KHÔNG ĐỔI (IF-02)
AGENT_DESCRIPTION = "..."            # KHÔNG ĐỔI ở Phase 1 (đề xuất đổi ghi trong ghi chú merge)

def build_research_agent(model=None, tools=None, prompt=None):
    """Điểm vào duy nhất theo hợp đồng IF-01/IF-03. Rẽ nhánh theo RESEARCH_ARCH."""
    from app.core.config import settings          # dùng đúng tên object/thuộc tính đang có
    if settings.research_arch == "topics":
        from app.agents.research_agent.lead import build_research_lead
        return build_research_lead(model=model, tools=tools, prompt=prompt)
    return _build_single_agent(model=model, tools=tools, prompt=prompt)  # = code hiện tại, nguyên hành vi
```

- `_build_single_agent` là phần thân hiện tại của `build_research_agent`, được dời nguyên vẹn vào hàm riêng.
- `RESEARCH_AGENT_PROMPT` phải **giữ nguyên từng byte**. Nếu tách khối GROUNDING ra thành `GROUNDING_RULES` thì chuỗi ghép lại vẫn phải y hệt bản cũ; viết test so sánh chuỗi.
- `default_research_tools()` giữ nguyên ý nghĩa: trả về tool lá cũ (`arxiv_search`, `wikipedia_search`). Tool của lead do `build_topic_tools()` cung cấp, không đi qua hàm này.

### 5.2 SearchProfile (`profiles.py`)

```python
@dataclass(frozen=True)
class SearchProfile:
    name: str                        # "eco" | "standard" | "full"
    paper_sources: tuple[str, ...]   # nguồn mà paper_search gọi, theo thứ tự
    per_source_limit: int            # số kết quả xin từ MỖI nguồn
    max_results: int                 # số bài giữ lại sau khử trùng + xếp hạng
    abstract_chars: int              # cắt abstract trước khi đưa cho LLM
    max_searches_per_topic: int      # trần lượt tìm kiếm cho MỘT lần gọi agent chủ đề
    max_lookups_per_topic: int       # trần doi_lookup cho MỘT lần gọi agent chủ đề
    max_topic_calls: int             # trần số lần lead gọi agent chủ đề cho MỘT câu hỏi
    inner_recursion_limit: int       # recursion_limit khi invoke agent chủ đề (LX-02)
```

Giá trị tạm thời (Phase 2 sẽ đo token rồi chỉnh):

| Trường | `eco` | `standard` (mặc định) | `full` |
|---|---|---|---|
| paper_sources | arxiv, openalex | arxiv, openalex, semantic_scholar | arxiv, openalex, semantic_scholar |
| per_source_limit | 2 | 3 | 5 |
| max_results | 3 | 5 | 8 |
| abstract_chars | 300 | 600 | 1000 |
| max_searches_per_topic | 2 | 3 | 5 |
| max_lookups_per_topic | 1 | 3 | 5 |
| max_topic_calls | 1 | 2 | 3 |
| inner_recursion_limit | 12 | 20 | 30 |

- `get_profile()` đọc `RESEARCH_MODE` qua `config.py`. Giá trị lạ → lỗi cấu hình rõ ràng.
- `RESEARCH_MAX_SEARCHES` (biến cũ): ở chế độ `single` giữ **nguyên ý nghĩa cũ**. Ở chế độ `topics`, nếu biến này được đặt thì nó **ghi đè** `max_searches_per_topic`.
- Mọi con số giới hạn ở §5.3–§5.10 phải **lấy từ profile**, không viết cứng ở chỗ khác.

### 5.3 Lớp nguồn dữ liệu (`sources/`)

**`PaperRecord`** (dataclass) — dạng chuẩn hoá chung cho mọi nguồn:

```python
@dataclass
class PaperRecord:
    title: str
    year: int | None
    published: str | None      # "YYYY-MM-DD" nếu có. arXiv: NGÀY NỘP (Published), KHÔNG dùng Last updated
    authors: list[str]
    venue: str | None
    abstract: str | None
    citations: int | None
    ids: dict[str, str]        # khoá ∈ {"arxiv","doi","pmid","openalex","s2"}
    url: str | None
    found_in: list[str]        # các nguồn đã trả về bài này

    def primary_label(self) -> str: ...
    # ưu tiên: arxiv > doi > pmid > openalex > s2 (xem định dạng nhãn ở §5.6)
```

**`SourceError(code, message)`** là exception **nội bộ** của lớp nguồn. Nó được bắt ở tầng tool và đổi thành chuỗi `ERROR:` hoặc thành dòng "Sources unavailable". Không bao giờ lọt ra khỏi tool (IF-05).

**`http_get(source, url, params=None, headers=None, timeout=15)`** — helper duy nhất gọi HTTP:
- Header `User-Agent: visual-agentic-ai/1.0 (mailto:<CONTACT_EMAIL>)` nếu có email.
- Gặp 429 hoặc 5xx → retry **1 lần** sau 2 giây. Hàm `sleep` phải tiêm được, để test không phải chờ thật.
- Ánh xạ lỗi:

| Tình huống | Mã lỗi |
|---|---|
| timeout / lỗi kết nối | `<SRC>_UNAVAILABLE` |
| 429 | `<SRC>_RATE_LIMITED` |
| mã HTTP khác không phải 2xx | `<SRC>_HTTP_ERROR` |
| body không phải JSON/XML hợp lệ | `<SRC>_BAD_RESPONSE` |

- `<SRC>` ∈ {`ARXIV`, `OPENALEX`, `SEMANTIC_SCHOLAR`, `PUBMED`, `CROSSREF`}.
- Không bao giờ log URL hay header chứa key. Phải che (mask) tham số `api_key` trong mọi log.

**Mỗi nguồn** có `search(query: str, limit: int) -> list[PaperRecord]`. Riêng Crossref có `lookup(doi: str) -> PaperRecord`.

> Tuân theo tinh thần MT-09: **đối chiếu tài liệu chính thức hiện hành** của từng API trước khi viết parser. Các chi tiết dưới đây đúng tại thời điểm soạn spec nhưng có thể đã đổi. Lệch nhỏ thì thích nghi và ghi vào báo cáo.

**arXiv** — bọc `tim_arxiv()` sẵn có, **không sửa** hàm đó và không đổi output của `arxiv_search`.
- Nếu `tim_arxiv()` chỉ trả chuỗi đã định dạng, được thêm một hàm có cấu trúc trong `tools.py`, dùng chung lõi. Điều kiện: `test_research_tools.py` phải xanh nguyên trạng.
- ID: `ids["arxiv"]` giữ cả version (ví dụ `2104.09864v5`). Nhãn dùng đúng dạng `http://arxiv.org/abs/<id>` như hiện tại.

**OpenAlex** — `GET https://api.openalex.org/works`
- Tham số: `search`, `per_page`, `select=id,doi,display_name,publication_year,publication_date,authorships,primary_location,cited_by_count,abstract_inverted_index,ids`, `api_key`.
- **Từ 02/2026 API bắt buộc có key** (miễn phí, có hạn mức theo ngày). Gọi search tốn phí hơn tra cứu theo ID/DOI, nên chỉ gọi search đúng số lần profile cho phép. Kiểm tra lại tại developers.openalex.org.
- **Thiếu `OPENALEX_API_KEY` → ném `SourceError("OPENALEX_NOT_CONFIGURED", ...)` mà không gọi HTTP.** `paper_search` coi đây là nguồn không khả dụng, không phải lỗi chết.
- Parse:
  - `id` → bỏ tiền tố URL, lấy dạng `W…`;
  - `doi` → bỏ tiền tố `https://doi.org/`, chuyển chữ thường;
  - abstract dựng lại từ `abstract_inverted_index` (sắp từ theo vị trí);
  - `venue` = `primary_location.source.display_name`;
  - `ids.pmid` (nếu có) → lấy phần số;
  - nếu `primary_location.landing_page_url` chứa `arxiv.org/abs/` thì rút mã arXiv.

**Semantic Scholar** — `GET https://api.semanticscholar.org/graph/v1/paper/search`
- Tham số: `query`, `limit`, `fields=paperId,title,abstract,year,publicationDate,authors,venue,citationCount,externalIds,url`.
- Header `x-api-key` chỉ gửi khi có `SEMANTIC_SCHOLAR_API_KEY`.
- Không có key thì hay dính 429 → được phép thất bại, `paper_search` vẫn trả kết quả từ các nguồn còn lại.
- `externalIds` cho `DOI`, `ArXiv`, `PubMed` → điền vào `ids`.

**PubMed (NCBI E-utilities)** — hai bước:
1. `GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi` với `db=pubmed&term=…&retmax=…&retmode=json`, kèm `tool=visual-agentic-ai`, `email`, `api_key` nếu có → lấy danh sách PMID.
2. `GET …/efetch.fcgi` với `db=pubmed&id=<danh sách phẩy>&retmode=xml` → parse bằng `xml.etree.ElementTree`:
   - `ArticleTitle`;
   - `AbstractText` (có thể nhiều đoạn, ghép lại);
   - năm lấy từ `PubDate/Year`, nếu không có thì lấy 4 số đầu của `MedlineDate`;
   - `Journal/Title`;
   - `AuthorList` (LastName + Initials);
   - `ArticleIdList` (lấy `doi`).

Không có key thì hạn mức thấp (khoảng 3 request/giây) — hai bước gọi tuần tự là ổn.

**Crossref** — `GET https://api.crossref.org/works/{doi}` với tham số `mailto` nếu có email.
- 404 → `SourceError("DOI_NOT_FOUND", ...)`.
- Parse:
  - `title[0]`;
  - năm lấy từ `issued.date-parts[0][0]`;
  - `container-title[0]`;
  - `author[].given/family`;
  - `is-referenced-by-count`;
  - `abstract` (JATS XML → bỏ thẻ).

**Khử trùng — `dedupe_records(records)`**
- Hai bản ghi là một bài nếu trùng một trong các khoá, xét theo thứ tự:
  1. DOI (chuẩn hoá chữ thường);
  2. mã arXiv **bỏ version**;
  3. PMID;
  4. tiêu đề chuẩn hoá (chữ thường, chỉ giữ `a-z0-9`, gộp khoảng trắng) **và** cùng năm (hoặc một bên thiếu năm).
- Gộp bản ghi:
  - hợp `ids` và `found_in`;
  - `abstract` dài nhất;
  - `citations` lớn nhất;
  - các trường còn lại lấy giá trị khác rỗng theo thứ tự nguồn arxiv > crossref > openalex > semantic_scholar > pubmed;
  - `published` của arXiv luôn thắng, vì đó là ngày nộp.

**Xếp hạng — `rank_records(records)`**
- Tiêu chí, theo thứ tự: số nguồn cùng tìm thấy (giảm dần) → thứ hạng tốt nhất trong các nguồn (tăng dần).
- Cắt còn `profile.max_results`.
- Viết thành một hàm riêng, để Phase 2 thay bằng chiến lược khác (Strategy) mà không đụng chỗ khác.

### 5.4 Tool lá mới (`paper_tools.py`)

`make_paper_tools(budget: SearchBudget, profile: SearchProfile) -> list[BaseTool]` trả về ba tool dưới đây. Cả ba đều tuân thủ:
- IF-04: đúng một tham số `text: str`, trả về `str`;
- IF-05: không raise; lỗi trả `"ERROR: <MÃ> | <thông điệp>"` qua `contracts.tool_error()`;
- IF-06: `return_direct=False`;
- IF-08: description tiếng Anh, nói rõ **khi nào dùng**;
- LX-05: "không có kết quả" phải trả câu thông báo, không trả chuỗi rỗng.

**`paper_search`**
- Description: *"Search scholarly papers (journal articles, conference papers, preprints) across arXiv, OpenAlex and Semantic Scholar at once, with duplicates merged. Use this FIRST whenever you need to find, list or cite research papers. Input: a short English keyword query (2-6 words). Not for plain definitions."*
- Xử lý theo thứ tự:
  1. Kiểm tra `SearchBudget`: từ chối truy vấn trùng, và từ chối khi quá `max_searches_per_topic`. Mỗi lần gọi tính **một** lượt, bất kể gọi bao nhiêu nguồn.
  2. Gọi **tuần tự** từng nguồn trong `profile.paper_sources`, mỗi nguồn `per_source_limit` kết quả.
  3. Nguồn nào lỗi thì ghi lại rồi đi tiếp.
  4. Khử trùng, xếp hạng, định dạng theo §5.5.
  5. Nếu **mọi** nguồn đều lỗi → `ERROR: ALL_SOURCES_FAILED | arxiv: <mã>; openalex: <mã>; …`.

**`pubmed_search`**
- Description: *"Search PubMed for biomedical and clinical literature (medicine, biology, health, genetics, pharmacology). Use IN ADDITION to paper_search when the question is biomedical. Input: English keywords."*
- Dùng chung `SearchBudget` với `paper_search`.

**`doi_lookup`**
- Description: *"Look up authoritative metadata (title, year, venue, authors) of ONE paper by its DOI via Crossref. Use it to verify a paper's year or venue before stating them. Input: a DOI like 10.xxxx/yyyy."*
- Có trần riêng `max_lookups_per_topic`, không ăn vào ngân sách tìm kiếm.
- Tra trùng DOI thì trả lại kết quả đã có, **không** gọi lại API.

### 5.5 Định dạng kết quả tool lá — thứ LLM đọc

Kết quả phải **mang đủ dữ liệu để trích dẫn** (bài học số 4): nhãn chép được nguyên văn, ngày nộp đúng.

```
paper_search results for "rotary position embedding"
Sources: arxiv, openalex, semantic_scholar | 5 papers after merging 9 hits
Sources unavailable: semantic_scholar (SEMANTIC_SCHOLAR_RATE_LIMITED)

[1] Title: <tiêu đề>
    Label: [http://arxiv.org/abs/2104.09864v5]
    Other IDs: doi:<doi> | openalex:<W…>
    Published: 2021-04-20 | Venue: <venue hoặc "n/a"> | Citations: <n hoặc "n/a">
    Authors: <A>, <B>, <C> et al.
    Found in: arxiv, openalex
    Abstract: <cắt còn abstract_chars ký tự>…

[2] …

Cite every claim with the exact Label of the paper it comes from. Use the Published date for the year.
```

- Dòng `Sources unavailable:` chỉ xuất hiện khi có nguồn lỗi.
- `Authors`: tối đa 3 tên, sau đó ghi `et al.`
- Không có kết quả: `No papers found for "<q>" in arxiv, openalex, semantic_scholar. Try broader or different English keywords.`
- Mọi mã trong `Label:` và `Other IDs:` đều nằm trong văn bản tool trả về, nên grounding dùng được làm bằng chứng.

### 5.6 Nhãn nguồn và mở rộng `app/core/grounding.py`

| Loại | Nhãn trong câu trả lời | ID dùng để đối chiếu | Chuẩn hoá khi so |
|---|---|---|---|
| arxiv | `[http://arxiv.org/abs/2104.09864v5]` (chấp nhận `https`) | mã arXiv | giữ hành vi hiện tại |
| wikipedia | `[wikipedia: <Page title>]` | tên trang | giữ hành vi hiện tại |
| doi | `[doi: 10.1234/abc.567]` | DOI | chữ thường, bỏ tiền tố `https://doi.org/`, bỏ dấu câu ở cuối |
| pmid | `[pmid: 12345678]` | dãy số | — |
| openalex | `[openalex: W1234567890]` | `W` + số | viết hoa chữ `W` |
| s2 | `[s2: <40 ký tự hex>]` | 40 hex | chữ thường |

**Cách mở rộng.** Thêm vào `grounding.py` một **bảng đăng ký loại nhãn**: mỗi loại gồm regex nhãn, regex mã trần, và hàm chuẩn hoá. Các hàm hiện có dùng bảng này thay cho regex viết cứng. Thêm loại nhãn về sau chỉ cần thêm một mục vào bảng.

Ngữ nghĩa ba loại vi phạm:
- `NHAN_BIA`: nhãn (bất kỳ loại nào) mà ID đã chuẩn hoá **không xuất hiện** trong văn bản bằng chứng (bằng chứng cũng chuẩn hoá cùng cách).
- `MA_BIA`: mã trần xuất hiện trong câu trả lời — trong hay ngoài nhãn đều tính — nhưng không có trong bằng chứng. Mã trần gồm: mã arXiv; DOI theo mẫu `10\.\d{4,9}/[^\s\]\)]+`; PMID **chỉ khi** đứng sau chữ `PMID`/`pmid:`; `W\d{6,}`. Không bắt số trần ngẫu nhiên.
- `THIEU_NGUON`: giữ nguyên định nghĩa; "có nhãn" giờ nhận mọi loại trong bảng.

**Ràng buộc bắt buộc:**
- Không đổi chữ ký hàm công khai.
- Test grounding cũ xanh nguyên trạng.
- **Dùng đúng hàm tách câu hiện có** (đã vá lỗi cắt nhãn đứng sau dấu chấm — bài học số 5), không viết hàm tách câu mới.

**Chính sách xử lý** (`research_agent/grounding_policy.py`, vùng Research):

```python
def apply_grounding_policy(answer: str, evidence: str) -> tuple[str, dict]:
    """Trả (answer_đã_làm_sạch, report).
    - Dòng đặc biệt 'KHONG DU DU LIEU:' hoặc 'CAN_LAM_RO:' → trả nguyên, report rỗng.
    - Xoá câu có MA_BIA hoặc NHAN_BIA.
    - THIEU_NGUON → giữ câu, chỉ đếm.
    - Xoá hết câu có nội dung → answer = 'KHONG DU DU LIEU: sources could not support a cited answer'.
    report = {"removed": int, "missing_source": int, "violations": [{"code","sentence","detail"}]}
    """
```

Nếu `grounding.py` không trả đủ thông tin theo từng câu để làm việc này, được thêm vào core **đúng một** hàm công khai nhỏ, rồi ghi vào báo cáo.

### 5.7 Khung agent chủ đề (`topics/`)

**Đăng ký** (`topics/registry.py`):

```python
@dataclass(frozen=True)
class TopicSpec:
    name: str              # "scholar_agent": snake_case, hậu tố _agent, trùng tên thư mục và tên tool
    description: str       # tiếng Anh, ≥ 20 ký tự, nói KHI NÀO dùng và KHI NÀO KHÔNG (IF-08)
    build: Callable[..., Any]                                        # build_<name>(model=None, tools=None, prompt=None)
    default_tools: Callable[[SearchBudget, SearchProfile], list]     # tool lá của agent này

TOPIC_SPECS: tuple[TopicSpec, ...] = (
    TopicSpec(scholar.TOPIC_NAME, scholar.TOPIC_DESCRIPTION, scholar.build_scholar_agent, scholar.default_scholar_tools),
    TopicSpec(explainer.TOPIC_NAME, explainer.TOPIC_DESCRIPTION, explainer.build_explainer_agent, explainer.default_explainer_tools),
)

def build_topic_tools(profile: SearchProfile, model=None, specs=TOPIC_SPECS) -> list[BaseTool]: ...
```

**Gói agent thành tool** (`topics/topic_tool.py`) — `make_topic_tool(spec, *, profile, model=None) -> BaseTool`:

- `name = spec.name`, `description = spec.description`, `return_direct=False`, `response_format="content_and_artifact"`.
- Schema tham số mà LLM thấy **chỉ có `text: str`**. State của lead được tiêm vào qua `InjectedState` của `langgraph.prebuilt` và phải bị ẩn khỏi schema. Viết test khẳng định `args_schema` chỉ có `text`.

Luồng xử lý một lần gọi:

1. `text` rỗng → `ERROR: EMPTY_QUERY | …`.
2. **TopicBudget** (`topics/budget.py`) — đếm trong code, dựa trên state đã tiêm vào, không dùng biến toàn cục:
   - xét các `ToolMessage` của tool chủ đề **nằm sau `HumanMessage` cuối cùng**;
   - số lần gọi ≥ `profile.max_topic_calls` → `ERROR: TOPIC_BUDGET_EXCEEDED | …`;
   - cùng chủ đề và cùng `text` đã chuẩn hoá → `ERROR: TOPIC_DUPLICATE_CALL | …`;
   - vì không có trạng thái toàn cục nên không cần cơ chế reset.
3. Tạo **`SearchBudget` mới** cho lần gọi này, trần `profile.max_searches_per_topic`. Lấy `tools = spec.default_tools(budget, profile)`, rồi `agent = spec.build(model=model, tools=tools)`. Nếu `model` là `None`, agent chủ đề tự lấy `get_llm("research_topic")`.
4. `agent.invoke({"messages": [HumanMessage(text)]}, config={"recursion_limit": profile.inner_recursion_limit})`.
   - `GraphRecursionError` → `ERROR: TOPIC_RECURSION_LIMIT | …`.
   - Lỗi 429 / hết hạn mức → `ERROR: LLM_RATE_LIMITED | role research_topic — run python -m app.main --config`.
   - Mọi exception khác → `ERROR: TOPIC_AGENT_FAILED | <TênLớp>: <thông điệp ≤ 200 ký tự>`.
   - Tuyệt đối không raise (IF-05).
5. Thu thập kết quả:
   - `answer_raw`: text của `AIMessage` cuối cùng, lấy bằng `app.core.pretty.message_text()`;
   - `evidence_text`: nối nội dung mọi `ToolMessage` trong lần chạy;
   - `trace`: dựng từ danh sách message (§5.13).
6. **Grounding tầng 1:** `apply_grounding_policy(answer_raw, evidence_text)`.
7. Trả về `(content, artifact)`:

```jsonc
// content — CHUỖI JSON gọn (json.dumps, ensure_ascii=False), đây là thứ LLM của lead đọc
{"topic": "scholar_agent", "status": "ok",          // "ok" | "no_data"
 "sub_question": "...", "answer": "... [label]",
 "labels": ["[http://arxiv.org/abs/...]", "[doi: ...]"],
 "grounding": {"removed": 0, "missing_source": 1}}
```

```jsonc
// artifact — dict đầy đủ, KHÔNG gửi cho LLM
{"topic": "...", "sub_question": "...", "profile": "standard",
 "answer_raw": "...", "answer_final": "...", "evidence_text": "<toàn bộ output các tool lá>",
 "grounding_report": {...}, "trace": [...],
 "usage": {"llm_calls": 3, "tool_calls": 2, "elapsed_ms": 4210}}
```

- `status="no_data"` khi câu trả lời cuối bắt đầu bằng `KHONG DU DU LIEU:`.
- Lỗi ở bước 1, 2, 4 thì `content` là chuỗi `ERROR: …` và artifact ghi lý do lỗi.
- Nếu `response_format="content_and_artifact"` không hoạt động với bản `langchain-core` đang ghim, được dùng phương án tương đương giữ artifact ngoài context LLM. Ghi rõ vào báo cáo. Không dùng được phương án nào → DỪNG.

### 5.8 `scholar_agent`

- `TOPIC_NAME = "scholar_agent"`
- `TOPIC_DESCRIPTION`: *"Use to FIND, compare or cite scholarly papers (journal articles, conference papers, preprints) in any research field, including biomedical. Returns a short cited summary of the most relevant papers. Do NOT use for plain definitions or explanations of a concept; use explainer_agent for that."*
- Tool: `paper_search`, `pubmed_search`, `doi_lookup`, lấy từ `make_paper_tools(budget, profile)`.
- `build_scholar_agent(model=None, tools=None, prompt=None)` theo khung IF-01/IF-03: `create_react_agent(..., name=TOPIC_NAME)`.

`SCHOLAR_AGENT_PROMPT` (tiếng Anh) phải nêu đủ:
- **Vai trò:** chuyên gia tìm tài liệu, chỉ dựa vào kết quả tool.
- **Cách truy vấn:** từ khoá tiếng Anh 2–6 từ. Gọi `paper_search` trước; câu hỏi y sinh/lâm sàng thì gọi thêm `pubmed_search`. Chỉ gọi `doi_lookup` để xác nhận năm/venue của bài **sắp trích**.
- **Năm xuất bản:** lấy từ `Published`, không bao giờ lấy từ `Last updated`. Không lặp lại truy vấn giống hệt. Dừng khi đã đủ tài liệu.
- **Đầu ra:** ≤ 200 từ, tiếng Anh, gồm các bài liên quan nhất, mỗi bài 1–2 câu. **Mỗi câu kết thúc bằng nhãn chép nguyên văn từ dòng `Label:`** (hoặc dòng tương đương của tool cũ).
- **Không đủ dữ liệu:** trả đúng một dòng `KHONG DU DU LIEU: <thiếu gì>`.
- Chèn nguyên khối `GROUNDING_RULES`.

### 5.9 `explainer_agent`

- `TOPIC_NAME = "explainer_agent"`
- `TOPIC_DESCRIPTION`: *"Use to EXPLAIN a scientific or technical concept, definition, mechanism or background (what is X, how does X work, why does X happen). Returns a short cited explanation based mainly on Wikipedia. Do NOT use to find or list research papers; use scholar_agent for that."*
- Tool: `wikipedia_search` và `arxiv_search` — **tái dùng tool cũ**, cùng tên, cùng hành vi.
  - Hai tool này phải dùng `SearchBudget` được truyền vào.
  - Nếu hiện chúng gắn với một ngân sách toàn cục, được refactor `tools.py` để nhận ngân sách qua factory. Điều kiện: không đổi tên tool, không đổi output, `test_research_tools.py` và `test_contract.py` xanh nguyên trạng.

`EXPLAINER_AGENT_PROMPT` (tiếng Anh) phải nêu đủ:
- **Vai trò:** giải thích cho người học, đi từ ý cơ bản lên ý sâu hơn.
- **Nguồn:** gọi `wikipedia_search` trước; chỉ gọi `arxiv_search` khi một khẳng định cụ thể cần bài báo làm dẫn chứng.
- **Đầu ra:** ≤ 200 từ, tiếng Anh, mỗi câu kết thúc bằng nhãn.
- **Không đủ dữ liệu:** `KHONG DU DU LIEU: …`.
- Chèn nguyên khối `GROUNDING_RULES`.

### 5.10 Research lead (`lead.py`)

```python
def build_research_lead(model=None, tools=None, prompt=None, profile=None):
    profile = profile or get_profile()
    if model is None:  model = get_llm("research")                 # vai trò cũ, không đổi
    if tools is None:  tools = build_topic_tools(profile)          # agent chủ đề tự lấy "research_topic"
    if prompt is None: prompt = render_lead_prompt(TOPIC_SPECS, profile)
    return create_react_agent(model=model, tools=tools, prompt=prompt,
                              name=AGENT_NAME,                      # "research_agent" — IF-02
                              post_model_hook=_grounding_hook)
```

**Prompt của lead** — `render_lead_prompt()` ghép `RESEARCH_LEAD_PROMPT_TEMPLATE` (tiếng Anh, trong `prompts.py`) với danh sách chủ đề sinh từ `TOPIC_SPECS`. Không hard-code tên chủ đề trong template. Nội dung bắt buộc:

1. **Vai trò:** research lead điều phối các agent chuyên trách; **không bao giờ trả lời bằng kiến thức riêng**.
2. **Quy trình:**
   - (a) xác định câu hỏi cần những chủ đề nào;
   - (b) nếu cần nhiều chủ đề, tách thành các câu con **tiếng Anh, tự đủ nghĩa**, mỗi chủ đề một câu;
   - (c) gọi từng tool chủ đề **một lần một cái, tuần tự**, không bao giờ gọi lại cùng một câu con;
   - (d) tối đa `{max_topic_calls}` lượt gọi — nếu câu hỏi có nhiều phần hơn, chỉ phủ phần quan trọng nhất và nói rõ phần nào chưa được phủ;
   - (e) tổng hợp.
3. **Làm rõ:** chỉ khi câu hỏi có từ hai nghĩa hợp lý trở lên dẫn tới những lần tìm kiếm khác nhau, và ngữ cảnh không phân định được → trả **đúng một dòng** `CAN_LAM_RO: <câu hỏi lại, bằng ngôn ngữ của người dùng>`, không gọi tool.
4. **Xử lý lỗi:**
   - tool trả `ERROR: LLM_RATE_LIMITED` → dừng và báo lỗi đó;
   - lỗi khác → dùng kết quả còn lại và nói rõ phần bị thiếu;
   - mọi chủ đề đều `no_data` → `KHONG DU DU LIEU: …`.
5. **Tổng hợp:**
   - trả lời bằng **ngôn ngữ của người dùng**;
   - mỗi câu kết thúc bằng nhãn **chép nguyên văn** từ `answer` hoặc `labels` của agent chủ đề — không tạo, không rút gọn, không sửa nhãn;
   - không thêm dữ kiện không có trong câu trả lời của agent chủ đề;
   - định dạng đầu ra cho supervisor theo đúng phần output của `RESEARCH_AGENT_PROMPT` hiện tại.

**Grounding tầng 2** — `_grounding_hook(state)`, chạy sau mỗi lượt gọi model của lead:
- Chỉ xử lý khi `AIMessage` cuối **không có `tool_calls`**, tức là câu trả lời cuối.
- `evidence` = nối `artifact["evidence_text"]` của mọi `ToolMessage` tool chủ đề nằm sau `HumanMessage` cuối.
- Chạy `apply_grounding_policy(answer, evidence)`.
  - Có câu bị xoá → **thay** `AIMessage` cuối bằng bản đã làm sạch (giữ nguyên `id` để reducer `add_messages` thay thế), và thêm một dòng cuối `(Đã lược bỏ N câu có nguồn không xác minh được.)`.
  - Không có `ToolMessage` chủ đề nào (lead trả lời không qua tool) và câu trả lời không phải dòng đặc biệt → vẫn áp chính sách như trên, thêm dòng `(Câu trả lời này không dựa trên nguồn đã tra cứu.)`.
- Báo cáo grounding ghi vào `response_metadata["grounding"]` của message và vào `logging`. **Không** ghi vào `additional_kwargs`, vì trường này có thể bị gửi ngược lại cho provider ở lượt sau.

**Kiểm tra tương thích (bước B0):**
- Xác nhận bản `langgraph` đang cài có `post_model_hook` trong `create_react_agent` và hook hoạt động (chú ý tham số `version` nếu có).
- Xác nhận `InjectedState` hoạt động.
- Phương án dự phòng nếu `post_model_hook` không dùng được: một `StateGraph` nhỏ `lead_subgraph → grounding_node`, compile với `name="research_agent"`. Phương án này chỉ được chọn nếu `test_contract.py` và `test_agents_e2e.py` vẫn xanh; nếu không → DỪNG.

### 5.11 Mã lỗi (LX-01)

| Mã | Nơi phát sinh |
|---|---|
| `EMPTY_QUERY` | mọi tool mới khi `text` rỗng |
| `ARXIV_*`, `OPENALEX_*`, `SEMANTIC_SCHOLAR_*`, `PUBMED_*`, `CROSSREF_*` với hậu tố `_UNAVAILABLE`, `_RATE_LIMITED`, `_HTTP_ERROR`, `_BAD_RESPONSE`, `_NOT_CONFIGURED` | lớp nguồn (§5.3) |
| `ALL_SOURCES_FAILED` | `paper_search` khi mọi nguồn đều lỗi |
| `DOI_NOT_FOUND`, `INVALID_DOI` | `doi_lookup` |
| `SEARCH_BUDGET_EXCEEDED`, `DUPLICATE_QUERY` | ngân sách tìm kiếm — **dùng đúng mã mà `SearchBudget` hiện có đang dùng** nếu đã có mã |
| `LOOKUP_BUDGET_EXCEEDED` | `doi_lookup` |
| `TOPIC_BUDGET_EXCEEDED`, `TOPIC_DUPLICATE_CALL`, `TOPIC_RECURSION_LIMIT`, `TOPIC_AGENT_FAILED`, `LLM_RATE_LIMITED` | tool chủ đề (§5.7) |

### 5.12 Cấu hình và biến môi trường

Tất cả biến đọc **chỉ trong `config.py`** (CH-02); thêm vào `.env.example` (chỉ ASCII — DT-06) và vào `APP_ENV_VARS` trong `tests/conftest.py` (TS-06).

| Biến | Mặc định | Bắt buộc? | Ghi chú |
|---|---|---|---|
| `RESEARCH_ARCH` | `single` | không | `single` \| `topics` |
| `RESEARCH_MODE` | `standard` | không | `eco` \| `standard` \| `full` |
| `MODEL_RESEARCH_TOPIC` | (trống) | **có khi** `RESEARCH_ARCH=topics` và chạy thật | vai trò `research_topic`, kèm tiền tố provider (CH-06). Gợi ý trong `.env.example`: `groq:qwen/qwen3.6-27b` — phải khác model của 5 vai trò còn lại; kiểm lại bằng `--models` (MT-09) |
| `OPENALEX_API_KEY` | (trống) | không | thiếu → bỏ qua OpenAlex (`OPENALEX_NOT_CONFIGURED`). Lấy miễn phí tại openalex.org, mỗi người một key |
| `SEMANTIC_SCHOLAR_API_KEY` | (trống) | không | không có key vẫn chạy nhưng hay dính 429 |
| `NCBI_API_KEY` | (trống) | không | tăng hạn mức PubMed |
| `CONTACT_EMAIL` | (trống) | không | dùng cho User-Agent, `mailto` của Crossref, `email` của NCBI. **Nếu `config.py` đã có biến email/contact (vd cho User-Agent Wikipedia) thì dùng lại biến đó**, không tạo biến mới |
| `RESEARCH_MAX_SEARCHES` | (đã có) | không | xem §5.2 |

Nếu `--config` của `main.py` liệt kê vai trò bằng cách đọc từ `config.py`, vai trò mới sẽ tự hiện. Nếu không, **không sửa `main.py`** — ghi vào ghi chú merge.

### 5.13 Vết thực thi (phục vụ Visual Agentic AI)

`artifact["trace"]` là danh sách bước, dựng từ message của agent chủ đề:

```jsonc
{"step": 1, "kind": "tool_call",   "tool": "paper_search", "input": "<≤200 ký tự>"}
{"step": 2, "kind": "tool_result", "tool": "paper_search", "output_chars": 3120, "error_code": null}
{"step": 3, "kind": "final",       "output_chars": 812}
```

- Kèm `usage`: `llm_calls` (số `AIMessage`), `tool_calls`, `elapsed_ms` (đo bằng `time.perf_counter` quanh lần `invoke`).
- Phase 1 **không** dựng UI. Chỉ cần artifact có mặt trong `ToolMessage` của state, để UI hoặc supervisor đọc được về sau qua `stream(..., stream_mode="updates")`.
- Mỗi lần gọi chủ đề ghi thêm một dòng `logging.info` gồm chủ đề, trạng thái, số lượt gọi LLM, số lượt gọi tool, thời gian, và số câu bị grounding xoá.

---

## 6. Luồng mẫu

**Một chủ đề** — *"Find recent papers on rotary position embedding"*
1. Lead quyết định: cần `scholar_agent` → gọi tool đó với `text = "recent papers on rotary position embedding"`.
2. Bên trong `scholar_agent`: gọi `paper_search("rotary position embedding")`. Có thể gọi thêm `doi_lookup` cho 1–2 bài. Sau đó viết câu trả lời có nhãn.
3. Grounding tầng 1 chạy → content JSON được trả về cho lead.
4. Lead viết câu trả lời cuối → grounding tầng 2 chạy → trả về supervisor.

**Hai chủ đề** — *"Transformer là gì, và có bài báo nào gần đây về giảm bộ nhớ của attention?"*
1. Lead tách thành hai câu con:
   - `explainer_agent("What is the Transformer architecture in deep learning?")`;
   - **sau đó** `scholar_agent("recent papers on reducing attention memory usage")`.
2. Lead tổng hợp bằng tiếng Việt, giữ nguyên nhãn của cả hai phần.
3. Nếu `RESEARCH_MODE=eco` (`max_topic_calls=1`): lead chỉ gọi một chủ đề và nói rõ phần còn lại chưa được tra.

**Mơ hồ** — *"Tìm tài liệu về Mercury"* (hành tinh, nguyên tố, ca sĩ, hay ngôn ngữ lập trình?)
→ Lead không gọi tool nào, trả đúng một dòng `CAN_LAM_RO: Bạn muốn tìm về Mercury nào — hành tinh, nguyên tố thuỷ ngân, hay …?`

## 7. Ước lượng lượt gọi LLM

Số liệu để tính hạn mức; Phase 2 sẽ đo lại bằng số thật.

| Loại câu hỏi | `single` (cũ) | `topics`, một chủ đề | `topics`, hai chủ đề |
|---|---|---|---|
| Gọi thẳng `--agent research_agent` | ~4 | ~5–6 (lead 2 + chủ đề 3–4) | ~8–10 (lead 2–3 + 2×3–4) |
| Qua supervisor | ~5–6 | ~7–8 | ~10–12 |

Lượt gọi tách làm hai sổ: vai trò `research` (lead) và `research_topic` (agent chủ đề) — D8.

## 8. Kiểm thử

Mọi test dưới đây chạy **offline**, dùng model giả và gọi HTTP giả (monkeypatch `requests`/`http_get`), riêng `test_research_sources_network.py` là ngoại lệ. Mỗi tool mới có **ít nhất một ca đúng và một ca lỗi** (TS-04).

**`tests/test_research_sources.py`**
- Parser của từng nguồn đọc fixture ra `PaperRecord` đúng:
  - OpenAlex: dựng lại abstract từ inverted index; rút `W…`, DOI, PMID;
  - Semantic Scholar: đọc `externalIds`;
  - PubMed: XML nhiều đoạn abstract; `MedlineDate`;
  - Crossref: `date-parts`; bỏ thẻ JATS;
  - arXiv: `published` là ngày nộp.
- `http_get`: timeout → `*_UNAVAILABLE`; 429 → retry một lần (với `sleep` giả) rồi `*_RATE_LIMITED`; body hỏng → `*_BAD_RESPONSE`; key không bao giờ xuất hiện trong log (dùng `caplog`).
- OpenAlex thiếu key → `OPENALEX_NOT_CONFIGURED`, **không có lời gọi HTTP nào**.
- Khử trùng:
  - cùng bài từ arXiv + OpenAlex + Semantic Scholar gộp thành 1 (qua DOI, qua mã arXiv khác version, qua tiêu đề + năm);
  - hai bài khác nhau cùng tiêu đề nhưng khác năm xa nhau thì **không** gộp;
  - `published` của arXiv thắng khi gộp.
- `paper_search`:
  - định dạng đúng §5.5 (có `Label:`, abstract bị cắt đúng `abstract_chars`);
  - một nguồn lỗi → có dòng `Sources unavailable`;
  - mọi nguồn lỗi → `ERROR: ALL_SOURCES_FAILED`;
  - không có kết quả → câu thông báo khác rỗng;
  - truy vấn trùng / quá ngân sách → bị từ chối;
  - parser ném exception bất ngờ → vẫn trả chuỗi, không raise.
- `pubmed_search`, `doi_lookup`: mỗi tool một ca đúng, một ca lỗi. `doi_lookup` tra trùng DOI thì không gọi HTTP lần hai; vượt `max_lookups_per_topic` thì bị từ chối.
- Hợp đồng tool cho cả ba tool mới: tham số duy nhất `text`, `return_direct=False`, description tiếng Anh (chỉ ASCII) ≥ 20 ký tự.

**`tests/test_grounding_labels.py`** (vùng chung)
- Mỗi loại nhãn mới: nhãn hợp lệ → không vi phạm; nhãn bịa → `NHAN_BIA`; mã trần bịa → `MA_BIA`.
- DOI khác chữ hoa/thường hoặc có dấu chấm cuối câu → vẫn khớp.
- PMID không bị bắt nhầm từ một số trần bất kỳ.
- **Hồi quy:** nhãn đứng sau dấu chấm không bị tách thành câu riêng; mọi hành vi cũ của arXiv/Wikipedia không đổi.

**`tests/test_research_topics.py`**
- **Registry:**
  - tên chủ đề là snake_case, hậu tố `_agent`, không trùng nhau, trùng tên thư mục;
  - description là ASCII và ≥ 20 ký tự;
  - mỗi `TopicSpec.build(model=<fake>)` dựng được.
- **Topic tool:**
  - `args_schema` chỉ có `text`;
  - trả `str` trong content và có artifact;
  - model giả được lập kịch bản gọi `paper_search` (nguồn đã monkeypatch) rồi trả câu có nhãn hợp lệ → `status="ok"`, artifact có `evidence_text` và `trace`.
- **Grounding tầng 1:**
  - câu chứa mã arXiv bịa → câu bị xoá, `removed=1`;
  - câu không nhãn → được giữ, `missing_source` tăng;
  - mọi câu đều bịa → `status="no_data"`.
- **TopicBudget:**
  - với `standard`, lượt gọi thứ ba bị từ chối (`TOPIC_BUDGET_EXCEEDED`);
  - gọi trùng bị từ chối;
  - có `HumanMessage` mới thì bộ đếm tính lại từ đầu.
- **Lỗi bên trong:** agent con ném exception → `ERROR: TOPIC_AGENT_FAILED`; vượt đệ quy → `TOPIC_RECURSION_LIMIT`; 429 → `LLM_RATE_LIMITED`.
- **Lead e2e (model giả):**
  - câu hai chủ đề → gọi tuần tự hai tool, câu trả lời cuối qua được hook;
  - lead chèn một nhãn bịa → câu đó bị xoá và có dòng "Đã lược bỏ";
  - `CAN_LAM_RO:` và `KHONG DU DU LIEU:` đi qua nguyên vẹn.
- **Công tắc:**
  - mặc định (`RESEARCH_ARCH` không đặt) → `build_research_agent(model=<fake>)` dựng agent cũ với đúng tool `arxiv_search`, `wikipedia_search`;
  - `RESEARCH_ARCH=topics` → dựng lead, tên graph là `research_agent`;
  - `RESEARCH_AGENT_PROMPT` giữ nguyên từng byte (so với chuỗi chụp lúc B0).
- **Profile:** `RESEARCH_MODE=eco/full` đổi đúng các trần; giá trị lạ → lỗi cấu hình; `RESEARCH_MAX_SEARCHES` ghi đè đúng.

**`tests/test_research_sources_network.py`** — `@pytest.mark.network`, skip (không fail) khi mất mạng hoặc thiếu key (TS-03). Mỗi nguồn một truy vấn thật, chỉ kiểm tra *cấu trúc* kết quả, không kiểm tra nội dung cụ thể.

**Fixtures:** `tests/fixtures/research/`, cắt gọn bằng tay, mỗi file < 20KB, **không chứa key hay email thật**.

**Model giả:** dùng `tests/fakes.py` sẵn có. Nếu thiếu khả năng cần thiết (ví dụ lập kịch bản gọi tool nhiều lượt), viết helper trong `tests/research_fakes.py` — không sửa `fakes.py`.

## 9. Các bước thực thi Phase 1

Mỗi bước: code → test → `pytest -q -m "not network"` xanh → commit. Commit message dạng `<scope>: <việc>` (GIT-04), scope ∈ {`research`, `core`, `test`, `docs`}.

**B0 — Khảo sát (không sửa code)**
1. Kích hoạt venv (TRUOC_KHI_CHAY Phần 1). Ghi lại kết quả `git status` (phải sạch) và nhánh hiện tại.
2. Tạo nhánh `feat/research-topics` từ nhánh Research hiện tại. Không tạo từ `main`/`develop` trừ khi nhánh Research không tồn tại — trường hợp đó thì ghi vào báo cáo.
3. Chạy `python -m pytest -q -m "not network"` → ghi số test baseline. Đỏ → **DỪNG** (§0.4-3).
4. Đọc và ghi tóm tắt vào báo cáo:
   - `test_contract.py`: những gì nó khẳng định về `research_agent` — tên, factory, tool, cách quét thư mục; nó có quét đệ quy thư mục con của agent không?;
   - `test_agents_e2e.py`, `test_research_tools.py`;
   - `grounding.py`: API công khai và hàm tách câu;
   - `SearchBudget`: cách khởi tạo, cách reset, mã lỗi;
   - `tim_arxiv()`: kiểu trả về;
   - `config.py`/`llm.py`: cách khai báo một vai trò model;
   - `fakes.py`: khả năng lập kịch bản.
5. Kiểm tra bằng `python -c "import inspect; ..."`:
   - `create_react_agent` có `post_model_hook` không;
   - `langgraph.prebuilt.InjectedState` có tồn tại không;
   - `StructuredTool.from_function` có nhận `response_format` không.
6. Chụp lại chuỗi `RESEARCH_AGENT_PROMPT` để dùng làm test so sánh byte.
7. Nếu `test_contract.py` quét đệ quy và sẽ coi `topics/<x>_agent/` là vi phạm → **DỪNG** và đề xuất đổi cấu trúc (ví dụ đặt tên thư mục con không có hậu tố `_agent`).

**B1 — Cấu hình và profile**
- Thêm biến ở §5.12 vào `config.py`, `.env.example`, `conftest.APP_ENV_VARS`. Đăng ký vai trò `research_topic`.
- Viết `profiles.py` cùng test profile.

**B2 — Nhãn mới trong grounding (core)**
- Bảng loại nhãn trong `grounding.py`, `grounding_policy.py`, `test_grounding_labels.py`.
- Commit scope `core` tách riêng khỏi commit `research`, để lúc merge dễ review.

**B3 — Lớp nguồn**
- `sources/base.py` → `arxiv_source` → `openalex_source` → `semantic_scholar_source` → `pubmed_source` → `crossref_source`. Mỗi nguồn kèm fixture và test.
- Khử trùng và xếp hạng kèm test.

**B4 — Tool lá mới**
- `paper_tools.py` + test.
- Refactor nhẹ `tools.py` (nếu cần) để `arxiv_search`/`wikipedia_search` nhận ngân sách truyền vào, **không đổi hành vi cũ**.

**B5 — Khung chủ đề**
- `topics/budget.py`, `topics/topic_tool.py`, `topics/registry.py` (lúc này registry còn rỗng hoặc dùng một chủ đề giả trong test) + test.

**B6 — Hai agent chủ đề**
- `scholar_agent/`, `explainer_agent/` (agent, tools, prompts) + đăng ký vào `TOPIC_SPECS` + test.

**B7 — Research lead**
- `lead.py`, template prompt của lead, hook grounding tầng 2, rẽ nhánh trong `agent.py` + test e2e với model giả.
- Chạy `python -m app.main --graph` và `python -m app.main --config` (hai lệnh này không tốn lượt) để xác nhận graph và cấu hình vẫn ổn.

**B8 — Hoàn tất**
- Chạy toàn bộ `pytest -q -m "not network"`, rồi **một lần** `pytest -q -m network -k research_sources`.
- Rà: không có `print` trong `app/`; không có chuỗi giống key trong diff (`sk-`, `AIza`, `AQ.`, `gsk_`); `git diff --stat` không đụng file cấm.
- Viết `docs/research-topics/PHASE1_REPORT.md` (§11).

## 10. Nghiệm thu (Definition of Done)

### 10.1 Tự động — Claude Code tự xác nhận

- [ ] `python -m pytest -q -m "not network"` xanh 100%; số test ≥ baseline + các test mới.
- [ ] `git diff <điểm bắt đầu>..HEAD -- tests/test_contract.py tests/fakes.py tests/test_agents_e2e.py` **rỗng**.
- [ ] `git diff --stat` không có file nào trong danh sách cấm (§4.3).
- [ ] `requirements.txt` không đổi.
- [ ] `RESEARCH_ARCH` không đặt → hành vi cũ nguyên vẹn (đã có test).
- [ ] `python -m app.main --graph` chạy được, vẫn đủ node.
- [ ] `python -m app.main --config` chạy được.
- [ ] Không có `print(` mới trong `app/`; không có chuỗi giống key trong diff.
- [ ] `.env.example` chỉ chứa ASCII (test `test_file_cau_hinh_chi_dung_ascii` xanh).
- [ ] `PHASE1_REPORT.md` đã viết.

### 10.2 Thủ công — Tuấn chạy với key thật

**Chuẩn bị `.env`:**

```
RESEARCH_ARCH=topics
RESEARCH_MODE=standard
MODEL_RESEARCH_TOPIC=<model con song, kiem bang --models>
OPENALEX_API_KEY=<key rieng>
```

Chạy `--config`, `--models` và `pytest` trước. Sau đó chạy các ca dưới đây, từ rẻ đến đắt. Nên dùng `--agent research_agent` để tiết kiệm lượt (LX-06).

| Ca | Câu hỏi | Kỳ vọng |
|---|---|---|
| T1 Học thuật | `"Find recent papers on rotary position embedding"` | Chỉ gọi `scholar_agent`; ≥ 2 bài; mọi câu có nhãn; `KIEM TRA NGUON` / log grounding không có `MA_BIA` |
| T2 Giải thích | `"Giải thích cơ chế self-attention trong Transformer"` | Chỉ gọi `explainer_agent`; nhãn `[wikipedia: …]` |
| T3 Đa chủ đề | `"Transformer là gì, và có bài báo nào gần đây về giảm bộ nhớ của attention?"` | Gọi explainer rồi scholar, **tuần tự**; trả lời tiếng Việt; nhãn của cả hai phần được giữ nguyên |
| T4 Y sinh | `"Tìm nghiên cứu về liệu pháp CRISPR cho bệnh thiếu máu hồng cầu hình liềm"` | Có gọi `pubmed_search`; có nhãn `[pmid: …]` hoặc `[doi: …]` |
| T5 Mơ hồ | `"Tìm tài liệu về Mercury"` | Một dòng `CAN_LAM_RO: …`, không gọi tool |
| T6 Không dữ liệu | `"Tìm bài báo về thuật toán xqzvbn-7 công bố năm 2031"` | `KHONG DU DU LIEU: …`; không có nhãn bịa |
| T7 eco | Câu T3 với `RESEARCH_MODE=eco` | Chỉ một chủ đề được gọi; câu trả lời nói rõ phần chưa tra |
| T8 Hồi quy | Ca 1 của nhóm với `RESEARCH_ARCH=single` | Giống hệt trước khi nâng cấp |
| T9 Qua supervisor | `python -m app.main "What is the latest research on positional embeddings?"` với `topics` | Chạy trọn luồng, supervisor nhận câu trả lời có nhãn |

Ghi lại số lượt gọi LLM của từng ca (LangSmith project riêng — CH-05) → làm đầu vào cho Phase 2. Tổng cả bộ ước khoảng 60–90 lượt LLM và khoảng 20 lượt tìm kiếm OpenAlex.

## 11. Báo cáo cuối phase — `docs/research-topics/PHASE1_REPORT.md`

Claude Code viết theo khung sau:

1. **Tóm tắt** (≤ 10 dòng): đã làm gì, trạng thái DoD 10.1.
2. **Kết quả test:** số test baseline so với hiện tại; kết quả chạy `network`.
3. **Khảo sát B0:** tóm tắt các phát hiện ở bước B0.4–B0.5.
4. **Danh sách commit** (hash + message).
5. **Quyết định tự đưa ra** ở những chỗ spec không nói rõ, kèm lý do.
6. **Chỗ lệch spec** và lý do (ví dụ API thật khác mô tả).
7. **Thay đổi vùng chung:** từng file, từng thay đổi, vì sao cần — dùng thẳng cho PR merge.
8. **Việc còn mở / nợ kỹ thuật.**
9. **Hướng dẫn nghiệm thu thủ công** cho Tuấn: chép §10.2, cập nhật nếu có gì thay đổi.
10. **(Nếu có) ĐÃ DỪNG** — theo khung ở §0.4.

## 12. Ghi chú merge vào dự án nhóm

Làm sau khi Phase 1 ổn định và đã qua nghiệm thu thủ công.

- **PR từ `feat/research-topics` vào `develop`, tag cả 2 thành viên** vì có đụng vùng chung (Bảng 9):
  - `app/core/grounding.py` (bảng nhãn);
  - `app/core/config.py` (biến mới + vai trò `research_topic`);
  - có thể `app/core/llm.py`;
  - `.env.example`;
  - `tests/conftest.py`.
- **CH-06 đổi từ 5 vai trò thành 6.** Cả nhóm cần một model thứ sáu, và mỗi người tự lấy `OPENALEX_API_KEY` riêng.
- **Mặc định vẫn là `RESEARCH_ARCH=single`.** Chỉ đổi mặc định sang `topics` khi cả nhóm đồng ý, sau khi chạy đủ 5 ca demo của nhóm với `topics`.
- **Đề xuất cho người làm Supervisor** (không bắt buộc): khối `KIEM TRA NGUON` trong `main.py` hiện chỉ chạy khi thấy `arxiv_search`/`wikipedia_search` trong luồng. Ở chế độ `topics`, các tool này nằm bên trong agent chủ đề nên CLI không thấy. Grounding đã chạy bên trong `research_agent`, nên hệ thống vẫn an toàn. Nếu muốn CLI hiển thị, có thể đọc `ToolMessage.artifact["grounding_report"]`.
- **Đề xuất đổi `AGENT_DESCRIPTION`** của `research_agent` để phản ánh phạm vi mới (tìm bài báo + giải thích khái niệm). Đây là thứ supervisor đọc để route (IF-08), nên đổi phải báo nhóm.

## 13. Lộ trình các phase sau

**Phase 2 — Tiết kiệm token và đo đạc**
- Đo token thật của từng vai trò (lấy `usage_metadata` đưa vào `artifact.usage`), rồi chỉnh bảng số liệu eco/standard/full.
- Cache kết quả tìm kiếm ra JSON theo khoá (nguồn + truy vấn chuẩn hoá) có TTL — cũng là phao cho ngày demo.
- Cân nhắc xếp hạng bằng embedding local (`all-MiniLM-L6-v2`). Phải hỏi nhóm trước vì cần thêm thư viện.

**Checklist thêm một chủ đề mới** (dùng cho Phase 3–5):
1. Tạo `topics/<ten>_agent/` gồm `__init__.py` (chỉ re-export), `agent.py`, `tools.py`, `prompts.py`.
2. Thêm **một dòng** `TopicSpec` vào `TOPIC_SPECS`.
3. Khai báo định dạng nhãn nguồn của chủ đề. Nhãn mới thì thêm một mục vào bảng loại nhãn trong `grounding.py` (vùng chung → báo nhóm).
4. Tool mới tuân IF-04…IF-08 và LX-05; mỗi tool ≥ 2 test; có test grounding cho nhãn mới.
5. Thêm nguồn và giới hạn của chủ đề vào `SearchProfile` nếu cần.
6. Kiểm lại hạn mức và điều khoản sử dụng của API trước khi viết code (MT-09).

**Phase 3 — Kỹ thuật & Code (`code_agent`)**
- Nguồn dự kiến: GitHub REST API (search repo/code), Stack Exchange API, tài liệu chính thức của thư viện.
- Nhãn dự kiến: `[github: owner/repo]`, `[stackoverflow: <id>]`.
- Lưu ý: GitHub search không cần xác thực có hạn mức rất thấp.

**Phase 4 — Du lịch & Địa điểm (`travel_agent`)**
- Nguồn dự kiến: Wikivoyage (MediaWiki API), OpenStreetMap Nominatim (giới hạn khoảng 1 request/giây, bắt buộc có User-Agent).
- Nhãn dự kiến: `[wikivoyage: <Page>]`, `[osm: <type>/<id>]`.
- Quy tắc riêng: thông tin như giá hay giờ mở cửa **không phải thời gian thực**, agent phải nói rõ điều đó.

**Phase 5 — Văn hoá & Nghệ thuật (`culture_agent`)**
- Gộp văn chương và âm nhạc. Nguồn dự kiến: Open Library, Gutendex (Project Gutenberg), MusicBrainz (khoảng 1 request/giây, bắt buộc có User-Agent), Wikipedia.
- **Quy tắc cứng:** không chép lời bài hát hay đoạn văn có bản quyền — chỉ tóm tắt và phân tích. Tác phẩm thuộc phạm vi công cộng được trích ngắn. Nên có thêm một kiểm tra trong code giới hạn độ dài trích dẫn nguyên văn.

**Phase song song — UI và trực quan hoá:** đọc `ToolMessage.artifact["trace"]` để vẽ cây nhiệm vụ lead → chủ đề → tool.

## 14. Rủi ro và cách giảm

| Rủi ro | Cách giảm |
|---|---|
| Số lượt gọi LLM tăng khoảng 1,5–2 lần, cạn hạn mức | Tách sổ theo vai trò (D8); `SearchProfile`/`eco`; `RESEARCH_ARCH=single` làm đường lui lúc demo |
| Đụng trần 8K TPM của Groq, `400 output_parse_failed` | Content gửi cho lead được rút gọn, bằng chứng nằm trong artifact (D9); cắt abstract; context của agent con ngắn; trần lượt tìm kiếm |
| Lead làm rơi hoặc bịa nhãn khi tổng hợp | Grounding tầng 2 (post_model_hook) |
| Grounding xoá nhầm câu đúng | Chỉ xoá vi phạm nặng, so khớp chính xác (D4); test hồi quy cho hàm tách câu |
| Nguồn học thuật dính rate limit (nhất là Semantic Scholar không có key) | Chấp nhận nguồn lỗi một phần; retry một lần; dòng "Sources unavailable" |
| OpenAlex bắt buộc key từ 02/2026 | Thiếu key thì bỏ qua nguồn này, không làm hỏng luồng |
| Merge đụng vùng chung | Thay đổi tối thiểu, commit `core` tách riêng, ghi đủ trong báo cáo |
| Grounding chỉ kiểm nguồn **có tồn tại**, không kiểm nguồn **có nói đúng** điều được trích | Giới hạn đã biết (TRUOC_KHI_CHAY Phần 6). Để dành cho Citation Agent ở phase sau — đây cũng là câu trả lời cho câu hỏi "tại sao cần nhiều agent" khi bảo vệ |

---

## Phụ lục A — Đối chiếu với bản thiết kế (dùng khi bảo vệ)

| Bản thiết kế | Hiện thực trong spec này |
|---|---|
| "Hierarchical là hướng mở rộng" | Lead bên trong `research_agent` điều phối các agent chủ đề (D1) |
| `AgentRegistry` (mẫu Registry) | `TOPIC_SPECS` — thêm chủ đề bằng một dòng |
| `PaperSourceAdapter` (mẫu Adapter) | `sources/*_source.py` → `PaperRecord` |
| Strategy (xếp hạng / phân rã) | `rank_records()`, `SearchProfile` |
| `Budget`, `QueryConstraint` (Value Object) | `SearchProfile` (frozen dataclass), `SearchBudget`, TopicBudget |
| `SubTask` cha–con (Command / Composite, `parent_subtask_id`) | Mỗi lần lead gọi agent chủ đề là một sub-task con, có vết riêng |
| `trace_events` (Observer) → Agent Trace Visualizer | `artifact.trace` + `usage` + `logging` |
| Khử trùng `papers.doi` UNIQUE + `(source, external_id)` | `dedupe_records()` theo DOI → arXiv → PMID → tiêu đề + năm |
| Luồng UC02 `plan → dispatch → evaluate → synthesize` | Lead: xác định chủ đề và tách câu con → gọi tuần tự → grounding → tổng hợp |
| UC02.E1 yêu cầu làm rõ truy vấn | `CAN_LAM_RO:` |

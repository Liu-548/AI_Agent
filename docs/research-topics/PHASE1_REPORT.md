# PHASE1_REPORT — Research Agent phân chủ đề (Phase 1)

> Người thực thi: Claude Code · Ngày: 25/09/2026 · Nhánh: `feat/research-topics` (tách từ `main`)
> Spec: `docs/research-topics/SPEC_RESEARCH_TOPICS.md` v1.0

## 1. Tóm tắt

Đã làm xong B0–B8: khung agent chủ đề (`topics/`), hai agent chủ đề (`scholar_agent`, `explainer_agent`),
bốn nguồn học thuật mới (OpenAlex, Semantic Scholar, PubMed, Crossref) cạnh arXiv, khử trùng + xếp hạng,
`SearchProfile` (eco/standard/full), grounding hai tầng, research lead, công tắc `RESEARCH_ARCH=single|topics`
(mặc định `single`), vai trò model thứ sáu `research_topic`.

**DoD §10.1:** đạt toàn bộ (xem bảng cuối mục 2). **Chưa chạy** bất kỳ lệnh nào gọi LLM thật (§10.2 là việc của Tuấn).

Việc cần Tuấn quyết/đọc trước khi merge: mục 5 (quyết định tự đưa ra), mục 6 (chỗ lệch spec — quan trọng nhất:
repo đã khác mô tả của spec ở phần `openalex_search`, định dạng đầu ra và test hợp đồng), mục 8 (việc còn mở).

## 2. Kết quả test

| | Baseline (B0) | Hiện tại |
|---|---|---|
| `pytest -q -m "not network"` | 163 passed, 4 deselected | **272 passed**, 9 deselected |
| Test mới | — | +109 |
| `pytest -q -m network -k research_sources` (chạy 1 lần) | — | 3 passed (arXiv, PubMed, Crossref), 2 skipped |

Hai ca skip của test mạng: OpenAlex (không có key trong môi trường test — `conftest.py` xoá biến môi trường của dự án) và
Semantic Scholar (429 lúc chạy). Riêng Semantic Scholar tôi gọi tay thêm một lần bằng `openalex_source`/`semantic_scholar_source`
ngoài pytest: **parser đọc đúng dữ liệu thật** (2 bài, nhãn `[http://arxiv.org/abs/...]`). **OpenAlex chưa được kiểm chứng với API thật**
vì máy này chưa có `OPENALEX_API_KEY` — parser viết theo tài liệu/spec và fixture; xem mục 8.

| DoD §10.1 | Kết quả |
|---|---|
| `pytest -m "not network"` xanh, ≥ baseline + test mới | ✅ 272 ≥ 163 + 109 |
| `git diff` của `test_contract.py`, `fakes.py`, `test_agents_e2e.py` rỗng | ✅ |
| Không có file cấm trong `git diff --stat` | ✅ (đã kiểm từng file trong danh sách cấm §4.3) |
| `requirements.txt` không đổi | ✅ |
| `RESEARCH_ARCH` không đặt → hành vi cũ nguyên vẹn (có test) | ✅ `test_mac_dinh_la_agent_cu_voi_tool_cu` |
| `python -m app.main --graph` chạy được, đủ node | ✅ (cả `--agent research_agent` với `RESEARCH_ARCH=topics`: thấy thêm node `post_model_hook`) |
| `python -m app.main --config` chạy được | ✅ (hiện thêm dòng `research_topic` và `research: arch=… mode=…`) |
| Không có `print(` mới trong `app/`; không có chuỗi giống key trong diff | ✅ |
| `.env.example` chỉ ASCII (`test_file_cau_hinh_chi_dung_ascii`) | ✅ |
| `PHASE1_REPORT.md` đã viết | ✅ (file này) |

Ghi chú môi trường: `python -m app.main --config` trong PowerShell/pipe có thể lỗi `UnicodeEncodeError` (cp1258) — có sẵn từ trước, không
liên quan thay đổi này; đặt `PYTHONUTF8=1` là chạy được.

## 3. Khảo sát B0

- **Git:** không sạch lúc bắt đầu (xem mục 5, QĐ-1). Nhánh Research (`Research_Develop`) là tổ tiên của `main` (0 commit phía sau) nên tách từ `main`.
- **`test_contract.py`:** quét `AGENT_SPECS` (không quét đệ quy thư mục) → `topics/<x>_agent/` **không** bị coi là vi phạm. Khẳng định tên tool của `research_agent`
  bằng `default_research_tools()` = `{arxiv_search, openalex_search, wikipedia_search}` (**3 tool, không phải 2 như spec**), mỗi tool qua `validate_tool` (tham số duy nhất `text`, description ≥ 20 ký tự).
- **`grounding.py`:** hàm công khai `kiem_tra_grounding(answer, tool_texts) -> list[str]` (chuỗi dạng `"MA_BIA: …"`), `tach_cau`, `tach_danh_sach_nguon`, `bao_cao`.
  Hàm tách câu đã vá lỗi nhãn đứng sau dấu chấm (giữ nguyên, tôi dùng lại). Định dạng hiện tại hỗ trợ **trích dẫn số `[1]` + mục NGUỒN**.
- **`SearchBudget`:** `SearchBudget(max_calls=None)`, `.xin_luot(ten_tool, query)`, `.bat_dau_cau_hoi_moi()`; từ chối bằng **chuỗi thường** `DA TIM TRUY VAN NAY ROI` / `HET LUOT TIM KIEM` (không phải `ERROR:`). Tôi dùng lại đúng các chuỗi này.
  `make_arxiv_tool` / `make_wikipedia_tool` đã nhận `budget=` sẵn → **không phải refactor `tools.py`**.
- **`tim_arxiv()`:** trả `list[dict]` (`entry_id`, `published`, `updated`, `title`, `authors` là chuỗi, `summary`, `withdrawn`) — đủ để bọc, không sửa.
- **`config.py`/`llm.py`:** `settings` là frozen dataclass dựng lúc import; vai trò model nằm trong `_MODEL_SPEC_BY_ROLE` của **`llm.py`** (không phải `config.py`) → bắt buộc sửa `llm.py` để đăng ký `research_topic`.
- **`fakes.py`:** `FakeToolCallingModel` đủ để lập kịch bản nhiều lượt gọi tool → **không cần** `research_fakes.py`.
- **Tương thích LangGraph** (`langgraph 1.2.11`, `langchain-core 1.5.5`): `create_react_agent` có `post_model_hook`; `InjectedState` có; `StructuredTool.from_function` nhận `response_format`. Không cần phương án dự phòng.
- **Baseline prompt:** sha256 của `RESEARCH_AGENT_PROMPT` = `5cadb066…8d8c41` (4703 byte), dùng làm test so sánh byte (so bằng hash thay vì dán cả chuỗi vào test).

## 4. Danh sách commit (trên `main` cũ → `feat/research-topics`)

```
6b918da chore: prompt tra loi co dau tieng Viet + chinh UI (WIP truoc khi lam research topics)
8b2fd85 docs: them SPEC_RESEARCH_TOPICS vao docs/research-topics
9d10a40 core: them RESEARCH_ARCH/MODE, key nguon hoc thuat va vai tro research_topic
28fd087 research: them SearchProfile (eco/standard/full) va test
8dc2dc2 core: bang loai nhan trong grounding (DOI, PMID, OpenAlex ngan, Semantic Scholar)
eea33f1 research: grounding_policy xoa cau MA_BIA/NHAN_BIA, dem THIEU_NGUON
5f2f978 research: lop nguon hoc thuat (arXiv, OpenAlex, S2, PubMed, Crossref), khu trung, xep hang
fd11a34 research: tool la paper_search, pubmed_search, doi_lookup
e36a3ab research: TopicBudget dem luot goi agent chu de tu state cua lead
f21662d research: khung agent chu de (registry, topic tool, grounding tang 1) va test
1c27bfe research: scholar_agent (paper_search, pubmed_search, doi_lookup) va khoi GROUNDING_RULES
f7f8529 research: explainer_agent, dang ky hai chu de vao TOPIC_SPECS va test
d170b14 research: them RESEARCH_LEAD_PROMPT_TEMPLATE cho research lead
098c845 research: research lead + grounding tang 2 (post_model_hook), cong tac RESEARCH_ARCH
ff1ceb9 test: test mang that cho cac nguon hoc thuat (skip khi mat mang/thieu key)
7b42879 test: dung key gia luc chay thay vi literal giong key that
```

Ghi chú: commit `5f2f978` (lớp nguồn + fixture + test, ~800 dòng) và `098c845` lớn hơn giới hạn ~200 dòng của GIT-06 — tôi gộp theo module thay vì tách nhỏ hơn.

## 5. Quyết định tự đưa ra (spec không nói rõ)

- **QĐ-1 — Working tree không sạch + nhánh xuất phát.** Lúc bắt đầu có sửa đổi chưa commit của Tuấn (3 file `prompts.py` của research/supervisor/vision + `web/UI_style.html`).
  Tôi **đã hỏi Tuấn** và làm theo lựa chọn "commit WIP trước" (`6b918da`), rồi tách `feat/research-topics` từ `main`. Các file untracked khác (`KE_HOACH_NANG_CAP.md`, `assets/`, `graphify-out/`, `temp.md`, `docs/SPEC_RESEARCH_TOPICS.md`) không đụng.
  Spec được **sao** sang `docs/research-topics/` (bản gốc `docs/SPEC_RESEARCH_TOPICS.md` vẫn còn, untracked).
- **QĐ-2 — Biến `CONTACT_EMAIL` không tạo mới.** `config.py` đã có `openalex_mailto` (`OPENALEX_MAILTO`, mặc định placeholder `team@example.com`); dùng lại cho User-Agent, `mailto` của Crossref, `email` của NCBI (đúng chỉ dẫn §5.12).
- **QĐ-3 — `research_max_searches_set`.** Thêm cờ bool trong `Settings` để biết `RESEARCH_MAX_SEARCHES` có được đặt thật hay đang ở mặc định 6 — không có cờ này thì "ghi đè khi được đặt" (§5.2) không cài được.
- **QĐ-4 — Kiểm tra giá trị lạ** của `RESEARCH_ARCH`/`RESEARCH_MODE` làm **lúc dùng** (`settings.research_arch_hop_le()`, `research_mode_hop_le()` → `RuntimeError` kèm hướng dẫn), không lúc import, để một dòng `.env` sai không làm sập cả ứng dụng ở chế độ khác.
- **QĐ-5 — `PaperRecord.rank`.** Thêm trường `rank: int = 0` (vị trí trong danh sách của nguồn) vì `rank_records` cần "thứ hạng tốt nhất trong các nguồn" mà dataclass trong spec không có chỗ chứa.
- **QĐ-6 — Khử trùng theo tiêu đề cho phép lệch ≤ 1 năm** (spec: "cùng năm hoặc một bên thiếu năm"). Lý do: preprint arXiv 2021 và bản tạp chí 2023 của cùng một bài vẫn phải gộp; hai bài cùng tiêu đề nhưng cách nhau xa (2010 vs 2021) vẫn không gộp (có test).
- **QĐ-7 — Bài arXiv bị tác giả rút (`withdrawn`) bị bỏ** khỏi kết quả của `arxiv_source` (prompt cũ đã dặn không dùng làm căn cứ; bỏ luôn ở nguồn là chắc nhất).
- **QĐ-8 — `TopicBudget` đếm theo `tool_calls` của `AIMessage`** (không chỉ `ToolMessage` như §5.7) để xử lý được trường hợp lead gọi nhiều chủ đề trong CÙNG một lượt (ToolNode chạy song song nên `ToolMessage` chưa có). Lần gọi bị từ chối (trùng/quá trần) **không** tính vào ngân sách của lần sau. Cần `InjectedToolCallId` để biết đang xét lần gọi nào.
- **QĐ-9 — `apply_grounding_policy` chấm từng câu bằng chính `kiem_tra_grounding()` của core**, không thêm hàm công khai mới vào `grounding.py` (§5.6 cho phép thêm một hàm nhưng không cần). Với định dạng số `[n]` + mục NGUỒN: câu trích dẫn số của một mục NGUỒN bịa cũng bị xoá, và dòng nguồn bịa bị bỏ khỏi danh sách NGUỒN.
- **QĐ-10 — Nhãn trong bảng `LOAI_NHAN_MOI` phát hiện cả hai kiểu:** nhãn bịa → `NHAN_BIA` **và** mã trần bịa → `MA_BIA` (cùng một nhãn bịa có thể báo cả hai — chấp nhận, khác với arXiv chỉ báo `MA_BIA`). Sửa `ma_openalex_that` của core để coi cả dạng `openalex: W…` là bằng chứng cho dạng URL.
- **QĐ-11 — Lead xuất NGUỒN bằng nhãn bỏ ngoặc vuông** (`[1] wikipedia: Self-attention`, `[2] http://arxiv.org/abs/…`, `[3] doi: …`) — không có tiêu đề bài như `NGUỒN` của chế độ `single`, vì content gọn của agent chủ đề chỉ mang nhãn (D9). Hợp lệ với `kiem_tra_grounding` của core.
- **QĐ-12 — Ngôn ngữ đầu ra của lead:** theo ngôn ngữ người dùng (§5.10) nhưng ưu tiên tiếng Việt có dấu nếu người dùng viết tiếng Việt (khớp prompt supervisor hiện tại).
- **QĐ-13 — Test tách thêm file** thay vì dồn vào các file spec liệt kê: `test_research_paper_tools.py` (tool lá), `test_research_topic_tool.py` (khung + TopicBudget), `test_research_topic_agents.py` (registry + 2 agent thật), `test_research_lead.py` (lead + công tắc + hash prompt). `test_research_topics.py` chứa profile/config/policy. Cùng mẫu tên `tests/test_research_*.py` cho phép ở §4.3.
- **QĐ-14 — `MODEL_RESEARCH_TOPIC` để trống mặc định** (không đặt model thay Tuấn). `.env.example` chỉ **gợi ý** `groq:qwen/qwen3.6-27b` trong chú thích. Thiếu → agent chủ đề trả `ERROR: TOPIC_AGENT_FAILED | RuntimeError…` và lead báo phần bị thiếu, không sập.
- **QĐ-15 — Extra:** che chuỗi giống key (`gsk_`, `sk-`, `AIza`, `AQ.`) khỏi thông điệp lỗi của provider trước khi đưa vào `ERROR: TOPIC_AGENT_FAILED`; lỗi `requests` chỉ ghi tên lớp, không ghi URL (vì URL có `api_key`).
- **QĐ-16 — Cả hai tool `openalex_search` cũ và nguồn OpenAlex mới cùng tồn tại** (xem 6.1).

## 6. Chỗ lệch spec

1. **Repo đã có `openalex_search` (không cần key, dùng `mailto`).** Spec mô tả `research_agent` chỉ có `arxiv_search` + `wikipedia_search`. Chế độ `single` giữ nguyên 3 tool cũ (`test_contract.py` khẳng định đúng 3 tool nên không thể đổi).
   Nguồn OpenAlex mới (`sources/openalex_source.py`, bắt buộc `OPENALEX_API_KEY` theo spec) là **thêm vào**, dùng riêng cho `paper_search`. Hai chỗ dùng hai cách xác thực khác nhau — nên thống nhất sau (mục 8).
   Test công tắc mặc định vì thế khẳng định `{arxiv_search, openalex_search, wikipedia_search}` chứ không phải hai tool như §8 của spec.
2. **Định dạng trích dẫn khác giả định của spec.** `RESEARCH_AGENT_PROMPT` hiện tại dùng TÓM TẮT/CHI TIẾT/NGUỒN với trích dẫn số `[1]` và tiếng Việt; spec giả định nhãn cuối mỗi câu. Đã thích nghi: agent chủ đề trả **nhãn cuối câu** (§5.8 — apply_grounding_policy chấm từng câu), lead đổi sang **số + NGUỒN** (như agent cũ). Không sửa `RESEARCH_AGENT_PROMPT` (hash trùng baseline).
3. **`GROUNDING_RULES` là khối MỚI**, không tách ra từ `RESEARCH_AGENT_PROMPT` (prompt hiện tại dùng định dạng số, không dùng lại được cho agent chủ đề). Vì vậy không có test "chuỗi ghép lại y hệt" — thay bằng test hash byte của prompt cũ.
4. **`llm.py` bị sửa** (§4.3 chỉ cho phép "khi bắt buộc"): bắt buộc vì `_MODEL_SPEC_BY_ROLE` và `Role` nằm ở đó; thêm cả `research_topic` vào điều kiện `reasoning_effort` của gpt-oss (giống vai trò `research`).
5. **`test_khong_hardcode_api_key_trong_source`** quét cả `tests/*.py` nên key giả trong test được dựng lúc chạy (`"gsk" + "_" + …`) thay vì viết literal.
6. **Nguồn OpenAlex & Semantic Scholar:** không có tài liệu chính thức được đối chiếu trực tiếp trong phiên (không có công cụ tra web) — parser dựa trên mô tả của spec. Kết quả kiểm chứng thực tế: arXiv/PubMed/Crossref qua test mạng, Semantic Scholar qua một lần gọi tay; OpenAlex **chưa** (thiếu key).

## 7. Thay đổi vùng chung (dùng cho PR)

| File | Thay đổi | Vì sao |
|---|---|---|
| `app/core/grounding.py` | Thêm `LoaiNhan`, `LOAI_NHAN_MOI` (DOI, PMID, OpenAlex dạng ngắn, S2), `ma_moi_trong()`; `_soi_nguon` nhận thêm tham số tuỳ chọn `ma_that`; `kiem_tra_grounding` thêm vòng MA_BIA cho mã trần mới và tra nhãn mới. **Không đổi chữ ký hàm công khai**; `tests/test_grounding.py` (24 test) xanh nguyên trạng. | D5 — bảng đăng ký loại nhãn; thêm loại nhãn về sau chỉ cần thêm một mục. |
| `app/core/config.py` | Thêm `model_research_topic`, `research_arch`, `research_mode`, `openalex_api_key`, `semantic_scholar_api_key`, `ncbi_api_key`, `research_max_searches_set`, hằng `RESEARCH_ARCHS/MODES`, hai hàm kiểm tra giá trị; `mo_ta_cau_hinh()` hiện vai trò `research_topic` + dòng `research:`. | §5.12 |
| `app/core/llm.py` | Đăng ký vai trò `research_topic` (Role, `_MODEL_SPEC_BY_ROLE`, `reasoning_effort` cho gpt-oss). | D8 |
| `.env.example` | `MODEL_RESEARCH_TOPIC`, `RESEARCH_ARCH`, `RESEARCH_MODE`, `OPENALEX_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY`, `NCBI_API_KEY` (chỉ ASCII, giá trị trống/ví dụ). | §5.12 |
| `tests/conftest.py` | Thêm vào `APP_ENV_VARS`: `MODEL_RESEARCH_TOPIC`, `RESEARCH_ARCH`, `RESEARCH_MODE`, `OPENALEX_API_KEY`, `OPENALEX_MAILTO`, `SEMANTIC_SCHOLAR_API_KEY`, `NCBI_API_KEY`. | TS-06 |
| `tests/test_grounding_labels.py` | File mới. | Test phần core. |

Báo nhóm khi merge: **CH-06 từ 5 → 6 vai trò**; mỗi người tự lấy `OPENALEX_API_KEY`; mặc định vẫn `RESEARCH_ARCH=single`. Không sửa `main.py`; vai trò mới tự hiện trong `--config` vì `mo_ta_cau_hinh()` nằm ở `config.py`.
Đề xuất (không bắt buộc): khối `KIEM TRA NGUON` trong `main.py` chỉ chạy khi thấy `arxiv_search`/`wikipedia_search` trong luồng; ở chế độ `topics` các tool này nằm trong agent chủ đề nên CLI không thấy — đọc `ToolMessage.artifact["grounding_report"]` nếu muốn hiển thị. Và đề xuất đổi `AGENT_DESCRIPTION` khi bật `topics` mặc định.

## 8. Việc còn mở / nợ kỹ thuật

- **Kiểm chứng OpenAlex thật** khi có `OPENALEX_API_KEY` (`OPENALEX_API_KEY_FOR_TESTS=<key> pytest -m network -k openalex`; tôi thêm biến riêng cho test vì `conftest.py` xoá `OPENALEX_API_KEY`).
- **Thống nhất hai đường OpenAlex** (tool cũ dùng `mailto`, nguồn mới dùng `api_key`) khi chuyển hẳn sang `topics`.
- **Số liệu eco/standard/full chưa đo** (Phase 2). Ước lượng lượt gọi LLM ở §7 spec chưa kiểm bằng số thật.
- **`explainer_agent` dùng `arxiv_search` cũ** (in cả `Published` lẫn `Last updated`; prompt dặn dùng `Published`), không dùng nguồn arXiv đã chuẩn hoá.
- **Grounding chỉ kiểm nguồn *có tồn tại*, không kiểm nguồn *có nói đúng* điều được trích** (giới hạn đã biết, dành cho Citation Agent).
- **Tầng 2 chỉ xoá câu vi phạm nặng**; câu không nhãn (`THIEU_NGUON`) chỉ được đếm (`response_metadata["grounding"]`, log), chưa hiển thị cho người dùng.
- **`dedupe_records` là O(n²)** (n nhỏ), ghi chú `ponytail:` trong code.
- **Chưa kiểm** tính đúng của `post_model_hook` với model thật (chỉ với model giả): việc thay `AIMessage` cuối giữ nguyên `id` đã có test, nhưng hành vi với `ChatOpenAI`/Groq nên xem lại ở T1–T3.
- DeprecationWarning từ `langchain_community` (`Search.results`) do `tim_arxiv()` gọi — có sẵn, không đụng.

## 9. Hướng dẫn nghiệm thu thủ công (Tuấn)

Chép từ §10.2 của spec, cập nhật theo thực tế:

**Chuẩn bị `.env`:**

```
RESEARCH_ARCH=topics
RESEARCH_MODE=standard
MODEL_RESEARCH_TOPIC=<model con song, kiem bang --models>   # khac model cua 5 vai tro con lai
OPENALEX_API_KEY=<key rieng>                               # thieu key: OpenAlex bi bo qua, van chay
```

Chạy trước (không tốn lượt): `python -m app.main --config`, `--models`, `pytest -m "not network"`. Thấy dòng `research_topic  groq  <model>` trong `--config` là đúng.
Sau đó chạy các ca dưới đây từ rẻ đến đắt, nên dùng `--agent research_agent` để tiết kiệm lượt (LX-06).

| Ca | Câu hỏi | Kỳ vọng |
|---|---|---|
| T1 Học thuật | `"Find recent papers on rotary position embedding"` | Chỉ gọi `scholar_agent`; ≥ 2 bài; mọi câu có nhãn/số trích dẫn; log grounding không có `MA_BIA` |
| T2 Giải thích | `"Giải thích cơ chế self-attention trong Transformer"` | Chỉ gọi `explainer_agent`; nguồn `wikipedia: …` |
| T3 Đa chủ đề | `"Transformer là gì, và có bài báo nào gần đây về giảm bộ nhớ của attention?"` | Gọi explainer rồi scholar, **tuần tự**; trả lời tiếng Việt có dấu; nguồn của cả hai phần được giữ |
| T4 Y sinh | `"Tìm nghiên cứu về liệu pháp CRISPR cho bệnh thiếu máu hồng cầu hình liềm"` | Có gọi `pubmed_search`; nguồn có `pmid: …` hoặc `doi: …` |
| T5 Mơ hồ | `"Tìm tài liệu về Mercury"` | Một dòng `CAN_LAM_RO: …`, không gọi tool |
| T6 Không dữ liệu | `"Tìm bài báo về thuật toán xqzvbn-7 công bố năm 2031"` | `KHONG DU DU LIEU: …`; không có nhãn bịa |
| T7 eco | Câu T3 với `RESEARCH_MODE=eco` | Chỉ một chủ đề được gọi; câu trả lời nói rõ phần chưa tra |
| T8 Hồi quy | Ca 1 của nhóm với `RESEARCH_ARCH=single` | Giống hệt trước khi nâng cấp |
| T9 Qua supervisor | `python -m app.main "What is the latest research on positional embeddings?"` với `topics` | Chạy trọn luồng, supervisor nhận câu trả lời có nguồn |

Lưu ý khi nghiệm thu (mới so với spec): (a) dòng `(Đã lược bỏ N câu…)` / `(Câu trả lời này không dựa trên nguồn…)` là do grounding tầng 2 thêm vào cuối câu trả lời của lead;
(b) khối `KIEM TRA NGUON` của `main.py` sẽ **không** hiện ở chế độ `topics` (xem mục 7); (c) T4 không cần key PubMed; `NCBI_API_KEY` chỉ nâng hạn mức.
Ghi lại số lượt gọi LLM từng ca (LangSmith project riêng, CH-05) → đầu vào Phase 2. Tổng cả bộ ước khoảng 60–90 lượt LLM và ~20 lượt tìm kiếm OpenAlex.

## 10. ĐÃ DỪNG

Không có. Không gặp điều kiện §0.4 nào. Hai chỗ tôi dừng để **hỏi Tuấn** ở B0 (không phải điều kiện dừng hẳn): working tree không sạch / nhánh xuất phát, và việc repo lệch spec (đã chọn "thích nghi, giữ code cũ").

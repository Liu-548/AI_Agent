# Nhật ký phát triển — Research Agent

> File này KHÔNG commit lên git (chỉ để cá nhân theo dõi tiến độ / lý do quyết
> định). Không thêm vào `.gitignore` — chỉ đơn giản không `git add` nó.
> Ngày bắt đầu: 2026-08-29.

## Bối cảnh

Sau khi rà lại `CLAUDE.md` mục 7 (Trạng thái & bước kế tiếp), các việc còn
trống là: thêm nguồn (OpenAlex/Semantic Scholar/Crossref), RAG cơ bản
(Chroma), citation-chasing, xếp hạng liên quan. Đã bàn với user và chọn thứ tự
làm từ dễ đến khó, ưu tiên: (1) trải nghiệm câu trả lời (chưa đụng UI), (2)
khả năng dùng lâu dài — tiết kiệm token, dùng API hiệu quả hơn.

Danh sách ý tưởng đầy đủ đã đề xuất cho user (2026-08-29):
1. Thêm nguồn học thuật thứ 3 (OpenAlex / Semantic Scholar) — DỄ NHẤT.
2. Citation-chasing thật sự (lần theo references/citations của một bài).
3. RAG cơ bản trên full-text thay vì chỉ abstract.
4. Query decomposition (tách câu hỏi phức tạp thành nhiều truy vấn con).
5. Test coverage cho tool mới.

→ Đã làm việc (1). Việc (2)-(5) vẫn còn treo, xem mục "Ý tưởng chưa làm" cuối
file để làm tiếp sau.

---

## Việc đã làm — 2026-08-29: thêm tool `openalex_search`

### Quyết định kỹ thuật (đã hỏi user trước khi làm)

- **Gọi thẳng REST API của OpenAlex qua `requests`**, KHÔNG dùng thư viện
  `pyalex` (dù CLAUDE.md liệt kê pyalex trong tech stack). Lý do: `requests`
  đã có sẵn trong `requirements.txt` (dùng cho arxiv/wikipedia), không cần
  thêm dependency mới; và tự kiểm soát được tham số `select=` để CHỈ lấy đúng
  field cần dùng (title, năm, tác giả, abstract, cited_by_count) → payload
  nhỏ hơn, tốn ít token hơn khi nhét vào prompt so với để pyalex trả về
  nguyên bản ghi đầy đủ.
- **`OPENALEX_MAILTO`**: mặc định là placeholder `team@example.com` (giống
  hệt cách `WIKIPEDIA_USER_AGENT` đang làm), KHÔNG dùng email thật của user.
  User có thể tự đổi trong `.env` nếu muốn vào "polite pool" của OpenAlex
  (nhanh + ổn định hơn, ít bị rate-limit) — nhưng đó là lựa chọn của họ, tool
  không tự ý gửi email thật ra ngoài.

### File đã sửa

| File | Thay đổi |
|---|---|
| `app/core/config.py` | Thêm `openalex_top_k` (mặc định 2), `openalex_max_chars` (mặc định 1000), `openalex_mailto` (mặc định placeholder). Env var tương ứng: `OPENALEX_TOP_K`, `OPENALEX_MAX_CHARS`, `OPENALEX_MAILTO`. |
| `app/agents/research_agent/tools.py` | Thêm `_dung_lai_abstract()` (OpenAlex trả abstract dạng "inverted index" `{tu: [vi_tri,...]}` chứ không phải văn bản thẳng — phải dựng lại), `tim_openalex()`, `format_openalex_docs()`, `make_openalex_tool()`. Cập nhật `default_research_tools()` → giờ trả về 3 tool (arxiv, openalex, wikipedia) dùng CHUNG một `SearchBudget`. |
| `app/agents/research_agent/prompts.py` | Dạy model: dùng `arxiv_search` cho CS/vật lý, `openalex_search` khi arxiv không ra gì hoặc chủ đề ngoài CS/vật lý (y sinh, khoa học xã hội...), không gọi cả hai cho cùng một câu hỏi con (tốn lượt tìm kiếm). Thêm dòng mẫu `[n] ... - <OpenAlex ID:>` vào mục NGUỒN. Cho phép trích số "Cited by:" trong CHI TIẾT vì đó là dữ liệu tool trả về thật (grounded). |
| `app/agents/research_agent/agent.py` | Cập nhật `AGENT_DESCRIPTION` và docstring nhắc tới OpenAlex. |
| `app/core/grounding.py` | Thêm `MA_OPENALEX_RE` + `ma_openalex_trong()` để nhận diện mã Work ID dạng `openalex.org/W123...`. Cập nhật `_soi_nguon()` và `kiem_tra_grounding()` để coi mã OpenAlex hợp lệ y hệt cách xử lý Entry ID của arXiv (kiểm tra mã có THẬT trong kết quả tool không, báo `MA_BIA` nếu bịa). |
| `tests/test_research_tools.py` | Thêm test cho `openalex_search`: empty query trả lỗi chuẩn, test mạng thật lấy được bài báo, test offline cho `_dung_lai_abstract()` (dựng lại abstract từ inverted index) và `format_openalex_docs()`. Sửa test `test_hai_tool_mac_dinh_dung_chung_mot_so` → `test_ba_tool_mac_dinh_dung_chung_mot_so` (giờ 3 tool). |
| `tests/test_grounding.py` | Thêm `TOOL_OPENALEX` + `TRA_LOI_OPENALEX` mẫu, test nguồn OpenAlex hợp lệ không bị báo lỗi, test mã OpenAlex bịa bị bắt là `MA_BIA`. |
| `tests/test_contract.py` | `EXPECTED_TOOLS["research_agent"]` cập nhật thêm `"openalex_search"` — đây là test hợp đồng khoá cứng danh sách tên tool, sửa CÓ CHỦ ĐÍCH vì đang chủ động thêm tool mới (không phải lỗi vô tình đổi tên). |

**Không cần sửa `requirements.txt`** vì không thêm dependency mới (dùng
`requests` sẵn có).

### Kết quả kiểm tra

- `pytest -m "not network"`: 98 passed (offline, không tốn quota).
- `pytest -m network -k openalex`: 1 passed — gọi API OpenAlex thật, lấy được
  bài báo kèm `OpenAlex ID:`.
- `pytest -m network`: 4 passed (arxiv + openalex + wikipedia x2) — không tool
  nào bị vỡ.
- `python -m app.main --config`: load settings mới không lỗi (lưu ý: cần
  `PYTHONIOENCODING=utf-8` khi chạy trên PowerShell/terminal dùng code page
  cp1258 của Windows, nếu không sẽ vỡ ở bước PRINT tiếng Việt ra console —
  đây là lỗi ĐÃ CÓ TỪ TRƯỚC, không liên quan tới thay đổi lần này).
- Smoke test sống với câu hỏi y sinh ("CRISPR gene editing co nhung ung dung
  y hoc nao"): agent tự chọn ĐÚNG thứ tự tool theo prompt mới — gọi
  `arxiv_search` trước, bị `SearchBudget` từ chối lần gọi lặp (không liên
  quan lỗi gì, đúng thiết kế), tự chuyển sang `openalex_search` và lấy được
  2 bài báo thật kèm `OpenAlex ID:` + `Cited by:` hợp lệ, rồi gọi
  `wikipedia_search`. Cơ chế 3-tool + search budget dùng chung hoạt động
  đúng như kỳ vọng.
  - **Quan sát phụ (KHÔNG liên quan tới OpenAlex, đã có từ trước)**: câu trả
    lời cuối bị CẮT NGANG giữa chừng (thiếu hẳn mục NGUỒN), khiến
    `grounding.py` báo 4 vi phạm `NGUON_THIEU`/`THIEU_NGUON`. Đây là model
    `groq:openai/gpt-oss-20b` (vai trò research) dừng sinh chữ giữa câu chứ
    không phải lỗi trong `tools.py`/`grounding.py` — 2 bài OpenAlex vẫn được
    trả về đúng, đủ dữ kiện. Nghi ngờ do giới hạn output token/reasoning
    budget mặc định của model, KHÔNG có `max_tokens` nào được set trong
    `app/core/llm.py`. CHƯA sửa vì đây là vấn đề khác, cần bàn với user
    trước khi đổi cấu hình model — ghi lại đây để không quên.

---

## Việc đã làm — 2026-08-29: sửa câu trả lời bị cắt ngang (reasoning_effort)

### Chẩn đoán (đã xác nhận bằng cách gọi API trực tiếp, không phải đoán)

Viết script gọi thẳng `get_llm("research")` với một câu hỏi dài để đọc
`response_metadata`. Kết quả:

```
finish_reason: length
token_usage: completion_tokens=2048, reasoning_tokens=2046, total=2151
```

Nguyên nhân: `openai/gpt-oss-20b` (model vai trò research, chạy qua Groq) là
**reasoning model**. Groq mặc định `reasoning_effort=medium`. Với câu hỏi
thử, model đốt 2046/2048 token ngân sách completion vào phần suy nghĩ ẨN
(`reasoning_tokens`), không còn chỗ in câu trả lời thật → cắt ngang giữa
chừng, đúng hiện tượng đã thấy ở bản smoke-test CRISPR trước đó.

Test lại với `reasoning_effort="low"` (đặt trực tiếp trên `ChatOpenAI`):
`finish_reason: stop`, `reasoning_tokens: 28`, tổng chỉ 493 token. Vừa hết
cắt ngang, vừa giảm mạnh token/lượt gọi (đúng ưu tiên "dùng lâu dài, tiết
kiệm token" đã đặt ra từ đầu).

### Quyết định phạm vi (đã hỏi user)

Model vai trò `supervisor` cũng dùng `openai/gpt-oss-120b` trên Groq nên
NHIỀU KHẢ NĂNG dính cùng lỗi — nhưng user chọn **chỉ sửa cho vai trò
`research`** trong lần này, KHÔNG đụng tới `supervisor`. Ghi chú để nhớ:
supervisor vẫn có thể đang bị cắt ngang câu trả lời/quyết định điều phối mà
chưa ai để ý — cân nhắc kiểm tra riêng sau nếu thấy hệ thống có dấu hiệu lạ
(vd. supervisor im lặng một nhịp, hoặc không route đúng).

### File đã sửa

| File | Thay đổi |
|---|---|
| `app/core/config.py` | Thêm `research_reasoning_effort` (mặc định `"low"`, env `RESEARCH_REASONING_EFFORT`). Để rỗng (`""`) trong `.env` sẽ tắt hẳn, không gửi tham số này nữa. |
| `app/core/llm.py` | Trong `get_llm()`, nhánh ChatOpenAI: nếu `role == "research"` VÀ tên model chứa `"gpt-oss"` VÀ `research_reasoning_effort` khác rỗng → truyền `reasoning_effort=...` vào `ChatOpenAI`. Điều kiện theo TÊN MODEL (không phải cứng theo role) để an toàn: nếu sau này đổi `MODEL_RESEARCH` sang model không phải gpt-oss (vd. llama), tham số này tự động KHÔNG được gửi nữa — tránh lỗi "unsupported parameter" cho model không hiểu field này. |
| `tests/test_llm_config.py` | Thêm biến `RESEARCH_REASONING_EFFORT` vào danh sách env cần dọn giữa các test. Thêm 4 test: gpt-oss ở vai trò research được đặt `reasoning_effort="low"`; model không phải gpt-oss thì KHÔNG đặt; vai trò `supervisor` (dù cùng model gpt-oss) KHÔNG bị đụng tới (khoá lại quyết định phạm vi ở trên bằng test, không phải chỉ ghi chú suông); có thể tắt qua env rỗng. |

### Kết quả kiểm tra

- `pytest -m "not network"`: 102 passed (thêm 4 test so với trước).
- Chạy lại ĐÚNG câu hỏi từng bị cắt ngang ("CRISPR gene editing co nhung ung
  dung y hoc nao"): giờ ra đủ 3 mục TÓM TẮT/CHI TIẾT/NGUỒN, không còn bị cắt.
- **Phát hiện phụ mới (nhỏ, KHÔNG liên quan reasoning_effort)**: trong lần
  chạy lại này, mục NGUỒN ghi `[1] CRISPR gene editing (Wikipedia)\n    -
  Page: CRISPR gene editing` thay vì đúng khuôn `[1] wikipedia: CRISPR gene
  editing` — lệch định dạng nên bị `grounding.py` báo `NGUON_BIA` (báo động
  giả, vì trang Wikipedia đó THẬT SỰ có trong kết quả tool, chỉ là model viết
  sai khuôn). Đây là vấn đề PROMPT (model đôi khi không theo đúng mẫu ví dụ
  cho nhãn wikipedia), khác hẳn nguyên nhân đang sửa ở đây. CHƯA sửa — để ý
  tưởng riêng, có thể cần nới lỏng `NHAN_WIKI_RE`/`_soi_nguon` để chấp nhận
  thêm 1-2 cách viết phổ biến, hoặc nhấn mạnh hơn trong prompt.

---

## Kiểm tra — 2026-08-30: supervisor có bị lỗi cắt-ngang-vì-reasoning không?

**Yêu cầu của user: chỉ kiểm tra và ghi chú, KHÔNG sửa.**

### Cách kiểm tra

1. Gọi thẳng `get_llm("supervisor")` (model `openai/gpt-oss-120b` qua Groq)
   với đúng câu hỏi thử đã dùng để phát hiện lỗi ở research (~200 từ tiếng
   Việt về CRISPR) và đọc `response_metadata`.
2. Chạy lại pipeline ĐẦY ĐỦ (`python -m app.main "CRISPR gene editing co
   nhung ung dung y hoc nao"`, không có `--agent`) để supervisor thật sự
   điều phối + tổng hợp câu trả lời cuối, xem có bị cắt ngang trong điều
   kiện dùng thật không (khác với test đơn lẻ gọi model trực tiếp).

### Kết quả: KHÔNG bị lỗi cắt-ngang-vì-reasoning

- Test trực tiếp: `finish_reason: stop`, `reasoning_tokens: 97` /
  `completion_tokens: 437` — so với research lúc lỗi là `reasoning_tokens:
  2046` / `completion_tokens: 2048` (gần như 100% ngân sách). Model 120b
  dùng ít token suy nghĩ hơn hẳn model 20b cho cùng một việc, dù cả hai đều
  ở mức `reasoning_effort` mặc định (medium) của Groq.
- Test pipeline thật: supervisor tổng hợp một câu trả lời DÀI (bảng markdown
  đầy đủ TÓM TẮT/CHI TIẾT/NGUỒN) và hoàn tất bình thường, không bị cắt giữa
  câu/giữa từ ở bất kỳ đâu.
- Kết luận: với 2 cách thử ở trên, supervisor KHÔNG có dấu hiệu của đúng lỗi
  đã sửa ở research (đốt hết ngân sách token vào reasoning ẩn). Có thể do
  model 120b "tiết kiệm" suy nghĩ hơn 20b, hoặc do nhiệm vụ điều phối/tổng
  hợp không đẩy nó vào tình huống suy luận sâu như research phải quyết định
  gọi tool nào. **Không chắc chắn 100% cho MỌI câu hỏi** — đây chỉ là 2 lần
  thử, không phải chứng minh toán học. Nếu sau này thấy supervisor trả lời
  cụt/thiếu phần cuối, quay lại đây trước, chạy lại đúng 2 bước trên để xác
  nhận bằng `response_metadata` chứ đừng đoán.

### Phát hiện KHÁC, không liên quan reasoning_effort — supervisor VIẾT LẠI câu trả lời đã có trích dẫn của research_agent, làm hỏng bộ kiểm tra grounding

Trong lần chạy pipeline thật ở trên, `KIEM_TRA_NGUON` báo **17 vi phạm**
(`NGUON_THIEU`, `THIEU_NGUON`) cho câu trả lời CUỐI CÙNG — nhưng nguyên nhân
HOÀN TOÀN KHÁC lỗi reasoning:

- `research_agent` trả lời đúng chuẩn (đã kiểm chứng độc lập nhiều lần trước
  đó): `TÓM TẮT` / `CHI TIẾT` / `NGUỒN` với `[n]` + dòng `OpenAlex ID:`/`Entry
  ID:`/`Page:` copy nguyên văn.
- Nhưng `supervisor` KHÔNG chuyển tiếp nguyên văn câu trả lời đó cho user.
  Nó tự **viết lại** thành một bảng markdown (tiêu đề in đậm, cột "Nguồn"
  ghi kiểu `1. **Tên bài** – OpenAlex ID: ... (2020).` thay vì đúng khuôn
  `[1] Tên bài (2020)\n    - OpenAlex ID: ...`). Khuôn mới này không khớp
  bất kỳ regex nào trong `grounding.py` (vốn được thiết kế để kiểm tra đúng
  định dạng mà PROMPT của research_agent quy định) → toàn bộ trích dẫn bị
  báo "thiếu nguồn" dù nội dung có thật.
- Gốc rễ: `app/agents/supervisor/prompts.py` (`SUPERVISOR_PROMPT_TEMPLATE`)
  đang dặn supervisor "combine their answers into one final response" mà
  KHÔNG hề nói phải giữ nguyên định dạng trích dẫn của agent con. Đây là lỗ
  hổng thiết kế: `grounding.py` chỉ có tác dụng bảo vệ nếu câu trả lời tới
  tay user đúng là câu research_agent đã viết, không phải bản supervisor
  diễn giải lại.
- **CHƯA sửa** (đúng yêu cầu chỉ ghi chú). Hướng sửa khả dĩ nếu làm sau này:
  (a) dặn thêm trong `SUPERVISOR_PROMPT_TEMPLATE` là khi agent con đã trả
  lời có mục NGUỒN thì PHẢI giữ nguyên văn mục đó, không diễn giải lại; hoặc
  (b) chạy `kiem_tra_grounding()` ngay tại lượt trả lời của research_agent
  (trước khi supervisor chạm vào) thay vì chỉ chạy trên câu trả lời cuối
  cùng — đây có lẽ là cách chắc chắn hơn vì không phụ thuộc supervisor có
  "ngoan" hay không.

---

## Ý tưởng chưa làm (để làm tiếp sau, thứ tự gợi ý)

0. ~~Kiểm tra xem `supervisor` có bị đúng lỗi cắt-ngang-vì-reasoning y hệt
   research không~~ — ĐÃ KIỂM TRA 2026-08-30, xem mục "Kiểm tra — supervisor
   có bị lỗi tương tự không" phía trên. Kết luận: 2 lần thử đều KHÔNG thấy
   dấu hiệu, nhưng phát hiện một lỗi KHÁC quan trọng hơn (supervisor viết
   lại câu trả lời làm hỏng trích dẫn) — xem mục 0c bên dưới.
0c. **(Mới, quan trọng)** `grounding.py` hiện chỉ chạy trên câu trả lời CUỐI
   CÙNG (sau khi supervisor có thể đã viết lại). Cân nhắc chạy
   `kiem_tra_grounding()` ngay khi `research_agent` vừa trả lời (trước khi
   supervisor chạm vào), để không phụ thuộc việc supervisor có giữ nguyên
   định dạng trích dẫn hay không. Xem chi tiết & 2 hướng sửa khả dĩ ở mục
   "Kiểm tra — supervisor có bị lỗi tương tự không" phía trên.
0b. **(Mới, nhỏ)** Nới `NHAN_WIKI_RE`/`_soi_nguon` trong `grounding.py` để
   chấp nhận thêm cách viết `[n] <Title> (Wikipedia)\n    - Page: <Title>`
   (model thỉnh thoảng viết kiểu này thay vì đúng khuôn `wikipedia: <Page>`),
   tránh báo động giả `NGUON_BIA` cho nguồn thật sự hợp lệ. Xem log ở mục
   "Việc đã làm — sửa câu trả lời bị cắt ngang" phía trên.
1. **Citation-chasing**: cần tool `get_references(id)` / `get_citations(id)`
   — Semantic Scholar có API trả thẳng danh sách reference/citation của một
   bài, phù hợp hơn OpenAlex cho việc này (OpenAlex cũng có field
   `referenced_works` là danh sách ID, có thể tận dụng thêm mà không cần
   thêm dependency: gọi `GET /works/{id}` rồi lấy `referenced_works`).
2. **RAG cơ bản trên full-text** thay vì chỉ abstract cắt ngắn — cần
   `rag/embed.py` + `rag/store.py` (Chroma) như CLAUDE.md đã phác thảo,
   hiện CHƯA tồn tại trong code thật.
3. **Query decomposition**: thêm 1 bước LLM nhỏ (dùng `model_utility` đã có
   sẵn trong config, rẻ) tách câu hỏi phức tạp thành nhiều truy vấn con
   trước khi vào ReAct loop.
4. **Cache truy vấn qua các lần chạy** (ý tưởng để dành, CHƯA làm — cân nhắc
   kỹ trước khi làm vì thêm state/độ phức tạp): hiện `SearchBudget` chỉ
   dedupe trong một tiến trình; CLI một-câu-một-lần thì mỗi lần chạy là một
   tiến trình mới nên không tận dụng được cache giữa các lần test thủ công.
   Một cache đĩa đơn giản (vd. `diskcache`, key = tool+query đã chuẩn hoá)
   giữa các lần chạy sẽ tiết kiệm quota khi dev/test lặp lại cùng câu hỏi.
   Rủi ro: thêm dependency mới, thêm 1 lớp state phải quản lý — CLAUDE.md
   nhắc "không nên over-engineer" nên để dành, chỉ làm nếu thấy thật sự cần.
5. **Semantic Scholar** như nguồn thứ 4 nếu cần citation count đáng tin hơn
   hoặc cần citation-chasing chuyên sâu — cân nhắc gộp vào việc (1) luôn.

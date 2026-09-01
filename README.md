# Visual Agentic AI — Multi-Agent System with Supervisor Architecture

Hệ thống multi-agent theo kiến trúc **Supervisor** dựng trên LangGraph, gồm:

| Agent | Vai trò | Tool |
|---|---|---|
| `supervisor` | Điều phối trung tâm, quyết định giao việc cho agent nào, tổng hợp câu trả lời | handoff tools |
| `research_agent` | Tìm bài báo khoa học và tra cứu khái niệm | `arxiv_search`, `wikipedia_search` |
| `vision_agent` | Mô tả ảnh, phát hiện và đếm vật thể | `image_describer`, `detect_and_count_objects` |

Hai agent con chạy theo **ReAct** (Thought → Action → Observation). Supervisor chuyển
quyền điều khiển bằng handoff tool `transfer_to_<agent_name>` và nhận lại qua
`transfer_back_to_supervisor`.

> **Trước khi viết dòng code đầu tiên, đọc [`QUY_TAC_THIET_KE.md`](QUY_TAC_THIET_KE.md).**
> Đó là hợp đồng chung của nhóm để 3 nhánh gộp lại được vào cuối tháng 8.
>
> **Mỗi lần ngồi vào làm, mở [`TRUOC_KHI_CHAY.md`](TRUOC_KHI_CHAY.md)** — danh sách
> kiểm tra trước khi chạy thử, kèm bảng tra lỗi.

---

## Cài đặt

**Bắt buộc Python 3.11** (quy tắc MT-01). Kiểm tra trước: `python --version`.
Nếu ra 3.12/3.13/3.14 thì phải cài thêm 3.11 — bản mới hơn sẽ không cài nổi
`pydantic-core` (phải build từ Rust) và `wikipedia==1.4.0`.

<details open>
<summary><b>Windows / PowerShell</b></summary>

```powershell
# 1. Cài Python 3.11 nếu chưa có, rồi MỞ CỬA SỔ POWERSHELL MỚI
winget install Python.Python.3.11
py -3.11 --version                     # phải ra 3.11.x

# 2. Tạo venv bằng đúng 3.11 (xoá .venv cũ nếu đã lỡ tạo bằng bản khác)
Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
py -3.11 -m venv .venvpython -m pip check

# 3. Kích hoạt. Nếu báo "running scripts is disabled" thì chạy dòng
#    Set-ExecutionPolicy ở dưới trước (chỉ có hiệu lực trong cửa sổ này).
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python --version                       # phải ra 3.11.x, đầu dòng lệnh có (.venv)

# 4. Cài thư viện — dùng `python -m pip`, không dùng `pip` trần
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

# 5. Tạo .env rồi điền GROQ_API_KEY và GEMINI_API_KEY
Copy-Item .env.example .env
notepad .env
```

Không muốn động tới ExecutionPolicy? Bỏ qua bước kích hoạt, gọi thẳng
`.\.venv\Scripts\python.exe -m pip install -r requirements.txt` và
`.\.venv\Scripts\python.exe -m pytest` — kết quả y hệt.
</details>

<details>
<summary><b>macOS / Linux</b></summary>

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
cp .env.example .env                # rồi điền GROQ_API_KEY + GEMINI_API_KEY
```
</details>

### Lỗi thường gặp trên Windows

| Thông báo | Nguyên nhân | Cách sửa |
|---|---|---|
| `source : The term 'source' is not recognized` | `source` là cú pháp bash | PowerShell dùng `.\.venv\Scripts\Activate.ps1` |
| `pip : The term 'pip' is not recognized` | Chưa kích hoạt venv | Kích hoạt venv, rồi gọi `python -m pip` thay cho `pip` |
| `... Activate.ps1 cannot be loaded because running scripts is disabled` | ExecutionPolicy chặn script | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| `error: Microsoft Visual C++ 14.0 or greater is required` | Đang dùng Python ≠ 3.11 nên pip phải build từ source | Tạo lại venv bằng `py -3.11` |
| `UnicodeDecodeError: 'charmap' codec can't decode byte 0x81` | File `.txt` có chữ tiếng Việt, pip đọc bằng codec cp1258 | File cấu hình trong repo đã chuyển sang ASCII; dùng bản mới nhất |
| Cài xong nhưng `import` báo thiếu gói | Quên kích hoạt venv, gói vào Python hệ thống | `.\.venv\Scripts\Activate.ps1` rồi cài lại. Đầu dòng lệnh phải có `(.venv)` |
| `--config` báo `key[...]: thiếu` dù `.env` đã có key | Chạy nhầm Python hệ thống nên không nạp được `.env` | Kích hoạt venv. `--config` in ra dòng `venv:` và `.env:` để nhận biết ngay |
| `400 Function call is missing a thought_signature` | Thư viện Google quá cũ so với model Gemini 3 | Cài lại đúng `requirements.txt` hiện tại (LangChain 1.x + `langchain-google-genai==4.3.4`) |

Người phụ trách Vision Agent cài thêm (kéo theo torch, ~2GB):

```bash
pip install ultralytics==8.3.108
```

Hai người còn lại **không cần** cài — tool YOLO import trễ nên toàn bộ test vẫn chạy.

## Nhà cung cấp LLM — cấu hình lai

Hệ thống chạy **hai nhà cung cấp cùng lúc**, mỗi vai trò một nơi:

| Vai trò | Nhà cung cấp | Model mặc định | Hạn mức miễn phí |
|---|---|---|---|
| `supervisor` | Groq | `openai/gpt-oss-120b` | ~1.000 req/ngày |
| `research` | Groq | `openai/gpt-oss-20b` | ~1.000 req/ngày |
| `vision` | Gemini | `gemini-3.5-flash` | ~20 req/ngày |
| `describe` | Gemini | `gemini-3.5-flash-lite` | ~20 req/ngày |
| `utility` | Gemini | `gemini-3.1-flash-lite` | ~20 req/ngày |

Lý do: free tier Gemini chỉ ~20 request/ngày mỗi model, mà một câu hỏi qua
supervisor tốn 4–6 lượt — tức chỉ 5–8 câu mỗi ngày. Groq cho ~1.000 request/ngày
mỗi model nên **đường chữ** (supervisor + research) đặt bên Groq. **Đường ảnh** đặt
bên Gemini vì Groq không có model đa phương thức ổn định — mà đường ảnh dù sao
cũng bị chặn ở ~20 req/ngày của Gemini nên để cả vòng ReAct của Vision Agent bên
đó luôn cho gọn.

> Nhà cung cấp có khai tử model theo lịch (Groq bỏ `llama-3.3-70b-versatile` cho
> free tier ngày 16/08/2026). Tài liệu của họ thường lạc hậu hơn thực tế — trước
> khi đổi model, chạy `python -m app.main --models` để lấy danh sách thật.

Lấy hai key (đều miễn phí, không cần thẻ tín dụng):

- Groq: [console.groq.com/keys](https://console.groq.com/keys) → điền `GROQ_API_KEY`, key bắt đầu bằng `gsk_`
- Gemini: [aistudio.google.com/apikey](https://aistudio.google.com/apikey) → điền `GEMINI_API_KEY`, key bắt đầu bằng `AQ.`

Cú pháp `provider:model` trong `.env` quyết định vai trò nào chạy ở đâu:

```
MODEL_RESEARCH=groq:openai/gpt-oss-120b
MODEL_DESCRIBE=google:gemini-3.5-flash-lite
```

Kiểm tra cấu hình (không in ra key):

```bash
python -m app.main --config     # vai trò -> provider/model, tình trạng key
python -m app.main --models     # model mà key của bạn thật sự dùng được
```

## Hạn mức miễn phí — mẹo tiết kiệm

Hạn mức tính **theo từng model**, nên 5 vai trò dùng 5 model là 5 sổ riêng. Cạn
một model thì chỉ cần đổi đúng dòng `MODEL_*` đó sang model khác.

```bash
python -m app.main --config                       # vai trò nào dùng model nào
python -m pytest -m "not network"                 # không tốn lượt (dùng model giả)
python -m app.main --agent research_agent "..."   # bỏ 2 lượt của supervisor
python -m app.main --graph                        # không gọi LLM
```

Hạn mức thực tế: [Groq](https://console.groq.com/docs/rate-limits) ·
[Gemini](https://aistudio.google.com/rate-limit). Gặp `429` thì không phải code
hỏng — chỉ là hết lượt của một model.

## Chạy test

```bash
pytest -m "not network"     # nhanh, không cần mạng, không cần API key
pytest                      # thêm test gọi arXiv/Wikipedia thật (tự skip nếu mất mạng)
pytest tests/test_contract.py   # chỉ kiểm tra hợp đồng chung của nhóm
```

Toàn bộ test end-to-end dùng **model giả** trong `tests/fakes.py`, nên chạy test
không tốn một đồng token nào.

## Kiến trúc thư mục

Toàn bộ hệ thống nằm trong **một folder tổng `app/`**; phần thiết lập môi trường
(`requirements.txt`, `.env`, `.venv/`) để ngoài gốc repo. Mỗi agent là **một thư mục
tự chứa** — agent, tool và prompt của nó nằm cùng chỗ, nên mỗi thành viên chỉ làm việc
trong đúng một thư mục.

```
app/                          <<< folder tổng
├── main.py                   # CLI
├── core/                     # [DÙNG CHUNG]
│   ├── config.py             #   nơi DUY NHẤT đọc biến môi trường
│   ├── llm.py                #   nơi DUY NHẤT khởi tạo ChatModel — get_llm(role)
│   ├── contracts.py          #   hợp đồng giữa các agent (máy kiểm tra được)
│   └── pretty.py             #   in trace khi stream
└── agents/
    ├── __init__.py           # registry — thêm agent chỉ sửa 1 dòng ở đây
    ├── supervisor/           # agent.py, prompts.py
    ├── research_agent/       # agent.py, tools.py, prompts.py
    └── vision_agent/         # agent.py, tools.py, prompts.py, image_utils.py
```

Thêm một agent mới cần đúng 2 việc:

1. Tạo thư mục `app/agents/<ten>_agent/` theo khung ở Bảng 3 của `QUY_TAC_THIET_KE.md`
   (tên thư mục phải trùng `AGENT_NAME`).
2. Thêm **một dòng** `AgentSpec(...)` vào `app/agents/__init__.py`.

Prompt của supervisor sinh tự động từ registry nên không phải sửa gì thêm.

## Biến môi trường

Xem `.env.example`. Đáng chú ý:

| Biến | Mặc định | Ghi chú |
|---|---|---|
| `GROQ_API_KEY` | — | **bắt buộc**, bắt đầu bằng `gsk_` |
| `GEMINI_API_KEY` | — | **bắt buộc** cho phần đọc ảnh, bắt đầu bằng `AQ.` |
| `LLM_PROVIDER` | `groq` | dùng khi `MODEL_*` không ghi tiền tố |
| `MODEL_SUPERVISOR` | `groq:llama-3.3-70b-versatile` | bộ điều phối |
| `MODEL_RESEARCH` | `groq:openai/gpt-oss-120b` | ReAct của Research Agent |
| `MODEL_VISION` | `groq:openai/gpt-oss-20b` | ReAct của Vision Agent |
| `MODEL_DESCRIBE` | `google:gemini-3.5-flash-lite` | tool `image_describer` |
| `MODEL_UTILITY` | `groq:llama-3.1-8b-instant` | tác vụ phụ |
| `YOLO_WEIGHTS` | `yolo11n.pt` | đổi `yolo11x.pt` khi quay demo |
| `VISION_DETAIL` | *(trống khi dùng Gemini)* | tham số riêng của OpenAI; tự để trống với `LLM_PROVIDER=google` |
| `RECURSION_LIMIT` | `50` | chặn agent lặp vô hạn |

## Tham khảo

- Tài liệu gốc của nhóm: `Visual Agentic AI.pdf`
- LangGraph Supervisor — https://reference.langchain.com/python/langgraph-supervisor
- Anthropic, How we built our multi-agent research system — https://www.anthropic.com/engineering/multi-agent-research-system

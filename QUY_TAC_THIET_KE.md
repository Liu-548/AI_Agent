# BẢNG YÊU CẦU — QUY TẮC THIẾT KẾ CHUNG
### Đồ án Visual Agentic AI · Multi-Agent System with Supervisor Architecture

| | |
|---|---|
| **Gửi cho** | 3 thành viên nhóm |
| **Áp dụng cho** | Toàn bộ code của Supervisor Agent, Research Agent, Vision Agent |
| **Ngày ban hành** | 17/08/2026 |
| **Ngày đóng băng hợp đồng (freeze)** | **20/08/2026** — sau ngày này, mọi thay đổi ở Bảng 3 phải cả nhóm đồng ý |
| **Ngày merge** | 28/08/2026 |
| **Tài liệu gốc** | `Visual Agentic AI.pdf` (mục V, VI, VII) |

---

## 0. Vì sao cần bảng này

Kế hoạch của nhóm là: mỗi người tự dựng cả 3 agent → mỗi người chọn 1 agent phát triển sâu →
cuối tháng 8 gộp 3 dự án làm một. **Rủi ro nằm ở bước gộp.** Ba người cùng làm theo một
notebook Colab sẽ tạo ra ba bản code trông giống nhau nhưng khác nhau ở đúng những chỗ chí
mạng: tên agent, tên tool, chữ ký hàm, cách đọc API key, phiên bản thư viện. Khi gộp lại,
Git không báo conflict (vì là 3 file khác nhau) nhưng hệ thống **chạy sai trong im lặng** —
supervisor gọi `transfer_to_vision` trong khi agent tên là `vision_agent`, và LangGraph chỉ
ném ra một lỗi routing khó hiểu vào đêm trước ngày nộp.

Ba nguyên tắc xuyên suốt:

1. **Hợp đồng quan trọng hơn code.** Bên trong agent của bạn, bạn viết thế nào cũng được.
   Nhưng phần *thò ra ngoài* (tên, chữ ký, kiểu trả về) là tài sản chung, không được tự đổi.
2. **Mỗi file có một chủ.** Hai người không cùng sửa một file → không có conflict.
3. **Sai hợp đồng phải đỏ ngay trên máy người sai**, chứ không phải lộ ra hôm merge.
   Vì vậy bảng này có bản dịch sang code là `app/core/contracts.py` + `tests/test_contract.py`.

> **Danh sách kiểm tra hằng ngày** nằm ở [`TRUOC_KHI_CHAY.md`](TRUOC_KHI_CHAY.md) —
> bảng này là *luật*, file kia là *thói quen*.
>
> **Việc phải làm ngay:** clone repo khung `visual-agentic-ai/` đã dựng sẵn, làm tiếp trên đó.
> Đừng ai bắt đầu lại từ notebook trắng — 80% rắc rối merge được loại bỏ chỉ bằng việc
> cả ba xuất phát từ cùng một cấu trúc thư mục.

---

## Bảng 1 — Môi trường & phiên bản

| Mã | Quy tắc | Vì sao | Mức |
|---|---|---|---|
| MT-01 | Python **3.11**. Ai đang dùng 3.12/3.13 phải đổi. | `wikipedia==1.4.0` dùng `setup.py` kiểu cũ, build hỏng trên môi trường setuptools mới. | Bắt buộc |
| MT-02 | Mỗi người tạo **virtualenv riêng** và **kích hoạt trước mỗi phiên làm việc**. Dấu hiệu đã kích hoạt: đầu dòng lệnh có `(.venv)`. | Mở cửa sổ terminal mới là venv tắt. Cài nhầm vào Python hệ thống thì `pip freeze` của mỗi người một khác, và cảnh 'chạy được trên máy tôi' bắt đầu từ đây. Kiểm tra: `python -c "import sys; print(sys.prefix)"` phải trỏ vào `.venv`. | Bắt buộc |
| MT-03 | Cài đúng `requirements.txt`, **version pin cứng**. Không ai tự `pip install -U`, cũng không ai tự hạ version. | LangChain/LangGraph đổi API rất nhanh. Bộ pin hiện tại đã được chạy qua toàn bộ test; đổi lẻ một gói là kéo theo cả chuỗi phụ thuộc (xem MT-08 để thấy một ví dụ thật). | Bắt buộc |
| MT-04 | Muốn nâng version thư viện → nhắn nhóm, sửa `requirements.txt` **một lần cho cả ba**. | Tránh cảnh "máy tôi chạy được mà máy bạn không". | Bắt buộc |
| MT-05 | `ultralytics` cài riêng, không nằm trong `requirements.txt` bắt buộc. | Nó kéo theo `torch` ~2GB. Người làm Research/Supervisor không cần, và vẫn chạy được toàn bộ test vì tool YOLO import trễ. | Bắt buộc |
| MT-06 | Chạy `pip freeze > /tmp/freeze.txt` và so với nhau **trước ngày merge**. | Phát hiện lệch version sớm 1 tuần thay vì 1 đêm. | Khuyến nghị |
| MT-07 | Cấu hình **LAI, hai nhà cung cấp**: Groq cho suy luận + gọi tool, Gemini chỉ cho phần đọc ảnh. Mỗi người tự lấy **key riêng** ở [console.groq.com/keys](https://console.groq.com/keys) và [aistudio.google.com/apikey](https://aistudio.google.com/apikey) bằng tài khoản riêng. | Free tier Gemini chỉ ~20 request/ngày/model, mà một câu qua supervisor tốn 4–6 lượt → chỉ 5–8 câu/ngày, không đủ làm đồ án. Groq cho 1.000–14.400 request/ngày. Nhưng Groq chưa có model đa phương thức đủ ổn định cho structured output nên phần đọc ảnh giữ Gemini — vai trò đó chỉ tốn 1 lượt mỗi câu hỏi ảnh nên 20/ngày là thừa. Hạn mức tính theo tài khoản/project: dùng chung key là ba người tranh nhau một sổ. | Bắt buộc |
| MT-08 | Dự án chạy trên **LangChain 1.x** (`langchain-core==1.5.5`, `langgraph==1.2.11`, `langchain-google-genai==4.3.4`). **Không hạ `langchain-google-genai` xuống dưới 3.0.** | Model Gemini 3 là model *thinking*: mỗi `functionCall` nó trả về kèm một `thought_signature`, và lượt sau phải gửi lại nguyên vẹn, nếu không API trả 400 `Function call is missing a thought_signature`. Chỉ từ `langchain-google-genai` 3.0 trở lên thư viện mới giữ và gửi lại chữ ký này, mà 3.0 lại đòi `langchain-core>=1.0`. Toàn bộ dòng Gemini 2.x đã bị Google tắt nên không có đường lùi về model không-thinking. | Bắt buộc |
| MT-09 | **Không tin tên model trong tài liệu.** Trước khi đổi `MODEL_*`, chạy `python -m app.main --models` để lấy danh sách model mà key thật sự dùng được. | Nhà cung cấp khai tử model theo lịch mà trang tài liệu cập nhật chậm: Groq bỏ `llama-3.3-70b-versatile` và `llama-3.1-8b-instant` cho free tier ngày **16/08/2026**, thay bằng `openai/gpt-oss-120b` và `-20b`, trong khi trang models vẫn còn liệt kê chúng. Lỗi ra là `404 model_not_found`, rất dễ nhầm là hỏng code. | Bắt buộc |

---

## Bảng 2 — Cấu trúc thư mục (chuẩn chung)

Nguyên tắc bố trí: **`app/` là folder tổng chứa toàn bộ hệ thống** — cả ba agent và mọi
file code cần thiết đều nằm trong đó. Những thứ thuộc về *thiết lập môi trường*
(`requirements.txt`, `.env`, `.venv/`, `pyproject.toml`) để ngoài gốc repo, không trộn vào
code. Nhờ vậy khi bạn muốn gộp hay đóng gói dự án của mình, chỉ cần cầm nguyên thư mục `app/`.

| Mã | Quy tắc | Vì sao | Mức |
|---|---|---|---|
| CT-01 | Dùng đúng cây thư mục dưới đây, không đổi tên thư mục. | Ba cấu trúc khác nhau thì không gộp được, phải viết lại import từ đầu. | Bắt buộc |
| CT-02 | **Một agent = một thư mục tự chứa** trong `app/agents/`, gồm `agent.py`, `tools.py`, `prompts.py` (và file phụ trợ riêng nếu cần). | Ranh giới thư mục trùng ranh giới phân công → mỗi người chỉ đụng thư mục của mình, gần như không thể conflict. | Bắt buộc |
| CT-03 | Code dùng chung của cả 3 agent nằm trong `app/core/`. Không ai được để logic riêng của agent mình vào đây. | `app/core/` là tài sản chung; mỗi lần có người nhét code riêng vào là một điểm đụng độ mới. | Bắt buộc |
| CT-04 | `__init__.py` của gói agent chỉ **re-export**, không chứa logic. Ngoại lệ duy nhất: `app/agents/__init__.py` (registry). | `__init__.py` là nơi ba người dễ đụng nhau nhất. | Bắt buộc |
| CT-05 | **Tên thư mục agent phải trùng `AGENT_NAME`** (`research_agent/` ↔ `AGENT_NAME = "research_agent"`). | Nhìn tên thư mục là biết node nào trong graph, ai sở hữu. Test `test_moi_agent_la_mot_goi_tu_chua` kiểm tra tự động. | Bắt buộc |
| CT-06 | Không để file `.py` rời trong `app/agents/` ngoài `__init__.py`. | Chặn kiểu cũ `research_agent.py` nằm lẫn với `research_agent/` — Python im lặng chọn một cái, rất khó lần. | Bắt buộc |
| CT-07 | Notebook (`.ipynb`) chỉ dùng để thử nghiệm, **không commit**. Code chạy được phải nằm trong `.py`. | Diff của notebook là JSON kèm output ảnh base64 — conflict gần như không giải được bằng tay. | Bắt buộc |

```
visual-agentic-ai/                    <- gốc repo: chỉ chứa thiết lập môi trường + tài liệu
├── requirements.txt                  # môi trường, KHÔNG phải code
├── pyproject.toml
├── .env.example / .env
├── .gitignore
├── README.md
├── QUY_TAC_THIET_KE.md
├── assets/                           # ảnh demo (chỉ ảnh nhỏ)
├── tests/
│   ├── fakes.py                      # model giả + detector giả (test không tốn tiền)
│   ├── test_contract.py              # bản dịch sang code của Bảng 2 + Bảng 3
│   ├── test_research_tools.py
│   ├── test_vision_tools.py
│   └── test_agents_e2e.py
│
└── app/                              <<< FOLDER TỔNG: toàn bộ hệ thống nằm trong đây
    ├── main.py                       # CLI chạy thử
    ├── core/                         # [TÀI SẢN CHUNG] dùng chung cho cả 3 agent
    │   ├── config.py                 #   DUY NHẤT nơi đọc biến môi trường
    │   ├── llm.py                    #   DUY NHẤT nơi khởi tạo ChatModel
    │   ├── contracts.py              #   hợp đồng máy kiểm tra được
    │   └── pretty.py                 #   in trace khi stream
    └── agents/
        ├── __init__.py               # REGISTRY — file duy nhất phải sửa khi thêm agent
        │
        ├── supervisor/               # ===== của người làm Supervisor =====
        │   ├── __init__.py
        │   ├── agent.py              #   build_supervisor()
        │   └── prompts.py
        │
        ├── research_agent/           # ===== của người làm Research =====
        │   ├── __init__.py
        │   ├── agent.py              #   AGENT_NAME + build_research_agent()
        │   ├── tools.py              #   arxiv_search, wikipedia_search
        │   └── prompts.py
        │
        └── vision_agent/             # ===== của người làm Vision =====
            ├── __init__.py
            ├── agent.py              #   AGENT_NAME + build_vision_agent()
            ├── tools.py              #   image_describer, detect_and_count_objects
            ├── prompts.py
            └── image_utils.py        #   encode_image, extract_image_ref
```

> Đọc cây thư mục này theo chiều dọc: **ba khối `supervisor/`, `research_agent/`,
> `vision_agent/` là ba vùng làm việc độc lập.** Trong 8 ngày phát triển riêng, mỗi người
> chỉ chạm vào đúng khối của mình; ba khối đó không có file nào chung nên Git không bao giờ
> phải merge nội dung của hai người trong cùng một file.
>
> `supervisor/` cố ý **không** có mặt trong registry `AGENT_SPECS`: nó là người điều phối
> registry, không phải một phần tử của registry. Đưa vào sẽ tạo vòng lặp import và khiến
> supervisor tự gọi chính nó.

---

## Bảng 3 — HỢP ĐỒNG GIAO DIỆN (quan trọng nhất — đóng băng 20/08)

Đây là phần duy nhất tuyệt đối không được tự ý đổi. Mọi thứ khác có thể thương lượng.

| Mã | Quy tắc | Vì sao | Mức |
|---|---|---|---|
| IF-01 | Mỗi module agent **phải** khai báo 3 thứ: `AGENT_NAME: str`, `AGENT_DESCRIPTION: str`, và factory `build_<agent_name>(model=None, tools=None, prompt=None)`. | Supervisor và test đều gọi qua đúng ba thứ này. Thiếu một cái là registry gãy. | Bắt buộc |
| IF-02 | `AGENT_NAME` viết `snake_case`, kết thúc bằng `_agent`, **khớp tuyệt đối** với tham số `name=` truyền vào `create_react_agent`. | `langgraph-supervisor` sinh handoff tool theo công thức `transfer_to_<AGENT_NAME>`. Lệch một ký tự → supervisor không route được, mà lỗi báo ra rất khó hiểu. | Bắt buộc |
| IF-03 | Factory **phải** nhận `model=None` và `tools=None` với giá trị mặc định. | Đây là điều kiện để test bằng model giả. Không có nó thì mọi test đều phải có API key và tốn tiền — nghĩa là sẽ không ai chạy test. | Bắt buộc |
| IF-04 | Mọi tool nhận **đúng một tham số tên `text: str`** và trả về **`str`**. Dữ liệu có cấu trúc thì `json.dumps(...)`. | Ba người đặt tên tham số `query`/`input`/`img_path` khác nhau → prompt của supervisor và của agent lệch nhau, LLM gọi tool sai tham số. | Bắt buộc |
| IF-05 | Tool **không được `raise`**. Lỗi trả về chuỗi `"ERROR: <MÃ_LỖI> | <thông điệp>"` (dùng `contracts.tool_error()`). | Một exception lọt ra sẽ giết cả graph, mất toàn bộ phiên. Trả chuỗi lỗi thì agent tự đọc được và xử lý tiếp. | Bắt buộc |
| IF-06 | `return_direct` của tool mặc định là **`False`**. | `return_direct=True` cắt ngang vòng ReAct: agent trả thẳng output thô của tool, không tổng hợp, và không gọi được tool thứ hai. Đúng ca "màu lông + giống chó" trong tài liệu sẽ hỏng. | Bắt buộc |
| IF-07 | Tên tool cố định: `arxiv_search`, `wikipedia_search`, `image_describer`, `detect_and_count_objects`. Đổi tên phải báo nhóm. | Tên tool là *một phần của prompt* — LLM đọc nó để quyết định gọi gì. Đổi tên tool = đổi hành vi hệ thống. | Bắt buộc |
| IF-08 | `description` của tool viết bằng **tiếng Anh**, ≥ 20 ký tự, nói rõ *khi nào dùng* chứ không chỉ *làm gì*. | Đây là thứ LLM đọc để route. Description mơ hồ = agent gọi nhầm tool, không phải lỗi code. | Bắt buộc |
| IF-09 | Thêm agent mới → chỉ thêm **một dòng `AgentSpec(...)`** vào `app/agents/__init__.py`. Không hard-code tên agent ở bất kỳ chỗ nào khác. | Prompt của supervisor được sinh tự động từ registry. Nhờ vậy bề mặt conflict khi thêm agent chỉ còn đúng 1 dòng. | Bắt buộc |
| IF-10 | State giữa các node dùng `MessagesState` mặc định của LangGraph. Ai cần key state riêng phải khai báo ở một schema chung và báo nhóm. | Ba schema state khác nhau thì không compile chung một graph được. | Bắt buộc |

**Khung bắt buộc — copy nguyên xi khi viết agent mới.** Tạo thư mục
`app/agents/<ten>_agent/` với 4 file:

```python
# app/agents/<ten>_agent/agent.py
from app.agents.<ten>_agent.prompts import <TEN>_AGENT_PROMPT

AGENT_NAME = "<ten>_agent"                    # PHẢI trùng tên thư mục (CT-05)
AGENT_DESCRIPTION = "Use for ... . Cannot ... ."   # 1 câu, supervisor đọc để route

def build_<ten>_agent(model=None, tools=None, prompt=None):
    from langgraph.prebuilt import create_react_agent
    if model is None:
        from app.core.llm import get_llm
        model = get_llm("agent")
    if tools is None:
        from app.agents.<ten>_agent.tools import default_<ten>_tools
        tools = default_<ten>_tools()
    return create_react_agent(
        model=model, tools=tools,
        prompt=prompt or <TEN>_AGENT_PROMPT,
        name=AGENT_NAME,                      # PHẢI trùng AGENT_NAME
    )
```

```python
# app/agents/<ten>_agent/__init__.py  — chỉ re-export, không có logic
from app.agents.<ten>_agent.agent import AGENT_DESCRIPTION, AGENT_NAME, build_<ten>_agent
from app.agents.<ten>_agent.tools import default_<ten>_tools

__all__ = ["AGENT_NAME", "AGENT_DESCRIPTION", "build_<ten>_agent", "default_<ten>_tools"]
```

Còn lại `tools.py` (các tool theo IF-04…IF-08) và `prompts.py` (hằng số `<TEN>_AGENT_PROMPT`).
Cuối cùng thêm **một dòng** vào `app/agents/__init__.py`.

---

## Bảng 4 — Đặt tên & phong cách code

| Mã | Quy tắc | Vì sao | Mức |
|---|---|---|---|
| DT-01 | Tên biến, hàm, file, tên tool: **tiếng Anh, `snake_case`, không dấu**. | Tên có dấu tiếng Việt gây lỗi encoding trên Windows và không đặt được tên tool cho LLM. | Bắt buộc |
| DT-02 | Comment và docstring: tiếng Việt thoải mái. Prompt gửi LLM: tiếng Anh. | Prompt tiếng Anh cho kết quả ổn định hơn; comment tiếng Việt để cả nhóm đọc nhanh. | Khuyến nghị |
| DT-03 | Prompt của agent nào nằm trong `prompts.py` của gói agent đó, đặt hằng số VIẾT HOA, hậu tố `_PROMPT`. Không viết prompt inline trong lời gọi `create_react_agent`. | Prompt là thứ chỉnh nhiều nhất khi tinh chỉnh agent. Để inline thì mỗi lần chỉnh là một thay đổi ngay giữa code chung; tách ra `prompts.py` riêng thì ba người sửa ba file khác nhau. | Bắt buộc |
| DT-04 | File encoding **UTF-8**, xuống dòng **LF**. Bật `git config core.autocrlf input` (Windows). | Người dùng Windows commit CRLF sẽ làm cả file hiện "thay đổi toàn bộ" → conflict giả trên mọi dòng. | Bắt buộc |
| DT-05 | Định dạng code: dòng ≤ 100 ký tự. Nếu dùng formatter thì cả ba dùng `ruff format`, cùng cấu hình trong `pyproject.toml`. | Một người chạy `black`, một người không → diff phình ra hàng trăm dòng vô nghĩa. | Khuyến nghị |
| DT-06 | **File cấu hình (`requirements.txt`, `.env`, `.env.example`) chỉ được chứa ký tự ASCII** — không dấu tiếng Việt. Giải thích tiếng Việt để trong file `.md`. | pip đọc `requirements.txt` bằng codec locale của Windows (cp1258 trên máy cài tiếng Việt), gặp chữ có dấu là hỏng cả lệnh cài: `UnicodeDecodeError: 'charmap' codec can't decode byte 0x81`. Test `test_file_cau_hinh_chi_dung_ascii` quét tự động. | Bắt buộc |

---

## Bảng 5 — Cấu hình & bí mật

| Mã | Quy tắc | Vì sao | Mức |
|---|---|---|---|
| CH-01 | **Tuyệt đối không hard-code API key** trong `.py` hay `.ipynb`, kể cả để test nhanh. | Key lộ lên GitHub bị bot quét trong vài phút, nhà cung cấp thu hồi key và cả nhóm mất phiên làm việc. Có test tự động quét cả `sk-…` (OpenAI) lẫn `AIza…` (Google) trong source. | Bắt buộc |
| CH-02 | Mọi biến môi trường chỉ đọc ở **`app/core/config.py`**. Cấm `os.getenv()` rải rác. | Muốn biết hệ thống cần những biến gì chỉ phải đọc một file; đổi provider chỉ sửa một chỗ. | Bắt buộc |
| CH-03 | Mọi `ChatModel` chỉ khởi tạo qua **`app.core.llm.get_llm(role)`**. Cấm gọi `ChatOpenAI(...)` trực tiếp trong agent/tool. | Ba người khởi tạo model ở 6 chỗ với 3 `temperature` khác nhau → không giải thích được kết quả khi bảo vệ đồ án. | Bắt buộc |
| CH-04 | Thêm biến môi trường mới → phải cập nhật `.env.example` trong cùng commit. | Người khác `git pull` về là chạy được ngay, không phải đi hỏi "thiếu biến gì". | Bắt buộc |
| CH-07 | Không hard-code nhà cung cấp. Đổi Groq ↔ Gemini ↔ OpenAI ↔ Ollama chỉ được phép qua `MODEL_*`, `LLM_PROVIDER`, `LLM_BASE_URL` trong `.env`. | Ba người dùng ba cấu hình khác nhau vẫn merge được, vì không ai đụng vào code. Ai sửa `llm.py` để cắm provider riêng là phá quy tắc này. | Bắt buộc |
| CH-05 | Mỗi người đặt `LANGSMITH_PROJECT` riêng (`...-tuan`, `...-a`, `...-b`). | Ba người trace chung một project thì không ai đọc được trace của mình. | Khuyến nghị |
| CH-06 | Model khai báo theo vai trò và **kèm tiền tố nhà cung cấp**: `MODEL_RESEARCH=groq:openai/gpt-oss-120b`, `MODEL_DESCRIBE=google:gemini-3.5-flash-lite`. Năm vai trò phải là **năm model khác nhau**. | Hạn mức tính riêng theo từng model; gộp hai vai trò vào một model là tự cắt đôi số lượt mỗi ngày. Tiền tố provider cho phép mỗi vai trò chạy một nhà cung cấp khác nhau mà agent không cần biết. `get_llm()` cố ý không có vai trò mặc định để không ai gộp nhầm. Kiểm tra: `python -m app.main --config`. | Bắt buộc |

---

## Bảng 6 — Lỗi, log và chi phí

| Mã | Quy tắc | Vì sao | Mức |
|---|---|---|---|
| LX-01 | Mã lỗi của tool viết HOA, có ý nghĩa: `NO_IMAGE_REF`, `IMAGE_UNREADABLE`, `ARXIV_UNAVAILABLE`, `YOLO_INFERENCE_FAILED`… | Khi hệ thống trả sai, đọc mã lỗi là biết ngay tầng nào hỏng, không phải đọc traceback 40 dòng. | Bắt buộc |
| LX-02 | Luôn đặt `recursion_limit` (mặc định 50) khi `.stream()` / `.invoke()`. | Agent lặp vô hạn sẽ đốt sạch quota API của nhóm trong vài phút. | Bắt buộc |
| LX-03 | Không `print()` trong `app/agents/` và `app/core/`. Muốn in thì in ở `main.py` hoặc dùng `logging`. | `print` trong tool làm bẩn output stream, và khi ghép vào web/UI sau này sẽ phải đi xoá từng dòng. | Khuyến nghị |
| LX-04 | Giữ `top_k_results` nhỏ (arXiv 2, Wikipedia 2) và `detail="low"` cho ảnh khi dev. | Chi phí token tăng tuyến tính theo số kết quả; `detail="high"` đắt gấp nhiều lần. Chỉ bật cao khi quay demo. | Khuyến nghị |
| LX-06 | **Đếm lượt gọi trước khi chạy.** Một câu hỏi qua supervisor tốn ~4–6 lượt LLM (supervisor → agent → tool → agent → supervisor). Khi đang sửa một agent, chạy thẳng `--agent <ten>` thay vì qua supervisor. | Với 20 request/ngày/model, chạy đủ bộ demo 5 ca là hết sạch hạn mức. Chạy thẳng agent con bỏ được 2 lượt của supervisor mỗi lần thử. | Khuyến nghị |
| LX-07 | Trước khi kêu "hệ thống hỏng", chạy `python -m app.main --config` rồi đối chiếu hạn mức ([Groq](https://console.groq.com/docs/rate-limits) · [Gemini](https://aistudio.google.com/rate-limit)). | 429 trông y như lỗi code nhưng thường chỉ là hết lượt của một model. | Khuyến nghị |
| LX-05 | Tool phải xử lý được cả trường hợp "không có kết quả" (trả câu thông báo, không trả chuỗi rỗng). | Chuỗi rỗng làm LLM tự bịa nội dung — lỗi này rất khó phát hiện khi chấm. | Bắt buộc |

---

## Bảng 7 — Git & nhánh

| Mã | Quy tắc | Vì sao | Mức |
|---|---|---|---|
| GIT-01 | Một repo chung trên GitHub, 3 nhánh: `feat/supervisor`, `feat/research`, `feat/vision`. Nhánh tích hợp: `develop`. `main` chỉ nhận bản chạy được. | Mỗi người một nhánh thì lịch sử sạch, revert được từng phần. | Bắt buộc |
| GIT-02 | **Không commit thẳng vào `main`/`develop`.** Merge qua Pull Request, có ít nhất 1 người review. | Người review chính là hàng rào bắt vi phạm Bảng 3 trước khi nó vào code chung. | Bắt buộc |
| GIT-03 | `git pull --rebase origin develop` **mỗi ngày**, không để dồn 1 tuần. | Conflict 1 ngày giải trong 5 phút; conflict 7 ngày giải trong 1 buổi và dễ làm mất code. | Bắt buộc |
| GIT-04 | Commit message: `<scope>: <việc đã làm>` — ví dụ `vision: them tool dem vat the bang YOLOv11`. Scope ∈ {supervisor, research, vision, core, docs, test}. | Nhìn `git log` là biết ai đụng vùng nào, truy vết nhanh khi hệ thống hỏng. | Khuyến nghị |
| GIT-05 | **Không commit**: `.env`, `*.pt`, `__pycache__/`, `.venv/`, `*.ipynb`, ảnh > 2MB. Đã có sẵn `.gitignore`. | `yolo11x.pt` nặng 109MB — vượt giới hạn 100MB của GitHub, và một khi đã vào lịch sử thì phải viết lại toàn bộ history mới xoá được. | Bắt buộc |
| GIT-06 | Commit nhỏ và thường xuyên (≤ ~200 dòng thay đổi). | Commit khổng lồ thì review không nổi, và conflict của nó cũng khổng lồ. | Khuyến nghị |

---

## Bảng 8 — Test

| Mã | Quy tắc | Vì sao | Mức |
|---|---|---|---|
| TS-01 | Trước khi mở PR: `pytest -m "not network"` phải **xanh 100%**. | Đây là điều kiện cần để merge. Test contract sẽ bắt được vi phạm Bảng 3 ngay trên máy người vi phạm. | Bắt buộc |
| TS-02 | Mỗi agent phải có test end-to-end dùng **model giả** (`tests/fakes.py`), không dùng API thật. | Test cần API key sẽ không ai chạy (tốn tiền, chậm, cần mạng) → coi như không có test. | Bắt buộc |
| TS-03 | Test gọi mạng thật đánh dấu `@pytest.mark.network` và **skip khi mất mạng**, không fail. | Wifi trường chặn `export.arxiv.org` là chuyện thường. Test đỏ giả khiến cả nhóm mất niềm tin vào test. | Bắt buộc |
| TS-04 | Thêm tool mới → thêm ít nhất 2 test: một ca chạy đúng, một ca lỗi (trả `ERROR:`). | Nhánh lỗi mới là nhánh hay hỏng lúc demo. | Bắt buộc |
| TS-05 | Không sửa `tests/test_contract.py` để test xanh. Nếu thấy contract sai thì **họp nhóm sửa contract**. | Sửa test cho qua là cách nhanh nhất để phá hợp đồng chung mà không ai biết. | Bắt buộc |
| TS-06 | Test **không được đọc `.env`**. `tests/conftest.py` vô hiệu hoá `load_dotenv` và xoá biến môi trường của dự án trước khi chạy. Thêm biến mới vào `config.py` thì thêm luôn tên biến đó vào `APP_ENV_VARS` trong `conftest.py`. | `config.py` gọi `load_dotenv()` ngay khi import, nên nếu không chặn thì kết quả test phụ thuộc `.env` của từng máy: xanh trên máy chưa tạo `.env`, đỏ trên máy đã tạo. Ví dụ thật: ai đặt `IMAGE_DESCRIBER_RETURN_DIRECT=true` trong `.env` sẽ làm đỏ một test hợp đồng dù code hoàn toàn đúng. | Bắt buộc |

---

## Bảng 9 — Phân chia sở hữu file (chống conflict tận gốc)

Cấu trúc thư mục ở Bảng 2 được thiết kế để bảng này đọc gọn đúng một dòng mỗi người:

| Vùng | Chủ sở hữu | Người khác muốn đổi |
|---|---|---|
| **cả thư mục** `app/agents/research_agent/` + `tests/test_research_tools.py` | Người làm **Research** | Nhắn nhóm, không tự sửa |
| **cả thư mục** `app/agents/vision_agent/` + `tests/test_vision_tools.py` | Người làm **Vision** | Nhắn nhóm, không tự sửa |
| **cả thư mục** `app/agents/supervisor/` + `app/main.py` + `app/core/pretty.py` | Người làm **Supervisor** | Nhắn nhóm, không tự sửa |
| `app/core/config.py`, `app/core/llm.py`, `app/core/contracts.py`, `app/agents/__init__.py`, `tests/fakes.py`, `tests/test_contract.py`, `tests/test_agents_e2e.py`, `requirements.txt`, `.env.example`, `.gitignore` | **TÀI SẢN CHUNG** | Sửa phải báo nhóm trong PR và tag cả 2 người còn lại |

> Quy tắc vàng: **thấy file không thuộc vùng của mình đang cản đường → nhắn, đừng sửa.**
> 90% conflict trong đồ án nhóm đến từ việc "tiện tay sửa luôn cho nhanh".

---

## Bảng 10 — Những chỗ code khung khác tài liệu gốc (và lý do)

Để mọi người không hoang mang khi đối chiếu với file PDF:

| Điểm | Tài liệu gốc | Code khung | Lý do |
|---|---|---|---|
| Nhận diện MIME của ảnh | `python-magic` | `Pillow` + `mimetypes` | `python-magic` cần `libmagic1` trên Linux và `python-magic-bin` trên Windows. Ba máy khác OS sẽ hỏng đúng ở dòng này. |
| Tách đường dẫn ảnh khỏi câu hỏi | Luôn gọi LLM (`PydanticOutputParser`) | Regex trước, LLM chỉ là phương án dự phòng | Mỗi lần gọi tool tốn thêm một lượt LLM (chậm + tốn tiền), và làm test bắt buộc phải có API key. |
| `image_describer` | `return_direct=True` | `return_direct=False` | `True` cắt ngang vòng ReAct → agent không gọi được tool thứ hai, hỏng đúng ca demo "màu lông + giống chó". |
| Tên tool | `arxiv`, `wikipedia` | `arxiv_search`, `wikipedia_search` | Đồng bộ với `detect_and_count_objects`; động từ trong tên giúp LLM chọn tool chính xác hơn. |
| `detect_and_count_objects` | trả `dict` | trả chuỗi JSON | Mọi tool trả cùng một kiểu `str` → hợp đồng đơn giản, serialize ổn định khi ghi trace. |
| Trọng số YOLO | `yolo11x.pt` (~109MB) | `yolo11n.pt` (~5MB) mặc định | Nhẹ, tải nhanh khi dev. Đổi sang `x` bằng biến môi trường khi quay demo. |
| Xử lý lỗi tool | lẫn lộn `raise` và trả chuỗi | luôn trả `"ERROR: MÃ | thông điệp"` | Exception lọt ra ngoài sẽ giết cả graph. |
| Nhà cung cấp LLM | OpenAI (`gpt-4o-mini`, `gpt-4.1-nano`) | Google Gemini, đường native (`langchain-google-genai`) | API OpenAI phải nạp tiền trước; Gemini có bậc miễn phí. Việc đổi gói gọn trong `app/core/llm.py` — agent và tool không đổi một dòng nào. |
| Biến môi trường key | `OPENAI_API_KEY` | `LLM_API_KEY` + `LLM_BASE_URL` | Dán key Gemini vào biến tên `OPENAI_API_KEY` gây hiểu nhầm. Vẫn đọc được `OPENAI_API_KEY`/`GEMINI_API_KEY` để không ai bị kẹt. |

---

## Bảng 11 — Lỗi đã biết (đọc trước, khỏi mất buổi tối)

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `JSONDecodeError: Expecting value: line 1 column 1 (char 0)` khi gọi Wikipedia | Wikimedia chặn User-Agent mặc định của `requests`, trả body rỗng | `wikipedia.set_user_agent("AppName/1.0 (contact: ...)")` — đã làm sẵn trong `research_tools.py` |
| `cv2.error: ... imshow not implemented` khi hiện ảnh YOLO | `results[0].show()` gọi `cv2.imshow`, không chạy được trên Colab/headless | Dùng `results[0].plot()` → đảo BGR sang RGB → hiển thị qua PIL/IPython |
| `pip install wikipedia` build hỏng | `setup.py` kiểu cũ, không tương thích setuptools mới | Dùng Python 3.11 + venv có `setuptools` mới nhất, hoặc `pip install --upgrade pip setuptools wheel` trước |
| GitHub từ chối push | Đã lỡ commit `yolo11x.pt` (109MB > giới hạn 100MB) | Có `.gitignore` sẵn. Nếu đã lỡ: `git rm --cached yolo11x.pt` rồi `git filter-repo`/`BFG` để xoá khỏi lịch sử |
| Supervisor không route, báo lỗi node lạ | Tên agent lệch với `transfer_to_<name>` | Chạy `pytest tests/test_contract.py` — sẽ chỉ ra ngay tên nào sai |
| Agent lặp vô hạn, cháy quota | Thiếu `recursion_limit` | Luôn truyền `config={"recursion_limit": 50}` |
| `401 Incorrect API key provided: sk-....` | `.env` vẫn giữ chuỗi mẫu, chưa dán key thật | Kiểm tra bằng `python -c "from app.core.config import settings as s; print(s.provider_name, len(s.llm_api_key))"` |
| Danh sách API key trên platform.openai.com trống trơn | Tài khoản ChatGPT **không** tự có key API; key lại còn scope theo project | Nhóm đã chuyển sang Gemini — lấy key ở [AI Studio](https://aistudio.google.com/apikey) |
| `400 Function call is missing a thought_signature in functionCall parts` | Thư viện `langchain-google-genai` quá cũ, không giữ lại chữ ký suy luận của model Gemini 3 giữa các lượt | Cài đúng `requirements.txt` hiện tại (`langchain-google-genai==4.3.4` trên nền LangChain 1.x). Xem MT-08 |
| `LangGraphDeprecatedSinceV10: create_react_agent has been moved to langchain.agents` | Cảnh báo của LangGraph 1.x | Chỉ là cảnh báo, hệ thống vẫn chạy đúng. `langgraph-supervisor` bên trong cũng còn dùng hàm này |
| `429 RESOURCE_EXHAUSTED` / `rate_limit_exceeded` | Cạn hạn mức của riêng MỘT model (không phải hỏng code) | `app/main.py` đã đổi lỗi này thành hướng dẫn thay vì traceback. Chạy `python -m app.main --config` xem vai trò nào dùng model nào, rồi đổi đúng dòng `MODEL_*` đó sang model còn hạn mức (vd `groq:llama-3.1-8b-instant`, 14.400 req/ngày) |
| Key Gemini không bắt đầu bằng `AIza` mà là `AQ.` | Google đổi định dạng key từ 06/2026 (Standard → Auth key) | Bình thường, không phải lỗi. Chỉ cần giữ `LLM_PROVIDER=google` |
| `401 invalid_api_key` / `400 multiple authentication credentials` khi gọi Gemini | Dùng key `AQ.` với endpoint tương thích OpenAI (`…/v1beta/openai/`) | Đặt `LLM_PROVIDER=google`, bỏ trống `LLM_BASE_URL`. `config.py` đã chặn sẵn tổ hợp này |
| `UnicodeDecodeError: 'charmap' codec can't decode byte 0x81` khi `pip install -r` | `requirements.txt` có chữ tiếng Việt có dấu, pip đọc bằng codec cp1258 của Windows tiếng Việt | File cấu hình chỉ dùng ASCII (quy tắc DT-06). Đã sửa sẵn trong repo |
| Cài xong thư viện mà `import` vẫn báo không thấy | Quên kích hoạt venv, gói đã cài vào Python hệ thống | Kích hoạt `.venv` rồi cài lại. Kiểm tra `python -c "import sys; print(sys.prefix)"` |
| `--config` báo thiếu key dù `.env` có đủ | Chạy nhầm Python hệ thống → thiếu `python-dotenv` → `.env` không được nạp | Kích hoạt venv. `python -m app.main --config` in sẵn dòng `python:`, `venv:`, `.env:` để nhìn ra ngay |
| `pip check` báo `arxiv 2.1.3 requires requests~=2.32.0` | Một thư viện mới kéo `requests` lên 2.34 | `requirements.txt` đã ghim `requests>=2.32,<2.33`; cài lại đúng file đó |
| Endpoint báo lỗi tham số `detail` không hợp lệ | `detail` là tham số riêng của OpenAI | Để `VISION_DETAIL=` (rỗng) trong `.env` — code sẽ bỏ hẳn trường này |

---

## Lịch trình & quy trình merge

| Ngày | Việc | Ai |
|---|---|---|
| 17–19/08 | Mỗi người dựng xong cả 3 agent theo tài liệu, chạy được ít nhất 1 trong 5 ca demo | Cả 3 |
| **20/08** | Họp chốt: ai làm agent nào + **đóng băng Bảng 3**. Push code khung lên `main`, cả 3 clone lại | Cả 3 |
| 20–27/08 | Phát triển sâu trên nhánh riêng. `git pull --rebase origin develop` mỗi ngày | Mỗi người |
| **26/08** | So `pip freeze`, chốt lại `requirements.txt` lần cuối | Cả 3 |
| **28/08** | Code freeze. Merge vào `develop` theo thứ tự: **research → vision → supervisor** | Người tích hợp |
| 29–30/08 | Chạy 5 ca demo trong tài liệu, sửa lỗi tích hợp, quay video demo | Cả 3 |
| 31/08 | Viết báo cáo, nộp | Cả 3 |

**Thứ tự merge có chủ đích:** hai agent con vào trước, supervisor vào sau cùng — vì supervisor
phụ thuộc vào tên của cả hai. Ngược lại thì phải merge hai lần.

### Checklist bắt buộc trước khi mở Pull Request

- [ ] `pytest -m "not network"` xanh 100%
- [ ] `pytest tests/test_contract.py` xanh (không sửa file test này để cho qua)
- [ ] Không có `.env`, `*.pt`, `*.ipynb`, `__pycache__/` trong `git status`
- [ ] Không có chuỗi `sk-...` nào trong diff
- [ ] Biến môi trường mới (nếu có) đã thêm vào `.env.example`
- [ ] Đã `git pull --rebase origin develop` và giải hết conflict
- [ ] Chỉ đụng vào file thuộc vùng sở hữu của mình (Bảng 9); nếu có đụng vùng chung thì đã tag 2 người kia
- [ ] Chạy thử `python -m app.main --graph` — state graph vẫn có đủ các node

### Checklist nghiệm thu sau khi merge (chạy đủ 5 ca của tài liệu)

- [ ] Ca 1 — Research-only: *"What is the latest research on positional embeddings?"*
- [ ] Ca 2 — Vision + Research: *"What is the concept visualized in the image? …"*
- [ ] Ca 3 — URL trực tiếp: ảnh từ link internet
- [ ] Ca 4 — Pure Vision: *"How many dogs are there in the image?"*
- [ ] Ca 5 — Tổng hợp: *"What color fur does the dog have? And look for more information about this dog."*

---

## Tóm tắt cho người bận

Nếu chỉ nhớ được 5 điều, hãy nhớ 5 điều này:

1. **Clone repo khung, đừng bắt đầu từ notebook trắng.**
2. `AGENT_NAME` và tên tool là tài sản chung — không tự đổi sau ngày 20/08.
3. Không hard-code API key. Không commit `.env`, `*.pt`, `*.ipynb`.
4. Tool không bao giờ `raise`; lỗi thì trả `"ERROR: MÃ | thông điệp"`.
5. `pytest -m "not network"` phải xanh trước khi mở PR.

# TRƯỚC KHI CHẠY THỬ — danh sách kiểm tra

> Mở file này mỗi lần ngồi vào làm. Toàn bộ nội dung đây được rút ra từ những lỗi
> nhóm đã thực sự gặp, không phải lý thuyết.

---

## Phần 0 — Chỉ làm MỘT LẦN trên mỗi máy

- [ ] **Python 3.11** (không phải 3.12/3.13/3.14)

  ```powershell
  py -3.11 --version        # phải ra 3.11.x
  ```

  Nếu chưa có: `winget install Python.Python.3.11` rồi **mở cửa sổ PowerShell mới**.

- [ ] **Tạo venv bằng đúng 3.11**

  ```powershell
  py -3.11 -m venv .venv
  ```

- [ ] **Cài thư viện** (sau khi đã kích hoạt venv ở Phần 1)

  ```powershell
  python -m pip install --upgrade pip setuptools wheel
  python -m pip install -r requirements.txt
  python -m pip check          # phải ra: No broken requirements found.
  ```

- [ ] **Tạo `.env` và điền HAI key**

  ```powershell
  Copy-Item .env.example .env
  notepad .env
  ```

  | Biến | Lấy ở đâu | Dạng key |
  |---|---|---|
  | `GROQ_API_KEY` | https://console.groq.com/keys | bắt đầu `gsk_` |
  | `GEMINI_API_KEY` | https://aistudio.google.com/apikey | bắt đầu `AQ.` |

  Dán key trần: **không dấu ngoặc kép, không khoảng trắng quanh dấu `=`**.

- [ ] **Chỉ người phụ trách Vision Agent** mới cần:

  ```powershell
  python -m pip install ultralytics==8.3.108     # ~2GB, kéo theo torch
  ```

---

## Phần 1 — MỖI LẦN mở cửa sổ terminal mới

Đây là bước hay quên nhất. Trong một buổi làm việc, quên bước này đã gây ra ba lỗi
khác nhau: `pip không tồn tại`, `ModuleNotFoundError: No module named 'pydantic'`,
và `key[groq]: thiếu` (dù key vẫn nằm nguyên trong `.env`).

- [ ] **Kích hoạt venv**

  ```powershell
  cd C:\CTK47C\DoAnChuyenNganh\visual-agentic-ai
  .\.venv\Scripts\Activate.ps1
  ```

  Báo `running scripts is disabled`? Chạy trước:
  `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

- [ ] **Xác nhận đã vào venv** — đầu dòng lệnh phải hiện `(.venv)`

---

## Phần 2 — Trước khi gọi API thật (tốn hạn mức)

- [ ] **Kiểm tra cấu hình** — lệnh này KHÔNG tốn lượt nào

  ```powershell
  python -m app.main --config
  ```

  Kết quả đúng phải có đủ ba điều:

  ```
    supervisor  groq    openai/gpt-oss-120b         <- 5 vai trò, 5 model khác nhau
    ...
    key[google]: Gemini Auth key (AQ.), 43 ký tự    <- KHÔNG được là "thiếu"
    key[groq]:   Groq key (gsk_), 56 ký tự
    venv   : có                                     <- KHÔNG được là "KHÔNG"
    .env   : đã nạp (...)                           <- KHÔNG được là "LỖI"
  ```

- [ ] **Kiểm tra model còn sống** — cũng không tốn lượt sinh nội dung

  ```powershell
  python -m app.main --models
  ```

  Mọi tên trong `--config` phải có mặt trong danh sách này. Nhà cung cấp khai tử
  model theo lịch, tài liệu của họ lạc hậu hơn thực tế — chỉ tin lệnh này.

- [ ] **Chạy test** — cũng không tốn lượt nào, dùng model giả

  ```powershell
  python -m pytest -q -m "not network"     # phải xanh hết
  ```

- [ ] **In sơ đồ** — không gọi LLM

  ```powershell
  python -m app.main --graph
  ```

Ba bước trên xanh thì mới sang gọi thật. Thứ tự chạy thật, rẻ trước đắt sau:

```powershell
python -m app.main --agent research_agent "rotary positional encoding"   # ~3 lượt
python -m app.main "machine learning là gì?"                             # ~5 lượt
```

---

## Phần 3 — Trước khi commit / mở Pull Request

- [ ] `python -m pytest -q -m "not network"` xanh 100%
- [ ] `git status` **không** có `.env`, `.venv/`, `*.pt`, `*.ipynb`, `__pycache__/`
- [ ] Trong diff không có chuỗi nào giống key (`sk-…`, `AIza…`, `AQ.…`, `gsk_…`)
- [ ] Biến môi trường mới (nếu có) đã thêm vào `.env.example` **và** vào
      `APP_ENV_VARS` trong `tests/conftest.py`
- [ ] Đã `git pull --rebase origin develop`
- [ ] Chỉ đụng vào thư mục agent của mình (Bảng 9 trong `QUY_TAC_THIET_KE.md`)

---

## Phần 4 — Gặp lỗi thì tra ở đây trước

| Thấy gì | Nguyên nhân thật | Làm gì |
|---|---|---|
| `source : ... is not recognized` | Đang gõ cú pháp bash trong PowerShell | `.\.venv\Scripts\Activate.ps1` |
| `pip : ... is not recognized` | Chưa kích hoạt venv | Phần 1, rồi dùng `python -m pip` |
| `ModuleNotFoundError` bất kỳ | Chưa kích hoạt venv | Phần 1 |
| `key[...]: thiếu` dù `.env` có key | Chưa kích hoạt venv → không nạp được `.env` | Phần 1 |
| `UnicodeDecodeError ... byte 0x81` | File cấu hình có chữ tiếng Việt có dấu | File `.txt`/`.env` chỉ được dùng ASCII (DT-06) |
| `Microsoft Visual C++ 14.0 required` | Đang dùng Python ≠ 3.11 | Tạo lại venv bằng `py -3.11` |
| `429` / `RESOURCE_EXHAUSTED` | Hết hạn mức của **một** model | `--config` xem vai trò nào, `--models` xem còn model nào, đổi dòng `MODEL_*` đó |
| `404 model_not_found` / `does not exist` | Model bị nhà cung cấp khai tử | `python -m app.main --models` rồi sửa `MODEL_*` |
| `thought_signature` | Thư viện Google cũ hơn model Gemini 3 | `python -m pip install -r requirements.txt` |
| `401` / `invalid_api_key` | Key sai chỗ (vd key `AQ.` đi đường OpenAI) | `--config`, dùng tiền tố `google:` cho model Gemini |
| Kết quả in ra `[{'type': 'text', ...}]` | Đọc `message.content` như chuỗi | Dùng `app.core.pretty.message_text()` |

---

## Phần 5 — Ngân sách hạn mức trong ngày

Mỗi model một sổ riêng. Cạn một model thì chỉ cần đổi đúng dòng `MODEL_*` đó.

| Model | Hạn mức/ngày | Vai trò đang dùng |
|---|---|---|
| `groq:openai/gpt-oss-120b` | ~1.000 | supervisor |
| `groq:openai/gpt-oss-20b` | ~1.000 | research |
| `google:gemini-3.5-flash` | ~20 | vision |
| `google:gemini-3.5-flash-lite` | ~20 | describe (đọc ảnh) |
| `google:gemini-3.1-flash-lite` | ~20 | utility |

> Tên model thay đổi theo lịch khai tử của nhà cung cấp. Đừng tin bảng này lâu dài —
> chạy `python -m app.main --models` để lấy danh sách thật của key bạn.

Ước lượng: một câu hỏi chữ tốn 4–6 lượt trên Groq → khoảng **200 câu/ngày**.
Câu hỏi có ảnh bị chặn bởi Gemini: **~10 câu/ngày**.

Không tốn lượt nào: `pytest -m "not network"`, `--config`, `--graph`, mọi thao tác sửa code.

Xem hạn mức thật: [Groq](https://console.groq.com/docs/rate-limits) ·
[Gemini](https://aistudio.google.com/rate-limit)

---

## Tóm tắt cho người vội

```powershell
.\.venv\Scripts\Activate.ps1     # (.venv) phải hiện ra
python -m app.main --config      # 5 model khác nhau · 2 key có · venv có · .env đã nạp
python -m pytest -q -m "not network"
python -m app.main --agent research_agent "câu hỏi"
```

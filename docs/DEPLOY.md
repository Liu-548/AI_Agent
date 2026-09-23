# Đưa web lên mạng cho cả nhóm cùng test

Mục tiêu: một đường link duy nhất, ai mở cũng hỏi được, và **bấm vào một hội
thoại cũ rồi hỏi tiếp thì agent vẫn nhớ đoạn trước**.

---

## 0. Điều quan trọng nhất: database phải nằm NGOÀI Render

Đây là chỗ hầu hết mọi người làm sai và chỉ phát hiện sau vài ngày, khi lịch sử
bỗng dưng trắng trơn. Hai lý do, đều đã kiểm chứng trên tài liệu chính thức:

| Chuyện gì xảy ra | Hậu quả |
|---|---|
| Render **xoá sạch ổ đĩa** mỗi lần restart hoặc deploy lại | File `conversations.db` (SQLite) bốc hơi cùng toàn bộ lịch sử |
| **Postgres miễn phí của chính Render hết hạn sau 30 ngày** kể từ lúc tạo | Đồ án đang chấm thì database tự biến mất |

Nên: web chạy trên Render, còn **database đặt ở Neon** — Postgres miễn phí
vĩnh viễn, 0.5 GB, 100 CU-hours/tháng, không cần thẻ tín dụng. Với đồ án thì
0.5 GB là rất nhiều: mỗi tin nhắn chỉ vài KB.

---

## 1. Tạo database ở Neon (5 phút)

1. Vào <https://neon.com> → đăng ký bằng tài khoản GitHub.
2. Tạo một project mới (đặt tên gì cũng được, ví dụ `visual-agentic-ai`).
3. Vào mục **Connection string**, chọn kiểu **psql / URI**, bấm copy. Chuỗi có dạng:

   ```
   postgresql://tenban:matkhau@ep-abc-xyz-123.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```

4. Giữ chuỗi này lại. **Đây là mật khẩu database — không dán vào Zalo nhóm,
   không commit lên GitHub.**

> Không cần tự tạo bảng. Lần đầu server khởi động, `app/store.py` tự tạo hai
> bảng `conversations` và `messages`.

---

## 2. Chạy thử ở máy trước khi deploy

Bước này tốn 2 phút và tránh được kiểu lỗi "deploy xong mới biết sai".

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

# Để trống DATABASE_URL trong .env -> dùng SQLite, không cần Neon
python -m app.main --config          # dòng "db :" phải hiện ra
python -m pytest -q -m "not network"
uvicorn app.api:app --reload --port 8000
```

Mở <http://127.0.0.1:8000> — đây chính là giao diện thật, không phải bản xem trước.
Hỏi một câu, rồi bấm lại hội thoại đó ở cột trái và hỏi tiếp: nếu agent hiểu
câu hỏi nối tiếp thì phần ngữ cảnh đã chạy đúng.

Muốn thử thẳng với Neon thì điền `DATABASE_URL` vào `.env` rồi chạy lại —
dòng `db :` trong `--config` sẽ đổi từ `sqlite` sang `postgresql @ ep-...`.

---

## 3. Đẩy code lên GitHub

```powershell
git checkout -b feat/web-lich-su
git add .
git commit -m "web: them lich su hoi thoai va giao dien moi"
git push origin feat/web-lich-su
```

Kiểm tra trước khi push: `git status` **không được** có `.env`,
`conversations.db`, `*.pt`, `__pycache__/`.

---

## 4. Tạo Web Service trên Render

Repo đã có sẵn `render.yaml` nên cách nhanh nhất là dùng Blueprint:

1. <https://render.com> → đăng nhập bằng GitHub.
2. **New** → **Blueprint** → chọn repo này → Render tự đọc `render.yaml`.
3. Render sẽ hỏi giá trị cho ba biến bí mật. Điền:

   | Biến | Giá trị |
   |---|---|
   | `GROQ_API_KEY` | key `gsk_...` của bạn |
   | `GEMINI_API_KEY` | key `AQ....` của bạn |
   | `DATABASE_URL` | chuỗi kết nối Neon ở bước 1 |

4. Bấm **Apply** và đợi build (lần đầu khoảng 3–5 phút).

Không muốn dùng Blueprint thì tạo Web Service thủ công với:

- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn app.api:app --host 0.0.0.0 --port $PORT`

> `--host 0.0.0.0` là bắt buộc. Thiếu nó, uvicorn chỉ nghe trong máy và Render
> báo *"no open ports detected"* rồi huỷ deploy.

Xong, Render cho một link dạng `https://visual-agentic-ai.onrender.com`.
Gửi đúng link đó cho cả nhóm — trang web và API nằm chung một địa chỉ nên
không ai phải cấu hình gì thêm.

---

## 5. Kiểm tra sau khi deploy

```
https://<tên-app>.onrender.com/api/health     -> {"status":"ok"}
https://<tên-app>.onrender.com/api/config     -> dòng "db : postgresql @ ep-..."
https://<tên-app>.onrender.com/docs           -> Swagger, test từng endpoint
https://<tên-app>.onrender.com/               -> giao diện chat
```

Nếu `/api/config` vẫn hiện `sqlite` thì `DATABASE_URL` chưa được nạp — kiểm tra
lại tên biến trong Render, rồi **Manual Deploy → Clear build cache & deploy**.

---

## 6. Đếm vật thể + ảnh khoanh vùng trên bản deploy

Muốn bản deploy trả về **ảnh có khung vuông quanh vật thể kèm số lượng**, cần
đúng hai thứ: một bộ chạy model đủ nhẹ, và bật cờ vẽ khung.

### Vì sao không cài thẳng `ultralytics` lên Render

Đo thực tế trên cùng một ảnh, cùng bộ trọng số `yolo11n`:

| Cách chạy | Đỉnh RAM | Vừa gói Free 512MB? |
|---|---|---|
| `ultralytics` + `torch` | **780 MB** | Không — bị kill giữa chừng |
| `onnxruntime` + `yolo11n.onnx` | **123 MB** | Vừa, còn dư cho FastAPI |

Gói Free của Render cấp 512MB cho **cả tiến trình**, tính luôn uvicorn và
FastAPI (~120MB). Đường torch không có cửa, kể cả khi cài bản CPU-only. Nâng gói
cũng không cứu được: Starter vẫn 512MB, phải lên Standard (2GB) mới đủ.

### Cách làm: chạy chính model đó bằng ONNX Runtime

Repo đã có sẵn `yolo11n.onnx` và `app/agents/vision_agent/onnx_detector.py`.
**Cùng một bộ trọng số**, chỉ khác định dạng file — đã đối chiếu với ultralytics
trên cả ba ảnh trong `assets/`: cùng số vật thể, cùng nhãn, khung lệch dưới 1 pixel.

Trên Render, vào **Environment** thêm hai biến:

```
YOLO_WEIGHTS=yolo11n.onnx
DRAW_DETECTIONS=true
```

Xong. Không phải đổi Build Command, không phải cài `ultralytics`, vì
`onnxruntime` đã nằm sẵn trong `requirements.txt`.

`app/agents/vision_agent/tools.py` tự chọn đường chạy theo đuôi file:
`.onnx` thì dùng ONNX Runtime, `.pt` thì dùng ultralytics như cũ. Nên máy dev
của bạn vẫn để `YOLO_WEIGHTS=yolo11n.pt` chạy bình thường, không phải sửa gì.

### Khi nào phải xuất lại file .onnx

Chỉ khi đổi sang bộ trọng số khác (ví dụ `yolo11x.pt` để quay demo cho nét).
Chạy trên máy đã cài ultralytics, rồi commit file mới:

```powershell
yolo export model=yolo11x.pt format=onnx imgsz=640 opset=12
```

`.gitignore` chặn `*.onnx` nhưng đã mở ngoại lệ cho `yolo11n.onnx` (10MB, dưới
giới hạn GitHub). File mới tên khác thì thêm ngoại lệ tương ứng.

### Kiểm tra sau khi bật

```
python -m pytest tests/test_onnx_detector.py -v
```

Bảy test này chạy offline, không cần torch, không tốn hạn mức API. Trên bản
deploy thì gửi một ảnh có vật thể rồi xem có khối "Ảnh đã khoanh vùng" hiện ra
kèm chip đếm số lượng không.

---

## 6b. Cả nhóm cùng phát triển tiếp trên bản đã deploy

Điều đầu tiên cần nói rõ: **không ai sửa code trực tiếp trên server đã deploy.**
Render chỉ là nơi chạy bản đã chốt. Mỗi người vẫn code trên máy mình, và bản
deploy tự cập nhật khi code được merge.

### Cách nối: Render tự deploy lại mỗi khi nhánh có commit mới

Trong Render → **Settings** → **Build & Deploy**:

| Mục | Đặt là | Ý nghĩa |
|---|---|---|
| Repository | repo GitHub của nhóm | |
| Branch | `main` | Chỉ nhánh này mới lên web thật |
| Auto-Deploy | `Yes` | Có commit mới trên `main` là tự build lại |

Từ đó vòng làm việc của nhóm là:

```
nhánh riêng của mỗi người  ->  PR  ->  develop  ->  PR  ->  main  ->  Render tự deploy
```

Đúng Bảng 7 trong `QUY_TAC_THIET_KE.md` mà nhóm đã thống nhất, chỉ thêm một vế
cuối: `main` giờ gắn với bản chạy thật nên càng phải giữ sạch.

### Mỗi người làm việc trên máy mình

```powershell
git checkout develop
git pull --rebase origin develop
git checkout -b feat/viec-cua-toi

uvicorn app.api:app --reload --port 8000    # sửa file là tự nạp lại
```

`--reload` nghĩa là sửa code xong lưu lại là thấy ngay ở `localhost:8000`,
không phải đợi deploy. Deploy chỉ là bước cuối khi đã chắc chắn.

### Database: đừng dùng chung khi đang code

Để `DATABASE_URL` **trống** trong `.env` của mỗi người → mỗi máy tự dùng file
SQLite riêng. Ba người nghịch dữ liệu của nhau trên cùng một database Neon là
cách nhanh nhất để mất buổi tối đi tìm "sao hội thoại tôi vừa tạo biến mất".

Chỉ Render mới trỏ vào Neon. Cần thử thật với Postgres thì Neon có tính năng
**branch** — tạo một nhánh database riêng để nghịch, không đụng dữ liệu thật.

### Muốn xem thử một nhánh trước khi merge

Tạo thêm **một Web Service Free thứ hai** trên Render, trỏ vào nhánh
`develop`, đặt tên khác (ví dụ `visual-agentic-ai-dev`) và cho nó một
`DATABASE_URL` khác. Cả nhóm có một link thử nghiệm riêng, link chính vẫn sạch.

> Nhớ giới hạn 750 giờ chạy mỗi tháng tính chung cho cả tài khoản. Hai dịch vụ
> Free cùng chạy liên tục sẽ vượt, nhưng vì cả hai đều tự ngủ sau 15 phút không
> ai dùng nên thực tế đồ án rất khó chạm trần.

### Khi deploy hỏng

Render giữ lịch sử deploy: vào tab **Deploys**, chọn bản chạy tốt gần nhất →
**Rollback**. Web trở lại bản cũ trong khoảng một phút, rồi sửa code từ từ.

Xem log lỗi ở tab **Logs** — mọi `print` và traceback của server đều hiện ở đó.

### Sửa gì thì phải báo nhóm

Theo Bảng 9, ba vùng dưới đây là tài sản chung, đụng vào phải tag cả hai người
còn lại trong PR:

- `app/core/config.py`, `app/core/llm.py`, `app/core/contracts.py`
- `app/agents/__init__.py`, `tests/fakes.py`, `tests/test_contract.py`
- `requirements.txt`, `.env.example`, `.gitignore`

Riêng `app/api.py`, `app/store.py`, `web/UI_style.html` là phần web — nên để một
người phụ trách, tránh ba người cùng sửa một file 1000 dòng.

---

## 7. Những điều nên nói trước với người vào test

- **Lần đầu vào chậm ~50 giây.** Render cho dịch vụ Free ngủ sau 15 phút không
  ai truy cập; request đầu tiên đánh thức nó dậy. Từ câu thứ hai trở đi là nhanh.
- **Mỗi người có lịch sử riêng.** Trình duyệt tự sinh một mã ngẫu nhiên lưu
  trong máy họ. Đổi máy hoặc xoá dữ liệu trình duyệt là mất lịch sử — đây không
  phải tài khoản đăng nhập.
- **Hạn mức model là thứ hết trước tiên.** Gemini chỉ khoảng 20 lượt/ngày mỗi
  model, nên phần đọc ảnh chỉ đủ cho ~10 câu hỏi có ảnh mỗi ngày cho **toàn bộ**
  người test cộng lại, vì tất cả dùng chung một key. Hết lượt thì giao diện báo
  "đã hết hạn mức" — không phải code hỏng.
- **Đừng gõ thông tin nhạy cảm.** Bản demo không có đăng nhập.

---

## 8. Bảo mật — làm ngay, đừng để sau

File `.env.example` trong repo đang chứa **key thật**, không phải placeholder.
Trước khi đẩy repo lên GitHub công khai:

1. Thay hai dòng đó bằng chỗ trống:

   ```
   GROQ_API_KEY=
   GEMINI_API_KEY=
   ```

2. **Thu hồi và tạo key mới** ở
   <https://console.groq.com/keys> và <https://aistudio.google.com/apikey>.
   Key đã từng nằm trong lịch sử git thì coi như đã lộ, kể cả khi bạn xoá nó ở
   commit sau — bot quét GitHub tìm thấy khoá trong vòng vài phút.
3. Key mới chỉ nằm ở hai nơi: file `.env` trên máy (đã được `.gitignore` bỏ qua)
   và ô Environment trong dashboard Render.

---

## 9. Đăng nhập bằng Google (mỗi người thấy lịch sử của mình)

Không bật phần này thì web vẫn chạy, nhưng lịch sử gắn với **từng trình duyệt**:
đổi máy, đổi trình duyệt, hoặc xoá dữ liệu duyệt web là coi như mất. Bật lên thì
giống Gemini/ChatGPT — đăng nhập ở máy nào cũng thấy đúng lịch sử của mình, và
không ai đọc được hội thoại của người khác.

### 9.1. Lấy Client ID ở Google Cloud Console (làm một lần, miễn phí)

1. Vào <https://console.cloud.google.com/> → tạo project mới (tên tuỳ ý).
2. Menu trái → **APIs & Services** → **OAuth consent screen**:
   - User type: **External** → Create.
   - Điền App name, User support email, Developer contact email → Save.
   - Phần **Audience**: để **Testing** cũng chạy được, nhưng chỉ những email bạn
     thêm vào danh sách *Test users* mới đăng nhập được (tối đa 100). Muốn cả
     lớp/cả nhóm ai cũng vào được thì bấm **Publish app**.
3. Menu trái → **Credentials** → **Create credentials** → **OAuth client ID**:
   - Application type: **Web application**.
   - **Authorized JavaScript origins** — thêm ĐỦ cả hai dòng:
     - `http://localhost:8000`
     - `https://<tên-app>.onrender.com`  ← đúng link Render của bạn, **không có
       dấu `/` ở cuối**
   - Bấm **Create** → copy chuỗi **Client ID** (đuôi
     `.apps.googleusercontent.com`).

> Thiếu đúng origin là lỗi hay gặp nhất: nút đăng nhập hiện ra nhưng bấm vào
> không có gì xảy ra, console báo `origin_mismatch`. Thêm origin xong phải đợi
> khoảng 1–2 phút mới có hiệu lực.

### 9.2. Khai báo ở máy mình (chạy local)

Trong file `.env`:

```
GOOGLE_CLIENT_ID=<chuoi-vua-copy>.apps.googleusercontent.com
SESSION_SECRET=<chuoi-ngau-nhien-tu-sinh>
SESSION_DAYS=30
```

Sinh `SESSION_SECRET` bằng lệnh:

```
python -c "import secrets; print(secrets.token_hex(32))"
```

Kiểm tra đã nhận chưa: `python -m app.main --config` → dòng `login :` phải ghi
`Google (mỗi người thấy lịch sử của mình)`.

> **`SESSION_SECRET` là bí mật thật sự.** Ai biết nó có thể tự ký một tấm phiếu
> mang tên người khác và đọc toàn bộ lịch sử của họ. Không commit, không dán vào
> chat nhóm. Ngược lại `GOOGLE_CLIENT_ID` là công khai — nó nằm sẵn trong HTML
> gửi xuống trình duyệt, lộ cũng không sao.

### 9.3. Khai báo trên Render

Vào service → **Environment** → thêm:

| Biến | Giá trị |
|---|---|
| `GOOGLE_CLIENT_ID` | chuỗi Client ID vừa tạo |
| `SESSION_SECRET` | Render **tự sinh sẵn** (`generateValue: true` trong `render.yaml`), không cần điền |

Lưu lại → Render tự deploy lại → vào link, sẽ thấy màn hình đăng nhập.

### 9.4. Ba trạng thái của web

| Trạng thái | Khi nào | Người dùng làm được gì |
|---|---|---|
| **Ẩn danh** (chưa bật đăng nhập) | `GOOGLE_CLIENT_ID` để trống | Hỏi đáp bình thường, lịch sử lưu theo **từng trình duyệt** — đổi máy là mất |
| **Khách vãng lai** (đã bật đăng nhập, chưa đăng nhập) | Mặc định khi mới vào — web **không chặn ai ở cửa** | Hỏi đáp bình thường nhưng **không lưu gì cả**; có dải nhắc và nút "Đăng nhập để lưu" |
| **Đã đăng nhập** | Đăng nhập bằng Google | Lịch sử lưu theo **tài khoản Google**, mở ở máy nào cũng thấy; không ai xem được của ai |

Màn hình đăng nhập **chỉ hiện khi người dùng tự bấm** nút đăng nhập (ở góc thanh
bên trái, hoặc nút "Đăng nhập để lưu" trong dải nhắc) — vào web lần đầu là thấy
khung chat luôn, hỏi được ngay. Trong màn hình đăng nhập luôn có lối thoát "Để
sau, dùng thử trước" để quay lại.

Lịch sử của khách vãng lai **không** được giữ lại rồi gộp vào tài khoản sau khi
đăng nhập — vì ngay từ đầu nó đã không được ghi xuống database.

### 9.5. Những điều cần biết khi dùng

- **Tắt lúc nào cũng được**: xoá rỗng `GOOGLE_CLIENT_ID` là web quay về chế độ ẩn
  danh, code không phải sửa gì. Nhờ vậy ai trong nhóm chưa kịp tạo Client ID vẫn
  chạy local bình thường.
- **Đổi `SESSION_SECRET` = đăng xuất toàn bộ người dùng** (mọi phiếu cũ thành vô
  hiệu). Đây cũng là cách xử lý nếu lỡ làm lộ khoá.
- **Lịch sử ẩn danh cũ không tự chuyển sang tài khoản Google.** Chúng vẫn nằm
  trong database dưới mã ẩn danh cũ, chỉ là không ai đăng nhập vào xem được nữa.
- Người dùng đăng nhập được lưu tên/email/ảnh đại diện trong bảng `users` để hiển
  thị ở góc thanh bên. Xoá bảng này không làm mất hội thoại của ai.

---

## Tra lỗi nhanh

| Thấy gì | Nguyên nhân | Sửa |
|---|---|---|
| `no open ports detected` | Thiếu `--host 0.0.0.0` | Sửa Start Command |
| `ModuleNotFoundError: psycopg2` | SQLAlchemy đang tìm driver cũ | Đã xử lý sẵn trong `app/store.py`; nếu vẫn lỗi, ghi rõ `postgresql+psycopg://` ở đầu `DATABASE_URL` |
| `/api/config` hiện `sqlite` dù đã set biến | Biến chưa nạp vào tiến trình | Clear build cache & deploy lại |
| Lịch sử mất sau vài ngày | Đang dùng SQLite hoặc Postgres của Render | Chuyển sang Neon (mục 1) |
| `server closed the connection unexpectedly` | Kết nối nhàn rỗi bị Neon ngắt | Đã xử lý bằng `pool_pre_ping`; nếu còn, deploy lại |
| Deploy bị kill, log ghi `Out of memory` | Đang chạy YOLO bằng torch | Đặt `YOLO_WEIGHTS=yolo11n.onnx` (mục 6) |
| Bấm nút đăng nhập Google không có phản ứng | Origin chưa khai báo đúng | Thêm ĐÚNG link (không có `/` cuối) vào Authorized JavaScript origins, đợi 1–2 phút |
| `Can dang nhap lai` (401) liên tục | `SESSION_SECRET` đổi giữa chừng, hoặc mỗi lần deploy lại sinh khoá mới | Đặt `SESSION_SECRET` cố định trong Environment của Render |
| Nút đăng nhập không hiện, báo không tải được | Máy không vào được `accounts.google.com` | Kiểm tra mạng/tường lửa; hoặc bỏ trống `GOOGLE_CLIENT_ID` để chạy ẩn danh |
| Đăng nhập xong không thấy hội thoại cũ | Hội thoại cũ thuộc mã ẩn danh trước đây | Đúng như thiết kế — lịch sử ẩn danh không tự chuyển sang tài khoản Google |
| Không thấy khối "Ảnh đã khoanh vùng" | Thiếu `DRAW_DETECTIONS=true`, hoặc chưa restart sau khi sửa | Thêm biến rồi deploy lại |
| `Chưa cài onnxruntime` | Cài thiếu gói | `pip install -r requirements.txt` |
| Giao diện báo "đã hết hạn mức" | Hết lượt của một model | `python -m app.main --models` rồi đổi dòng `MODEL_*` |
| Trang trắng, F12 báo lỗi CORS | Đang mở file HTML từ ổ đĩa | Mở qua địa chỉ server, hoặc điền "Địa chỉ API" trong phần Cài đặt |

# Hướng dẫn lấy "tên miền" cho game/app — đúng như cách đã dùng ở dự án Bang!

## Sự thật cần biết trước (quan trọng)

Dự án Bang! (`C:\Game\BoardGame`) **chưa bao giờ mua một tên miền thật** kiểu
`bang-game.com`. Cách "lấy tên miền" đã dùng thực chất là: **deploy lên
Cloudflare Workers, và Cloudflare tự cấp MIỄN PHÍ một tên miền phụ (subdomain)**
dạng:

```
<tên-worker>.<tên-tài-khoản-cloudflare>.workers.dev
```

Ví dụ dự án Bang! có 2 địa chỉ, cả 2 đều là subdomain miễn phí kiểu này (xem
`wrangler.jsonc` trong repo Bang!):

- Bản chính: `bang-boardgame.nguyenngoctuan548.workers.dev`
- Bản beta: `bang-boardgame-beta.nguyenngoctuan548.workers.dev`

Không có bước "mua domain" nào cả — không tốn tiền, không cần thẻ. Nếu bạn
muốn một tên miền thật dạng `.com`/`.vn` (không có chữ `workers.dev`), đó là
một việc KHÁC (mua qua Cloudflare Registrar hoặc nhà đăng ký khác, tốn phí
hàng năm) — dự án Bang! chưa từng làm bước đó, nên phần dưới đây chỉ hướng dẫn
đúng cách miễn phí đã dùng thật.

## Vì sao cách này không áp dụng thẳng cho `visual-agentic-ai`

Dự án Bang! là code TypeScript chạy trên **Cloudflare Workers** (`wrangler
deploy`), nên Cloudflare cấp subdomain `workers.dev` tự động ngay khi deploy.

`visual-agentic-ai` là app **Python** (LangGraph, có vẻ chạy dạng script/CLI
hoặc server nội bộ theo `README.md`/`chay.ps1`) — Cloudflare Workers KHÔNG
chạy Python trực tiếp. Vì vậy có 2 hướng, tuỳ bạn muốn gì:

- **Chỉ cần 1 địa chỉ web công khai, miễn phí, không cần domain thật** → xem
  Cách A hoặc Cách B bên dưới (không cần sửa gì nhiều).
- **Bắt buộc phải dùng đúng cơ chế Cloudflare Workers như Bang!** → phải viết
  lại phần giao diện/API bằng JavaScript/TypeScript chạy trên Workers (hoặc
  dùng Workers chỉ làm lớp trung chuyển gọi sang backend Python chạy nơi
  khác) — việc này tốn công hơn nhiều, cân nhắc kỹ trước khi chọn.

---

## Cách A — Giống hệt Bang!: deploy lên Cloudflare Workers (chỉ khi có phần code chạy được trên Workers, ví dụ giao diện web/frontend)

Dùng khi bạn có (hoặc sẽ viết) một phần chạy được trên Cloudflare Workers —
ví dụ một trang web tĩnh + API nhỏ, không cần Python.

### Bước 1 — Tạo tài khoản Cloudflare (miễn phí)

1. Vào https://dash.cloudflare.com/sign-up
2. Đăng ký bằng email, xác nhận email.
3. Không cần nhập thẻ tín dụng cho gói miễn phí.

### Bước 2 — Cài công cụ dòng lệnh Wrangler

```powershell
npm install -g wrangler
wrangler login   # mở trình duyệt, bấm "Allow" để Wrangler nối vào tài khoản
```

### Bước 3 — Khởi tạo project (nếu chưa có `wrangler.jsonc`/`wrangler.toml`)

```powershell
wrangler init
```

Trả lời các câu hỏi cơ bản (tên project, có dùng TypeScript không...).

### Bước 4 — Deploy

```powershell
wrangler deploy
```

Lần đầu deploy, Wrangler sẽ hỏi bạn chọn **subdomain workers.dev** cho tài
khoản (chỉ hỏi 1 lần duy nhất cho cả tài khoản, dùng chung cho mọi Worker sau
này) — ví dụ chọn `nguyenngoctuan548` thì mọi Worker sau đó đều có dạng
`<tên-worker>.nguyenngoctuan548.workers.dev`, giống hệt cách dự án Bang! đang
dùng.

Sau khi deploy xong, lệnh sẽ in ra thẳng URL, ví dụ:

```
https://visual-agentic-ai.nguyenngoctuan548.workers.dev
```

Đó chính là "tên miền" miễn phí — dùng ngay được, chia sẻ được cho người
khác truy cập.

### Bước 5 (tuỳ chọn) — Có bản "beta" song song như Bang!

Copy đúng cách Bang! đang làm trong `wrangler.jsonc`: thêm 1 khối `env.beta`
với `name` khác (ví dụ `visual-agentic-ai-beta`), rồi deploy bằng:

```powershell
wrangler deploy --env beta
```

Sẽ ra 1 URL `workers.dev` riêng, dữ liệu tách biệt hoàn toàn với bản chính.

---

## Cách B — Nếu app Python cần chạy nguyên trạng (không viết lại bằng Workers)

Vì Cloudflare Workers không chạy Python, muốn có 1 địa chỉ web công khai
miễn phí cho app Python thì dùng 1 trong các cách sau (không phải cách đã
dùng cho Bang!, nhưng cùng tinh thần "miễn phí, không cần mua domain"):

1. **Cloudflare Tunnel** (`cloudflared`) — chạy app Python trên máy/server của
   bạn như bình thường, rồi dùng `cloudflared tunnel` để lộ ra internet qua
   1 địa chỉ dạng `<tên>.trycloudflare.com` (tạm) hoặc gắn vào domain riêng
   nếu có. Phù hợp nếu chỉ cần demo/test.
2. **Deploy lên nền tảng có hỗ trợ Python sẵn** (Render, Railway, Fly.io,
   Hugging Face Spaces...) — các nền tảng này đều cấp 1 subdomain miễn phí
   kiểu `<tên-app>.onrender.com`, `<tên-app>.hf.space`... tương tự tinh thần
   `workers.dev` nhưng của nền tảng khác.

Cách B **không liên quan trực tiếp** tới cách đã làm ở Bang! — chỉ liệt kê
để bạn có lựa chọn nếu Cách A không phù hợp với Python.

> Lưu ý: mục 1 (Cloudflare Tunnel) trong Cách B **cần máy/server của bạn bật
> sẵn** thì tunnel mới sống — tắt máy là link chết. Nếu muốn app **luôn bật
> 24/7 mà không phải giữ máy mình mở**, xem **Cách C** bên dưới.

---

## Cách C — Oracle Cloud Free Tier: máy chủ ảo LUÔN BẬT, miễn phí, không cần giữ máy mình mở

Đây là cách gần nhất với đúng tinh thần "luôn bật, miễn phí, không thời hạn"
của Cloudflare Workers ở Bang! — nhưng vì Workers không chạy được Python
nặng (project này có `torch`/`ultralytics` qua `yolo11n.pt`), thay vào đó ta
thuê 1 **máy chủ ảo (VM) thật, chạy liên tục trên server của Oracle**, miễn
phí vĩnh viễn (gói "Always Free"), rồi cài app Python lên đó chạy dưới dạng
service — không phụ thuộc máy tính cá nhân của bạn có bật hay không.

**Kiến trúc đề xuất** (làm đủ cả 2 phần thì có link đẹp + HTTPS free):

```
Người dùng → https://<ten>.trycloudflare.com (hoặc domain riêng nếu có)
              → Cloudflare Tunnel (chạy NGAY TRÊN VM Oracle, không phải máy bạn)
                → app Python (LangGraph) chạy nền bằng systemd trên VM
```

Nếu chỉ cần dùng ngay không cần link đẹp, có thể bỏ qua phần Cloudflare
Tunnel ở Bước 9 và dùng thẳng địa chỉ IP public của VM.

### Bước 1 — Đăng ký tài khoản Oracle Cloud

1. Vào https://signup.oraclecloud.com/
2. Điền thông tin, xác nhận email.
3. **Cần nhập thẻ tín dụng/ghi nợ để xác minh danh tính** — đây là khác biệt
   so với Cloudflare (không cần thẻ). Oracle KHÔNG tự trừ tiền nếu bạn chỉ
   dùng đúng tài nguyên nằm trong gói "Always Free" (xem Bước 2, phải chọn
   đúng loại máy có nhãn "Always Free eligible").
4. Chọn Home Region lúc đăng ký (ví dụ Singapore/Tokyo cho gần Việt Nam) —
   **không đổi được sau này**, nên chọn cẩn thận.

### Bước 2 — Tạo VM (Compute Instance) thuộc gói Always Free

1. Vào Console Oracle Cloud → menu ☰ → **Compute → Instances → Create
   Instance**.
2. **Image and shape**:
   - Image: chọn **Ubuntu 22.04** (hoặc bản mới hơn nếu có, dễ dùng hơn
     Oracle Linux cho người mới).
   - Shape: bấm "Change shape", chọn **VM.Standard.A1.Flex** (kiến trúc ARM
     Ampere) — đây là loại **mạnh nhất trong gói Always Free**: tối đa
     **4 OCPU + 24 GB RAM miễn phí vĩnh viễn**, đủ sức chạy `torch`/YOLO.
     Chỉnh thanh trượt lên tối đa (4 OCPU / 24 GB) nếu form cho phép.
   - Nếu shape báo **"Out of host capacity"** — khu vực bạn chọn tạm hết
     tài nguyên free, thử lại sau vài phút/vài giờ, hoặc đổi Availability
     Domain trong cùng region. Đây là vấn đề rất phổ biến của Oracle Always
     Free, không phải lỗi thao tác.
3. **Networking**: để mặc định (tạo VCN mới) là được.
4. **Add SSH keys**: chọn "Generate a key pair for me" rồi **tải cả 2 file
   `.key`/`.pub` về máy, cất cẩn thận** (dùng để SSH vào VM sau này — mất là
   phải tạo lại VM). Hoặc nếu đã có sẵn SSH key (ví dụ từ GitHub), dán public
   key vào ô "Paste public key".
5. Bấm **Create**. Đợi vài phút tới khi trạng thái VM chuyển thành
   **RUNNING**, ghi lại **Public IP Address** hiện trên trang chi tiết
   instance.

### Bước 3 — Mở cổng mạng (Security List)

Oracle chặn hầu hết cổng theo mặc định, phải mở tay:

1. Vào **Networking → Virtual Cloud Networks** → chọn VCN vừa tạo → chọn
   **Security Lists** → chọn Default Security List.
2. Bấm **Add Ingress Rules**, thêm các dòng (mỗi dòng 1 rule):
   - Source CIDR `0.0.0.0/0`, IP Protocol TCP, Destination Port `22` (SSH —
     thường có sẵn rồi).
   - Source CIDR `0.0.0.0/0`, IP Protocol TCP, Destination Port `80` (HTTP).
   - Source CIDR `0.0.0.0/0`, IP Protocol TCP, Destination Port `443`
     (HTTPS).
   - Source CIDR `0.0.0.0/0`, IP Protocol TCP, Destination Port `8501`
     (cổng mặc định của `streamlit run` — dùng để test trực tiếp bằng IP
     trước khi gắn Cloudflare Tunnel ở Bước 10).

### Bước 4 — SSH vào VM (từ PowerShell trên Windows, dùng OpenSSH có sẵn)

```powershell
# Đường dẫn tới file .key vừa tải ở Bước 2
ssh -i "C:\đường-dẫn\ssh-key.key" ubuntu@<PUBLIC_IP_CỦA_VM>
```

Nếu báo `Permissions for '...key' are too open`, chạy trước:

```powershell
icacls "C:\đường-dẫn\ssh-key.key" /inheritance:r
icacls "C:\đường-dẫn\ssh-key.key" /grant:r "$($env:USERNAME):(R)"
```

### Bước 5 — Mở tường lửa NGAY TRONG hệ điều hành của VM

Oracle có **2 lớp tường lửa**: Security List (đã mở ở Bước 3) **và**
`iptables`/`netfilter` chạy sẵn bên trong chính VM Ubuntu — thiếu bước này
là lỗi rất hay gặp khi làm theo hướng dẫn Oracle Cloud (mở Security List rồi
mà vẫn không truy cập được từ ngoài):

```bash
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 8501 -j ACCEPT   # port mac dinh cua streamlit run
sudo netfilter-persistent save   # lưu lại để không mất khi reboot VM
```

### Bước 6 — Cài Python 3.11 + git trên VM

```bash
sudo apt update
sudo apt install -y software-properties-common git
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev build-essential
python3.11 --version
```

### Bước 7 — Đưa code `visual-agentic-ai` lên VM

Cách gọn nhất: đẩy code lên 1 repo Git (GitHub) từ máy Windows rồi clone về
VM (khớp đúng cách Bang! quản lý code — commit/push, không copy tay):

```bash
git clone <URL-repo-của-bạn>.git
cd visual-agentic-ai
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

`requirements.txt` đã có sẵn `streamlit==1.63.0` (thêm khi tạo
`streamlit_app.py` — xem Bước 9), nên không cần cài tay thêm gì.

> Vision Agent (`ultralytics`/`torch`, ~2GB) là **tuỳ chọn**, không nằm trong
> `requirements.txt` chính (xem ghi chú cuối file đó) — chỉ cài nếu bạn muốn
> Vision Agent chạy được trên bản public:
> `python -m pip install ultralytics==8.3.108`

### Bước 8 — Tạo `.env` trên VM

```bash
cp .env.example .env
nano .env   # điền GROQ_API_KEY, GEMINI_API_KEY... rồi Ctrl+O lưu, Ctrl+X thoát
```

**Không commit file `.env` thật lên Git** (đã có `.gitignore` chặn theo cấu
trúc project hiện tại) — chỉ gõ tay trên VM.

### Bước 9 — Chạy app 24/7 bằng systemd (tự sống khi đóng SSH, tự bật lại khi VM reboot)

`visual-agentic-ai` gốc chỉ là **CLI** (`python -m app.main "câu hỏi"` — nhận
1 câu hỏi rồi thoát), không phải web server, nên không có gì để "luôn bật"
hay tunnel ra ngoài. Để có link web public thật, project này có thêm
**`streamlit_app.py`** ở thư mục gốc — lớp giao diện web mỏng gọi lại đúng
logic agent trong `app/main.py` (không đổi logic agent gì cả). Đây chính là
lệnh sẽ chạy 24/7.

Nếu chỉ chạy lệnh `streamlit run streamlit_app.py` trong phiên SSH bình
thường, app sẽ **chết ngay khi bạn đóng cửa sổ SSH**. Tạo 1 service:

```bash
sudo nano /etc/systemd/system/visual-agentic-ai.service
```

Dán nội dung:

```ini
[Unit]
Description=Visual Agentic AI
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/visual-agentic-ai
ExecStart=/home/ubuntu/visual-agentic-ai/.venv/bin/streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
Restart=always
RestartSec=5
EnvironmentFile=/home/ubuntu/visual-agentic-ai/.env

[Install]
WantedBy=multi-user.target
```

Cổng `8501` là cổng mặc định của Streamlit — khớp với port đã mở ở Bước 3 và
Bước 5 (nhớ đổi `8000` ở 2 bước đó thành `8501` nếu bạn làm theo đúng thứ tự
file này).

Kích hoạt:

```bash
sudo systemctl daemon-reload
sudo systemctl enable visual-agentic-ai   # tự bật lại mỗi khi VM khởi động
sudo systemctl start visual-agentic-ai
sudo systemctl status visual-agentic-ai   # kiểm tra đang "active (running)"
journalctl -u visual-agentic-ai -f        # xem log trực tiếp, Ctrl+C để thoát
```

Từ giờ, **đóng SSH/tắt máy Windows của bạn hoàn toàn không ảnh hưởng** — app
vẫn chạy trên VM Oracle. VM cũng tự khởi động lại app nếu chính nó bị Oracle
reboot bảo trì.

### Bước 10 (khuyến nghị) — Gắn Cloudflare Tunnel NGAY TRÊN VM để có link đẹp + HTTPS free

Khác lúc trước (chạy Tunnel trên máy Windows cá nhân — link chết khi tắt
máy), lần này cài `cloudflared` **trên chính VM Oracle** (đang luôn bật) —
tunnel sẽ luôn sống theo VM, không phụ thuộc máy bạn nữa:

```bash
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared.deb
cloudflared tunnel login   # mở link trong output bằng trình duyệt trên máy bạn để xác nhận
```

Tạo tunnel cố định (không đổi link mỗi lần chạy) rồi chạy nền bằng systemd:

```bash
cloudflared tunnel create visual-agentic-ai
cloudflared tunnel route dns visual-agentic-ai <tên-bạn-muốn>.<domain-nếu-có>
# Nếu CHƯA có domain riêng, dùng lệnh nhanh không cần đăng nhập (link tạm
# dạng trycloudflare.com, đổi mỗi lần chạy lại — chỉ hợp demo ngắn hạn):
#   cloudflared tunnel --url http://localhost:8501
sudo cloudflared service install
sudo systemctl start cloudflared
```

### Chi phí & thời hạn (Oracle Always Free) — tóm tắt

- **Miễn phí vĩnh viễn**, không phải bản dùng thử theo tháng/năm.
- Tài nguyên free tối đa: **4 OCPU + 24 GB RAM** (ARM Ampere A1, chia được
  thành nhiều VM nhỏ hơn nếu muốn), cộng 2 VM AMD Micro nhỏ riêng, 200 GB ổ
  đĩa, 10 TB băng thông ra ngoài/tháng.
- **Cần thẻ lúc đăng ký** để xác minh — Oracle không tự trừ tiền nếu bạn chỉ
  dùng đúng shape có nhãn "Always Free eligible" (đã chọn đúng ở Bước 2).
- Rủi ro cần biết: Oracle từng có trường hợp **tự thu hồi VM nếu tài khoản
  không hoạt động quá lâu** (không đăng nhập Console/VM im lìm nhiều tuần) —
  thỉnh thoảng đăng nhập lại Console hoặc SSH vào kiểm tra để tránh bị dọn.

---

## Tóm tắt nhanh (nếu chỉ muốn làm đúng như Bang!)

```powershell
npm install -g wrangler
wrangler login
wrangler init          # nếu project chưa có config Workers
wrangler deploy        # ra thẳng URL dạng <ten>.<tai-khoan>.workers.dev
```

Không mua domain nào cả — đây là subdomain miễn phí do Cloudflare cấp khi
deploy Worker, y hệt cách `bang-boardgame.nguyenngoctuan548.workers.dev` đã
có.

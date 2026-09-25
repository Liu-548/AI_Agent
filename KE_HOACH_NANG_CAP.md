# KE HOACH NANG CAP (8 muc)

Chi la ke hoach, chua sua code. Moi muc ghi: lam gi, sua o dau, cach kiem tra.
Quy uoc: lam tung muc, commit nho, chay `.\chay.ps1 -Test` (khong ton luot API) truoc khi sang muc tiep.

## Thu tu de xuat

| Pha | Muc | Vi sao dat o day | Cong |
|-----|-----|------------------|------|
| 1 | 7 - Che do "chi cau tra loi" **(XONG)** | Gan nhu chi sua UI, du lieu da tach san (`answer` / `agent_answers`) | nho |
| - | 1 - Go tieng Viet khong dau **(BO QUA, da co san)** | Mot cong tac + mot ham, khong dong cham DB | nho |
| 1 | 3 - Trinh bay van ban **(XONG)** | UI hien chua co bo render markdown, thay doi thay ngay | vua |
| 2 | 5 - Mobile **(XONG, tru buoc thu may that)** | Lam sau muc 3 vi bang/code block anh huong bo cuc mobile | vua |
| 2 | 2 - Tom tat / de tiep can | Can 1 endpoint moi + nut tren UI | vua |
| 3 | 4 - Context theo tai khoan (diem cong) | Can bang moi + prompt, co van de rieng tu | lon |
| 3 | 6 - Nhom project | Can doi schema DB (Neon dang chay that) | lon |
| 3 | 8 - Agent khac | Lam cuoi, moi agent la 1 goi rieng | tuy |

---

## 1. Go tieng Viet khong dau - BO QUA

Y cua ban la NGUOI DUNG go khong dau. Supervisor da xu ly (xem `app/agents/supervisor/prompts.py`: doc nhu co dau, tra loi co dau). Khong can lam gi them.

## 2. Tom tat van ban va noi dung de tiep can hon

- Endpoint moi `POST /api/summarize` nhan `text` + `mode` (`tldr` | `de_hieu` | `y_chinh`):
  - `tldr`: 3 gach dau dong.
  - `de_hieu`: viet lai bang cau ngan, tu don gian, giai thich thuat ngu.
  - `y_chinh`: chi giu ket luan + con so quan trong.
- Dung vai tro model **nhe** (Groq) trong `app/core/llm.py` de tiet kiem quota Gemini. Khong luu DB, khong qua supervisor (1 luot LLM).
- UI: duoi moi cau tra loi them nut "Tom tat" / "Giai thich de hieu" (canh nut Copy co san).
- De tiep can (khong can LLM, lam bang trinh duyet):
  - Doc to: `speechSynthesis` cua trinh duyet (lang `vi-VN`), khong them thu vien.
  - Chinh co chu (A-/A+) va khoang cach dong, luu `localStorage`.
  - Kiem tra tuong phan mau + thu tu Tab + nhan `aria-label` cho nut chi co icon.
- Kiem tra: test endpoint bang `tests/fakes.py` (LLM gia), khong goi API that.

## 3. Nang cao kha nang trinh bay van ban - XONG

Da lam trong `renderMd` (khong them thu vien): tieu de h3/h4, bang (boc `.tbl` cuon ngang), code block co nut Sao chep, [n] bam duoc nhay toi dong NGUON (chi khi co dong NGUON tuong ung), nut tai hoi thoai .md o thanh tren (`#btn-tai`, doc lai tu server nen chi dung khi da dang nhap/luu). Chua lam: blockquote, duong ke ngang.

`UI_style.html` da co ham `renderMd` tu viet (dong ~907). Viec can lam la kiem tra no ho tro gi con thieu (bang, code block, tieu de) va bo sung dan; chua can them thu vien. Neu them `marked` + `DOMPurify` thi **bat buoc lam sach HTML** vi noi dung tu LLM/web.
- Ma trich dan `[1]`, `[2]` thanh the bam duoc, bam thi cuon toi dung dong trong danh sach NGUON.
- Code block co nut Copy; bang cuon ngang duoc (quan trong cho mobile).
- Nut "Tai ve .md" cho ca hoi thoai (tao Blob o trinh duyet, khong can server).
- Giu nguyen hop dong voi backend: van tra `answer` la markdown, khong doi API.
- Kiem tra: mo 1 cau tra loi co bang + code + trich dan tren desktop va dien thoai.

## 4. Context chung theo tai khoan (diem cong)

Muc tieu: agent biet ten, so thich, ngu canh cua nguoi dung ma khong can nhac lai.
- Bang moi `user_profiles` trong `app/store.py`: `user_id` (khoa), `display_name`, `ngon_ngu`, `linh_vuc` (vd "sinh vien CNTT"), `ghi_chu` (van ban tu do), `updated_at`. Bang moi thi `create_all` tao duoc, khong dung vao bang cu.
- Trang "Ho so cua toi" trong UI: form sua + nut "Xoa het". Chi nguoi dang nhap Google moi co (khach vang lai khong luu).
- Tiem vao prompt: `_lich_su_cho_graph` (`app/api.py`) chen 1 tin nhan he thong ngan dau danh sach:
  `Thong tin nguoi dung: ten=..., linh vuc=..., ghi chu=...`. **Cat toi da ~500 ky tu** de khong ton token va chan nguoi dung nhoi prompt.
- Pha 2 (tuy chon): agent **de xuat** ghi nho ("Ban muon minh nho la ban ten X?") - chi luu khi nguoi dung dong y.
- Rieng tu: hien ro cai gi dang duoc luu, cho xem/sua/xoa; khong luu thong tin nhay cam (so the, mat khau); noi ro trong UI.
- Kiem tra: test that tin nhan he thong duoc chen dung va bi cat dung do dai.

## 5. Cai thien giao dien mobile - XONG

Da lam: `viewport-fit=cover` + safe-area cho topbar/composer, nut >=44px khi `pointer:coarse`, input anh dung MIME (`image/*`-kieu) de dien thoai hien ca camera, bang khong lam tran trang. Da xem o khung 390px (khong tran ngang). Chua thu tren dien thoai that / iPhone co tai tho.

Git log cho thay da xu ly ban phim che khung nhap. Con lai:
- Kiem tra tren may that / DevTools o 360px, 390px, 412px (hien co `@media` o 860px va 400px).
- Sidebar thanh ngan keo (drawer) co nut mo ro rang, bam ra ngoai de dong.
- Vung bam >= 44px; `env(safe-area-inset-*)` cho tai tho/thanh duoi iPhone.
- Nut chup anh: `<input type="file" accept="image/*" capture="environment">` cho vision agent.
- Bang/code block khong lam vo bo cuc (lien quan muc 3).
- Chi tiet "AI nao lam viec gi" gap lai tren mobile (lien quan muc 7).
- Kiem tra: chup man hinh truoc/sau o 3 kich thuoc, khong duoc co thanh cuon ngang toan trang.

## 6. Tinh nang nhom project

- Bang `projects` (`id`, `user_id`, `name`, `instructions`, `created_at`) va cot `conversations.project_id` (cho phep NULL).
- **Canh bao migration:** `metadata.create_all` chi tao bang moi, **khong them cot vao bang cu**. Neon dang co du lieu that nen: them buoc `ALTER TABLE conversations ADD COLUMN project_id ...` chay 1 lan luc khoi dong (kiem tra cot da co chua truoc khi them), hoac dung bang noi rieng `project_conversations` de khoi dung bang cu. De xuat: bang noi (an toan hon, khong can ALTER).
- API: `GET/POST /api/projects`, `PATCH/DELETE /api/projects/{id}`, gan hoi thoai vao project qua `PATCH /api/conversations/{id}` (endpoint da co).
- Xoa project **khong xoa hoi thoai** (chi go nhom) - hoi lai truoc khi xoa.
- UI: sidebar chia theo project (thu gon/mo), keo hoac menu "Chuyen vao project".
- "Huong dan cua project" (`instructions`) duoc tiem vao prompt giong muc 4 -> moi project co phong cach/ngu canh rieng (vd "Project luan van: luon tra loi kem trich dan").
- Kiem tra: test store voi SQLite (khong can Neon): tao project, gan, xoa project, hoi thoai con nguyen.

## 7. Giu phan chia agent nhung them che do "chi cau tra loi" - XONG

Da lam: nut 3 gach o thanh tren (`#btn-gon`) bat/tat class `gon` tren `<body>`; CSS an `.route` va `.agent-note`; nho lua chon qua `localStorage` (`vaai_gon`). Con lai (mac dinh bat tren mobile, tuy chon `concise=1` o backend) chua lam.

Backend da tach san: `answer`, `agents_used`, `agent_answers`, `warnings`. Chi can UI:
- Cong tac "Gon" o thanh tren: bat thi chi hien `answer`, an khoi "AI nao lam viec gi" (van co nut "Xem chi tiet" bung ra).
- Mac dinh luu `localStorage`; tren mobile nen bat san.
- Tuy chon backend (sau): `concise=1` them 1 dong vao prompt "tra loi ngan, khong lap lai qua trinh".
- Kiem tra: bat/tat cong tac, chi tiet van xem lai duoc, khong mat du lieu.

## 8. Mot so tinh nang AI Agent khac

Them agent moi chi can dang ky trong registry (`app/agents/__init__.py`, quy tac IF-09), khong sua `chay.ps1`. Xep theo gia tri/cong:
1. **Doc URL / PDF**: dan link bai bao -> tom tat, rut y chinh (nen dung lai tool fetch san co).
2. **Goi y cau hoi tiep theo**: sau moi cau tra loi hien 2-3 nut cau hoi goi y (1 luot LLM nhe).
3. **So sanh 2-3 bai bao**: bang so sanh phuong phap/ket qua/han che.
4. **Xuat literature review**: gom cac nguon da trich dan trong hoi thoai thanh 1 bai co danh muc tai lieu.
5. **Vision mo rong**: doc chu trong anh (OCR), mo ta anh (ngoai dem vat the).
6. **Streaming cau tra loi** (SSE): chu hien dan, cam giac nhanh hon nhieu - lam khi da on dinh cac muc tren.
- Moi agent moi: test bang LLM gia trong `tests/`, chi 1 test co `-m network` cho lan chay that.

---

## Nguyen tac khi lam

- Giu quota free tier: dev/test dung `tests/fakes.py`, chi goi API that 1-2 lan de xac nhan.
- Sua `requirements.txt` / `.gitignore` / `render.yaml` / `.env.example`: **hoi truoc**. Ke hoach nay hau nhu khong can them thu vien Python (muc 3 dung CDN phia trinh duyet).
- Doi schema DB (muc 4, 6): thu tren SQLite truoc, roi moi cho Neon.
- Sau moi muc: `.\chay.ps1 -Test`, mo UI bang `mo_server.bat` xem bang mat, roi commit rieng.

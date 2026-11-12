# Bộ đánh giá Vision

Đo chất lượng phần nhìn ảnh bằng **ONNX Runtime chạy local**: không gọi Gemini/Groq nên không tốn lượt, chạy được lúc hết hạn mức, và chạy lại bao nhiêu lần cũng ra cùng một số.

```bash
pip install -r requirements.txt            # đã có onnxruntime, pillow, requests
python eval/vision/tai_anh.py              # một lần: tải 33 ảnh về eval/vision/anh/ (kiểm sha256)
python eval/vision/run_eval.py             # ~20 giây, ghi eval/vision/KET_QUA.md
```

Tùy chọn: `--gemini` đo thêm phần 5 (vật ngoài 80 loại COCO, mỗi cặp tốn **một lượt Gemini**, cần key trong `.env`), `--conf 0.35` (ngưỡng chính), `--weights đường/dẫn/model.onnx`, `--json ra.json`, `--ghi -` (chỉ in ra màn hình, không ghi file).

## Đo cái gì

| Phần | Câu hỏi trả lời | Dữ liệu |
|---|---|---|
| 1. Đếm | YOLO đếm đúng bao nhiêu %? Ngưỡng `YOLO_CONF` nào tốt nhất? | `dataset.json` |
| 2. Lọc loại vật | Hỏi "có mấy con mèo" thì còn trả kèm bao nhiêu loại thừa? | `dataset.json` |
| 3. EXIF | Ảnh dọc chụp từ điện thoại có bị đếm sai không, sửa xong thì sao? | `dataset.json` xoay giả lập |
| 4. Chủ đề | Câu hỏi nào được đưa đúng chủ đề (động vật/du lịch/món ăn/tài liệu/biểu đồ/chung)? | `cau_hoi.json` |
| 5. Ngoài COCO (`--gemini`) | Gemini đếm đúng vật YOLO không biết ("con bướm", "người hói đầu") không? | `dem_ngoai` trong `dataset.json`, ảnh riêng |

## Đáp án từ đâu, đáng tin đến đâu

- Ảnh lấy từ các repo mẫu công khai của dự án phát hiện vật thể (darknet, OpenCV, Mask R-CNN, YOLOv5/v7...). Không commit ảnh vào repo; `tai_anh.py` tải lại và kiểm sha256 để đáp án không bao giờ lệch ảnh.
- **Đáp án đếm do Claude xem ảnh và gắn bằng mắt, cần một thành viên xem lại.** Ở lần gắn đầu có một nhãn sai (ảnh bánh donut, 9 cái chứ không phải 8) và chỉ bắt được vì YOLO lệch đáp án rồi mình kiểm lại bằng mắt: hãy làm tương tự với các ca "sai" trong `KET_QUA.md` trước khi đưa số ra bảo vệ.
- Chỉ gắn loại thấy RÕ và đếm chắc chắn. Không gắn đám đông, vật bị che nhiều, vật quá nhỏ. Vì vậy số liệu nói về "đếm vật rõ ràng", ảnh đông đúc sẽ kém hơn.
- Ảnh trong bộ này là kiểu ảnh YOLO được dùng để demo nên có xu hướng **lạc quan hơn** ảnh người dùng thật. Hãy thêm ảnh của nhóm (bên dưới).
- Phần 4 đo bước định tuyến theo TỪ KHOÁ trong câu hỏi. Phân loại chủ đề theo nội dung ảnh dùng Gemini nên không nằm trong bộ này.

## Thêm ảnh của nhóm (khuyến nghị)

1. Bỏ ảnh vào `eval/vision/anh_rieng/`, ghi đáp án vào `anh_rieng/nhan_rieng.json` (có hướng dẫn trong file). Khoá là tên lớp COCO tiếng Anh (`"dog"`) thì chấm YOLO; khoá là cụm tiếng Việt khác (`"quả xoài"`, `"người đội mũ bảo hiểm"`) thì vào phần 5 (Gemini).
2. Có vài ảnh **dọc chụp thẳng từ điện thoại** (không gửi qua Zalo/Messenger vì chúng hay xóa cờ xoay EXIF).
3. Chạy lại `run_eval.py`: ảnh riêng được gộp vào phần 1 và, nếu mang cờ xoay, hiện thêm một bảng "cũ so với mới" ở phần 3.

## Thêm câu hỏi / ảnh vào bộ chuẩn

- Câu hỏi: thêm vào `cau_hoi.json` (đáp án mong đợi viết TRƯỚC khi chạy).
- Ảnh: thêm một mục vào `dataset.json` với `url`, `sha256`, `dem` (xem các mục có sẵn).

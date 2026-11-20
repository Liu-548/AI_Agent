# Kết quả đánh giá Vision (2026-11-05)

Chạy bằng `python eval/vision/run_eval.py`. ONNX Runtime local, **không gọi Gemini/Groq**.

- Model: `yolo11n.onnx` · conf=0.25 · iou=0.45
- Bộ ảnh: 30 ảnh có đáp án (44 cặp ảnh–loại), 3 ảnh không có vật COCO
- Tốc độ: trung vị 73 ms/ảnh trên máy chạy báo cáo (CPU, chưa tính mạng/LLM)
- **Đáp án đếm do Claude gắn nhãn bằng mắt, chưa có người kiểm lại.** Chỉ gắn những loại thấy rõ và đếm chắc chắn (không gắn đám đông, vật bị che nhiều, vật quá nhỏ). Số liệu dưới đây vì thế dùng cho cảnh "đếm vật rõ ràng", không đại diện cho ảnh đông đúc.

## 1. Độ chính xác đếm của YOLO

| Chỉ số | Giá trị |
|---|---|
| Đếm đúng tuyệt đối | **40/44 = 90.9%** |
| Sai số trung bình (MAE) | 0.09 vật/cặp |
| Precision / Recall / F1 (mức số lượng) | 100.0% / 93.4% / 96.6% |
| Chỉ 1 vật cần đếm | 33/36 = 91.7% |
| Từ 2 vật trở lên | 7/8 = 87.5% |

Quét ngưỡng tin cậy (cùng một lần chạy model):

| conf | Đếm đúng | MAE | Precision | Recall | F1 |
|---|---|---|---|---|---|
| 0.15 | 90.9% | 0.09 | 98.3% | 95.1% | 96.7% |
| 0.25 ← đang dùng | 90.9% | 0.09 | 100.0% | 93.4% | 96.6% |
| 0.35 | 88.6% | 0.11 | 100.0% | 91.8% | 95.7% |
| 0.5 | 84.1% | 0.16 | 100.0% | 88.5% | 93.9% |

Các cặp đếm sai ở conf=0.25 (4):

| Ảnh | Loại | Đáp án | YOLO |
|---|---|---|---|
| cv_apple.jpg | apple (táo) | 1 | 0 |
| cv_orange.jpg | orange (cam) | 1 | 0 |
| mmdet_demo.jpg | bench (ghế dài) | 2 | 1 |
| mrcnn_8734543718_37f6b8bd45_z.jpg | knife (dao) | 1 | 0 |

Ảnh không có vật COCO: 2/3 ảnh YOLO trả đúng "không có gì". Bịa ra: cv_baboon.jpg → {'person': 1}

## 2. Lọc theo loại vật thể (hỏi gì trả nấy)

44 câu hỏi dạng "Có mấy <loại>?" trên các ảnh có loại đó (câu hỏi viết cho từng loại, xem `CAU_HOI_LOP`).

| Chỉ số | Không lọc (cũ) | Có lọc (mới) |
|---|---|---|
| Số loại vật trả về mỗi câu (trung bình) | 2.3 | 0.9 |
| Số khung trả về mỗi câu (trung bình) | 4.2 | 1.3 |
| Loại vật KHÔNG được hỏi bị trả kèm (trung bình/câu) | 1.4 | 0.0 |

- Hiểu đúng loại được hỏi từ câu tiếng Việt: **44/44**
- Kết quả chỉ chứa loại được hỏi: **44/44**
- Số đếm của loại được hỏi giữ nguyên sau lọc: **44/44**

## 3. Lỗi xoay ảnh EXIF (ảnh dọc chụp từ điện thoại)

Mỗi ảnh có đáp án được lưu lại kiểu điện thoại (pixel xoay + cờ EXIF Orientation 6, 8 và 3), rồi đếm lại.

| Cách đọc ảnh | Đếm đúng | MAE |
|---|---|---|
| Ảnh gốc đúng chiều (mức tối đa có thể) | 90.9% | 0.09 |
| **Cũ**: bỏ qua cờ EXIF | 47.0% | 0.57 |
| Mới: detector tự xoay theo EXIF | 90.9% | 0.09 |
| Mới: xoay ngay khi upload | 90.9% | 0.09 |

Theo hướng EXIF (đếm đúng cũ → sau upload):

| Orientation | Ý nghĩa | Cũ | Sau sửa |
|---|---|---|---|
| 6 | ảnh dọc, cầm máy xoay phải | 43.2% | 90.9% |
| 8 | ảnh dọc, cầm máy xoay trái | 45.5% | 90.9% |
| 3 | ảnh lộn ngược | 52.3% | 90.9% |

## 4. Phân loại chủ đề và hiểu loại vật từ câu hỏi

Chủ đề (hàm `chu_de_tu_cau_hoi`, chạy local, không tốn model): **52/59 = 88.1%** trên 59 câu viết tay.

| Chủ đề mong đợi | Số câu | Đúng | Tỉ lệ |
|---|---|---|---|
| animal | 12 | 9 | 75.0% |
| chart | 7 | 6 | 85.7% |
| document | 8 | 8 | 100.0% |
| food | 7 | 6 | 85.7% |
| general | 16 | 16 | 100.0% |
| travel | 9 | 7 | 77.8% |

Câu phân loại sai:

| Câu hỏi | Mong đợi | Hàm trả |
|---|---|---|
| Đây là loài chim gì? | animal | general |
| loài chim này sống ở đâu | animal | general |
| Con mèo này bao nhiêu tuổi? | animal | general |
| Bức ảnh này chụp ở đâu? | travel | general |
| Đĩa này là món Việt hay món Hàn? | food | general |
| Đường nào tăng nhanh nhất trên đồ thị? | chart | general |
| Đây là khu đô thị nào? | travel | general |

Loại vật trong câu hỏi (`lop_tu_cau_hoi`): **34/34 = 100.0%** trên 34 câu.

**Lưu ý khi trình bày:** phần 4 đo bước định tuyến chủ đề theo CÂU HỎI (từ khoá). Bước phân loại chủ đề theo NỘI DUNG ẢNH dùng Gemini nên không nằm trong bộ này (tốn lượt). Hai bộ câu hỏi do người viết tay nên là mẫu nhỏ, không phải số đo trên dữ liệu người dùng thật. Riêng `lop_tu_cau_hoi`: bộ 34 câu từng lộ một lỗi ("Đếm số chó và mèo" chỉ ra mèo) và quy tắc đã được sửa sau đó, nên 100% ở đây là con số SAU KHI chỉnh theo chính bộ này, lạc quan hơn so với câu hỏi chưa từng thấy. Phần 2 "hiểu đúng loại" dùng câu hỏi mẫu do người viết biết trước từ khoá nên cũng không độc lập.

## 5. Đếm vật ngoài 80 loại COCO bằng Gemini

Câu hỏi "Có mấy <cụm>?" được chia đúng sang Gemini: **6/6** (đọc câu hỏi, không tốn lượt).

Chưa đo độ chính xác: chạy lại với `--gemini` (tốn 6 lượt Gemini, cần GEMINI/GOOGLE key trong .env).

Mẫu rất nhỏ, đáp án gắn tay: chỉ để minh hoạ tính năng, chưa đủ để kết luận độ chính xác của Gemini.


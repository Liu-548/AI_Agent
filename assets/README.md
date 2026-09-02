# Ảnh demo

Đặt ảnh test ở đây (two-dogs.jpg, multi-dogs.jpg, github_logo.png, rope.png).
Chỉ commit ảnh nhỏ (< 2MB). Ảnh lớn để ngoài repo.
Trước khi chạy thì kích hoạt venv:

```
.\start.ps1
```

Lệnh chạy test đếm vật thể (render sẵn ảnh có khung vào assets/):

```
python -m app.main --agent vision_agent "how many birds in Image: .\assets\chim.jpg"
```

Cũng có thể hỏi màu sắc hoặc yêu cầu miêu tả ảnh (được hỏi bằng tiếng Việt).
Test ảnh khác thì kéo file ảnh đó vào assets/.

# Ảnh demo

Đặt ảnh test ở đây (two-dogs.jpg, multi-dogs.jpg, github_logo.png, rope.png).
Chỉ commit ảnh nhỏ (< 2MB). Ảnh lớn để ngoài repo.
trước khi chạy thì ae nhập lệnh này vào de chay venv

.\start.ps1
lệnh chạy test:
python -m app.main --agent vision_agent "how many birds in Image: .\assets\chim.jpg"
đây là lệnh đếm vật thể trong ảnh nó sẽ render cho ae 1 ảnh trong assets 
ae có thể hỏi màu sắc hoặc miêu tả như nào thì cũng đc ae cho thể tiếng việt nếu test ảnh khác thì ae có thể kéo file ảnh đó vào assets 


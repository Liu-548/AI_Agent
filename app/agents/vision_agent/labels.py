"""Nhãn tiếng Việt cho 80 lớp COCO và bộ lọc "hỏi con gì thì chỉ trả con đó".

Hai việc, đều KHÔNG cần model mới và KHÔNG tốn lượt Gemini/Groq:

1. Đổi tên lớp của YOLO ("cat" -> "mèo") để chỉ gọi bằng một tên duy nhất ở mọi nơi
   (câu trả lời, chip, khung trên ảnh).
2. Đọc CÂU HỎI để biết người dùng muốn đếm loại nào. "Có mấy con mèo?" thì chỉ trả
   mèo, không trả luôn cả chó, ghế, người đang nằm trong ảnh. Câu không nêu loại cụ
   thể ("trong ảnh có gì", "đếm các vật thể") thì không lọc gì cả (như cũ).

Chỉ dùng thư viện chuẩn + `topics.khong_dau` để import ở đâu cũng nhẹ (CT-03).
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Dict, FrozenSet, Iterable, Iterator, List, Optional

from app.agents.vision_agent.topics import khong_dau

# --------------------------------------------------------------------------- #
# 80 lớp COCO -> tên tiếng Việt (đúng thứ tự tên mà yolo11n.onnx ghi trong metadata)
# --------------------------------------------------------------------------- #
COCO_VI: Dict[str, str] = {
    "person": "người",
    "bicycle": "xe đạp",
    "car": "ô tô",
    "motorcycle": "xe máy",
    "airplane": "máy bay",
    "bus": "xe buýt",
    "train": "tàu hỏa",
    "truck": "xe tải",
    "boat": "thuyền",
    "traffic light": "đèn giao thông",
    "fire hydrant": "trụ cứu hỏa",
    "stop sign": "biển báo dừng",
    "parking meter": "đồng hồ đỗ xe",
    "bench": "ghế dài",
    "bird": "chim",
    "cat": "mèo",
    "dog": "chó",
    "horse": "ngựa",
    "sheep": "cừu",
    "cow": "bò",
    "elephant": "voi",
    "bear": "gấu",
    "zebra": "ngựa vằn",
    "giraffe": "hươu cao cổ",
    "backpack": "ba lô",
    "umbrella": "ô dù",
    "handbag": "túi xách",
    "tie": "cà vạt",
    "suitcase": "vali",
    "frisbee": "đĩa ném",
    "skis": "ván trượt tuyết (ski)",
    "snowboard": "ván trượt tuyết (snowboard)",
    "sports ball": "quả bóng",
    "kite": "diều",
    "baseball bat": "gậy bóng chày",
    "baseball glove": "găng bóng chày",
    "skateboard": "ván trượt",
    "surfboard": "ván lướt sóng",
    "tennis racket": "vợt tennis",
    "bottle": "chai",
    "wine glass": "ly rượu vang",
    "cup": "cốc",
    "fork": "nĩa",
    "knife": "dao",
    "spoon": "thìa",
    "bowl": "bát",
    "banana": "chuối",
    "apple": "táo",
    "sandwich": "bánh sandwich",
    "orange": "cam",
    "broccoli": "bông cải xanh",
    "carrot": "cà rốt",
    "hot dog": "xúc xích kẹp bánh",
    "pizza": "pizza",
    "donut": "bánh donut",
    "cake": "bánh ngọt",
    "chair": "ghế",
    "couch": "ghế sofa",
    "potted plant": "chậu cây",
    "bed": "giường",
    "dining table": "bàn ăn",
    "toilet": "bồn cầu",
    "tv": "tivi",
    "laptop": "laptop",
    "mouse": "chuột máy tính",
    "remote": "điều khiển từ xa",
    "keyboard": "bàn phím",
    "cell phone": "điện thoại",
    "microwave": "lò vi sóng",
    "oven": "lò nướng",
    "toaster": "máy nướng bánh mì",
    "sink": "bồn rửa",
    "refrigerator": "tủ lạnh",
    "book": "sách",
    "clock": "đồng hồ",
    "vase": "bình hoa",
    "scissors": "kéo",
    "teddy bear": "gấu bông",
    "hair drier": "máy sấy tóc",
    "toothbrush": "bàn chải đánh răng",
}


def ten_viet(lop: str) -> str:
    """Tên tiếng Việt của một lớp COCO; lớp lạ thì trả nguyên tên gốc."""
    return COCO_VI.get(lop, lop)


def nhan_viet(lop_iter: Iterable[str]) -> Dict[str, str]:
    """{"cat": "mèo", ...} cho các lớp đã gặp, để gửi kèm kết quả cho UI/LLM."""
    return {c: ten_viet(c) for c in lop_iter}


# --------------------------------------------------------------------------- #
# Câu hỏi -> loại vật thể
# --------------------------------------------------------------------------- #
# Viết KHÔNG DẤU, chữ thường (so khớp sau `khong_dau`). Tiếng Việt có nhiều từ ngắn
# trùng nghĩa khác ("cho" = cho/chó, "ban" = bạn/bàn, "voi" = với/voi, "tao" = táo/tao,
# "dieu" = điều/diều), nên các từ đó BẮT BUỘC có từ loại đứng trước ("con cho",
# "cai ban"). Test bắt các câu hỏi thường ngày không bị hiểu nhầm.
_CON = r"(?:con|chu|may con|nhung con|cac con|bay|dan)\s+"
_CAI = r"(?:cai|chiec|may cai|may chiec|nhung|cac)\s+"
_QUA = r"(?:qua|trai|may qua|may trai)\s+"

_TU_KHOA: Dict[str, str] = {
    "person": r"\b(?:nguoi|people|persons?)\b",
    "bicycle": r"\b(?:xe dap|bicycles?|bikes?)\b",
    "car": r"\b(?:o to|oto|xe hoi|xe con|cars?)\b",
    "motorcycle": r"\b(?:xe may|xe gan may|mo to|motorcycles?|motorbikes?)\b",
    "airplane": r"\b(?:may bay|airplanes?|planes?)\b",
    "bus": r"\b(?:xe buyt|xe bus|buses|bus)\b",
    "train": r"\b(?:tau hoa|xe lua|trains?)\b",
    "truck": r"\b(?:xe tai|xe container|trucks?)\b",
    "boat": r"\b(?:thuyen|ca no|tau thuy|boats?)\b",
    "traffic light": r"\b(?:den giao thong|den xanh den do|traffic lights?)\b",
    "fire hydrant": r"\b(?:tru cuu hoa|fire hydrants?)\b",
    "stop sign": r"\b(?:bien bao dung|bien stop|stop signs?)\b",
    "parking meter": r"\b(?:dong ho do xe|parking meters?)\b",
    "bench": r"\b(?:ghe dai|ghe da|ghe cong vien|benches|bench)\b",
    "bird": rf"\b(?:{_CON}chim|chim|birds?)\b",
    "cat": rf"\b(?:{_CON}meo|meo|cats?)\b",
    # "cho" trần chỉ nhận khi đứng trong cụm đếm/liệt kê ("số chó", "chó và mèo"): ngoài ra nó là "cho".
    "dog": rf"\b(?:{_CON}cho|(?:so|dem) cho|cho (?:va|hoac)|(?:va|hoac) cho|dogs?|puppy|puppies)\b",
    "horse": rf"\b(?:{_CON}ngua(?! van)|ngua(?! van)|horses?)\b",
    "sheep": rf"\b(?:{_CON}cuu|cuu|sheep)\b",
    "cow": rf"\b(?:{_CON}bo|bo sua|cows?|cattle)\b",
    "elephant": rf"\b(?:{_CON}voi|elephants?)\b",
    "bear": rf"\b(?:{_CON}gau(?! bong)|bears?)\b",
    "zebra": r"\b(?:ngua van|zebras?)\b",
    "giraffe": r"\b(?:huou cao co|giraffes?)\b",
    "backpack": r"\b(?:ba lo|cap sach|backpacks?)\b",
    "umbrella": rf"\b(?:{_CAI}(?:o|du)(?! to\b|to\b)|cay du|umbrellas?)\b",
    "handbag": r"\b(?:tui xach|tui da|handbags?)\b",
    "tie": r"\b(?:ca vat|neckties?)\b",
    "suitcase": r"\b(?:vali|suitcases?)\b",
    "frisbee": r"\b(?:dia nem|frisbees?)\b",
    "skis": r"\b(?:van truot tuyet|skis?)\b",
    "snowboard": r"\b(?:van truot tuyet|snowboards?)\b",
    "sports ball": r"\b(?:qua bong|trai bong|bong da|bong chuyen|bong ro|sports? balls?|balls?)\b",
    "kite": rf"\b(?:{_CON}dieu|{_CAI}dieu|canh dieu|kites?)\b",
    "baseball bat": r"\b(?:gay bong chay|baseball bats?)\b",
    "baseball glove": r"\b(?:gang tay bong chay|baseball gloves?)\b",
    "skateboard": r"\b(?:van truot(?! tuyet)|skateboards?)\b",
    "surfboard": r"\b(?:van luot song|surfboards?)\b",
    "tennis racket": r"\b(?:vot tennis|vot tenis|vot|tennis rackets?)\b",
    "bottle": rf"\b(?:{_CAI}chai|chai|bottles?)\b",
    "wine glass": r"\b(?:ly ruou|ly vang|wine glass(?:es)?)\b",
    "cup": rf"\b(?:{_CAI}(?:coc|ly)(?! ruou)|coc|cups?|mugs?)\b",
    "fork": rf"\b(?:{_CAI}nia|nia|forks?)\b",
    "knife": rf"\b(?:{_CAI}dao|{_CON}dao|knife|knives)\b",
    "spoon": rf"\b(?:{_CAI}thia|{_CAI}muong|thia|spoons?)\b",
    "bowl": rf"\b(?:{_CAI}bat|{_CAI}to(?! chuc)|bowls?)\b",
    "banana": r"\b(?:chuoi|bananas?)\b",
    "apple": rf"\b(?:{_QUA}tao|{_CAI}tao|apples?)\b",
    "sandwich": r"\b(?:sandwich(?:es)?|banh mi kep)\b",
    "orange": rf"\b(?:{_QUA}cam|oranges?)\b",
    "broccoli": r"\b(?:bong cai xanh|bong cai|broccoli)\b",
    "carrot": r"\b(?:ca rot|carrots?)\b",
    "hot dog": r"\b(?:xuc xich|hot ?dogs?)\b",
    "pizza": r"\b(?:pizzas?|pi za)\b",
    "donut": r"\b(?:banh donut|donuts?|doughnuts?|banh vong)\b",
    "cake": r"\b(?:banh kem|banh ngot|banh sinh nhat|cakes?)\b",
    "chair": r"\b(?:ghe(?! sofa| dai| da| cong vien| bang| salon)|chairs?)\b",
    "couch": r"\b(?:ghe sofa|sofa|ghe bang|ghe salon|couch(?:es)?)\b",
    "potted plant": r"\b(?:chau cay|cay chau|cay canh|potted plants?)\b",
    "bed": r"\b(?:giuong|beds?)\b",
    "dining table": rf"\b(?:ban an|{_CAI}ban|dining tables?|tables?)\b",
    "toilet": r"\b(?:bon cau|toilets?)\b",
    "tv": r"\b(?:ti vi|tivi|tv|television)\b",
    "laptop": r"\b(?:laptops?|may tinh xach tay)\b",
    "mouse": r"\b(?:chuot may tinh|con chuot may tinh|computer mouse)\b",
    "remote": r"\b(?:dieu khien|remotes?)\b",
    "keyboard": r"\b(?:ban phim|keyboards?)\b",
    "cell phone": r"\b(?:dien thoai|cell ?phones?|smartphones?|phones?)\b",
    "microwave": r"\b(?:lo vi song|microwaves?)\b",
    "oven": r"\b(?:lo nuong|ovens?)\b",
    "toaster": r"\b(?:may nuong banh mi|toasters?)\b",
    "sink": r"\b(?:bon rua|sinks?)\b",
    "refrigerator": r"\b(?:tu lanh|refrigerators?|fridges?)\b",
    "book": rf"\b(?:{_CAI}sach|quyen sach|cuon sach|books?)\b",
    "clock": r"\b(?:dong ho(?! do xe)|clocks?)\b",
    "vase": r"\b(?:binh hoa|lo hoa|vases?)\b",
    "scissors": rf"\b(?:{_CAI}keo|keo cat|scissors)\b",
    "teddy bear": r"\b(?:gau bong|teddy(?: bears?)?)\b",
    "hair drier": r"\b(?:may say toc|hair dr[iy]ers?)\b",
    "toothbrush": r"\b(?:ban chai danh rang|toothbrush(?:es)?)\b",
}

# Cách gọi chung -> cả nhóm lớp. Khi người dùng hỏi "bao nhiêu động vật", "bao nhiêu xe".
_NHOM: Dict[str, tuple] = {
    r"\b(?:dong vat|con vat|animals?)\b": (
        "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe",
    ),
    r"\b(?:phuong tien|vehicles?)\b": (
        "bicycle", "car", "motorcycle", "bus", "truck", "train", "airplane", "boat",
    ),
    # "xe" đứng một mình (không kèm đạp/máy/buýt/tải/hơi/con/khách/lửa)
    r"\bxe\b(?! (?:dap|may|gan|buyt|bus|tai|hoi|con|khach|lua|container))": (
        "bicycle", "car", "motorcycle", "bus", "truck",
    ),
    r"\b(?:trai cay|hoa qua|fruits?)\b": ("banana", "apple", "orange"),
}

_RE_LOP = {lop: re.compile(mau) for lop, mau in _TU_KHOA.items()}
_RE_NHOM = [(re.compile(mau), lops) for mau, lops in _NHOM.items()]

# Bỏ đường dẫn / URL / tên file ảnh trước khi dò: "C:\\...\\cat.jpg" không có nghĩa là
# người dùng đang hỏi về mèo.
_RE_DUONG_DAN = re.compile(
    r"https?://\S+|\S*[\\/]\S*|\S+\.(?:jpe?g|png|webp|bmp|gif|tiff?)\b", re.IGNORECASE
)
_RE_BI_DANH = re.compile(r"\bimg[\s_#-]?\d{1,3}\b")


def lop_tu_cau_hoi(cau_hoi: str) -> FrozenSet[str]:
    """Các lớp COCO mà câu hỏi nhắm tới; rỗng = không nêu loại nào (không lọc)."""
    chuan = khong_dau(_RE_DUONG_DAN.sub(" ", cau_hoi or ""))
    chuan = _RE_BI_DANH.sub(" ", chuan)
    chuan = re.sub(r"\s+", " ", chuan)
    if not chuan.strip():
        return frozenset()
    thay = set()
    for lop, mau in _RE_LOP.items():
        if mau.search(chuan):
            thay.add(lop)
    for mau, lops in _RE_NHOM:
        if mau.search(chuan):
            thay.update(lops)
    return frozenset(thay)


# --------------------------------------------------------------------------- #
# Lọc kết quả YOLO theo câu hỏi
# --------------------------------------------------------------------------- #
def loc_theo_lop(payload: dict, lop: Optional[Iterable[str]]) -> dict:
    """Giữ lại đúng các lớp trong `lop`; `lop` rỗng thì trả nguyên (không lọc).

    Trả bản sao: không sửa payload gốc. Khi có lọc, thêm `filtered_by` để người đọc
    (và LLM) biết kết quả đã bị lọc chứ không phải ảnh thật sự không có gì khác.
    """
    chon = frozenset(lop or ())
    if not chon:
        return payload
    dets = [d for d in payload.get("detections", []) if d.get("class") in chon]
    dem: Dict[str, int] = {}
    for d in dets:
        dem[d["class"]] = dem.get(d["class"], 0) + 1
    ra = dict(payload)
    ra["counting"] = dem
    ra["detections"] = dets
    ra["filtered_by"] = sorted(chon)
    return ra


# --------------------------------------------------------------------------- #
# Đưa câu hỏi từ vision_tool xuống detect_and_count_objects
# --------------------------------------------------------------------------- #
# Tool chỉ nhận một tham số `text` (hợp đồng IF-07) và agent con thường chỉ truyền
# đường dẫn ảnh vào đó, không có câu hỏi. Cùng cơ chế với `topics.dung_chu_de`.
_CAU_HOI_HIEN_TAI: ContextVar[Optional[str]] = ContextVar("vision_cau_hoi", default=None)


@contextmanager
def dung_cau_hoi(cau_hoi: Optional[str]) -> Iterator[None]:
    """Trong khối `with`, detect_and_count_objects lọc theo loại vật thể trong câu hỏi."""
    token = _CAU_HOI_HIEN_TAI.set(cau_hoi)
    try:
        yield
    finally:
        _CAU_HOI_HIEN_TAI.reset(token)


def cau_hoi_hien_tai() -> Optional[str]:
    """Câu hỏi của lượt hiện tại (đặt bởi `dung_cau_hoi`), None nếu không có."""
    return _CAU_HOI_HIEN_TAI.get()


def lop_dang_loc() -> FrozenSet[str]:
    """Các lớp cần giữ cho lượt hiện tại; rỗng nếu không có câu hỏi hay không nêu loại."""
    cau_hoi = _CAU_HOI_HIEN_TAI.get()
    return lop_tu_cau_hoi(cau_hoi) if cau_hoi else frozenset()


# --------------------------------------------------------------------------- #
# Gom theo NHÓM: người / phương tiện / động vật / khác
# --------------------------------------------------------------------------- #
# Người dùng hay hỏi "tổng cộng bao nhiêu người, bao nhiêu xe, bao nhiêu con vật",
# không phải từng lớp COCO. Thứ tự ở đây là thứ tự in ra.
NHOM_VAT: Dict[str, tuple] = {
    "nguoi": ("Người", ("person",)),
    "phuong_tien": (
        "Phương tiện",
        ("bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat"),
    ),
    "dong_vat": (
        "Động vật",
        ("bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"),
    ),
}
NHOM_KHAC = ("khac", "Đồ vật khác")


def nhom_cua(lop: str) -> str:
    """Mã nhóm của một lớp COCO: nguoi / phuong_tien / dong_vat / khac."""
    for ma, (_ten, cac_lop) in NHOM_VAT.items():
        if lop in cac_lop:
            return ma
    return NHOM_KHAC[0]


def tong_theo_nhom(counting: Dict[str, int]) -> List[dict]:
    """{"person": 9, "car": 3, "motorcycle": 4} -> [{"nhom", "ten", "tong", "chi_tiet"}, ...].

    Chỉ trả nhóm có ít nhất một vật, đúng thứ tự Người, Phương tiện, Động vật, Khác.
    """
    ra = []
    for ma, ten in [(m, v[0]) for m, v in NHOM_VAT.items()] + [NHOM_KHAC]:
        chi_tiet = {c: n for c, n in counting.items() if nhom_cua(c) == ma and n}
        if chi_tiet:
            ra.append({"nhom": ma, "ten": ten, "tong": sum(chi_tiet.values()), "chi_tiet": chi_tiet})
    return ra

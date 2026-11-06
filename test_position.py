from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from io import BytesIO


# ==========================================
# إعدادات مكان QR
# ==========================================

QR_X = 370
QR_Y = 130
QR_SIZE = 250


# ==========================================
# ملفات البطاقات
# ==========================================

cards = [
    {
        "input": "Cards.pdf",
        "output": "test_normal.pdf"
    },
    {
        "input": "cards vip.pdf",
        "output": "test_vip.pdf"
    }
]


# ==========================================
# معالجة كل بطاقة
# ==========================================

for card in cards:

    input_pdf = card["input"]
    output_pdf = card["output"]

    print(f"Processing: {input_pdf}")

    # قراءة التصميم
    reader = PdfReader(input_pdf)

    page = reader.pages[0]

    page_width = float(page.mediabox.width)
    page_height = float(page.mediabox.height)

    # إنشاء طبقة QR التجريبية
    buffer = BytesIO()

    c = canvas.Canvas(
        buffer,
        pagesize=(page_width, page_height)
    )

    # رسم مربع أحمر
    c.setLineWidth(2)
    c.setStrokeColorRGB(1, 0, 0)

    c.rect(
        QR_X,
        QR_Y,
        QR_SIZE,
        QR_SIZE,
        stroke=1,
        fill=0
    )

    c.save()

    buffer.seek(0)

    # دمج الطبقة مع التصميم
    overlay_reader = PdfReader(buffer)

    page.merge_page(
        overlay_reader.pages[0]
    )

    # حفظ ملف PDF منفصل
    writer = PdfWriter()

    writer.add_page(page)

    with open(output_pdf, "wb") as output_file:
        writer.write(output_file)

    print(f"Created successfully: {output_pdf}")


print("\nAll test files created successfully!")
import os
import secrets
from io import BytesIO

import qrcode
from qrcode.constants import ERROR_CORRECT_H
from PIL import Image, ImageDraw

from dotenv import load_dotenv
from supabase import create_client

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


# ============================================================
# 1. الإعدادات
# ============================================================

TOTAL_CARDS = 650

DESIGN_PDF = "(English) (2).pdf"

# استخدم نفس الأيقونة التي استخدمناها في البطاقة التجريبية
LOGO_PATH = "translation.png"

# ملف PDF النهائي
OUTPUT_PDF = "graduation_cards_650.pdf"

# ملفات مؤقتة اختيارية
CSV_FILE = "cards.csv"

# مكان وحجم QR داخل البطاقة
QR_X = 100
QR_Y = 60
QR_SIZE = 100


# ============================================================
# 2. التحقق من الملفات
# ============================================================

if not os.path.exists(DESIGN_PDF):
    raise Exception(
        f"Design PDF not found: {DESIGN_PDF}"
    )

if not os.path.exists(LOGO_PATH):
    raise Exception(
        f"Logo not found: {LOGO_PATH}"
    )


# ============================================================
# 3. الاتصال بـ Supabase
# ============================================================

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SECRET_KEY")

if not supabase_url:
    raise Exception(
        "SUPABASE_URL not found in .env"
    )

if not supabase_key:
    raise Exception(
        "SUPABASE_SECRET_KEY not found in .env"
    )

supabase = create_client(
    supabase_url,
    supabase_key
)

print("Connected to Supabase.")
print()


# ============================================================
# 4. فحص البطاقات الموجودة
# ============================================================

print("Checking existing cards in Supabase...")

existing_response = (
    supabase
    .table("cards")
    .select("card_number")
    .gte("card_number", 1)
    .lte("card_number", TOTAL_CARDS)
    .execute()
)

existing_cards = existing_response.data or []

if existing_cards:

    existing_numbers = sorted(
        int(card["card_number"])
        for card in existing_cards
    )

    print()
    print("ERROR:")
    print("Some card numbers already exist in Supabase.")
    print()
    print(
        f"Existing cards count: {len(existing_numbers)}"
    )

    print(
        "First existing numbers:",
        existing_numbers[:20]
    )

    raise Exception(
        "Generation stopped to prevent duplicate cards."
    )


print("No existing cards from 001 to 650.")
print()


# ============================================================
# 5. تحميل تصميم البطاقة مرة واحدة
# ============================================================

design_reader = PdfReader(
    DESIGN_PDF
)

if len(design_reader.pages) < 1:
    raise Exception(
        "Design PDF does not contain any pages."
    )

design_page = design_reader.pages[0]

page_width = float(
    design_page.mediabox.width
)

page_height = float(
    design_page.mediabox.height
)

print("Card dimensions:")
print(
    f"Width  = {page_width}"
)

print(
    f"Height = {page_height}"
)

print()


# ============================================================
# 6. تحميل الأيقونة مرة واحدة
# ============================================================

logo_original = (
    Image.open(LOGO_PATH)
    .convert("RGBA")
)


# ============================================================
# 7. دالة إنشاء QR
# ============================================================

def create_qr_image(token):

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=20,
        border=4
    )

    qr.add_data(token)

    qr.make(
        fit=True
    )

    matrix = qr.get_matrix()

    box_size = 20
    border = 4

    matrix_size = len(matrix)

    image_size = (
        matrix_size + border * 2
    ) * box_size

    # خلفية بيضاء
    image = Image.new(
        "RGBA",
        (image_size, image_size),
        "white"
    )

    draw = ImageDraw.Draw(image)


    # ========================================================
    # رسم وحدات QR بشكل دائري
    # ========================================================

    for y, row in enumerate(matrix):

        for x, cell in enumerate(row):

            if cell:

                left = (
                    x + border
                ) * box_size

                top = (
                    y + border
                ) * box_size

                right = (
                    left + box_size
                )

                bottom = (
                    top + box_size
                )

                padding = 2

                draw.ellipse(
                    (
                        left + padding,
                        top + padding,
                        right - padding,
                        bottom - padding
                    ),
                    fill="black"
                )


    # ========================================================
    # إنشاء نسخة من الأيقونة
    # ========================================================

    logo = logo_original.copy()

    logo_size = int(
        image_size * 0.15
    )

    logo.thumbnail(
        (
            logo_size,
            logo_size
        ),
        Image.Resampling.LANCZOS
    )


    # ========================================================
    # خلفية بيضاء حول الأيقونة
    # ========================================================

    logo_padding = 12

    background_size = (
        logo.width + logo_padding * 2,
        logo.height + logo_padding * 2
    )

    logo_background = Image.new(
        "RGBA",
        background_size,
        "white"
    )

    logo_x = (
        background_size[0] - logo.width
    ) // 2

    logo_y = (
        background_size[1] - logo.height
    ) // 2

    logo_background.paste(
        logo,
        (
            logo_x,
            logo_y
        ),
        logo
    )


    # ========================================================
    # وضع الأيقونة في منتصف QR
    # ========================================================

    logo_position = (
        (
            image.width
            - logo_background.width
        ) // 2,

        (
            image.height
            - logo_background.height
        ) // 2
    )

    image.paste(
        logo_background,
        logo_position,
        logo_background
    )

    return image


# ============================================================
# 8. إنشاء PDF النهائي
# ============================================================

print("Creating final PDF...")
print()

writer = PdfWriter()

cards = []

used_tokens = set()


# ============================================================
# 9. إنشاء 650 بطاقة
# ============================================================

for card_number in range(
    1,
    TOTAL_CARDS + 1
):

    print(
        f"Creating card "
        f"{card_number:03d}/{TOTAL_CARDS}"
    )


    # --------------------------------------------------------
    # إنشاء Token فريد
    # --------------------------------------------------------

    token = secrets.token_urlsafe(24)

    # تأكيد عدم وجود تكرار
    while token in used_tokens:

        token = secrets.token_urlsafe(24)

    used_tokens.add(token)


    # --------------------------------------------------------
    # حفظ معلومات البطاقة في الذاكرة
    # --------------------------------------------------------

    cards.append({
        "card_number": card_number,
        "token": token
    })


    # --------------------------------------------------------
    # إنشاء QR
    # --------------------------------------------------------

    qr_image = create_qr_image(
        token
    )


    # --------------------------------------------------------
    # تحويل QR إلى PNG في الذاكرة
    # --------------------------------------------------------

    qr_buffer = BytesIO()

    qr_image.save(
        qr_buffer,
        format="PNG"
    )

    qr_buffer.seek(0)


    # --------------------------------------------------------
    # إنشاء طبقة QR فوق التصميم
    # --------------------------------------------------------

    overlay_buffer = BytesIO()

    c = canvas.Canvas(
        overlay_buffer,
        pagesize=(
            page_width,
            page_height
        )
    )

    c.drawImage(
        ImageReader(qr_buffer),
        QR_X,
        QR_Y,
        width=QR_SIZE,
        height=QR_SIZE,
        mask="auto"
    )

    c.save()

    overlay_buffer.seek(0)


    # --------------------------------------------------------
    # قراءة طبقة QR
    # --------------------------------------------------------

    overlay_reader = PdfReader(
        overlay_buffer
    )


    # --------------------------------------------------------
    # إنشاء نسخة جديدة من تصميم البطاقة
    # --------------------------------------------------------

    card_reader = PdfReader(
        DESIGN_PDF
    )

    card_page = card_reader.pages[0]


    # --------------------------------------------------------
    # دمج QR مع التصميم
    # --------------------------------------------------------

    card_page.merge_page(
        overlay_reader.pages[0]
    )


    # --------------------------------------------------------
    # إضافة الصفحة إلى PDF النهائي
    # --------------------------------------------------------

    writer.add_page(
        card_page
    )


# ============================================================
# 10. التأكد من عدد صفحات PDF
# ============================================================

print()
print("Checking PDF page count...")

if len(writer.pages) != TOTAL_CARDS:

    raise Exception(
        f"PDF page count error: "
        f"{len(writer.pages)} instead of "
        f"{TOTAL_CARDS}"
    )

print(
    f"PDF contains exactly "
    f"{TOTAL_CARDS} pages."
)


# ============================================================
# 11. حفظ PDF
# ============================================================

print()
print("Saving final PDF...")

with open(
    OUTPUT_PDF,
    "wb"
) as output_file:

    writer.write(
        output_file
    )


print(
    f"PDF saved: {OUTPUT_PDF}"
)


# ============================================================
# 12. حفظ نسخة CSV احتياطية
# ============================================================

print()
print("Saving CSV backup...")

with open(
    CSV_FILE,
    "w",
    newline="",
    encoding="utf-8"
) as file:

    import csv

    csv_writer = csv.writer(
        file
    )

    csv_writer.writerow([
        "card_number",
        "token"
    ])

    for card in cards:

        csv_writer.writerow([
            card["card_number"],
            card["token"]
        ])


print(
    f"CSV saved: {CSV_FILE}"
)


# ============================================================
# 13. تسجيل البطاقات في Supabase
# ============================================================

print()
print("Saving 650 cards to Supabase...")


# تقسيم الإدخال إلى دفعات
BATCH_SIZE = 100

for start in range(
    0,
    len(cards),
    BATCH_SIZE
):

    batch = cards[
        start:start + BATCH_SIZE
    ]

    rows = []

    for card in batch:

        rows.append({
            "card_number": card["card_number"],
            "token": card["token"],
            "status": "UNUSED"
        })


    supabase.table(
        "cards"
    ).insert(
        rows
    ).execute()


    end_number = batch[-1]["card_number"]

    print(
        f"Saved cards "
        f"{batch[0]['card_number']:03d}"
        f"-"
        f"{end_number:03d}"
    )


# ============================================================
# 14. التحقق النهائي من قاعدة البيانات
# ============================================================

print()
print("Verifying database...")

verify_response = (
    supabase
    .table("cards")
    .select("card_number, token, status")
    .gte("card_number", 1)
    .lte("card_number", TOTAL_CARDS)
    .execute()
)

database_cards = (
    verify_response.data or []
)


# ============================================================
# التحقق من العدد
# ============================================================

if len(database_cards) != TOTAL_CARDS:

    raise Exception(
        "Database verification failed: "
        f"expected {TOTAL_CARDS}, "
        f"found {len(database_cards)}"
    )


# ============================================================
# التحقق من الـ Tokens
# ============================================================

database_tokens = {
    card["token"]
    for card in database_cards
}

if len(database_tokens) != TOTAL_CARDS:

    raise Exception(
        "Database verification failed: "
        "duplicate tokens detected."
    )


# ============================================================
# التحقق من الحالات
# ============================================================

invalid_statuses = [
    card
    for card in database_cards
    if card["status"] != "UNUSED"
]

if invalid_statuses:

    raise Exception(
        "Database verification failed: "
        "some cards are not UNUSED."
    )


# ============================================================
# النهاية
# ============================================================

print()
print("==============================================")
print("650 GRADUATION CARDS CREATED SUCCESSFULLY")
print("==============================================")
print()
print(f"PDF        : {OUTPUT_PDF}")
print(f"Pages      : {TOTAL_CARDS}")
print(f"Cards      : {TOTAL_CARDS}")
print(f"QR X       : {QR_X}")
print(f"QR Y       : {QR_Y}")
print(f"QR Size    : {QR_SIZE}")
print(f"Status     : UNUSED")
print(f"CSV backup : {CSV_FILE}")
print()
print("Supabase verification: PASSED")
print("Token uniqueness: PASSED")
print("PDF page count: PASSED")
print("==============================================")
import os
import csv
import secrets
from io import BytesIO
from pathlib import Path

import qrcode
from qrcode.constants import ERROR_CORRECT_H
from PIL import Image, ImageDraw

from dotenv import load_dotenv
from supabase import create_client

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


# ============================================================
# 1. CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

LOGO_PATH = BASE_DIR / "medicine.png"

QR_X = 370
QR_Y = 130
QR_SIZE = 250

BATCH_SIZE = 100

CARD_TYPES = [
    {
        "type": "NORMAL",
        "design": "Cards.pdf",
        "count": 580,
        "start": 1,
        "output": "cards_normal_580.pdf"
    },
    {
        "type": "VIP",
        "design": "cards vip.pdf",
        "count": 80,
        "start": 581,
        "output": "cards_vip_80.pdf"
    },
    {
        "type": "CHILD",
        "design": "cards child.pdf",
        "count": 50,
        "start": 661,
        "output": "cards_child_50.pdf"
    }
]

TOTAL_CARDS = sum(item["count"] for item in CARD_TYPES)

CSV_FILE = BASE_DIR / "cards_generated_710.csv"


# ============================================================
# 2. VALIDATE FILES
# ============================================================

print("=" * 55)
print("GRADUATION CARDS GENERATOR")
print("=" * 55)

if not LOGO_PATH.exists():
    raise FileNotFoundError(f"Logo not found: {LOGO_PATH}")

for item in CARD_TYPES:
    design_path = BASE_DIR / item["design"]

    if not design_path.exists():
        raise FileNotFoundError(
            f"Design not found: {design_path}"
        )

print("All design files and logo found.")


# ============================================================
# 3. CONNECT TO SUPABASE
# ============================================================

load_dotenv(BASE_DIR / ".env")

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SECRET_KEY")

if not supabase_url or not supabase_key:
    raise Exception(
        "SUPABASE_URL or SUPABASE_SECRET_KEY missing from .env"
    )

supabase = create_client(
    supabase_url,
    supabase_key
)

print("Connected to Supabase.")


# ============================================================
# 4. CHECK EXISTING CARD NUMBERS
# ============================================================

print("\nChecking existing card numbers...")

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

    print("\nERROR: Existing card numbers detected.")
    print("Existing count:", len(existing_numbers))
    print("First existing numbers:", existing_numbers[:30])

    raise Exception(
        "Generation stopped to prevent duplicate card numbers. "
        "Do not delete existing records automatically."
    )

print("No existing card numbers from 001 to 710.")


# ============================================================
# 5. LOAD LOGO AND PDF DESIGNS
# ============================================================

logo_original = Image.open(LOGO_PATH).convert("RGBA")

designs = {}

for item in CARD_TYPES:

    reader = PdfReader(
        str(BASE_DIR / item["design"])
    )

    if not reader.pages:
        raise Exception(
            f"Empty PDF design: {item['design']}"
        )

    page = reader.pages[0]

    designs[item["type"]] = {
        "width": float(page.mediabox.width),
        "height": float(page.mediabox.height)
    }

    print(
        f"{item['type']} design loaded: "
        f"{item['design']}"
    )


# ============================================================
# 6. CREATE QR IMAGE
# ============================================================

def create_qr_image(token):

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=20,
        border=4
    )

    qr.add_data(token)
    qr.make(fit=True)

    matrix = qr.get_matrix()

    box_size = 20
    border = 4

    matrix_size = len(matrix)

    image_size = (
        matrix_size + border * 2
    ) * box_size

    image = Image.new(
        "RGBA",
        (image_size, image_size),
        "white"
    )

    draw = ImageDraw.Draw(image)

    # Draw circular QR modules
    for y, row in enumerate(matrix):

        for x, cell in enumerate(row):

            if cell:

                left = (x + border) * box_size
                top = (y + border) * box_size

                right = left + box_size
                bottom = top + box_size

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

    # Prepare center logo
    logo = logo_original.copy()

    logo_size = int(image_size * 0.15)

    logo.thumbnail(
        (logo_size, logo_size),
        Image.Resampling.LANCZOS
    )

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
        (logo_x, logo_y),
        logo
    )

    # Center logo inside QR
    logo_position = (
        (image.width - logo_background.width) // 2,
        (image.height - logo_background.height) // 2
    )

    image.paste(
        logo_background,
        logo_position,
        logo_background
    )

    return image


# ============================================================
# 7. GENERATE UNIQUE TOKENS AND CARD DATA
# ============================================================

print("\nGenerating card tokens...")

cards = []
used_tokens = set()

for item in CARD_TYPES:

    card_type = item["type"]

    for offset in range(item["count"]):

        card_number = item["start"] + offset

        token = secrets.token_urlsafe(24)

        while token in used_tokens:
            token = secrets.token_urlsafe(24)

        used_tokens.add(token)

        cards.append({
            "card_number": card_number,
            "token": token,
            "card_type": card_type
        })

    print(
        f"{card_type}: {item['count']} cards generated."
    )

if len(cards) != TOTAL_CARDS:
    raise Exception("Generated card count mismatch.")

if len(used_tokens) != TOTAL_CARDS:
    raise Exception("Duplicate tokens detected.")

print(f"\nTotal unique cards: {TOTAL_CARDS}")


# ============================================================
# 8. GENERATE SEPARATE PDF FILES
# ============================================================

print("\nGenerating PDF files...")

pdf_outputs = {}

for item in CARD_TYPES:

    card_type = item["type"]

    writer = PdfWriter()

    template = designs[card_type]

    page_width = template["width"]
    page_height = template["height"]

    type_cards = [
        card for card in cards
        if card["card_type"] == card_type
    ]

    print(
        f"\nProcessing {card_type}: "
        f"{len(type_cards)} pages"
    )

    for index, card in enumerate(type_cards, start=1):

        # Create QR
        qr_image = create_qr_image(card["token"])

        qr_buffer = BytesIO()

        qr_image.save(
            qr_buffer,
            format="PNG"
        )

        qr_buffer.seek(0)

        # Create QR overlay
        overlay_buffer = BytesIO()

        c = canvas.Canvas(
            overlay_buffer,
            pagesize=(page_width, page_height)
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

        overlay_reader = PdfReader(overlay_buffer)

        # Load a fresh original design page for each card
        card_reader = PdfReader(
            str(BASE_DIR / item["design"])
        )

        card_page = card_reader.pages[0]

        # Merge QR with design
        card_page.merge_page(
            overlay_reader.pages[0]
        )

        writer.add_page(card_page)

        if index % 100 == 0 or index == len(type_cards):

            print(
                f"{card_type}: {index}/{len(type_cards)}"
            )

    if len(writer.pages) != item["count"]:
        raise Exception(
            f"{card_type} PDF page count mismatch."
        )

    # Keep PDF in memory until database verification
    pdf_buffer = BytesIO()

    writer.write(pdf_buffer)

    pdf_outputs[item["output"]] = pdf_buffer.getvalue()

    print(
        f"{item['output']} prepared successfully."
    )


# ============================================================
# 9. SAVE CARDS TO SUPABASE
# ============================================================

print("\nSaving cards to Supabase...")

saved_count = 0

for start in range(0, len(cards), BATCH_SIZE):

    batch = cards[start:start + BATCH_SIZE]

    rows = [
        {
            "card_number": card["card_number"],
            "token": card["token"],
            "status": "UNUSED",
            "card_type": card["card_type"]
        }
        for card in batch
    ]

    supabase.table("cards").insert(rows).execute()

    saved_count += len(batch)

    print(
        f"Saved {saved_count}/{TOTAL_CARDS}"
    )

print("\nDatabase insertion completed.")


# ============================================================
# 10. VERIFY DATABASE
# ============================================================

print("\nVerifying Supabase records...")

verify_response = (
    supabase
    .table("cards")
    .select("card_number,token,status,card_type")
    .gte("card_number", 1)
    .lte("card_number", TOTAL_CARDS)
    .execute()
)

database_cards = verify_response.data or []

if len(database_cards) != TOTAL_CARDS:
    raise Exception(
        f"Database count mismatch: "
        f"expected {TOTAL_CARDS}, "
        f"found {len(database_cards)}"
    )

database_numbers = {
    int(card["card_number"])
    for card in database_cards
}

if len(database_numbers) != TOTAL_CARDS:
    raise Exception("Duplicate card numbers detected.")

if database_numbers != set(range(1, TOTAL_CARDS + 1)):
    raise Exception("Card number sequence mismatch.")

database_tokens = {
    card["token"]
    for card in database_cards
}

if len(database_tokens) != TOTAL_CARDS:
    raise Exception("Duplicate tokens detected.")

expected_types = {
    item["type"]: item["count"]
    for item in CARD_TYPES
}

actual_types = {}

for card in database_cards:

    if card["status"] != "UNUSED":
        raise Exception(
            f"Invalid status on card {card['card_number']}"
        )

    card_type = card["card_type"]

    actual_types[card_type] = (
        actual_types.get(card_type, 0) + 1
    )

if actual_types != expected_types:
    raise Exception(
        f"Card type mismatch: {actual_types}"
    )

print("Database verification: PASSED")
print("Card numbers: PASSED")
print("Token uniqueness: PASSED")
print("Card types: PASSED")
print("Initial statuses: PASSED")


# ============================================================
# 11. SAVE FINAL PDF FILES
# ============================================================

print("\nSaving final PDF files...")

for filename, pdf_data in pdf_outputs.items():

    output_path = BASE_DIR / filename

    with open(output_path, "wb") as file:
        file.write(pdf_data)

    print(f"Created: {filename}")


# ============================================================
# 12. SAVE CSV BACKUP
# ============================================================

print("\nSaving CSV backup...")

with open(
    CSV_FILE,
    "w",
    newline="",
    encoding="utf-8-sig"
) as file:

    csv_writer = csv.DictWriter(
        file,
        fieldnames=[
            "card_number",
            "token",
            "card_type"
        ]
    )

    csv_writer.writeheader()
    csv_writer.writerows(cards)

print(f"CSV backup: {CSV_FILE.name}")


# ============================================================
# 13. FINAL REPORT
# ============================================================

print("\n")
print("=" * 55)
print("ALL GRADUATION CARDS GENERATED SUCCESSFULLY")
print("=" * 55)

for item in CARD_TYPES:

    print(
        f"{item['type']:8} : "
        f"{item['count']} cards | "
        f"{item['start']:03d}-"
        f"{item['start'] + item['count'] - 1:03d}"
    )

print("-" * 55)
print(f"TOTAL CARDS : {TOTAL_CARDS}")
print(f"QR X        : {QR_X}")
print(f"QR Y        : {QR_Y}")
print(f"QR SIZE     : {QR_SIZE}")
print("STATUS      : UNUSED")
print("SUPABASE    : VERIFIED")
print("TOKENS      : UNIQUE")
print("PDF FILES   : 3")
print("CSV BACKUP  : CREATED")
print("=" * 55)
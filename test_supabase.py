import os
from dotenv import load_dotenv
from supabase import create_client


# تحميل بيانات .env
load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SECRET_KEY")

if not url:
    raise Exception("SUPABASE_URL not found in .env")

if not key:
    raise Exception("SUPABASE_SECRET_KEY not found in .env")


# إنشاء الاتصال
supabase = create_client(url, key)


# اختبار الاتصال بجدول cards
response = (
    supabase
    .table("cards")
    .select("id")
    .limit(1)
    .execute()
)


print("Supabase connection successful!")
print("Cards table is accessible.")
print("Current records:", len(response.data))



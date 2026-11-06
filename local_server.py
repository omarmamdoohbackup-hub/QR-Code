"""
Local Development Server for Graduation QR Security Scanner
Serves security_page/ and handles /api/verify using Supabase and .env
"""

import http.server
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    print("⚠️ WARNING: SUPABASE_URL or SUPABASE_SECRET_KEY not found in .env")

# Initialize Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY) if (SUPABASE_URL and SUPABASE_SECRET_KEY) else None

PORT = 3000
WEB_DIR = Path(__file__).resolve().parent / "security_page"


def get_local_ip():
    """Get the local IP address for phone testing over the same Wi-Fi network."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class SecurityAppHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path.startswith("/api/verify"):
            self.handle_verify()
        else:
            self.send_error(404, "Endpoint not found")

    def handle_verify(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length)

        try:
            body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except Exception:
            self.send_json_response(400, {"valid": False, "reason": "INVALID_JSON"})
            return

        token = body.get("token")
        if not token or not isinstance(token, str):
            self.send_json_response(400, {"valid": False, "reason": "TOKEN_REQUIRED"})
            return

        token = token.strip()

        if not supabase:
            self.send_json_response(500, {"valid": False, "reason": "SERVER_CONFIG_ERROR"})
            return

        try:
            # 1. Query Supabase for card
            query_res = supabase.table("cards").select("id, card_number, token, status, scanned_at").eq("token", token).execute()
            cards = query_res.data or []

            # CASE 3: Not Found
            if not cards:
                self.send_json_response(200, {
                    "valid": False,
                    "reason": "NOT_FOUND"
                })
                return

            card = cards[0]
            def ensure_utc_iso(ts):
                if not ts:
                    return ts
                s = str(ts).strip()
                if not s.endswith("Z") and "+" not in s and "-" not in s[10:]:
                    s = s.replace(" ", "T") + "Z"
                return s

            # CASE 1: Card UNUSED -> Update to USED conditionally
            if card.get("status") == "UNUSED":
                now_iso = datetime.now(timezone.utc).isoformat()
                update_res = (
                    supabase.table("cards")
                    .update({"status": "USED", "scanned_at": now_iso})
                    .eq("token", token)
                    .eq("status", "UNUSED")
                    .execute()
                )

                updated_cards = update_res.data or []
                if updated_cards:
                    updated_card = updated_cards[0]
                    self.send_json_response(200, {
                        "valid": True,
                        "card_number": updated_card.get("card_number"),
                        "status": "USED",
                        "scanned_at": ensure_utc_iso(updated_card.get("scanned_at")) or now_iso
                    })
                    return
                else:
                    # Race condition: already used
                    self.send_json_response(200, {
                        "valid": False,
                        "reason": "ALREADY_USED",
                        "card_number": card.get("card_number"),
                        "scanned_at": ensure_utc_iso(card.get("scanned_at")) or now_iso
                    })
                    return

            # CASE 2: Card Already USED
            self.send_json_response(200, {
                "valid": False,
                "reason": "ALREADY_USED",
                "card_number": card.get("card_number"),
                "scanned_at": ensure_utc_iso(card.get("scanned_at"))
            })

        except Exception as err:
            print(f"Database error during verification: {err}")
            self.send_json_response(500, {
                "valid": False,
                "reason": "INTERNAL_ERROR",
                "message": str(err)
            })

    def send_json_response(self, status_code, data):
        response_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)


def run_server():
    server_address = ("0.0.0.0", PORT)
    httpd = http.server.ThreadingHTTPServer(server_address, SecurityAppHandler)
    local_ip = get_local_ip()

    print()
    print("================================================================")
    print("Graduation Security QR Scanner - Local Server Running")
    print("================================================================")
    print(f"Local (PC):         http://localhost:{PORT}")
    print(f"Phone (Same Wi-Fi): http://{local_ip}:{PORT}")
    print("================================================================")
    print("Press Ctrl+C to stop the server.\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()


if __name__ == "__main__":
    run_server()

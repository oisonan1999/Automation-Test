# setup_login.py
import os
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()

def login_and_save_state():
    with sync_playwright() as p:
        # Mở trình duyệt có giao diện để bạn thao tác
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        url = os.getenv("WEB_URL")
        print(f"--- Đang mở: {url} ---")
        page.goto(url)

        print("\n" + "="*50)
        print("⚠️  HÀNH ĐỘNG CỦA BẠN:")
        print("1. Trình duyệt đã mở. Hãy bấm vào nút 'Login with Google'.")
        print("2. Điền email, password, xác thực 2 bước trên trình duyệt đó.")
        print("3. Đợi đến khi vào được trang Dashboard chính của The Brick.")
        print("4. Quay lại đây và bấm phím ENTER để lưu cookie.")
        print("="*50 + "\n")

        # Treo script chờ bạn bấm Enter ở Terminal
        input("👉 Đã Login xong? Bấm ENTER tại đây để lưu lại cookie...")

        # Lưu trạng thái vào file auth.json
        context.storage_state(path="auth.json")
        print("✅ Đã lưu file 'auth.json'. Các lần sau AI sẽ tự động đăng nhập!")

        browser.close()

if __name__ == "__main__":
    login_and_save_state()
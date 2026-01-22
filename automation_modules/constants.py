# automation_modules/constants.py
import os

# Định nghĩa đường dẫn Download
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")

# Đảm bảo thư mục tồn tại
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)
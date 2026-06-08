#!/bin/bash

# Tạo thư mục chứa profile riêng cho Bot để không ảnh hưởng Chrome chính của bạn
mkdir -p brave_profile

# Đường dẫn Brave trên Windows (Git Bash/WSL)
BRAVE="/c/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe"

# Mở Brave với cổng Debug 9222 và Profile riêng
"$BRAVE" \
  --remote-debugging-port=9222 \
  --user-data-dir="$(pwd)/brave_profile" \
  --no-first-run \
  --no-default-browser-check

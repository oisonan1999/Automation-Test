#!/bin/bash

# Tạo thư mục chứa profile riêng cho Bot để không ảnh hưởng Chrome chính của bạn
mkdir -p chrome_profile

# Đường dẫn Chrome trên macOS
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Mở Chrome với cổng Debug 9222 và Profile riêng
"$CHROME" \
  --remote-debugging-port=9222 \
  --user-data-dir="$(pwd)/chrome_profile" \
  --no-first-run \
  --no-default-browser-check
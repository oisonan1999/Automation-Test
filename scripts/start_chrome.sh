#!/bin/bash

# Tạo một thư mục cố định cho Profile (Ví dụ: tại /tmp/chrome-debug hoặc trong thư mục dự án)
PROFILE_DIR="/tmp/chrome-debug-profile"
mkdir -p "$PROFILE_DIR"

echo "🚀 Starting Chrome with Remote Debugging on Port 9222..."
echo "📂 User Data Dir: $PROFILE_DIR"

"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --no-first-run \
  --no-default-browser-check \
  --user-data-dir="$PROFILE_DIR"
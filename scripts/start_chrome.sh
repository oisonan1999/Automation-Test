#!/bin/bash

# Tạo một thư mục cố định cho Profile (Ví dụ: tại /tmp/chrome-debug hoặc trong thư mục dự án)
PROFILE_DIR="/tmp/brave-debug-profile"
mkdir -p "$PROFILE_DIR"

echo "🚀 Starting Brave with Remote Debugging on Port 9222..."
echo "📂 User Data Dir: $PROFILE_DIR"

"/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \
  --remote-debugging-port=9222 \
  --no-first-run \
  --no-default-browser-check \
  --user-data-dir="$PROFILE_DIR"
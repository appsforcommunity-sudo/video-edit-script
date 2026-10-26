#!/usr/bin/env bash
# One-time setup inside a GitHub Codespace (or any Linux box).
set -e
command -v ffmpeg >/dev/null || (sudo apt-get update && sudo apt-get install -y ffmpeg)
pip install -e . -r requirements-dev.txt
echo "Ready. Try: vedit --help"

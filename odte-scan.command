#!/bin/bash
# Double-click launcher for macOS Terminal.
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
/usr/bin/env python3 "$DIR/scanner.py" --live
echo
read -r -p "Press Enter to close..."

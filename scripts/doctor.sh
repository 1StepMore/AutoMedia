#!/usr/bin/env bash
# AutoMedia dependency checker.
# Verifies that all external tools required by the pipeline are available.
# Usage: bash scripts/doctor.sh
set -euo pipefail

echo "=== AutoMedia Dependency Check ==="
echo ""

check_tool() {
    local name="$1"
    local cmd="$2"
    local version_arg="${3:---version}"

    if command -v "$cmd" &>/dev/null; then
        local version
        version=$("$cmd" "$version_arg" 2>&1 | head -1)
        echo "  ✓ $name  $version"
        return 0
    else
        echo "  ✗ $name  not found"
        return 1
    fi
}

MISSING=0

check_tool "Python"       "python3"
check_tool "FFmpeg"       "ffmpeg"
check_tool "Bun"          "bun"
check_tool "Whisper"      "whisper"
check_tool "edge-tts"     "edge-tts" ""
check_tool "ComfyUI"      "comfyui" ""
check_tool "Chrome/Chromium" "google-chrome" "--version"

echo ""
if [ "$MISSING" -gt 0 ]; then
    echo "⚠  $MISSING tool(s) missing — corresponding pipeline gates will fail at runtime."
else
    echo "✓ All dependencies satisfied."
fi
exit "$MISSING"

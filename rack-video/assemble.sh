#!/bin/bash
# Assembles the full promo draft:
#   1. prep the UI capture (seekable texture + 16:9 crop)
#   2. render the 3D shot with the UI on the rack screen
#   3. crossfade 3D -> full-screen UI -> stat card
# Usage: ./assemble.sh [skip-render]
set -euo pipefail
cd "$(dirname "$0")"

BOOT=15.5        # film.html T_BOOT: screen turns on, UI video t=0
XFADE_AT=19.2    # 3D time where we blend to the full-screen UI
XFADE_DUR=0.8

if [ ! -f out/ui_tex.mp4 ] || [ out/ui.webm -nt out/ui_tex.mp4 ]; then
  # dense keyframes so per-frame currentTime seeks stay fast and exact
  ffmpeg -y -v error -i out/ui.webm -c:v libx264 -g 15 -crf 18 \
    -pix_fmt yuv420p out/ui_tex.mp4
  ffmpeg -y -v error -i out/ui.webm -vf "crop=1920:1080:0:60" -c:v libx264 \
    -crf 18 -pix_fmt yuv420p out/ui_crop.mp4
fi

if [ "${1:-}" != "skip-render" ]; then
  UI_VIDEO=/rack-video/out/ui_tex.mp4 node render.mjs draft
fi

UI_DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 out/ui_crop.mp4)
TRIM=$(echo "$XFADE_AT - $BOOT" | bc)                 # UI time at the blend point
B_DUR=$(echo "$UI_DUR - $TRIM" | bc)
AB_DUR=$(echo "$XFADE_AT + $B_DUR" | bc)
XF2=$(echo "$AB_DUR - 0.7" | bc)

ffmpeg -y -v error \
  -i out/draft.mp4 \
  -ss "$TRIM" -i out/ui_crop.mp4 \
  -i out/statcard.mp4 \
  -filter_complex "\
    [1:v]setpts=PTS-STARTPTS[ui]; \
    [0:v][ui]xfade=transition=fade:duration=${XFADE_DUR}:offset=${XFADE_AT}[ab]; \
    [ab][2:v]xfade=transition=fade:duration=0.7:offset=${XF2},fade=t=out:st=$(echo "$XF2 + 7.5 - 0.6" | bc):d=0.6[v]" \
  -map "[v]" -c:v libx264 -preset slow -crf 17 -pix_fmt yuv420p \
  -movflags +faststart out/nowva_promo_draft.mp4

ffprobe -v error -show_entries format=duration -of csv=p=0 out/nowva_promo_draft.mp4
echo "out/nowva_promo_draft.mp4"

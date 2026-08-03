#!/bin/bash
# Assembles the promo from the real-footage edit:
#   1. render the 3D rack shot with out/ui_tex.mp4 playing on the screen
#   2. crossfade 3D -> full-screen UI edit -> stat card
#   3. mux Nova's voice track (UI t=0 lands at output t=BOOT)
# Usage: ./assemble.sh [draft|final] [skip-render]
set -euo pipefail
cd "$(dirname "$0")"

MODE=${1:-draft}
FPS=$([ "$MODE" = final ] && echo 60 || echo 30)
BOOT=9.8         # film.html T_BOOT: screen turns on, UI video t=0
XFADE_AT=12.4    # 3D time where we blend to the full-screen UI
XFADE_DUR=0.8

if [ "${2:-}" != "skip-render" ]; then
  UI_VIDEO=/rack-video/out/ui_tex.mp4 node render.mjs "$MODE"
fi

UI_DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 out/ui_edit.mp4)
STAT_DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 out/statcard.mp4)
TRIM=$(echo "$XFADE_AT - $BOOT" | bc)                 # UI time at the blend point
B_DUR=$(echo "$UI_DUR - $TRIM" | bc)
XF2=$(echo "$XFADE_AT + $B_DUR - 0.7" | bc)
FADE_ST=$(echo "$XF2 + $STAT_DUR - 0.9" | bc)
DELAY_MS=$(echo "$BOOT * 1000 / 1" | bc)

ffmpeg -y -v error \
  -i "out/${MODE}.mp4" \
  -ss "$TRIM" -i out/ui_edit.mp4 \
  -i out/statcard.mp4 \
  -i out/ui_edit.mp4 \
  -filter_complex "\
    [0:v]settb=AVTB[base]; \
    [1:v]setpts=PTS-STARTPTS,fps=${FPS},settb=AVTB[ui]; \
    [2:v]fps=${FPS},settb=AVTB[sc]; \
    [base][ui]xfade=transition=fade:duration=${XFADE_DUR}:offset=${XFADE_AT}[ab]; \
    [ab][sc]xfade=transition=fadeblack:duration=0.7:offset=${XF2},fade=t=out:st=${FADE_ST}:d=0.8[v]; \
    [3:a]adelay=${DELAY_MS}|${DELAY_MS},apad,afade=t=out:st=${FADE_ST}:d=0.8[a]" \
  -map "[v]" -map "[a]" -shortest \
  -c:v libx264 -preset slow -crf 17 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -movflags +faststart \
  "out/nowva_promo_${MODE}.mp4"

ffprobe -v error -show_entries format=duration -of csv=p=0 "out/nowva_promo_${MODE}.mp4"
echo "out/nowva_promo_${MODE}.mp4"

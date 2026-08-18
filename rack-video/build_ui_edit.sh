#!/bin/bash
# Builds the SILENT real-footage UI edit for the promo (v12):
#   out/ui_edit.mp4  1920x1080@30, video only — every section change animated
#   out/ui_tex.mp4   1920x1200 16:10 pad, dense keyframes, for the 3D screen texture
#
# Story: boot -> deterministic menu with Quick Exercise selection animation ->
# setup card fill (2/5/BW/20s LOCKED IN) -> explainer card -> the user's real
# (flawed) assessment rep -> choreographer stance fix -> explainer -> workout
# reps + "A little wider." cues -> explainer -> rep 5 -> SET 1 REPORT during
# rest -> three set-2 reps -> "Strong work." session recap.
# Transitions: smoothleft pushes between scenes, fades around explainer cards
# and within same-scene montages. No hard cuts anywhere.
set -euo pipefail
cd "$(dirname "$0")"

REC="../user_test_runs/2026-08-03_19-48-24/screen_recording.mp4"
CAP="out/setup_cap.mp4"
FS="crop=2864:1611:0:186"                 # full-screen page content, chrome-free
BOOT="crop=2528:1422:176:238"             # windowed boot: inside window, no chrome
CURWIPE="delogo=x=1215:y=870:w=90:h=95"   # static cursor on the boot screen (post-scale)
TAIL="fps=30,setsar=1,format=yuv420p,settb=AVTB"

# FPS-text blur patches (post-FS-crop coords). Assessment view has no covering
# HUD pill, and its FPS text sits lower — use a taller patch there.
wp()  { echo "split[wa$1][wb$1];[wb$1]crop=222:56:2:1,gblur=sigma=25[wp$1];[wa$1][wp$1]overlay=2:1"; }
wpa() { echo "split[wa$1][wb$1];[wb$1]crop=260:80:2:1,gblur=sigma=28[wp$1];[wa$1][wp$1]overlay=2:1"; }

ffmpeg -y -v error \
  -ss 5.5    -t 2.4  -i "$REC" \
  -ss 1.2    -t 4.2  -i "$CAP" \
  -ss 9.3    -t 4.0  -i "$CAP" \
  -i out/card_a.mp4 \
  -ss 103.8  -t 2.8  -i "$REC" \
  -ss 113.9  -t 5.1  -i "$REC" \
  -i out/card_b.mp4 \
  -ss 166.5  -t 3.1  -i "$REC" \
  -ss 179.0  -t 3.0  -i "$REC" \
  -ss 198.4  -t 4.6  -i "$REC" \
  -i out/card_c.mp4 \
  -ss 203.9  -t 1.4  -i "$REC" \
  -ss 205.45 -t 7.3  -i "$REC" \
  -ss 238.0  -t 2.4  -i "$REC" \
  -ss 241.5  -t 2.4  -i "$REC" \
  -ss 244.3  -t 2.4  -i "$REC" \
  -ss 248.0  -t 5.0  -i "$REC" \
  -filter_complex "\
    [0:v]$BOOT,scale=1920:1080:flags=lanczos,$CURWIPE,$TAIL[v0]; \
    [1:v]crop=1920:1080:0:60,$TAIL[v1]; \
    [2:v]crop=1920:1080:0:60,$TAIL[v2]; \
    [3:v]$TAIL[v3]; \
    [4:v]$FS,$(wpa 4),scale=1920:1080:flags=lanczos,$TAIL[v4]; \
    [5:v]$FS,scale=1920:1080:flags=lanczos,$TAIL[v5]; \
    [6:v]$TAIL[v6]; \
    [7:v]$FS,$(wp 7),scale=1920:1080:flags=lanczos,$TAIL[v7]; \
    [8:v]$FS,$(wp 8),scale=1920:1080:flags=lanczos,$TAIL[v8]; \
    [9:v]$FS,$(wp 9),scale=1920:1080:flags=lanczos,$TAIL[v9]; \
    [10:v]$TAIL[v10]; \
    [11:v]$FS,$(wp 11),scale=1920:1080:flags=lanczos,$TAIL[v11]; \
    [12:v]$FS,scale=1920:1080:flags=lanczos,$TAIL[v12]; \
    [13:v]$FS,$(wp 13),scale=1920:1080:flags=lanczos,$TAIL[v13]; \
    [14:v]$FS,$(wp 14),scale=1920:1080:flags=lanczos,$TAIL[v14]; \
    [15:v]$FS,$(wp 15),scale=1920:1080:flags=lanczos,$TAIL[v15]; \
    [16:v]$FS,scale=1920:1080:flags=lanczos,$TAIL[v16]; \
    [v0][v1]xfade=transition=fade:duration=0.3:offset=2.1,settb=AVTB[x1]; \
    [x1][v2]xfade=transition=fade:duration=0.35:offset=5.95,settb=AVTB[x2]; \
    [x2][v3]xfade=transition=fade:duration=0.4:offset=9.55,settb=AVTB[x3]; \
    [x3][v4]xfade=transition=smoothleft:duration=0.5:offset=11.48,settb=AVTB[x4]; \
    [x4][v5]xfade=transition=smoothleft:duration=0.5:offset=13.78,settb=AVTB[x5]; \
    [x5][v6]xfade=transition=fade:duration=0.4:offset=18.48,settb=AVTB[x6]; \
    [x6][v7]xfade=transition=smoothleft:duration=0.5:offset=20.41,settb=AVTB[x7]; \
    [x7][v8]xfade=transition=fade:duration=0.25:offset=23.26,settb=AVTB[x8]; \
    [x8][v9]xfade=transition=fade:duration=0.25:offset=26.01,settb=AVTB[x9]; \
    [x9][v10]xfade=transition=fade:duration=0.4:offset=30.21,settb=AVTB[x10]; \
    [x10][v11]xfade=transition=smoothleft:duration=0.5:offset=32.14,settb=AVTB[x11]; \
    [x11][v12]xfade=transition=fade:duration=0.3:offset=33.24,settb=AVTB[x12]; \
    [x12][v13]xfade=transition=smoothleft:duration=0.5:offset=40.04,settb=AVTB[x13]; \
    [x13][v14]xfade=transition=fade:duration=0.25:offset=42.19,settb=AVTB[x14]; \
    [x14][v15]xfade=transition=fade:duration=0.25:offset=44.34,settb=AVTB[x15]; \
    [x15][v16]xfade=transition=fade:duration=0.45:offset=46.29,settb=AVTB[vc]" \
  -map "[vc]" -an \
  -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p \
  out/ui_edit.mp4

ffmpeg -y -v error -i out/ui_edit.mp4 \
  -vf "pad=1920:1200:0:60:color=black" -an \
  -c:v libx264 -g 15 -crf 18 -pix_fmt yuv420p \
  out/ui_tex.mp4

ffprobe -v error -show_entries format=duration -of csv=p=0 out/ui_edit.mp4
echo "out/ui_edit.mp4 + out/ui_tex.mp4"

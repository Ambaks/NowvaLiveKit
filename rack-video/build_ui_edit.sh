#!/bin/bash
# Builds the real-footage UI edit for the promo from the full demo recording:
#   out/ui_edit.mp4  1920x1080@30 + Nova voice track (two-pass loudnorm, gap-conformed)
#   out/ui_tex.mp4   1920x1200 16:10 pad, dense keyframes, for the 3D screen texture
# Beat times were frame-mapped from the 2026-08-03 19-48-24 session; audio cuts
# all land inside digital-silence gaps of the TTS stream (0:a:1).
# Crop is 2864x1611 (not 2880x1620): drops a baked-in cursor sliver at the
# right edge and the top rows of the dev FPS overlay without clipping any HUD.
# The remaining FPS text on live-camera beats is hidden by overlaying a clean
# wall patch sampled beside it (delogo interpolation left visible streaks).
set -euo pipefail
cd "$(dirname "$0")"

REC="../user_test_runs/2026-08-03_19-48-24/screen_recording.mp4"
FS="crop=2864:1611:0:186"                 # full-screen page content, chrome-free
BOOT="crop=2528:1422:176:238"             # windowed boot: inside window, no chrome
CURWIPE="delogo=x=1215:y=870:w=90:h=95"   # static cursor on the boot screen (post-scale)
# live-camera beats: dissolve the dev FPS text into the wall with an in-place blur
WALLPATCH="split[wa][wb];[wb]crop=222:56:2:1,gblur=sigma=25[wp];[wa][wp]overlay=2:1"
TAIL="fps=30,setsar=1,format=yuv420p,settb=AVTB"
AUD="aresample=48000:async=1:first_pts=0,asetpts=PTS-STARTPTS,aformat=sample_fmts=fltp:channel_layouts=stereo"

# beats: 0 boot 5.5+2.4 | 1 menu 40.3+2.4 | 2 setup 68.7+2.4 | 3 demo 113.9+4.7 (voice)
#        4 first_rep 166.5+3.1 (spoken "Chest up!", REPS 0->1) | 5 rep2 179+3
#        6 cue 198.5+3.5 (voice) | 7 recap 203.9+8.6 (rep 5, SET 1 REPORT + spoken summary)
#        8 deep 241.6+2.3 | 9 strong 248.2+4.2 (voice)
# boot->menu gets a 0.3s crossfade; the rest hard-cut.
# audio: beats 0-2 are silence (6.9s = 4.5 xfaded + 2.4), voice from the demo beat on.
build() {
  ffmpeg -y -v error \
    -ss 5.5   -t 2.4 -i "$REC" \
    -ss 40.3  -t 2.4 -i "$REC" \
    -ss 68.7  -t 2.4 -i "$REC" \
    -ss 113.9 -t 4.7 -i "$REC" \
    -ss 166.5 -t 3.1 -i "$REC" \
    -ss 179.0 -t 3.0 -i "$REC" \
    -ss 198.5 -t 3.5 -i "$REC" \
    -ss 203.9 -t 8.6 -i "$REC" \
    -ss 241.6 -t 2.3 -i "$REC" \
    -ss 248.2 -t 4.2 -i "$REC" \
    -filter_complex "\
      [0:v]$BOOT,scale=1920:1080:flags=lanczos,$CURWIPE,$TAIL[v0]; \
      [1:v]$FS,scale=1920:1080:flags=lanczos,$TAIL[v1]; \
      [2:v]$FS,scale=1920:1080:flags=lanczos,$TAIL[v2]; \
      [3:v]$FS,scale=1920:1080:flags=lanczos,$TAIL[v3]; \
      [4:v]$FS,$WALLPATCH,scale=1920:1080:flags=lanczos,$TAIL[v4]; \
      [5:v]$FS,$WALLPATCH,scale=1920:1080:flags=lanczos,$TAIL[v5]; \
      [6:v]$FS,$WALLPATCH,scale=1920:1080:flags=lanczos,$TAIL[v6]; \
      [7:v]$FS,$WALLPATCH,scale=1920:1080:flags=lanczos,$TAIL[v7]; \
      [8:v]$FS,$WALLPATCH,scale=1920:1080:flags=lanczos,$TAIL[v8]; \
      [9:v]$FS,scale=1920:1080:flags=lanczos,$TAIL[v9]; \
      [v0][v1]xfade=transition=fade:duration=0.3:offset=2.1,settb=AVTB[vx]; \
      [vx][v2][v3][v4][v5][v6][v7][v8][v9]concat=n=9:v=1:a=0[vc]; \
      anullsrc=r=48000:cl=stereo:d=6.9,aformat=sample_fmts=fltp:channel_layouts=stereo[sil]; \
      [3:a:1]$AUD[a3]; [4:a:1]$AUD[a4]; [5:a:1]$AUD[a5]; [6:a:1]$AUD[a6]; \
      [7:a:1]$AUD[a7]; [8:a:1]$AUD[a8]; [9:a:1]$AUD[a9]; \
      [sil][a3][a4][a5][a6][a7][a8][a9]concat=n=8:v=0:a=1[ac]" \
    "$@"
}

# pass 1: encode video once, dump the raw voice mix for measurement
build -map "[vc]" -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p out/ui_video.mp4 \
      -map "[ac]" -c:a pcm_s16le out/ui_audio_raw.wav

# measure once, then apply loudnorm as a single static gain (linear mode):
# dynamic one-pass loudnorm pumped 9-13dB between bursts and clipped the long
# set-summary narration.
MEAS=$(ffmpeg -hide_banner -i out/ui_audio_raw.wav \
  -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json -f null - 2>&1 | grep -A 14 '^{')
j() { echo "$MEAS" | grep "\"$1\"" | sed 's/.*: *"//; s/".*//'; }
LN="loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=$(j input_i):measured_TP=$(j input_tp)"
LN="$LN:measured_LRA=$(j input_lra):measured_thresh=$(j input_thresh)"
LN="$LN:offset=$(j target_offset):linear=true"

# this session's live Cartesia render came out ~5% above Nova's usual register
# (F0 187 Hz vs 160-180 Hz in the cached cue renders) — pitch down, keep tempo
PITCH="asetrate=45600,aresample=48000,atempo=1.0526315789"

ffmpeg -y -v error -i out/ui_video.mp4 -i out/ui_audio_raw.wav \
  -map 0:v -map 1:a -c:v copy \
  -af "$PITCH,$LN" -c:a aac -b:a 192k -ar 48000 \
  out/ui_edit.mp4

ffmpeg -y -v error -i out/ui_edit.mp4 \
  -vf "pad=1920:1200:0:60:color=black" -an \
  -c:v libx264 -g 15 -crf 18 -pix_fmt yuv420p \
  out/ui_tex.mp4

ffprobe -v error -show_entries format=duration -of csv=p=0 out/ui_edit.mp4
echo "out/ui_edit.mp4 + out/ui_tex.mp4"

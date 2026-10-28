#!/usr/bin/env python3
"""Add a local text-to-speech narration (and optional background music) to a take.

    .venv/bin/python video/narrate.py video/plate/marks.json in.mp4 out.mp4 --lines video/lines_plate.json
    .venv/bin/python video/narrate.py video/tour/marks.json in.mp4 out.mp4 --music video/audio/music.flac

Sentences come from `--lines` (a JSON list, one per mark, null = silent) or from the "line" field of each mark
(takes that use `Take.scene`). Each sentence is spoken by ComfyUI (tts.py, one cloned narrator voice), placed at
the frame where its scene starts and mixed onto the video. A sentence that is longer than its scene is not cut:
the next one starts after it. Audio is cached per text+voice+seed under video/audio/.

--music: a track mixed in underneath at low volume (ducked further while the narrator speaks), faded in and out.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tts

AUDIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio")


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(out.stdout.strip())


def clip(line, voice=tts.NARRATOR, seed=1):
    """(path, seconds) of the spoken sentence, generated on first use."""
    os.makedirs(AUDIO, exist_ok=True)
    key = hashlib.sha1(f"clone2|{line}|{voice}|{seed}".encode()).hexdigest()[:12]
    path = os.path.join(AUDIO, f"{key}.flac")
    if not os.path.exists(path):
        print("TTS:", line, flush=True)
        tts.synthesize(line, path, voice, seed)
    return path, duration(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("marks")
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--lines")
    ap.add_argument("--music")
    ap.add_argument("--music-volume", type=float, default=0.22, help="linear gain of the music (0.22 is about -13 dB)")
    ap.add_argument("--voice", default=tts.NARRATOR)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    marks = json.load(open(a.marks))
    lines = json.load(open(a.lines)) if a.lines else [m.get("line") for m in marks["marks"]]
    assert len(lines) == len(marks["marks"]), f"{len(lines)} lines but {len(marks['marks'])} marks"
    clips, cursor = [], 0.0
    for m, line in zip(marks["marks"], lines):
        if not line:
            continue
        path, dur = clip(line, a.voice, a.seed)
        start = max(m["frame"] / marks["fps"], cursor)      # never overlap the previous sentence
        clips.append((path, start))
        cursor = start + dur + 0.25
    vdur = marks["frames"] / marks["fps"]
    if cursor > vdur:
        print(f"Warning: narration runs {cursor - vdur:.1f} s past the end of the video and is cut: lengthen the last scene")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", a.video]
    for p, _ in clips:
        cmd += ["-i", p]
    if a.music:
        cmd += ["-i", a.music]
    filt = "".join(f"[{i + 1}:a]adelay={int(st * 1000)}|{int(st * 1000)}[a{i}];" for i, (_, st) in enumerate(clips))
    filt += "".join(f"[a{i}]" for i in range(len(clips))) + f"amix=inputs={len(clips)}:normalize=0[voice];"
    if a.music:
        mi = len(clips) + 1
        filt += (f"[{mi}:a]atrim=0:{vdur:.2f},afade=t=in:d=2,afade=t=out:st={max(vdur - 4, 0):.2f}:d=4,volume={a.music_volume}[mus];"
                 "[voice]asplit[v1][v2];[mus][v2]sidechaincompress=threshold=0.02:ratio=6:attack=40:release=500[duck];"
                 "[v1][duck]amix=inputs=2:normalize=0,loudnorm=I=-16:TP=-1.5,apad[aout]")
    else:
        filt += "[voice]loudnorm=I=-16:TP=-1.5,apad[aout]"
    cmd += ["-filter_complex", filt, "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", f"{vdur:.3f}", os.path.abspath(os.path.expanduser(a.out))]
    subprocess.run(cmd, check=True)
    print("Saved", a.out)


if __name__ == "__main__":
    main()

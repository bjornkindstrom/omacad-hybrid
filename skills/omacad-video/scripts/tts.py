#!/usr/bin/env python3
"""Local text-to-speech through ComfyUI (Qwen3-TTS, nothing leaves the machine). The voice is designed once
from a description (VoiceDesign) and every sentence is then a clone of that one clip, so it is the same person.

    .venv/bin/python video/tts.py "Text to say" out.flac                       # default narrator voice
    .venv/bin/python video/tts.py --voice "A warm female voice..." --seed 7 "Text" out.flac

ComfyUI must be running on 127.0.0.1:8188 (the Comfy desktop app). Same voice description + same seed
gives (nearly) the same voice, so keep both fixed for a whole video. Output is whatever extension you give
(flac/mp3/wav; converted with ffmpeg).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request

SERVER = os.environ.get("COMFY", "http://127.0.0.1:8188")
NARRATOR = ("A calm, clear male narrator in his thirties with a warm, friendly tone. Natural pace, "
            "relaxed and confident, like a software tutorial on YouTube.")


def _post(path, data):
    req = urllib.request.Request(SERVER + path, json.dumps(data).encode(), {"Content-Type": "application/json"})
    body = urllib.request.urlopen(req).read()
    return json.loads(body) if body.strip() else {}


def _get(path):
    return urllib.request.urlopen(SERVER + path).read()


def synthesize(text, out, voice=NARRATOR, seed=1, language="English", timeout=600, tries=4):
    """Retries after freeing ComfyUI's GPU memory: on an 8 GB card the model sometimes does not fit on the first try."""
    for k in range(tries):
        try:
            _post("/free", {"unload_models": True, "free_memory": True})
            time.sleep(2)
            return _synthesize(text, out, voice, seed, language, timeout)
        except RuntimeError as e:
            if "out of memory" not in str(e) or k == tries - 1:
                raise
            time.sleep(5)


COMFY_INPUT = os.environ.get("COMFY_INPUT", os.path.expanduser("~/ComfyUI-Shared/input"))
REF_TEXT = ("Welcome to Omacad. Today I will show you how a few simple steps can turn a sketch into a finished part, "
            "with every measurement under your control.")


def _run(graph, out, timeout):
    pid = _post("/prompt", {"prompt": graph})["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < timeout:
        hist = json.loads(_get(f"/history/{pid}"))
        if pid in hist:
            h = hist[pid]
            if h.get("status", {}).get("status_str") == "error":
                raise RuntimeError(json.dumps(h["status"])[:800])
            files = [a for o in h["outputs"].values() for a in o.get("audio", [])]
            if files:
                a = files[0]
                q = urllib.parse.urlencode({"filename": a["filename"], "subfolder": a.get("subfolder", ""), "type": a.get("type", "output")})
                raw = _get("/view?" + q)
                os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
                tmp = out + ".src" + os.path.splitext(a["filename"])[1]
                open(tmp, "wb").write(raw)
                if os.path.splitext(tmp)[1] == os.path.splitext(out)[1]:
                    shutil.move(tmp, out)
                else:
                    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, out], check=True)
                    os.remove(tmp)
                return out
        time.sleep(1)
    raise TimeoutError("ComfyUI did not finish in time")


def reference(voice: str, seed: int, language: str = "English") -> str:
    """The narrator: VoiceDesign speaks REF_TEXT once. Every later line is a clone of this clip, so the voice
    stays the same (VoiceDesign alone invents a slightly different person for every sentence)."""
    import hashlib
    key = hashlib.sha1(f"{voice}|{seed}|{REF_TEXT}".encode()).hexdigest()[:10]
    name = f"omacad_narrator_{key}.flac"
    dest = os.path.join(COMFY_INPUT, name)
    if not os.path.exists(dest):
        graph = {
            "1": {"class_type": "FB_Qwen3TTSVoiceDesign", "inputs": {
                "text": REF_TEXT, "instruct": voice, "model_choice": "1.7B", "device": "auto", "precision": "bf16",
                "language": language, "seed": seed, "max_new_tokens": 1024, "attention": "sdpa", "unload_model_after_generate": True}},
            "2": {"class_type": "SaveAudio", "inputs": {"audio": ["1", 0], "filename_prefix": "audio/omacad_ref"}},
        }
        _run(graph, dest, 600)
    return name


def _synthesize(text: str, out: str, voice: str = NARRATOR, seed: int = 1, language: str = "English", timeout: int = 600) -> str:
    ref = reference(voice, seed, language)
    graph = {
        "0": {"class_type": "LoadAudio", "inputs": {"audio": ref}},
        "1": {"class_type": "FB_Qwen3TTSVoiceClone", "inputs": {
            "target_text": text, "ref_text": REF_TEXT, "model_choice": "1.7B", "device": "auto", "precision": "bf16",
            "language": language, "ref_audio": ["0", 0], "seed": seed, "max_new_tokens": 512, "attention": "sdpa",
            "unload_model_after_generate": True}},
        "2": {"class_type": "SaveAudio", "inputs": {"audio": ["1", 0], "filename_prefix": "audio/omacad_tts"}},
    }
    return _run(graph, out, timeout)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("out")
    ap.add_argument("--voice", default=NARRATOR)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--language", default="English")
    a = ap.parse_args()
    print("Saved", synthesize(a.text, a.out, a.voice, a.seed, a.language))

#!/usr/bin/env python3
"""Local background music through ComfyUI (ACE-Step 1.5 XL, instrumental). Needs the Comfy desktop app running.

    .venv/bin/python video/music.py video/audio/music.flac --seconds 130 --seed 3
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tts

TAGS = ("calm modern instrumental, soft warm synth pads, gentle plucked arpeggio, light steady lo-fi drum groove, "
        "deep round bass, airy and inspiring, techy but friendly, clean production, no vocals")


def generate(out, seconds=130.0, seed=3, tags=TAGS, bpm=100, key="D minor", steps=40):
    g = {
        "104": {"class_type": "UNETLoader", "inputs": {"unet_name": "acestep_v1.5_xl_sft_bf16.safetensors", "weight_dtype": "default"}},
        "106": {"class_type": "VAELoader", "inputs": {"vae_name": "ace_1.5_vae.safetensors"}},
        "105": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "qwen_0.6b_ace15.safetensors", "clip_name2": "qwen_4b_ace15.safetensors", "type": "ace", "device": "default"}},
        "78": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["104", 0], "shift": 3}},
        "94": {"class_type": "TextEncodeAceStepAudio1.5", "inputs": {
            "clip": ["105", 0], "tags": tags, "lyrics": "[Instrumental]", "seed": seed, "bpm": bpm, "duration": float(seconds),
            "timesignature": "4", "language": "en", "keyscale": key, "generate_audio_codes": True, "cfg_scale": 2.0,
            "temperature": 0.85, "top_p": 0.9, "top_k": 0, "min_p": 0.0}},
        "47": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["94", 0]}},
        "98": {"class_type": "EmptyAceStep1.5LatentAudio", "inputs": {"seconds": float(seconds), "batch_size": 1}},
        "3": {"class_type": "KSampler", "inputs": {"model": ["78", 0], "positive": ["94", 0], "negative": ["47", 0], "latent_image": ["98", 0],
                                                  "seed": seed, "steps": steps, "cfg": 7, "sampler_name": "euler", "scheduler": "simple", "denoise": 1}},
        "18": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["3", 0], "vae": ["106", 0]}},
        "110": {"class_type": "SaveAudio", "inputs": {"audio": ["18", 0], "filename_prefix": "audio/omacad_music"}},
    }
    tts._post("/free", {"unload_models": True, "free_memory": True})
    return tts._run(g, out, 3600)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=130.0)
    ap.add_argument("--seed", type=int, default=3)
    a = ap.parse_args()
    print("Saved", generate(a.out, a.seconds, a.seed))

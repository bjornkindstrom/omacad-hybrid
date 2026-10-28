#!/usr/bin/env python3
"""
Omacad 48-Hour Evolution Video:
Showcases all major changes and features implemented in the last 2 days:
1. UI Transformation: Clean Fusion 360 styling, transparent floating overlays (Browser & Inspector), removal of status bar, equal-size ribbon buttons.
2. Section View Hatching: Technical Fusion 360-style diagonal hatching with border & per-body tinting.
3. Move Face to Face: Touch, Flush, Slide assembly alignment with centring.
4. Offset Face on Threads: Curved surface tolerance offset for 3D printed jars, lids & coils.
5. Thread Follows Cylinder & Performance Engine: GPU VBO acceleration & live rebuilds.

Narrated with a clear English female voiceover and backed by ComfyUI lo-fi music.
"""

import os
import sys
import math
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path("/home/kindstrom/Work/omacad")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "video"))

import tts

OUTDIR = ROOT / "video" / "showcase_48h"
OUTDIR.mkdir(parents=True, exist_ok=True)
FRAMES_DIR = OUTDIR / "frames"
FRAMES_DIR.mkdir(parents=True, exist_ok=True)

WIDTH = 1920
HEIGHT = 1080
FPS = 30

FONT_REG = "/usr/share/fonts/liberation/LiberationSans-Regular.ttf"
FONT_BOLD = "/usr/share/fonts/liberation/LiberationSans-Bold.ttf"

f_huge = ImageFont.truetype(FONT_BOLD, 64)
f_h1 = ImageFont.truetype(FONT_BOLD, 46)
f_h2 = ImageFont.truetype(FONT_BOLD, 32)
f_h3 = ImageFont.truetype(FONT_BOLD, 26)
f_body = ImageFont.truetype(FONT_REG, 23)
f_badge = ImageFont.truetype(FONT_BOLD, 19)
f_time = ImageFont.truetype(FONT_BOLD, 22)

BG_COLOR = (11, 13, 21)
CARD_BG = (18, 22, 34, 215)
CARD_BORDER = (55, 68, 98, 240)
ACCENT_ORANGE = (255, 115, 30)
ACCENT_CYAN = (0, 225, 255)
TEXT_WHITE = (245, 248, 255)
TEXT_MUTED = (160, 175, 205)

FEMALE_VOICE = (
    "A calm, clear female narrator in her twenties with a warm, friendly tone. Natural pace, "
    "relaxed and confident, like a high quality software tutorial on YouTube."
)

SCENES = [
    {
        "id": "ui_evolution",
        "tag": "MODERN DESIGN • v0.7.9+",
        "title": "Clean & Modern UI Evolution",
        "badge": "FUSION 360 PARITY",
        "summary": "Full transformation of the interface for maximum viewport canvas and zero clutter.",
        "milestones": [
            ("Floating transparent panels", "Browser and Inspector now float subtly directly above the 3D canvas."),
            ("No status bar", "Status text, sketch status and units are painted into the viewport hud."),
            ("Equal-width ribbon", "Balanced tool buttons and the SOLID/SKETCH selector docked directly in the view."),
            ("Title in titlebar", "Document name and modification state show cleanly at the top.")
        ],
        "image": str(ROOT / "video" / "stills" / "ui_before_after_comparison.png"),
        "image_caption": "Before & After: From docked gray frames to transparent floating modern UI",
        "narration": "Here is the dramatic evolution of the interface over the last two days. Gone are the bulky gray docked panels and bottom status bar. Instead, the model tree and tools float transparently over the viewport for maximum workspace clarity."
    },
    {
        "id": "section_hatching",
        "tag": "VISUAL INSPECTION • v0.7.9.14 - 23",
        "title": "Technical Section Hatching",
        "badge": "TECHNICAL DRAWING",
        "summary": "Cut faces receive authentic diagonal cad hatching with individual body tints.",
        "milestones": [
            ("Fusion 360 style hatching", "Crisp diagonal crosshatching with constant screen density."),
            ("Individual body tint", "Every body in an assembly receives its own distinct tint on the cut face."),
            ("Real-time clipping", "Active tool previews and cuts clip cleanly against the section plane.")
        ],
        "image": str(ROOT / "video" / "stills" / "ui_section_hatching.png"),
        "image_caption": "Technical section hatching with sharp outlines and multi-body tints",
        "narration": "Section view now features technical diagonal hatching with constant screen density, just like Fusion 360. Each solid gets a distinct tint, making it effortless to inspect internal clearances and wall thicknesses."
    },
    {
        "id": "move_f2f",
        "tag": "ASSEMBLY & ALIGNMENT • v0.7.9.42",
        "title": "Move Face to Face",
        "badge": "SMART MATING",
        "summary": "Assemble and align separate bodies with two clicks, without manual measurements.",
        "milestones": [
            ("Touch / Flush / Slide", "Choose whether faces mate, align in the same plane, or slide along the normal."),
            ("Automatic centring", "Centers parts precisely on the target face in a single click."),
            ("Refined Move Gizmo", "Muted, compact rotation rings with angle snapping outside the ring.")
        ],
        "image": str(ROOT / "video" / "stills" / "ui_move_face_to_face.png"),
        "image_caption": "Face to Face: Assemble bodies effortlessly with Touch, Flush, and Slide",
        "narration": "With the new Move Face to Face tool, assembling parts is as simple as clicking two faces. Choose between Touch, Flush, or Slide, with automatic centering directly onto the target."
    },
    {
        "id": "offset_face_threads",
        "tag": "TOLERANCES & 3D PRINT • v0.7.9.21 - 37",
        "title": "Offset Face on Threads",
        "badge": "PERFECT CLEARANCE",
        "summary": "Dial in exact 3D printer tolerances directly on curved coils, threads, and jars.",
        "milestones": [
            ("Curved surface offset", "Easily adjust tolerances on thread flanks, cylinders, and walls."),
            ("Diameter following", "Threads wrapped on a cylinder dynamically follow its diameter changes."),
            ("Isolated body offset", "Offsetting a thread modifies only the target part so caps get true clearance.")
        ],
        "image": str(ROOT / "video" / "stills" / "ui_offset_face_thread.png"),
        "image_caption": "Offset Face on thread flanks for zero-friction 3D printed fit",
        "narration": "Offset Face now works seamlessly on threads and curved surfaces. Enter a point two millimeter clearance to ensure your 3D printed jars, caps, and threaded parts screw together with zero friction."
    },
    {
        "id": "gpu_perf",
        "tag": "CORE ENGINE • v0.7.8.7",
        "title": "GPU Acceleration & Timeline",
        "badge": "EXTREME SPEED",
        "summary": "Hardware acceleration takes over with GPU VBO caching and incremental timeline.",
        "milestones": [
            ("GPU VBO/VAO caching", "Silky smooth 60 FPS viewport orbit and camera navigation."),
            ("Incremental timeline", "Only modified downstream features recompute when editing history."),
            ("Timeline step preview", "Hovering any step highlights exactly what geometry it created.")
        ],
        "image": str(ROOT / "video" / "stills" / "ui_clean_modern_fusion.png"),
        "image_caption": "Hardware-accelerated rendering and incremental parametric timeline",
        "narration": "Under the hood, Omacad now leverages full GPU VBO caching and an incremental timeline. Only modified features recompute, keeping your cad workflow fast, responsive, and fluid."
    }
]

INTRO_TEXT = "Welcome to Omacad. Over the last forty-eight hours, the app has undergone a major transformation, featuring a brand new interface and powerful cad tools."
OUTRO_TEXT = "Experience Omacad on Omarchy Linux. Lightning fast, open source, and built for precision cad design."

def render_intro_frame(progress):
    im = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR + (255,))
    draw = ImageDraw.Draw(im)
    offset = int(progress * 80) % 60
    for x in range(0, WIDTH, 60):
        draw.line([(x + offset, 0), (x + offset, HEIGHT)], fill=(20, 24, 38), width=1)
    for y in range(0, HEIGHT, 60):
        draw.line([(0, y), (WIDTH, y)], fill=(20, 24, 38), width=1)
        
    glow_radius = int(320 + math.sin(progress * math.pi) * 40)
    draw.ellipse([WIDTH//2 - glow_radius, HEIGHT//2 - glow_radius - 40,
                  WIDTH//2 + glow_radius, HEIGHT//2 + glow_radius - 40],
                 fill=(25, 45, 80, 160))
                 
    title_text = "OMACAD"
    bb = draw.textbbox((0, 0), title_text, font=f_huge)
    tw = bb[2] - bb[0]
    draw.text((WIDTH//2 - tw//2, 330), title_text, font=f_huge, fill=ACCENT_ORANGE)
    
    sub1 = "48 HOURS OF RAPID EVOLUTION"
    bb1 = draw.textbbox((0, 0), sub1, font=f_h2)
    tw1 = bb1[2] - bb1[0]
    draw.text((WIDTH//2 - tw1//2, 430), sub1, font=f_h2, fill=TEXT_WHITE)
    
    sub2 = "CLEAN MODERN UI • MOVE FACE-TO-FACE • OFFSET FACE THREADS • GPU CACHING"
    bb2 = draw.textbbox((0, 0), sub2, font=f_h3)
    tw2 = bb2[2] - bb2[0]
    draw.text((WIDTH//2 - tw2//2, 500), sub2, font=f_h3, fill=ACCENT_CYAN)
    
    badges = ["FUSION 360 PARITY", "TRANSPARENT HUD", "150+ COMMITS", "OMARCHY NATIVE"]
    bx_start = WIDTH//2 - 440
    for i, b in enumerate(badges):
        bx = bx_start + i * 230
        by = 640
        draw.rounded_rectangle([bx, by, bx + 205, by + 45], radius=8, fill=(24, 32, 50), outline=(60, 80, 120), width=2)
        bb = draw.textbbox((0, 0), b, font=f_badge)
        bw = bb[2] - bb[0]
        draw.text((bx + (205 - bw)//2, by + 12), b, font=f_badge, fill=(220, 230, 250))
        
    p_bar_w = 600
    p_bar_x = WIDTH//2 - p_bar_w//2
    p_bar_y = 780
    draw.rounded_rectangle([p_bar_x, p_bar_y, p_bar_x + p_bar_w, p_bar_y + 8], radius=4, fill=(35, 45, 70))
    draw.rounded_rectangle([p_bar_x, p_bar_y, p_bar_x + int(p_bar_w * progress), p_bar_y + 8], radius=4, fill=ACCENT_ORANGE)
    
    return im.convert("RGB")


def render_outro_frame(progress):
    im = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR + (255,))
    draw = ImageDraw.Draw(im)
    for x in range(0, WIDTH, 60):
        draw.line([(x, 0), (x, HEIGHT)], fill=(20, 24, 38), width=1)
    for y in range(0, HEIGHT, 60):
        draw.line([(0, y), (WIDTH, y)], fill=(20, 24, 38), width=1)
        
    draw.ellipse([WIDTH//2 - 350, HEIGHT//2 - 350, WIDTH//2 + 350, HEIGHT//2 + 350], fill=(30, 40, 70, 150))
    draw.text((WIDTH//2 - 250, 320), "OMACAD CAD", font=f_huge, fill=ACCENT_ORANGE)
    draw.text((WIDTH//2 - 360, 420), "The Future of 3D CAD on Omarchy Linux", font=f_h1, fill=TEXT_WHITE)
    draw.text((WIDTH//2 - 390, 520), "Speed, precision and parametric control built into your desktop.", font=f_h2, fill=TEXT_MUTED)
    draw.text((WIDTH//2 - 370, 600), "Open the app and explore the full changelog under Help > Changelog", font=f_h3, fill=ACCENT_CYAN)
    return im.convert("RGB")


def render_scene_frame(scene_idx, progress, preloaded_images):
    scene = SCENES[scene_idx]
    im = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR + (255,))
    draw = ImageDraw.Draw(im)
    
    # Background lines
    for y in range(0, HEIGHT, 40):
        draw.line([(0, y), (WIDTH, y)], fill=(16, 20, 32), width=1)
        
    # Top Header Bar
    draw.rectangle([0, 0, WIDTH, 125], fill=(16, 20, 32, 230))
    draw.line([(0, 125), (WIDTH, 125)], fill=(35, 45, 70), width=2)
    
    draw.text((50, 20), "OMACAD", font=f_h1, fill=ACCENT_ORANGE)
    draw.text((270, 32), "LAST 48 HOURS OF CAD PROGRESS", font=f_h3, fill=TEXT_WHITE)
    draw.text((WIDTH - 380, 36), "v0.7.8 → v0.7.9.49", font=f_h3, fill=ACCENT_CYAN)
    
    # Timeline bar
    t_start_x = 70
    t_end_x = WIDTH - 70
    t_y = 95
    step_x = (t_end_x - t_start_x) / (len(SCENES) - 1)
    
    draw.line([(t_start_x, t_y), (t_end_x, t_y)], fill=(40, 50, 75), width=5)
    current_head_x = t_start_x + (scene_idx + progress) * step_x
    current_head_x = min(t_end_x, current_head_x)
    draw.line([(t_start_x, t_y), (current_head_x, t_y)], fill=ACCENT_ORANGE, width=5)
    
    for i, sc in enumerate(SCENES):
        cx = int(t_start_x + i * step_x)
        is_cur = (i == scene_idx)
        is_done = (i < scene_idx)
        node_r = 13 if is_cur else 8
        if is_cur:
            pulse = int(5 * math.sin(progress * math.pi * 2))
            draw.ellipse([cx - node_r - 7 - pulse, t_y - node_r - 7 - pulse,
                          cx + node_r + 7 + pulse, t_y + node_r + 7 + pulse],
                         fill=(255, 115, 30, 80))
            draw.ellipse([cx - node_r, t_y - node_r, cx + node_r, t_y + node_r], fill=ACCENT_ORANGE, outline=(255, 255, 255), width=3)
        elif is_done:
            draw.ellipse([cx - node_r, t_y - node_r, cx + node_r, t_y + node_r], fill=(255, 140, 60), outline=(200, 220, 255), width=2)
        else:
            draw.ellipse([cx - node_r, t_y - node_r, cx + node_r, t_y + node_r], fill=(25, 32, 48), outline=(60, 75, 105), width=2)
            
        d_lbl = f"STEP {i+1}"
        bb = draw.textbbox((0, 0), d_lbl, font=f_time)
        lw = bb[2] - bb[0]
        lbl_col = (255, 255, 255) if is_cur else ((200, 210, 230) if is_done else (100, 115, 140))
        draw.text((cx - lw//2, t_y - 32), d_lbl, font=f_time, fill=lbl_col)
        
    # Left Card
    card_x = 50
    card_y = 150
    card_w = 780
    card_h = HEIGHT - card_y - 40
    
    draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=2)
    
    # Category badge & tag
    draw.rounded_rectangle([card_x + 35, card_y + 30, card_x + 35 + 240, card_y + 65], radius=6, fill=(35, 50, 85), outline=ACCENT_CYAN, width=1)
    draw.text((card_x + 48, card_y + 37), scene["badge"], font=f_badge, fill=ACCENT_CYAN)
    draw.text((card_x + 295, card_y + 36), scene["tag"], font=f_badge, fill=TEXT_MUTED)
    
    # Title & Summary
    draw.text((card_x + 35, card_y + 85), scene["title"], font=f_h1, fill=TEXT_WHITE)
    draw.text((card_x + 35, card_y + 145), scene["summary"], font=f_body, fill=(210, 225, 250))
    draw.line([(card_x + 35, card_y + 190), (card_x + card_w - 35, card_y + 190)], fill=(45, 58, 85), width=2)
    
    # Milestones
    item_y = card_y + 215
    for m_idx, (m_title, m_desc) in enumerate(scene["milestones"]):
        draw.ellipse([card_x + 35, item_y + 7, card_x + 49, item_y + 21], fill=ACCENT_ORANGE)
        draw.text((card_x + 60, item_y), m_title, font=f_h3, fill=TEXT_WHITE)
        
        words = m_desc.split(" ")
        line = ""
        desc_y = item_y + 34
        for w in words:
            test_line = line + (" " if line else "") + w
            bb = draw.textbbox((0, 0), test_line, font=f_body)
            if (bb[2] - bb[0]) > (card_w - 110):
                draw.text((card_x + 60, desc_y), line, font=f_body, fill=TEXT_MUTED)
                desc_y += 28
                line = w
            else:
                line = test_line
        if line:
            draw.text((card_x + 60, desc_y), line, font=f_body, fill=TEXT_MUTED)
            desc_y += 36
        item_y = desc_y + 8
        
    # Right Showcase: Ken-Burns image
    shot_x = 870
    shot_y = 150
    shot_w = WIDTH - shot_x - 50
    shot_h = HEIGHT - shot_y - 40
    
    draw.rounded_rectangle([shot_x, shot_y, shot_x + shot_w, shot_y + shot_h], radius=16, fill=(18, 22, 34), outline=CARD_BORDER, width=2)
    draw.rounded_rectangle([shot_x + 30, shot_y + 25, shot_x + 220, shot_y + 60], radius=6, fill=(28, 38, 60), outline=(60, 80, 120), width=1)
    draw.text((shot_x + 45, shot_y + 32), "LIVE APP CAPTURE", font=f_badge, fill=ACCENT_ORANGE)
    draw.text((shot_x + 240, shot_y + 33), scene["image_caption"], font=f_h3, fill=TEXT_WHITE)
    
    vp_x = shot_x + 30
    vp_y = shot_y + 80
    vp_w = shot_w - 60
    vp_h = shot_h - 110
    
    s_path = scene["image"]
    if s_path in preloaded_images:
        src_img = preloaded_images[s_path]
        zoom = 1.0 + 0.06 * math.sin(progress * math.pi)
        drift_x = math.sin(progress * math.pi) * 12
        drift_y = math.cos(progress * math.pi) * 8
        
        aspect_src = src_img.width / src_img.height
        aspect_dst = vp_w / vp_h
        if aspect_src > aspect_dst:
            new_h = int(vp_h * zoom)
            new_w = int(new_h * aspect_src)
        else:
            new_w = int(vp_w * zoom)
            new_h = int(new_w / aspect_src)
            
        scaled = src_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        crop_x = int((new_w - vp_w) / 2 + drift_x)
        crop_y = int((new_h - vp_h) / 2 + drift_y)
        crop_x = max(0, min(new_w - vp_w, crop_x))
        crop_y = max(0, min(new_h - vp_h, crop_y))
        cropped = scaled.crop((crop_x, crop_y, crop_x + vp_w, crop_y + vp_h))
        im.paste(cropped, (vp_x, vp_y))
        draw.rounded_rectangle([vp_x, vp_y, vp_x + vp_w, vp_y + vp_h], radius=8, outline=(80, 110, 160), width=2)
        
    return im.convert("RGB")


def main():
    print("Pre-synthesizing voiceovers with ComfyUI Qwen3-TTS (English female, 'cad' not 'C-A-D')...")
    audio_dir = OUTDIR / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    
    durations = {}
    
    # 1. Intro voice
    intro_audio = audio_dir / "intro.flac"
    tts.synthesize(INTRO_TEXT, str(intro_audio), voice=FEMALE_VOICE, seed=77, language="English")
    durations["intro"] = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(intro_audio)
    ]).strip())
    print(f"Intro duration: {durations['intro']:.2f}s")
    
    # 2. Scene voices
    for sc in SCENES:
        sc_audio = audio_dir / f"{sc['id']}.flac"
        tts.synthesize(sc["narration"], str(sc_audio), voice=FEMALE_VOICE, seed=77, language="English")
        dur = float(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(sc_audio)
        ]).strip())
        durations[sc["id"]] = dur
        print(f"Scene {sc['id']} duration: {dur:.2f}s")
        
    # 3. Outro voice
    outro_audio = audio_dir / "outro.flac"
    tts.synthesize(OUTRO_TEXT, str(outro_audio), voice=FEMALE_VOICE, seed=77, language="English")
    durations["outro"] = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(outro_audio)
    ]).strip())
    print(f"Outro duration: {durations['outro']:.2f}s")
    
    # Preload images
    preloaded = {}
    for sc in SCENES:
        p = sc["image"]
        if os.path.exists(p):
            preloaded[p] = Image.open(p).convert("RGBA")
            
    print("Generating frames synchronized to voiceover...")
    frame_count = 0
    
    # Intro
    intro_frames = int(max(durations["intro"] + 1.0, 4.0) * FPS)
    for f in range(intro_frames):
        p = f / intro_frames
        f_img = render_intro_frame(p)
        f_img.save(FRAMES_DIR / f"frame_{frame_count:05d}.png")
        frame_count += 1
        
    # Scenes
    for sc_idx, sc in enumerate(SCENES):
        sc_dur = max(durations[sc["id"]] + 1.2, 5.0)
        sc_frames = int(sc_dur * FPS)
        for f in range(sc_frames):
            p = f / sc_frames
            f_img = render_scene_frame(sc_idx, p, preloaded)
            # Crossfade first 10 frames
            if f < 10 and frame_count > 0:
                blend_alpha = f / 10.0
                prev_path = FRAMES_DIR / f"frame_{frame_count-1:05d}.png"
                if prev_path.exists():
                    prev_img = Image.open(prev_path)
                    f_img = Image.blend(prev_img, f_img, blend_alpha)
            f_img.save(FRAMES_DIR / f"frame_{frame_count:05d}.png")
            frame_count += 1
            
    # Outro
    outro_frames = int(max(durations["outro"] + 1.5, 4.0) * FPS)
    for f in range(outro_frames):
        p = f / outro_frames
        f_img = render_outro_frame(p)
        if f < 10:
            blend_alpha = f / 10.0
            prev_path = FRAMES_DIR / f"frame_{frame_count-1:05d}.png"
            if prev_path.exists():
                prev_img = Image.open(prev_path)
                f_img = Image.blend(prev_img, f_img, blend_alpha)
        f_img.save(FRAMES_DIR / f"frame_{frame_count:05d}.png")
        frame_count += 1
        
    print(f"Rendered {frame_count} frames! Building audio track...")
    
    # Concatenate speech track with exact delays
    speech_track = audio_dir / "full_speech.flac"
    filter_parts = []
    inputs = [
        "-i", str(intro_audio)
    ]
    for sc in SCENES:
        inputs.extend(["-i", str(audio_dir / f"{sc['id']}.flac")])
    inputs.extend(["-i", str(outro_audio)])
    
    # Build adelay filter
    curr_time = 0.5  # start intro speech at 0.5s
    delays = [int(curr_time * 1000)]
    curr_time += max(durations["intro"] + 1.0, 4.0)
    for sc in SCENES:
        delays.append(int(curr_time * 1000))
        curr_time += max(durations[sc["id"]] + 1.2, 5.0)
    delays.append(int(curr_time * 1000))
    
    filter_str = ""
    for idx, d_ms in enumerate(delays):
        filter_str += f"[{idx}:a]adelay={d_ms}|{d_ms}[a{idx}];"
    amix_inputs = "".join(f"[a{idx}]" for idx in range(len(delays)))
    filter_str += f"{amix_inputs}amix=inputs={len(delays)}:dropout_transition=0,volume=1.8[aout]"
    
    speech_cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", filter_str, "-map", "[aout]", str(speech_track)]
    subprocess.run(speech_cmd, check=True)
    
    # Final video muxing with background music ducked under speech
    music_file = ROOT / "video" / "audio" / "music.flac"
    out_video = Path("/home/kindstrom/Videos/omacad-senaste-2-dagarna.mp4")
    total_video_dur = frame_count / FPS
    
    print("Muxing final video with ducked music and speech...")
    mux_cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(FRAMES_DIR / "frame_%05d.png"),
        "-i", str(music_file),
        "-i", str(speech_track),
        "-filter_complex",
        f"[1:a]afade=t=in:ss=0:d=1.5,volume=0.22[bgm];"
        f"[bgm][2:a]sidechaincompress=threshold=0.15:ratio=4:attack=50:release=300[ducked];"
        f"[ducked][2:a]amix=inputs=2:weights=1 1.2[audio_mix];"
        f"[audio_mix]afade=t=out:st={total_video_dur - 2.5}:d=2.5[final_audio]",
        "-map", "0:v",
        "-map", "[final_audio]",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "17",
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", str(total_video_dur),
        str(out_video)
    ]
    subprocess.run(mux_cmd, check=True)
    print(f"SUCCESS! Video written to: {out_video}")

if __name__ == "__main__":
    main()

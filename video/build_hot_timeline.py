#!/usr/bin/env python3
"""
Hot & Dynamic Timeline Showcase Video Generator for Omacad.
Creates an ultra-slick, modern motion graphics video with:
- Dynamic Ken-Burns pan/zoom on actual app screenshots
- Frosted glass UI overlays & glowing timeline progress bar
- Smooth alpha crossfades between dates and features
- Synchronized energetic lo-fi/tech background soundtrack
"""
import os
import sys
import math
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import numpy as np

ROOT = Path("/home/kindstrom/Work/omacad")
OUTDIR = ROOT / "video" / "timeline_hot"
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

# Color Palette: Deep Space Navy, Electric Neon Orange, Cyber Cyan, Crisp White
BG_COLOR = (11, 13, 21)
CARD_BG = (18, 22, 34, 210)
CARD_BORDER = (55, 68, 98, 240)
ACCENT_ORANGE = (255, 115, 30)
ACCENT_CYAN = (0, 225, 255)
TEXT_WHITE = (245, 248, 255)
TEXT_MUTED = (160, 175, 205)

TIMELINE_DATA = [
    {
        "date": "2026-10-11",
        "tag": "DAG 1 • v0.4.0 → v0.6.8",
        "title": "Grundfundament & Paritet",
        "badge": "CAD-KÄRNAN STARTAR",
        "summary": "Från grundläggande extrude till ett komplett parametriskt CAD-system med realtidsrespons.",
        "milestones": [
            ("Extrude med dragpilar", "Intuitiv dragpil med distansangivelse och automatisk fasdetektering."),
            ("Revolve & Shell", "Rotationskroppar och dynamisk urholkning (inåt/utåt/båda)."),
            ("Smart Skiss-offset", "Offset-kedjor hanterar nu kurvor och bågar med bibehållet centrum."),
            ("Interaktiv Tidslinje", "Klick på steg färgkodar grönt (tillagt) och rött (borttaget material)."),
            ("F9 Direkthjälp", "Rapportera buggar direkt med automatisk skärmdump och projektfil.")
        ],
        "image": "/home/kindstrom/Work/omacad/screenshots/11_extrude_arrow.png",
        "image_caption": "3D Extrude med dynamisk dragpil & profilmarkering"
    },
    {
        "date": "2026-10-12",
        "tag": "DAG 2 • v0.6.9 → v0.6.31",
        "title": "Smart Circle & Fill Pattern",
        "badge": "INTELLIGENTA VERKTYG",
        "summary": "Fokus på snabbhet i arbetsflödet: rita med exakta siffror och mönsterfyll komplexa ytor.",
        "milestones": [
            ("Smart Circle (Shift+C)", "Mata in diameter + avstånd till två kanter. Placera på sekunder."),
            ("Fill Pattern", "Packar 3–8-sidiga polygoner optimalt runt hål, öar och cylindrar."),
            ("Lay on Plane", "Ett klick för att rotera och lägga vilken yta som helst mot marken."),
            ("Avrundade rektanglar", "Måttas nu på total bredd/höjd och hörnen ställs direkt med radie."),
            ("Globala Kontextmenyer", "Högerklicka på profiler, ytor eller i 3D-rymden för snabbkommandon.")
        ],
        "image": "/home/kindstrom/Work/omacad/video/stills/fill_pattern.png",
        "image_caption": "Fill Pattern packar hexagoner tätt kring hål och kanter"
    },
    {
        "date": "2026-10-13",
        "tag": "DAG 3 • v0.7.0 → v0.7.4",
        "title": "Modell-träd & Shell Preview",
        "badge": "HIERARKISK STRUKTUR",
        "summary": "Full överblick med Fusion 360-inspirerat browser-träd och interaktiv solid-preview.",
        "milestones": [
            ("Hierarkiskt Modell-träd", "Kroppar och skisser ordnas logiskt med föräldrarelationer."),
            ("3D-klick på Bodies", "Markera solider direkt i 3D-vyn för att inspektera och dölja."),
            ("Shell Live Preview", "Välj öppna ytor och se skalväggen uppdateras i realtid."),
            ("Direktinmatning i Extrude", "Sifferbrickan låter dig skriva måttet direkt utan dialoger."),
            ("Skalbar Ribbon-design", "Knappar och ikoner anpassar sig perfekt till alla skärmupplösningar.")
        ],
        "image": "/home/kindstrom/Work/omacad/video/stills/shell.png",
        "image_caption": "Realtids-Shell med valbara öppna ytor & preview"
    },
    {
        "date": "2026-10-14",
        "tag": "DAG 4 • v0.7.5.0 → v0.7.7",
        "title": "3D-Print Gängor & Gizmo",
        "badge": "FUSION 360 INTERAKTION",
        "summary": "Skräddarsydda CAD-verktyg för 3D-printning och interaktiva 3D-rotationsringar.",
        "milestones": [
            ("Thread / Coil-verktyg", "Metriska, trapetsformade och runda gängor optimerade för 3D-print."),
            ("Flush End Trimming", "Automatisk ren kapning av gängändar för felfria utskrifter."),
            ("3D Body Rotation Gizmo", "Interaktiva rotationsringar och dragpilar i klassisk Fusion-stil."),
            ("Combine med verktygsminne", "Booleska operationer kan behålla skärkroppen (*Keep tool bodies*)."),
            ("Blueprint Ikonset", "Nytt knivskarpt ikonsystem i tre valbara stilar.")
        ],
        "image": "/home/kindstrom/Work/omacad/video/stills/rotate_gizmo.png",
        "image_caption": "3D Rotation Gizmo med interaktiva vinkelringar"
    },
    {
        "date": "2026-10-15",
        "tag": "DAG 5 • v0.7.7.1 → v0.7.9.0",
        "title": "GPU-Caching & Tangentkedjor",
        "badge": "EXTREM PRESTANDA",
        "summary": "Arkitektoniskt språng: hårdvaruacceleration och smart topologikedjning.",
        "milestones": [
            ("GPU VBO/VAO Caching", "Solider renderas med full grafikhårdvaruacceleration utan lagg."),
            ("Inkrementell Tidslinje", "Endast modifierade steg i historiken räknas om vid ändring."),
            ("Tangent Chain i Fillet", "Ett klick väljer en hel sammanhängande kedja av tangentiella kanter."),
            ("Flerkärnig Shell-motor", "Parallelliserad geometriberäkning snabbar upp komplexa skal."),
            ("Antigravity AI i F9", "Koppla direkt mot Antigravity eller Claude för direkt bugglagning.")
        ],
        "image": "/home/kindstrom/Work/omacad/video/stills/fillet_chamfer.png",
        "image_caption": "Tangentkedje-urval för jämn och obruten Fillet"
    },
    {
        "date": "2026-10-16",
        "tag": "DAG 6 • v0.7.9.1 → v0.7.9.29",
        "title": "Offset Face & Skraverat Snitt",
        "badge": "FULL PARITET & FINISH",
        "summary": "Finjustera toleranser för passningar och inspektera inre detaljer med teknisk snittvy.",
        "milestones": [
            ("Offset Face", "Flytta plana eller kurvade ytor (gängor/cylindrar) för perfekt passform."),
            ("Skraverad Snittvy (Hatch)", "Diagonal teknisk skravering à la Fusion 360 med konstant skärmtäthet."),
            ("Named Views & Webbläsare", "Klicka Home, Top, Front, Right för att omedelbart docka vyn."),
            ("Inline Måttrutor", "Mått visas som interaktiva rutor precis vid markören i 3D-rymden."),
            ("Inbyggd Changelog-visare", "Sök och läs hela utvecklingshistoriken direkt i appen.")
        ],
        "image": "/home/kindstrom/Work/omacad/video/stills/section_view.png",
        "image_caption": "Tekniskt skraverad Section View & inre snitt"
    }
]


def render_intro_frame(progress):
    """Dramatic high-tech intro frame."""
    im = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR + (255,))
    draw = ImageDraw.Draw(im)
    
    # Animated subtle background grid
    offset = int(progress * 80) % 60
    for x in range(0, WIDTH, 60):
        draw.line([(x + offset, 0), (x + offset, HEIGHT)], fill=(20, 24, 38), width=1)
    for y in range(0, HEIGHT, 60):
        draw.line([(0, y), (WIDTH, y)], fill=(20, 24, 38), width=1)
        
    # Ambient glowing central circle
    glow_radius = int(320 + math.sin(progress * math.pi) * 40)
    draw.ellipse([WIDTH//2 - glow_radius, HEIGHT//2 - glow_radius - 40,
                  WIDTH//2 + glow_radius, HEIGHT//2 + glow_radius - 40],
                 fill=(25, 45, 80, 160))
                 
    # Titles with entrance pop
    scale = min(1.0, progress * 1.5)
    
    title_text = "OMACAD"
    bb = draw.textbbox((0, 0), title_text, font=f_huge)
    tw = bb[2] - bb[0]
    draw.text((WIDTH//2 - tw//2, 340), title_text, font=f_huge, fill=ACCENT_ORANGE)
    
    sub1 = "TIMELINE EVOLUTION • CHANGELOG MILESTONES"
    bb1 = draw.textbbox((0, 0), sub1, font=f_h2)
    tw1 = bb1[2] - bb1[0]
    draw.text((WIDTH//2 - tw1//2, 440), sub1, font=f_h2, fill=TEXT_WHITE)
    
    sub2 = "11 – 16 OKTOBER 2026: EN VECKA AV INTENSIV CAD-UTVECKLING"
    bb2 = draw.textbbox((0, 0), sub2, font=f_h3)
    tw2 = bb2[2] - bb2[0]
    draw.text((WIDTH//2 - tw2//2, 510), sub2, font=f_h3, fill=ACCENT_CYAN)
    
    # Tech spec badges
    badges = ["150+ COMMITS", "FUSION 360 PARITET", "GPU ACCELERERAD", "NATIVE LINUX"]
    bx_start = WIDTH//2 - 420
    for i, b in enumerate(badges):
        bx = bx_start + i * 220
        by = 640
        draw.rounded_rectangle([bx, by, bx + 190, by + 45], radius=8, fill=(24, 32, 50), outline=(60, 80, 120), width=2)
        bb = draw.textbbox((0, 0), b, font=f_badge)
        bw = bb[2] - bb[0]
        draw.text((bx + (190 - bw)//2, by + 12), b, font=f_badge, fill=(220, 230, 250))
        
    # Progress indicator bar
    p_bar_w = 600
    p_bar_x = WIDTH//2 - p_bar_w//2
    p_bar_y = 780
    draw.rounded_rectangle([p_bar_x, p_bar_y, p_bar_x + p_bar_w, p_bar_y + 8], radius=4, fill=(35, 45, 70))
    draw.rounded_rectangle([p_bar_x, p_bar_y, p_bar_x + int(p_bar_w * progress), p_bar_y + 8], radius=4, fill=ACCENT_ORANGE)
    
    return im.convert("RGB")


def render_outro_frame(progress):
    """Sleek outro card."""
    im = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR + (255,))
    draw = ImageDraw.Draw(im)
    
    # Glow & grid
    for x in range(0, WIDTH, 60):
        draw.line([(x, 0), (x, HEIGHT)], fill=(20, 24, 38), width=1)
    for y in range(0, HEIGHT, 60):
        draw.line([(0, y), (WIDTH, y)], fill=(20, 24, 38), width=1)
        
    draw.ellipse([WIDTH//2 - 350, HEIGHT//2 - 350, WIDTH//2 + 350, HEIGHT//2 + 350], fill=(30, 40, 70, 150))
    
    draw.text((WIDTH//2 - 250, 320), "OMACAD CAD", font=f_huge, fill=ACCENT_ORANGE)
    draw.text((WIDTH//2 - 360, 420), "Framtidens 3D CAD för Omarchy Linux", font=f_h1, fill=TEXT_WHITE)
    draw.text((WIDTH//2 - 390, 520), "Snabbhet, precision och full kontroll direkt i ditt system.", font=f_h2, fill=TEXT_MUTED)
    draw.text((WIDTH//2 - 370, 600), "Öppna appen och utforska alla nyheter via Help > Changelog", font=f_h3, fill=ACCENT_CYAN)
    
    return im.convert("RGB")


# Pre-load & prepare screenshots
PRELOADED_IMAGES = {}
for day in TIMELINE_DATA:
    p = day["image"]
    if os.path.exists(p):
        img = Image.open(p).convert("RGBA")
        PRELOADED_IMAGES[p] = img


def render_day_frame(day_idx, frame_in_day, total_frames_in_day):
    """
    Renders an ultra-polished day frame with:
    - Glowing interactive timeline progress bar on top
    - Left glass card with milestones & badges
    - Right dynamic Ken-Burns zoom on the high-res screenshot
    """
    day = TIMELINE_DATA[day_idx]
    progress = frame_in_day / total_frames_in_day
    
    im = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR + (255,))
    draw = ImageDraw.Draw(im)
    
    # 1. Subtle high-tech background pattern
    for y in range(0, HEIGHT, 40):
        draw.line([(0, y), (WIDTH, y)], fill=(16, 20, 32), width=1)
        
    # 2. Top Header Bar
    draw.rectangle([0, 0, WIDTH, 125], fill=(16, 20, 32, 230))
    draw.line([(0, 125), (WIDTH, 125)], fill=(35, 45, 70), width=2)
    
    # Header texts
    draw.text((50, 20), "OMACAD", font=f_h1, fill=ACCENT_ORANGE)
    draw.text((270, 32), "CHRONOLOGICAL MILESTONES & CHANGELOG", font=f_h3, fill=TEXT_WHITE)
    draw.text((WIDTH - 380, 36), "OMARCHY CAD EVOLUTION", font=f_h3, fill=ACCENT_CYAN)
    
    # 3. Top Glowing Timeline Bar
    t_start_x = 70
    t_end_x = WIDTH - 70
    t_y = 95
    step_x = (t_end_x - t_start_x) / (len(TIMELINE_DATA) - 1)
    
    # Timeline inactive track
    draw.line([(t_start_x, t_y), (t_end_x, t_y)], fill=(40, 50, 75), width=5)
    
    # Timeline active fill
    current_head_x = t_start_x + (day_idx + progress) * step_x
    current_head_x = min(t_end_x, current_head_x)
    draw.line([(t_start_x, t_y), (current_head_x, t_y)], fill=ACCENT_ORANGE, width=5)
    
    # Timeline node badges
    for i, d in enumerate(TIMELINE_DATA):
        cx = int(t_start_x + i * step_x)
        is_cur = (i == day_idx)
        is_done = (i < day_idx)
        
        node_r = 13 if is_cur else 8
        if is_cur:
            # Pulsing glow around current node
            pulse = int(5 * math.sin(progress * math.pi * 2))
            draw.ellipse([cx - node_r - 7 - pulse, t_y - node_r - 7 - pulse,
                          cx + node_r + 7 + pulse, t_y + node_r + 7 + pulse],
                         fill=(255, 115, 30, 80))
            draw.ellipse([cx - node_r, t_y - node_r, cx + node_r, t_y + node_r], fill=ACCENT_ORANGE, outline=(255, 255, 255), width=3)
        elif is_done:
            draw.ellipse([cx - node_r, t_y - node_r, cx + node_r, t_y + node_r], fill=(255, 140, 60), outline=(200, 220, 255), width=2)
        else:
            draw.ellipse([cx - node_r, t_y - node_r, cx + node_r, t_y + node_r], fill=(25, 32, 48), outline=(60, 75, 105), width=2)
            
        # Date label above
        d_lbl = d["date"].split("-")[1] + "/" + d["date"].split("-")[2]
        bb = draw.textbbox((0, 0), d_lbl, font=f_time)
        lw = bb[2] - bb[0]
        lbl_col = (255, 255, 255) if is_cur else ((200, 210, 230) if is_done else (100, 115, 140))
        draw.text((cx - lw//2, t_y - 32), d_lbl, font=f_time, fill=lbl_col)
        
    # 4. Left Glass Card: Day Milestones
    card_x = 50
    card_y = 150
    card_w = 780
    card_h = HEIGHT - card_y - 40
    
    # Semi-transparent frosted card background
    draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=2)
    
    # Category badge & Date
    draw.rounded_rectangle([card_x + 35, card_y + 30, card_x + 35 + 230, card_y + 65], radius=6, fill=(35, 50, 85), outline=ACCENT_CYAN, width=1)
    draw.text((card_x + 48, card_y + 37), day["badge"], font=f_badge, fill=ACCENT_CYAN)
    
    draw.text((card_x + 285, card_y + 36), day["tag"], font=f_badge, fill=TEXT_MUTED)
    
    # Title
    draw.text((card_x + 35, card_y + 85), day["title"], font=f_h1, fill=TEXT_WHITE)
    
    # Summary
    draw.text((card_x + 35, card_y + 145), day["summary"], font=f_body, fill=(210, 225, 250))
    
    draw.line([(card_x + 35, card_y + 190), (card_x + card_w - 35, card_y + 190)], fill=(45, 58, 85), width=2)
    
    # Milestone list items with animated entrance stagger
    item_y = card_y + 215
    for m_idx, (m_title, m_desc) in enumerate(day["milestones"]):
        # Entrance slide/opacity check
        m_prog = min(1.0, max(0.0, (progress * 5.0) - m_idx * 0.3))
        
        # Glow bullet
        draw.ellipse([card_x + 35, item_y + 7, card_x + 49, item_y + 21], fill=ACCENT_ORANGE)
        
        # Milestone Title
        draw.text((card_x + 60, item_y), m_title, font=f_h3, fill=TEXT_WHITE)
        
        # Milestone Description (wrapped)
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
        
    # 5. Right Column: High-Tech Screenshot Showcase with Dynamic Ken-Burns
    shot_x = 870
    shot_y = 150
    shot_w = WIDTH - shot_x - 50
    shot_h = HEIGHT - shot_y - 40
    
    # Showcase container
    draw.rounded_rectangle([shot_x, shot_y, shot_x + shot_w, shot_y + shot_h], radius=16, fill=(18, 22, 34), outline=CARD_BORDER, width=2)
    
    # Header tag on screenshot
    draw.rounded_rectangle([shot_x + 30, shot_y + 25, shot_x + 220, shot_y + 60], radius=6, fill=(28, 38, 60), outline=(60, 80, 120), width=1)
    draw.text((shot_x + 45, shot_y + 32), "LIVE APP CAPTURE", font=f_badge, fill=ACCENT_ORANGE)
    draw.text((shot_x + 240, shot_y + 33), day["image_caption"], font=f_h3, fill=TEXT_WHITE)
    
    # Inner viewport area for screenshot
    vp_x = shot_x + 30
    vp_y = shot_y + 80
    vp_w = shot_w - 60
    vp_h = shot_h - 110
    
    # Render Ken-Burns animated screenshot
    s_path = day["image"]
    if s_path in PRELOADED_IMAGES:
        src_img = PRELOADED_IMAGES[s_path]
        
        # Ken Burns zoom: 1.0 -> 1.08 + subtle drift
        zoom = 1.0 + 0.08 * math.sin(progress * math.pi)
        drift_x = math.sin(progress * math.pi) * 15
        drift_y = math.cos(progress * math.pi) * 10
        
        # Scale image to cover vp_w, vp_h while keeping ratio
        aspect_src = src_img.width / src_img.height
        aspect_dst = vp_w / vp_h
        
        if aspect_src > aspect_dst:
            new_h = int(vp_h * zoom)
            new_w = int(new_h * aspect_src)
        else:
            new_w = int(vp_w * zoom)
            new_h = int(new_w / aspect_src)
            
        scaled = src_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # Center crop into vp_w, vp_h
        crop_x = int((new_w - vp_w) / 2 + drift_x)
        crop_y = int((new_h - vp_h) / 2 + drift_y)
        crop_x = max(0, min(new_w - vp_w, crop_x))
        crop_y = max(0, min(new_h - vp_h, crop_y))
        
        cropped = scaled.crop((crop_x, crop_y, crop_x + vp_w, crop_y + vp_h))
        
        # Paste into canvas
        im.paste(cropped, (vp_x, vp_y))
        
        # Subtle glowing inner border around viewport
        draw.rounded_rectangle([vp_x, vp_y, vp_x + vp_w, vp_y + vp_h], radius=8, outline=(80, 110, 160), width=2)
        
    return im.convert("RGB")


def build_hot_timeline_video():
    print("Building Hot Timeline Video...")
    total_frames = 0
    
    # Timeline config:
    # Intro: 3.5 sec (105 frames)
    # 6 Days: 6.5 sec each (195 frames each)
    # Outro: 3.5 sec (105 frames)
    # Total = ~46 seconds
    
    intro_frames = 3 * FPS
    day_frames = int(6.5 * FPS)
    outro_frames = 3 * FPS
    
    frame_count = 0
    
    # 1. Intro Frames
    print("Generating Intro frames...")
    for f in range(intro_frames):
        p = f / intro_frames
        f_img = render_intro_frame(p)
        f_path = FRAMES_DIR / f"frame_{frame_count:05d}.png"
        f_img.save(f_path)
        frame_count += 1
        
    # 2. Daily Milestone Frames with crossfade
    print("Generating Daily Milestones...")
    for day_idx in range(len(TIMELINE_DATA)):
        print(f"  Rendering Day {day_idx + 1}/6: {TIMELINE_DATA[day_idx]['date']}...")
        for f in range(day_frames):
            f_img = render_day_frame(day_idx, f, day_frames)
            
            # Crossfade transition (first 10 frames)
            if f < 10 and (day_idx > 0 or frame_count > intro_frames):
                blend_alpha = f / 10.0
                prev_path = FRAMES_DIR / f"frame_{frame_count-1:05d}.png"
                if prev_path.exists():
                    prev_img = Image.open(prev_path)
                    f_img = Image.blend(prev_img, f_img, blend_alpha)
                    
            f_path = FRAMES_DIR / f"frame_{frame_count:05d}.png"
            f_img.save(f_path)
            frame_count += 1
            
    # 3. Outro Frames
    print("Generating Outro frames...")
    for f in range(outro_frames):
        p = f / outro_frames
        f_img = render_outro_frame(p)
        if f < 10:
            blend_alpha = f / 10.0
            prev_path = FRAMES_DIR / f"frame_{frame_count-1:05d}.png"
            if prev_path.exists():
                prev_img = Image.open(prev_path)
                f_img = Image.blend(prev_img, f_img, blend_alpha)
        f_path = FRAMES_DIR / f"frame_{frame_count:05d}.png"
        f_img.save(f_path)
        frame_count += 1
        
    print(f"Rendered {frame_count} frames! Encoding with ffmpeg and mixing audio...")
    
    # Encode with audio (music.flac from repository)
    music_file = ROOT / "video" / "audio" / "music.flac"
    out_video = Path("/home/kindstrom/Videos/omacad-changelog-timeline-hot.mp4")
    
    duration_sec = frame_count / FPS
    
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(FRAMES_DIR / "frame_%05d.png"),
        "-i", str(music_file),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "17",
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", "192k",
        "-af", f"afade=t=in:ss=0:d=1.5,afade=t=out:st={duration_sec - 2.0}:d=2.0",
        "-t", str(duration_sec),
        "-shortest",
        str(out_video)
    ]
    
    subprocess.run(cmd, check=True)
    print(f"SUCCESS! Hot video created at: {out_video}")


if __name__ == "__main__":
    build_hot_timeline_video()

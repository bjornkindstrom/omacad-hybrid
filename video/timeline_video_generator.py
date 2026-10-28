#!/usr/bin/env python3
"""
Timeline video generator for Omacad changelog milestones.
Generates an HD 1080p video walking through each day's milestones and app screenshots.
"""
import os
import sys
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path("/home/kindstrom/Work/omacad")
OUTDIR = ROOT / "video" / "timeline"
OUTDIR.mkdir(parents=True, exist_ok=True)
FRAMES_DIR = OUTDIR / "frames"
FRAMES_DIR.mkdir(parents=True, exist_ok=True)

WIDTH = 1920
HEIGHT = 1080
FPS = 30

FONT_REG = "/usr/share/fonts/liberation/LiberationSans-Regular.ttf"
FONT_BOLD = "/usr/share/fonts/liberation/LiberationSans-Bold.ttf"

f_title = ImageFont.truetype(FONT_BOLD, 46)
f_subtitle = ImageFont.truetype(FONT_BOLD, 30)
f_date = ImageFont.truetype(FONT_BOLD, 26)
f_bullet = ImageFont.truetype(FONT_REG, 23)
f_caption = ImageFont.truetype(FONT_BOLD, 20)
f_header = ImageFont.truetype(FONT_BOLD, 54)
f_timeline = ImageFont.truetype(FONT_BOLD, 22)

TIMELINE_DAYS = [
    {
        'date': '2026-10-11',
        'version': 'v0.4.0 → v0.6.8',
        'title': 'Grundfundament & Fusion 360-paritet',
        'bullets': [
            'Extrude med visuella dragpilar, Revolve & Shell',
            'Smart Skiss-offset med bågar & Box-selektion',
            'Projektion av befintliga ytkantar (Include Face Edges)',
            'Interaktiv tidslinje (visualiserar tillagt/borttaget material i grönt/rött)',
            'F9 direkt problem- och ändringsrapportering med skärmdump'
        ],
        'images': [
            ('/home/kindstrom/Work/omacad/screenshots/11_extrude_arrow.png', 'Extrude med pil'),
            ('/home/kindstrom/Work/omacad/screenshots/20_revolve.png', 'Revolve-rotation'),
            ('/home/kindstrom/Work/omacad/screenshots/4_history_rolled_back.png', 'Tidslinje-historik')
        ]
    },
    {
        'date': '2026-10-12',
        'version': 'v0.6.9 → v0.6.31',
        'title': 'Smart Circle, Fill Pattern & Smidighet',
        'bullets': [
            'Smart Circle: cirklar placeras med mått och tangent-inmatning',
            'Fill Pattern: packar polygoner tätt (3-8 sidor) runt hål och hinder',
            'Move / Rotate Body: \"Lay on plane\" lägger detaljen mot planet direkt',
            'Avrundade rektanglar med direkt radie- och storlekskontroll',
            'Rikliga kontextmenyer (högerklick på profiler, ytor och tomrum)'
        ],
        'images': [
            ('/home/kindstrom/Work/omacad/video/stills/smart_circle.png', 'Smart Circle'),
            ('/home/kindstrom/Work/omacad/video/stills/fill_pattern.png', 'Fill Pattern'),
            ('/home/kindstrom/Work/omacad/video/stills/move_lay.png', 'Lay on Plane')
        ]
    },
    {
        'date': '2026-10-13',
        'version': 'v0.7.0 → v0.7.4',
        'title': 'Trädstruktur & Shell Live Preview',
        'bullets': [
            'Modell-träd: Hierarkisk struktur med Bodies och skisser grupperade',
            '3D-markering av bodies med enkelt vänsterklick',
            'Shell med direkt live-preview & valbara öppna ytor',
            'Direktinmatning i Extrude-bricka & skalbara ribbon-knappar',
            'Utökat temastöd och förfinat modernt gränssnitt'
        ],
        'images': [
            ('/home/kindstrom/Work/omacad/video/stills/side_panel.png', 'Modell-träd'),
            ('/home/kindstrom/Work/omacad/video/stills/shell.png', 'Shell Preview'),
            ('/home/kindstrom/Work/omacad/video/stills/type_numbers.png', 'Direktinmatning')
        ]
    },
    {
        'date': '2026-10-14',
        'version': 'v0.7.5.0 → v0.7.7',
        'title': '3D-Print Gängor & Fusion-stil Gizmo',
        'bullets': [
            '3D-Print-optimerat Thread / Coil (metriska, trapets & runda gängor)',
            'Automatisk trimning vid cylinderändar för rena 3D-utskrifter',
            '3D Rotation Gizmo i Fusion 360-stil med roteringsringar och pilar',
            'Combine med \"Keep tool bodies\" och interaktiva 3D-kroppsklick',
            'Webb-stills och skärmdumpar automatiserade för releaser'
        ],
        'images': [
            ('/home/kindstrom/Work/omacad/video/stills/rotate_gizmo.png', '3D Rotation Gizmo'),
            ('/home/kindstrom/Work/omacad/video/stills/place_primitive.png', 'Primitives & Threads'),
            ('/home/kindstrom/Work/omacad/video/stills/icon_sets.png', 'Crisp Blueprint Icons')
        ]
    },
    {
        'date': '2026-10-15',
        'version': 'v0.7.7.1 → v0.7.9.0',
        'title': 'Prestanda-språng & Fusion 360 Paritet',
        'bullets': [
            'GPU VBO/VAO caching för blixtsnabb rendering av komplexa solider',
            'Inkrementell tidslinjeomräkning (recomputar endast ändrade steg)',
            'Fillet/Chamfer ytväljning och tangentkedjemarkering (Tangent Chain)',
            'Massiv flerkärnig optimering av Shell-verktyget',
            'Stöd för Antigravity och Claude som integrerade AI-assistenter vid F9'
        ],
        'images': [
            ('/home/kindstrom/Work/omacad/video/stills/fillet_chamfer.png', 'Tangent Chain Fillet'),
            ('/home/kindstrom/Work/omacad/video/stills/timeline.png', 'Incremental Timeline'),
            ('/home/kindstrom/Work/omacad/video/stills/report_problem.png', 'F9 AI Agent Integration')
        ]
    },
    {
        'date': '2026-10-16',
        'version': 'v0.7.9.1 → v0.7.9.29',
        'title': 'Offset Face, Skraverad Snittvy & Full Paritet',
        'bullets': [
            'Offset Face på plana & kurvade ytor (för gäng-/passningstoleranser)',
            'Snittvy (Section View) med teknisk snedskravering (hatch) à la Fusion 360',
            'Modell-läsare i Fusion 360-layout med Named Views (Home, Top osv.)',
            'Inline dynamiska måttrutor i 3D-vyn & uppdaterad Mått-ikon',
            'Inbyggd sökbar Help > Changelog direkt inuti appen'
        ],
        'images': [
            ('/home/kindstrom/Work/omacad/video/stills/section_view.png', 'Hatched Section View'),
            ('/home/kindstrom/Work/omacad/video/stills/dimensions.png', 'Inline Dimensions'),
            ('/home/kindstrom/Work/omacad/video/stills/themes.png', 'Full Theme Suite')
        ]
    }
]


def draw_timeline_bar(draw, active_idx):
    bar_y = 150
    start_x = 120
    end_x = WIDTH - 120
    step_x = (end_x - start_x) / (len(TIMELINE_DAYS) - 1)
    
    # Background line
    draw.line([(start_x, bar_y), (end_x, bar_y)], fill=(50, 56, 75), width=6)
    active_x = start_x + active_idx * step_x
    draw.line([(start_x, bar_y), (active_x, bar_y)], fill=(255, 120, 40), width=6)
    
    for i, day in enumerate(TIMELINE_DAYS):
        cx = int(start_x + i * step_x)
        cy = bar_y
        is_active = (i == active_idx)
        is_past = (i < active_idx)
        
        radius = 16 if is_active else 11
        if is_active:
            glow_r = radius + 6
            draw.ellipse([cx - glow_r, cy - glow_r, cx + glow_r, cy + glow_r], fill=(255, 140, 60, 100), outline=(255, 170, 80), width=2)
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(255, 120, 40), outline=(255, 255, 255), width=3)
        elif is_past:
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(255, 140, 60), outline=(200, 200, 200), width=2)
        else:
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(35, 40, 55), outline=(70, 80, 105), width=2)
        
        # Date label
        d_text = day['date'].replace("2026-", "")
        bb = draw.textbbox((0, 0), d_text, font=f_timeline)
        tw = bb[2] - bb[0]
        color = (255, 255, 255) if is_active else ((170, 180, 200) if is_past else (110, 120, 140))
        draw.text((cx - tw // 2, cy + 22), d_text, font=f_timeline, fill=color)


def create_milestone_slide(day_idx, day_data):
    im = Image.new("RGBA", (WIDTH, HEIGHT), (16, 18, 27, 255))
    draw = ImageDraw.Draw(im)
    
    # Subtle background styling
    draw.rectangle([0, 0, WIDTH, 100], fill=(22, 25, 38))
    draw.text((60, 26), "OMACAD — EVOLUTION & MILESTONES TIMELINE", font=f_header, fill=(245, 245, 250))
    draw.text((WIDTH - 380, 36), "Oktober 2026 Utveckling", font=f_subtitle, fill=(255, 140, 60))
    
    # Draw Timeline Bar
    draw_timeline_bar(draw, day_idx)
    
    # Left Column: Day Highlights
    left_x = 70
    left_y = 230
    left_w = 780
    
    # Card background for highlights
    draw.rounded_rectangle([left_x, left_y, left_x + left_w, HEIGHT - 50], radius=16, fill=(24, 28, 42), outline=(42, 48, 70), width=2)
    
    # Title & Version Badge
    draw.text((left_x + 35, left_y + 30), f"DAG: {day_data['date']}", font=f_title, fill=(255, 140, 60))
    draw.text((left_x + 35, left_y + 85), f"Versioner: {day_data['version']}", font=f_subtitle, fill=(130, 200, 255))
    draw.text((left_x + 35, left_y + 130), day_data['title'], font=f_subtitle, fill=(240, 240, 240))
    
    draw.line([(left_x + 35, left_y + 175), (left_x + left_w - 35, left_y + 175)], fill=(45, 52, 76), width=2)
    
    # Bullets
    by = left_y + 200
    for bullet in day_data['bullets']:
        # bullet symbol
        draw.ellipse([left_x + 35, by + 8, left_x + 45, by + 18], fill=(255, 140, 60))
        
        # wrap text if long
        words = bullet.split(" ")
        line = ""
        for w in words:
            test_line = line + (" " if line else "") + w
            bb = draw.textbbox((0, 0), test_line, font=f_bullet)
            if (bb[2] - bb[0]) > (left_w - 90):
                draw.text((left_x + 58, by), line, font=f_bullet, fill=(225, 230, 240))
                by += 32
                line = w
            else:
                line = test_line
        if line:
            draw.text((left_x + 58, by), line, font=f_bullet, fill=(225, 230, 240))
            by += 44
            
    # Right Column: 3 Screenshots / Stills
    right_x = 900
    right_y = 230
    right_w = 950
    right_h = HEIGHT - 230 - 50
    
    draw.rounded_rectangle([right_x, right_y, right_x + right_w, right_y + right_h], radius=16, fill=(24, 28, 42), outline=(42, 48, 70), width=2)
    
    # 3 screenshot slots
    slot_w = 285
    slot_h = 360
    slot_y = right_y + 60
    
    draw.text((right_x + 35, right_y + 20), "SKÄRMDUMPAR FRÅN APPEN (MILSTOLPAR)", font=f_caption, fill=(180, 190, 210))
    
    for idx, (img_path, label) in enumerate(day_data['images']):
        sx = right_x + 30 + idx * (slot_w + 25)
        # card container for image
        draw.rounded_rectangle([sx, slot_y, sx + slot_w, slot_y + slot_h + 100], radius=10, fill=(18, 20, 30), outline=(50, 58, 85), width=2)
        
        if os.path.exists(img_path):
            with Image.open(img_path) as s_img:
                s_img = s_img.convert("RGBA")
                # thumbnail keeping aspect
                s_img.thumbnail((slot_w - 12, slot_h), Image.Resampling.LANCZOS)
                # paste centered
                ix = sx + (slot_w - s_img.width) // 2
                iy = slot_y + (slot_h - s_img.height) // 2
                im.paste(s_img, (ix, iy), s_img)
        
        # Label below
        bb = draw.textbbox((0, 0), label, font=f_caption)
        tw = bb[2] - bb[0]
        draw.text((sx + (slot_w - tw) // 2, slot_y + slot_h + 30), label, font=f_caption, fill=(255, 200, 100))
        
    return im.convert("RGB")


def create_intro_slide():
    im = Image.new("RGBA", (WIDTH, HEIGHT), (16, 18, 27, 255))
    draw = ImageDraw.Draw(im)
    
    # Title Box
    draw.text((WIDTH // 2 - 450, 240), "OMACAD — TIMELINE EVOLUTION", font=f_header, fill=(255, 140, 60))
    draw.text((WIDTH // 2 - 380, 330), "Från de första byggstenarna till full CAD-paritet", font=f_title, fill=(230, 235, 245))
    
    draw.rounded_rectangle([WIDTH // 2 - 460, 440, WIDTH // 2 + 460, 760], radius=16, fill=(24, 28, 42), outline=(42, 48, 70), width=2)
    
    desc_lines = [
        "En visuell resa genom Omacads GitHub Changelog: 11 - 16 Oktober 2026.",
        "Över 150 commits och dussintals nya funktioner implementerade:",
        " • Parametrisk tidslinje, Extrude, Revolve & Shell med realtidspreview",
        " • Smart Circle, Fill Pattern & Lay-on-plane positionering",
        " • 3D-Print-optimerat gängverktyg & 3D-rotations-gizmo à la Fusion 360",
        " • GPU-caching, inkrementell rendering och tangentkedjefillets",
        " • Offset Face för toleranser och tekniskt skraverad snittvy"
    ]
    dy = 475
    for dl in desc_lines:
        draw.text((WIDTH // 2 - 420, dy), dl, font=f_subtitle if dl.startswith("En") else f_bullet, fill=(255, 200, 100) if dl.startswith("En") else (210, 220, 235))
        dy += 36 if not dl.startswith("En") else 46
        
    draw.text((WIDTH // 2 - 180, 830), "STARTAR TIDSLINJEN...", font=f_subtitle, fill=(100, 220, 255))
    return im.convert("RGB")


def create_outro_slide():
    im = Image.new("RGBA", (WIDTH, HEIGHT), (16, 18, 27, 255))
    draw = ImageDraw.Draw(im)
    draw.text((WIDTH // 2 - 280, 300), "OMACAD CAD", font=f_header, fill=(255, 140, 60))
    draw.text((WIDTH // 2 - 420, 400), "Blixtsnabb parametrisk 3D CAD för Omarchy Linux", font=f_title, fill=(230, 235, 245))
    draw.text((WIDTH // 2 - 320, 520), "Utvecklad med fokus på användbarhet och prestanda.", font=f_subtitle, fill=(180, 190, 210))
    draw.text((WIDTH // 2 - 300, 580), "Se hela changeloggen i appen via Help > Changelog", font=f_subtitle, fill=(100, 220, 255))
    return im.convert("RGB")


def render_all():
    print("Generating slides...")
    slides = []
    
    # Intro slide (4 seconds)
    intro_img = create_intro_slide()
    slides.append((intro_img, 4 * FPS))
    
    # 6 Milestone slides (6 seconds each)
    for i, day in enumerate(TIMELINE_DAYS):
        slide_img = create_milestone_slide(i, day)
        slides.append((slide_img, 6 * FPS))
        
    # Outro slide (4 seconds)
    outro_img = create_outro_slide()
    slides.append((outro_img, 4 * FPS))
    
    # Save frames
    print("Saving frames to PNG...")
    frame_idx = 0
    for slide_img, count in slides:
        # Crossfade transition (15 frames) if not first
        for _ in range(count):
            p = FRAMES_DIR / f"frame_{frame_idx:05d}.png"
            slide_img.save(p)
            frame_idx += 1
            if frame_idx % 100 == 0:
                print(f"Saved {frame_idx} frames...")
                
    print(f"Total frames generated: {frame_idx}")
    
    # Encode with ffmpeg
    out_video = Path("/home/kindstrom/Videos/omacad-changelog-timeline.mp4")
    print(f"Encoding video to {out_video}...")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(FRAMES_DIR / "frame_%05d.png"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "18",
        str(out_video)
    ]
    subprocess.run(cmd, check=True)
    print(f"DONE! Video saved at: {out_video}")


if __name__ == "__main__":
    render_all()

#!/usr/bin/env python3
import os
import re
import sys
import math
import html
import wave
import array
import shutil
import tarfile
import asyncio
import argparse
import textwrap
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

try:
    import requests
except ImportError:
    requests = None

try:
    import edge_tts
except ImportError:
    edge_tts = None

try:
    from gtts import gTTS
except ImportError:
    gTTS = None


BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
WORK_DIR = BASE_DIR.parent / "temp_build"
OUT_DIR = BASE_DIR.parent / "review-output-pack"
PIPER_CACHE = Path("/tmp/piper_studio")

# Coordinates matching presenter_visemes.png sprite sheet
MOUTH_ROI_XY = (780, 430)   # width=360, height=250 (5 levels stacked vertically: y=0..1250)
MOUTH_W, MOUTH_H = 360, 250
BLINK_ROI_XY = (800, 295)   # width=310, height=80  (2 levels at y=1250..1410)
BLINK_W, BLINK_H = 310, 80

# Lock whichever voice engine succeeds on segment 1 so voice stays 100% consistent
_LOCKED_TTS_ENGINE = None


def load_font(size: int, bold: bool = True):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def draw_rounded_rect(draw, xy, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def ensure_presenter_assets(presenter_base: Path):
    """Fallback generator in case assets folder was ever missing presenter_base.png."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    if not presenter_base.exists():
        img = Image.new("RGB", (1920, 1080), (15, 23, 42))
        img.save(presenter_base, "PNG")


def create_presenter_slide(presenter_path: Path, out_path: Path, badge_top: str, headline: str, subline: str):
    """Creates 1920x1080 presenter frame + transparent lower-third overlay for Segment 1 talking intro."""
    base = Image.open(presenter_path).convert("RGBA").resize((1920, 1080), Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    draw_rounded_rect(draw, (1510, 40, 1870, 96), radius=14, fill=(15, 23, 42, 220), outline=(245, 158, 11, 255), width=2)
    f_small = load_font(24, bold=True)
    draw.text((1535, 54), "VERIFIED SOFTWARE REVIEW", font=f_small, fill=(255, 255, 255, 255))

    draw_rounded_rect(draw, (90, 845, 1830, 1030), radius=20, fill=(15, 23, 42, 235), outline=(59, 130, 246, 255), width=3)
    draw_rounded_rect(draw, (115, 822, 540, 868), radius=10, fill=(220, 38, 38, 255))

    f_badge = load_font(23, bold=True)
    f_head = load_font(42, bold=True)
    f_sub = load_font(28, bold=False)

    draw.text((135, 831), badge_top[:32].upper(), font=f_badge, fill=(255, 255, 255, 255))
    draw.text((125, 882), headline[:68], font=f_head, fill=(255, 255, 255, 255))
    draw.text((125, 952), subline[:95], font=f_sub, fill=(253, 224, 71, 255))

    overlay.save(out_path.with_suffix(".overlay.png"), "PNG")
    combined = Image.alpha_composite(base, overlay).convert("RGB")
    combined.save(out_path, "PNG")


def create_product_cutaway_slide(
    out_path: Path,
    product_name: str,
    main_result: str,
    features: list,
    coupon_code: str,
):
    """Creates full-screen B-Roll cutaway slide with 3 features and expanded coupon box (NO presenter photo)."""
    canvas = Image.new("RGBA", (1920, 1080), (11, 17, 32, 255))
    draw = ImageDraw.Draw(canvas)

    draw_rounded_rect(draw, (60, 55, 1860, 1025), radius=28, fill=(19, 28, 49, 255), outline=(51, 65, 85, 255), width=2)
    draw_rounded_rect(draw, (60, 55, 1860, 220), radius=28, fill=(30, 41, 59, 255))

    f_tag = load_font(24, bold=True)
    f_title = load_font(54, bold=True)
    f_sub = load_font(30, bold=False)
    f_feat_title = load_font(34, bold=True)
    f_coupon_val = load_font(42, bold=True)

    draw_rounded_rect(draw, (105, 85, 455, 130), radius=10, fill=(37, 99, 235, 255))
    draw.text((125, 94), "INSIDE OVERVIEW & SPECS", font=f_tag, fill=(255, 255, 255, 255))
    draw.text((480, 78), f"{product_name} — Full Review", font=f_title, fill=(255, 255, 255, 255))
    wrapped_res = textwrap.shorten(f"Built to help you {main_result} without coding or monthly fees.", width=95, placeholder="...")
    draw.text((105, 156), wrapped_res, font=f_sub, fill=(148, 163, 184, 255))

    y_positions = [265, 470, 675]
    for idx, feat in enumerate(features[:3]):
        y0 = y_positions[idx]
        draw_rounded_rect(draw, (105, y0, 1340, y0 + 170), radius=20, fill=(15, 23, 42, 255), outline=(59, 130, 246, 200), width=2)
        draw.ellipse((135, y0 + 45, 215, y0 + 125), fill=(245, 158, 11, 255))
        draw.text((163, y0 + 62), str(idx + 1), font=load_font(42, bold=True), fill=(15, 23, 42, 255))

        lines = textwrap.wrap(feat, width=48)[:2]
        text_y = y0 + 42 if len(lines) > 1 else y0 + 62
        for line in lines:
            draw.text((245, text_y), line, font=f_feat_title, fill=(248, 250, 252, 255))
            text_y += 46

    # Expanded full-height Deal & Coupon Card on the right (replaces circular PiP avatar)
    draw_rounded_rect(draw, (1390, 265, 1815, 985), radius=22, fill=(15, 23, 42, 255), outline=(245, 158, 11, 255), width=3)
    draw_rounded_rect(draw, (1390, 265, 1815, 350), radius=22, fill=(136, 19, 55, 255))
    draw.text((1432, 293), "ACTIVE DISCOUNT CODE", font=load_font(25, bold=True), fill=(254, 205, 211, 255))

    draw_rounded_rect(draw, (1420, 380, 1785, 475), radius=14, fill=(255, 255, 255, 255))
    draw.text((1442, 402), coupon_code[:14].upper(), font=f_coupon_val, fill=(225, 29, 72, 255))

    perks = [
        "+ Highest Launch Discount",
        "+ 6 VIP Bonus Packages",
        "+ Direct OTO Upgrade Links",
        "+ Instant Receipt Delivery",
        "+ Official Money-Back Shield",
    ]
    py = 520
    for p in perks:
        draw.text((1422, py), p, font=load_font(23, bold=True), fill=(226, 232, 240, 255))
        py += 58

    draw_rounded_rect(draw, (1420, 860, 1785, 945), radius=14, fill=(37, 99, 235, 255))
    draw.text((1448, 888), "1ST LINK IN DESCRIPTION", font=load_font(22, bold=True), fill=(255, 255, 255, 255))

    draw_rounded_rect(draw, (105, 885, 1340, 985), radius=16, fill=(30, 58, 138, 255), outline=(96, 165, 250, 255), width=2)
    draw.text((140, 918), "Check Description Below: Full Review + OTO Links + Coupon + 6 VIP Bonuses", font=load_font(29, bold=True), fill=(255, 255, 255, 255))

    canvas.convert("RGB").save(out_path, "PNG")


def create_transition_slide(out_path: Path, product_name: str, coupon_code: str):
    """Creates clean studio graphic transition slide before Live Demo (NO presenter photo)."""
    canvas = Image.new("RGBA", (1920, 1080), (11, 17, 32, 255))
    draw = ImageDraw.Draw(canvas)

    draw_rounded_rect(draw, (75, 70, 1845, 1010), radius=30, fill=(19, 28, 49, 255), outline=(59, 130, 246, 255), width=3)
    draw_rounded_rect(draw, (120, 115, 500, 172), radius=12, fill=(220, 38, 38, 255))
    draw.text((145, 129), "LIVE WALKTHROUGH NEXT", font=load_font(24, bold=True), fill=(255, 255, 255, 255))

    draw.text((120, 215), f"Inside {product_name[:34]} — Live Demo", font=load_font(54, bold=True), fill=(255, 255, 255, 255))
    draw.text((120, 295), "Watch the real dashboard and step-by-step workflow in action right now.", font=load_font(29, bold=False), fill=(148, 163, 184, 255))

    draw_rounded_rect(draw, (120, 375, 1800, 775), radius=24, fill=(15, 23, 42, 255), outline=(245, 158, 11, 255), width=2)
    draw.text((165, 418), "WHAT YOU WILL SEE INSIDE THIS WALKTHROUGH:", font=load_font(32, bold=True), fill=(253, 224, 71, 255))

    points = [
        "1. Complete inside dashboard tour & setup speed (zero coding needed)",
        "2. Live execution of the core tools & commercial output quality",
        f"3. Full 6 VIP Bonus Packages breakdown + Coupon [{coupon_code}] right after the demo",
    ]
    py = 500
    for pt in points:
        draw.text((165, py), pt[:86], font=load_font(28, bold=True), fill=(248, 250, 252, 255))
        py += 76

    draw_rounded_rect(draw, (120, 825, 1800, 950), radius=18, fill=(30, 58, 138, 255), outline=(96, 165, 250, 255), width=2)
    draw.text((165, 870), f"First Link in Description: Grab {product_name[:28]} + Code [{coupon_code}] + 6 VIP Bonuses", font=load_font(29, bold=True), fill=(253, 224, 71, 255))

    canvas.convert("RGB").save(out_path, "PNG")


def create_bonuses_slide(out_path: Path, product_name: str, coupon_code: str):
    """Creates 1920x1080 showcase slide for the 6 VIP Bonus Packages (NO presenter photo)."""
    canvas = Image.new("RGBA", (1920, 1080), (15, 23, 42, 255))
    draw = ImageDraw.Draw(canvas)

    draw_rounded_rect(draw, (60, 50, 1860, 205), radius=24, fill=(30, 41, 59, 255), outline=(245, 158, 11, 255), width=3)
    draw.text((100, 75), f"FREE WITH {product_name[:28].upper()} — 6 VIP BONUS PACKAGES", font=load_font(44, bold=True), fill=(253, 224, 71, 255))
    draw.text((100, 142), f"Use Coupon '{coupon_code}' via First Link in Description — Instant Automated Delivery at Checkout!", font=load_font(28, bold=False), fill=(226, 232, 240, 255))

    bonuses = [
        ("VIP BONUS #1", "Rapid Traffic & Buyer Surge Blueprint", "Drive targeted daily clicks to your offers without paid ad waste."),
        ("VIP BONUS #2", "High-Converting Funnel & Bridge Templates", "Ready-to-deploy pages built to double front-end & OTO conversions."),
        ("VIP BONUS #3", "Commercial Client Acquisition Kit", "Outreach scripts, proposals & contracts to land $500-$1,500 clients."),
        ("VIP BONUS #4", "SEO & YouTube #1 Ranking Accelerator", "Rank product & niche campaigns on Google & YouTube fast."),
        ("VIP BONUS #5", "Automated Email Follow-Up Profit Swipes", "Plug-and-play promotional sequences that turn leads into buyers."),
        ("VIP BONUS #6", "Priority Setup Checklist & Scaling Vault", "Step-by-step execution roadmap so you launch in under 30 minutes."),
    ]

    coords = [
        (70, 240), (740, 240),
        (70, 485), (740, 485),
        (70, 730), (740, 730),
    ]
    for (tag, title, desc), (x, y) in zip(bonuses, coords):
        draw_rounded_rect(draw, (x, y, x + 635, y + 215), radius=18, fill=(30, 41, 59, 255), outline=(71, 85, 105, 255), width=2)
        draw_rounded_rect(draw, (x + 24, y + 22, x + 220, y + 62), radius=8, fill=(37, 99, 235, 255))
        draw.text((x + 38, y + 29), tag, font=load_font(21, bold=True), fill=(255, 255, 255, 255))
        draw.text((x + 24, y + 80), title[:38], font=load_font(28, bold=True), fill=(255, 255, 255, 255))
        wrapped = textwrap.wrap(desc, width=44)[:2]
        ty = y + 125
        for line in wrapped:
            draw.text((x + 24, ty), line, font=load_font(22, bold=False), fill=(148, 163, 184, 255))
            ty += 30

    # Full-height How-To-Claim sidebar on the right (replaces circular PiP avatar)
    draw_rounded_rect(draw, (1415, 240, 1855, 945), radius=24, fill=(23, 37, 84, 255), outline=(245, 158, 11, 255), width=3)
    draw_rounded_rect(draw, (1415, 240, 1855, 325), radius=24, fill=(30, 58, 138, 255))
    draw.text((1465, 266), "HOW TO CLAIM:", font=load_font(34, bold=True), fill=(253, 224, 71, 255))

    steps = [
        ("STEP 1", "Click 1st Link Below"),
        ("STEP 2", f"Code: {coupon_code[:14].upper()}"),
        ("STEP 3", "Complete Checkout"),
        ("STEP 4", "Instant Receipt Access"),
    ]
    sy = 355
    for badge_s, line_s in steps:
        draw_rounded_rect(draw, (1440, sy, 1830, sy + 82), radius=12, fill=(15, 23, 42, 255), outline=(59, 130, 246, 200), width=2)
        draw_rounded_rect(draw, (1452, sy + 18, 1548, sy + 62), radius=8, fill=(220, 38, 38, 255))
        draw.text((1462, sy + 28), badge_s, font=load_font(18, bold=True), fill=(255, 255, 255, 255))
        draw.text((1562, sy + 27), line_s[:22], font=load_font(21, bold=True), fill=(248, 250, 252, 255))
        sy += 98

    draw_rounded_rect(draw, (1440, 760, 1830, 920), radius=16, fill=(136, 19, 55, 255), outline=(251, 113, 133, 255), width=2)
    draw.text((1465, 782), "100% AUTOMATED DELIVERY", font=load_font(21, bold=True), fill=(254, 205, 211, 255))
    draw.text((1465, 820), "Unlocked Inside Your Receipt", font=load_font(20, bold=False), fill=(255, 255, 255, 235))
    draw_rounded_rect(draw, (1460, 860, 1810, 903), radius=8, fill=(255, 255, 255, 255))
    draw.text((1505, 871), "FREE VIP BONUS VAULT", font=load_font(20, bold=True), fill=(225, 29, 72, 255))

    canvas.convert("RGB").save(out_path, "PNG")


def create_outro_slide(out_path: Path, product_name: str, coupon_code: str):
    """Creates clean studio Final Verdict & CTA slide for Segment 5 (NO presenter photo)."""
    canvas = Image.new("RGBA", (1920, 1080), (11, 17, 32, 255))
    draw = ImageDraw.Draw(canvas)

    draw_rounded_rect(draw, (75, 70, 1845, 1010), radius=30, fill=(19, 28, 49, 255), outline=(245, 158, 11, 255), width=3)
    draw_rounded_rect(draw, (120, 115, 505, 172), radius=12, fill=(37, 99, 235, 255))
    draw.text((145, 129), "FINAL VERDICT & DEAL LINK", font=load_font(24, bold=True), fill=(255, 255, 255, 255))

    draw.text((120, 215), f"Claim {product_name[:32]} + All 6 VIP Bonuses", font=load_font(52, bold=True), fill=(255, 255, 255, 255))
    draw.text((120, 295), f"Apply Secret Coupon '{coupon_code}' at Checkout Before the Launch Price Expires.", font=load_font(29, bold=False), fill=(253, 224, 71, 255))

    draw_rounded_rect(draw, (120, 375, 1800, 775), radius=24, fill=(15, 23, 42, 255), outline=(59, 130, 246, 255), width=2)
    draw.text((165, 418), "YOUR 3-STEP INSTANT ACCESS CHECKLIST:", font=load_font(32, bold=True), fill=(255, 255, 255, 255))

    o_points = [
        "1. Click the First Link in the Description right below this video.",
        f"2. Enter Discount Coupon [{coupon_code}] on the official checkout page.",
        "3. Access your software + all 6 VIP Bonus Packages instantly inside your receipt!",
    ]
    py = 500
    for opt in o_points:
        draw.text((165, py), opt[:86], font=load_font(28, bold=True), fill=(226, 232, 240, 255))
        py += 76

    draw_rounded_rect(draw, (120, 825, 1800, 950), radius=18, fill=(136, 19, 55, 255), outline=(251, 113, 133, 255), width=3)
    draw.text((165, 870), f"Click 1st Link Below Now  |  Active Coupon: {coupon_code}  |  Full OTO Review in Description", font=load_font(28, bold=True), fill=(255, 255, 255, 255))

    canvas.convert("RGB").save(out_path, "PNG")


def create_demo_overlay_png(out_path: Path, product_name: str, coupon_code: str):
    """Creates transparent 1920x1080 PNG overlay placed on top of Demo video."""
    overlay = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    draw_rounded_rect(draw, (1525, 28, 1885, 80), radius=12, fill=(15, 23, 42, 195), outline=(245, 158, 11, 220), width=2)
    draw.text((1548, 41), f"{product_name[:18]} Live Demo", font=load_font(23, bold=True), fill=(255, 255, 255, 240))

    draw_rounded_rect(draw, (180, 1005, 1740, 1068), radius=14, fill=(15, 23, 42, 230), outline=(225, 29, 72, 255), width=2)
    bar_txt = f"GRAB {product_name.upper()} + COUPON [{coupon_code}] + 6 VIP BONUSES  >>  FIRST LINK IN DESCRIPTION"
    draw.text((225, 1022), bar_txt[:88], font=load_font(26, bold=True), fill=(253, 224, 71, 255))

    overlay.save(out_path, "PNG")


def create_youtube_thumbnail(presenter_path: Path, out_path: Path, product_name: str, coupon_code: str):
    """Generates high-CTR 1280x720 YouTube thumbnail with adaptive title sizing."""
    base = Image.open(presenter_path).convert("RGBA").resize((1280, 720), Image.Resampling.LANCZOS)
    shifted = Image.new("RGBA", (1280, 720), (15, 23, 42, 255))
    shifted.paste(base, (220, 0))

    grad = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grad)
    for x in range(780):
        alpha = int(245 * (1 - (x / 780) ** 1.4))
        gdraw.line([(x, 0), (x, 720)], fill=(11, 17, 32, alpha))

    thumb = Image.alpha_composite(shifted, grad)
    draw = ImageDraw.Draw(thumb)

    clean_title = product_name.strip().upper()[:22]
    t_size = 64 if len(clean_title) <= 13 else (50 if len(clean_title) <= 18 else 40)
    t_y = 84 if t_size >= 60 else (92 if t_size >= 50 else 98)

    draw_rounded_rect(draw, (45, 55, 700, 185), radius=18, fill=(37, 99, 235, 255), outline=(255, 255, 255, 255), width=3)
    draw.text((72, t_y), clean_title, font=load_font(t_size, bold=True), fill=(255, 255, 255, 255))

    draw_rounded_rect(draw, (45, 215, 660, 345), radius=18, fill=(220, 38, 38, 255))
    draw.text((75, 242), "FULL REVIEW + DEMO", font=load_font(54, bold=True), fill=(255, 255, 255, 255))

    draw_rounded_rect(draw, (45, 370, 680, 500), radius=18, fill=(30, 41, 59, 255), outline=(245, 158, 11, 255), width=4)
    draw.text((75, 398), "6 VIP BONUSES + OTOs", font=load_font(50, bold=True), fill=(253, 224, 71, 255))

    draw_rounded_rect(draw, (45, 540, 560, 645), radius=16, fill=(255, 255, 255, 255))
    draw.text((72, 566), f"COUPON: {coupon_code[:12].upper()}", font=load_font(42, bold=True), fill=(15, 23, 42, 255))

    thumb.convert("RGB").save(out_path, "JPEG", quality=95)


# ==============================================================================
# MULTI-LAYER BULLETPROOF STUDIO VOICE ENGINE (Immune to Azure/GitHub IP Blocks)
# ==============================================================================

def _download_file(urls, dest: Path):
    for url in urls:
        try:
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
            if dest.exists() and dest.stat().st_size > 500:
                return True
        except Exception as e:
            print(f"[WARN] Download attempt failed ({url}): {e}")
    return False


def ensure_piper_studio_ready():
    """Downloads standalone Piper neural TTS + Ryan High HD studio male voice once per job."""
    piper_bin = PIPER_CACHE / "piper" / "piper"
    model_onnx = PIPER_CACHE / "en_US-ryan-high.onnx"
    model_json = PIPER_CACHE / "en_US-ryan-high.onnx.json"

    PIPER_CACHE.mkdir(parents=True, exist_ok=True)

    if not piper_bin.exists():
        print("[TTS] Installing Offline Studio Neural Engine (Piper Linux x86_64)...")
        tar_path = PIPER_CACHE / "piper_linux.tar.gz"
        ok = _download_file(
            ["https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz"],
            tar_path
        )
        if not ok:
            return None, None
        with tarfile.open(tar_path, "r:gz") as tf:
            tf.extractall(PIPER_CACHE)
        piper_bin.chmod(0o755)

    if not model_onnx.exists() or not model_json.exists():
        print("[TTS] Downloading Studio Broadcaster Neural Model (en_US-ryan-high)...")
        ok_m = _download_file(
            [
                "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/high/en_US-ryan-high.onnx",
                "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx",
            ],
            model_onnx
        )
        ok_j = _download_file(
            [
                "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/high/en_US-ryan-high.onnx.json",
                "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx.json",
            ],
            model_json
        )
        if not (ok_m and ok_j):
            return None, None

    return piper_bin, model_onnx


def _try_elevenlabs(text: str, out_mp3: Path) -> bool:
    api_key = (os.getenv("ELEVENLABS_API_KEY") or "").strip()
    if not api_key or requests is None:
        return False
    try:
        voice_id = "nPczCjzI2devNBz1zQrb"
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.50, "similarity_boost": 0.78}
            },
            timeout=45
        )
        if resp.status_code == 200 and len(resp.content) > 2000:
            out_mp3.write_bytes(resp.content)
            return True
    except Exception as e:
        print(f"[WARN] ElevenLabs TTS skipped: {e}")
    return False


async def _try_edge_tts(text: str, preferred_voice: str, out_mp3: Path) -> bool:
    if edge_tts is None:
        return False
    candidates = []
    for v in [preferred_voice, "en-US-GuyNeural", "en-US-ChristopherNeural"]:
        if v and v not in candidates:
            candidates.append(v)

    for v in candidates:
        try:
            comm = edge_tts.Communicate(text, v)
            await asyncio.wait_for(comm.save(str(out_mp3)), timeout=15)
            if out_mp3.exists() and out_mp3.stat().st_size > 2000:
                return True
        except Exception as e:
            print(f"[INFO] Edge-TTS ({v}) unavailable on cloud IP: {type(e).__name__}")
    return False


def _try_piper_studio(text: str, out_mp3: Path) -> bool:
    if sys.platform != "linux" or requests is None:
        return False
    try:
        piper_bin, model_onnx = ensure_piper_studio_ready()
        if not piper_bin or not model_onnx:
            return False
        raw_wav = out_mp3.with_suffix(".piper.wav")
        env = os.environ.copy()
        piper_lib_dir = str(piper_bin.parent.resolve())
        env["LD_LIBRARY_PATH"] = f"{piper_lib_dir}:{env.get('LD_LIBRARY_PATH', '')}"

        subprocess.run(
            [
                str(piper_bin),
                "--model", str(model_onnx),
                "--length_scale", "0.97",
                "--sentence_silence", "0.24",
                "--output_file", str(raw_wav),
            ],
            input=text.encode("utf-8"),
            env=env,
            check=True,
        )
        if not raw_wav.exists() or raw_wav.stat().st_size < 1000:
            return False

        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(raw_wav),
                "-af", "highpass=f=75,acompressor=threshold=-18dB:ratio=2.2:attack=15:release=120,loudnorm=I=-16:TP=-1.5:LRA=11",
                "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k",
                str(out_mp3)
            ],
            check=True
        )
        raw_wav.unlink(missing_ok=True)
        return out_mp3.exists() and out_mp3.stat().st_size > 2000
    except Exception as e:
        print(f"[WARN] Piper Studio TTS failed: {e}")
        return False


def _try_gtts_broadcast(text: str, out_mp3: Path) -> bool:
    if gTTS is None:
        return False
    try:
        raw_gtts = out_mp3.with_suffix(".gtts.mp3")
        tts = gTTS(text=text, lang="en", tld="com", slow=False)
        tts.save(str(raw_gtts))
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(raw_gtts),
                "-af", "atempo=1.06,highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11",
                "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k",
                str(out_mp3)
            ],
            check=True
        )
        raw_gtts.unlink(missing_ok=True)
        return out_mp3.exists() and out_mp3.stat().st_size > 2000
    except Exception as e:
        print(f"[WARN] gTTS fallback failed: {e}")
        return False


def _try_espeak_emergency(text: str, out_mp3: Path) -> bool:
    raw_wav = out_mp3.with_suffix(".espeak.wav")
    subprocess.run(["espeak-ng", "-v", "en-us", "-s", "162", "-w", str(raw_wav), text], check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(raw_wav), "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", str(out_mp3)],
        check=True
    )
    raw_wav.unlink(missing_ok=True)
    return True


async def synth_voice(text: str, preferred_voice: str, out_mp3: Path):
    """Synthesizes speech and locks the winning engine so all segments share one identical voice."""
    global _LOCKED_TTS_ENGINE

    if _LOCKED_TTS_ENGINE == "elevenlabs" and _try_elevenlabs(text, out_mp3):
        return
    if _LOCKED_TTS_ENGINE == "edge" and await _try_edge_tts(text, preferred_voice, out_mp3):
        return
    if _LOCKED_TTS_ENGINE == "piper" and _try_piper_studio(text, out_mp3):
        return
    if _LOCKED_TTS_ENGINE == "gtts" and _try_gtts_broadcast(text, out_mp3):
        return

    if _LOCKED_TTS_ENGINE is None:
        if _try_elevenlabs(text, out_mp3):
            _LOCKED_TTS_ENGINE = "elevenlabs"
            print("[TTS] Locked Voice Engine: ElevenLabs Studio")
            return
        if await _try_edge_tts(text, preferred_voice, out_mp3):
            _LOCKED_TTS_ENGINE = "edge"
            print("[TTS] Locked Voice Engine: Edge Neural")
            return
        if _try_piper_studio(text, out_mp3):
            _LOCKED_TTS_ENGINE = "piper"
            print("[TTS] Locked Voice Engine: Piper Studio HD (en_US-ryan-high)")
            return
        if _try_gtts_broadcast(text, out_mp3):
            _LOCKED_TTS_ENGINE = "gtts"
            print("[TTS] Locked Voice Engine: Broadcast gTTS")
            return

    if _try_piper_studio(text, out_mp3):
        return
    if _try_gtts_broadcast(text, out_mp3):
        return
    _try_espeak_emergency(text, out_mp3)


# ==============================================================================
# REAL-TIME AUDIO-SYNCHRONIZED LIP-SYNC ENGINE (Segment 1 Presenter Hook Only)
# ==============================================================================

def extract_lipsync_states(wav_path: Path, total_frames: int, fps: int = 30) -> list:
    """
    Analyzes 16-bit mono PCM WAV audio frame-by-frame at 30 FPS and returns
    a list of (mouth_level_0_to_5, blink_level_0_to_2) synchronized to speech.
    """
    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        n_samples = wf.getnframes()
        raw_bytes = wf.readframes(n_samples)

    samples = array.array("h")
    samples.frombytes(raw_bytes)
    if sys.byteorder == "big":
        samples.byteswap()

    raw_rms = []
    for f_idx in range(total_frames):
        s0 = int(f_idx * sr / fps)
        s1 = int((f_idx + 1) * sr / fps)
        if s0 >= len(samples):
            raw_rms.append(0.0)
            continue
        chunk = samples[s0:min(s1, len(samples))]
        if not chunk:
            raw_rms.append(0.0)
            continue
        sq_sum = sum(int(v) * int(v) for v in chunk)
        raw_rms.append(math.sqrt(sq_sum / len(chunk)))

    voiced = sorted(v for v in raw_rms if v > 80.0)
    ref_peak = voiced[int(0.90 * (len(voiced) - 1))] if voiced else 4000.0
    ref_peak = max(ref_peak, 500.0)

    mouth_levels = []
    smoothed = 0.0
    for f_idx, val in enumerate(raw_rms):
        norm = min(1.0, val / ref_peak)
        if norm < 0.09:
            target = 0.0
        else:
            # Natural syllabic jaw cadence during sustained vowels
            cadence = 0.80 + 0.20 * math.sin(2.0 * math.pi * 4.4 * (f_idx / fps))
            target = min(1.0, ((norm - 0.09) / 0.91) ** 0.78 * cadence)

        # Asymmetric jaw physics: snappy opening, smooth natural closing
        if target > smoothed:
            smoothed = 0.65 * target + 0.35 * smoothed
        else:
            smoothed = 0.42 * target + 0.58 * smoothed

        lvl = int(round(min(1.0, max(0.0, smoothed)) * 5.0))
        mouth_levels.append(lvl)

    # Settle cleanly at start and end of intro clip
    if len(mouth_levels) >= 4:
        mouth_levels[0] = 0
        mouth_levels[-2] = min(mouth_levels[-2], 1)
        mouth_levels[-1] = 0

    # Natural eye blinks every ~3.2s (preferring brief speech dips)
    blink_levels = [0] * total_frames
    next_blink = 72
    while next_blink < total_frames - 8:
        # Search small window for lowest mouth aperture (natural pause blink)
        best_f = min(range(next_blink, min(next_blink + 18, total_frames - 6)), key=lambda i: mouth_levels[i])
        for offset, b_val in [(0, 1), (1, 2), (2, 2), (3, 1)]:
            if best_f + offset < total_frames:
                blink_levels[best_f + offset] = b_val
        next_blink = best_f + 98

    return list(zip(mouth_levels, blink_levels))


def render_talking_presenter_segment(
    presenter_base: Path,
    visemes_png: Path,
    slide_img: Path,
    audio_path: Path,
    out_mp4: Path,
) -> float:
    """Renders Segment 1 with real audio-synced lip movement, natural blinking, and lower-third banner."""
    if not visemes_png.exists():
        return render_image_audio_segment(slide_img, audio_path, out_mp4)

    dur = get_media_duration(audio_path)
    fps = 30
    total_frames = max(30, int(math.ceil(dur * fps)) + 2)

    sync_wav = WORK_DIR / "seg1_lipsync.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(audio_path), "-ac", "1", "-ar", "16000", "-f", "wav", str(sync_wav)],
        check=True,
    )
    states = extract_lipsync_states(sync_wav, total_frames=total_frames, fps=fps)
    sync_wav.unlink(missing_ok=True)

    base_rgb = Image.open(presenter_base).convert("RGB").resize((1920, 1080), Image.Resampling.LANCZOS)
    sheet = Image.open(visemes_png).convert("RGB")
    overlay_path = slide_img.with_suffix(".overlay.png")
    overlay_rgba = Image.open(overlay_path).convert("RGBA") if overlay_path.exists() else None

    mouth_patches = [
        sheet.crop((0, i * MOUTH_H, MOUTH_W, (i + 1) * MOUTH_H))
        for i in range(5)
    ]
    blink_patches = [
        sheet.crop((0, 5 * MOUTH_H, BLINK_W, 5 * MOUTH_H + BLINK_H)),
        sheet.crop((0, 5 * MOUTH_H + BLINK_H, BLINK_W, 5 * MOUTH_H + 2 * BLINK_H)),
    ]

    frame_bytes_cache = {}

    def get_composited_bytes(m_lvl: int, b_lvl: int) -> bytes:
        key = (m_lvl, b_lvl)
        if key not in frame_bytes_cache:
            canvas = base_rgb.copy()
            if m_lvl > 0:
                canvas.paste(mouth_patches[m_lvl - 1], MOUTH_ROI_XY)
            if b_lvl > 0:
                canvas.paste(blink_patches[b_lvl - 1], BLINK_ROI_XY)
            if overlay_rgba is not None:
                canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay_rgba).convert("RGB")
            frame_bytes_cache[key] = canvas.tobytes()
        return frame_bytes_cache[key]

    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-pix_fmt", "rgb24", "-s", "1920x1080", "-framerate", str(fps),
        "-i", "-",
        "-i", str(audio_path),
        "-t", f"{dur:.2f}",
        "-vf", "setsar=1,fps=30,format=yuv420p",
        "-af", "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,apad",
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        str(out_mp4),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for m_lvl, b_lvl in states:
            proc.stdin.write(get_composited_bytes(m_lvl, b_lvl))
    except (BrokenPipeError, OSError):
        pass
    finally:
        if proc.stdin:
            try:
                proc.stdin.close()
            except Exception:
                pass
    ret = proc.wait()
    if ret != 0 or not out_mp4.exists():
        raise RuntimeError(f"FFmpeg talking presenter render failed with exit code {ret}")
    return dur


# ==============================================================================
# MEDIA HELPERS & WISTIA / YOUTUBE / VIMEO / MP4 DEMO ENGINE
# ==============================================================================

def get_media_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    return max(float(out), 1.0)


def has_audio(path: Path) -> bool:
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "csv=p=0",
        str(path)
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    return len(out) > 0


def render_image_audio_segment(img_path: Path, audio_path: Path, out_mp4: Path):
    dur = get_media_duration(audio_path)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", "30", "-i", str(img_path),
        "-i", str(audio_path),
        "-t", f"{dur:.2f}",
        "-vf", "scale=1920:1080,setsar=1,fps=30,format=yuv420p",
        "-af", "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,apad",
        "-c:v", "libx264", "-tune", "stillimage", "-preset", "veryfast", "-crf", "21",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        str(out_mp4)
    ]
    subprocess.run(cmd, check=True)
    return dur


def has_video_stream(path: Path) -> bool:
    """Verifies via ffprobe that a downloaded file actually contains a valid video stream."""
    if not path.exists() or path.stat().st_size <= 10000:
        return False
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path)
        ]
        out = subprocess.check_output(cmd, text=True).strip()
        return len(out) > 0
    except Exception:
        return False


def normalize_demo_url(raw_input: str) -> tuple:
    """Normalizes demo_url and detects Wistia links/embeds across all formats."""
    if not raw_input or not raw_input.strip():
        return "", False

    cleaned = html.unescape(raw_input.strip())
    reserved_words = {
        "iframe", "medias", "external", "popover", "player",
        "assets", "deliveries", "oembed", "embed", "projects", "channels"
    }

    wistia_patterns = [
        r"wistia\.(?:com|net)/(?:embed/(?:iframe|medias)|medias)/([a-zA-Z0-9]+)",
        r"wi\.st/(?:medias|embed/iframe|embed)/([a-zA-Z0-9]+)",
        r"[?&](?:wvideo|wmediaid)=([a-zA-Z0-9]+)",
        r"wistia_async_([a-zA-Z0-9]+)",
    ]
    for pat in wistia_patterns:
        m = re.search(pat, cleaned, flags=re.IGNORECASE)
        if m:
            media_id = m.group(1)
            if media_id.lower() not in reserved_words and len(media_id) >= 6:
                return f"https://fast.wistia.net/embed/iframe/{media_id}", True

    if not cleaned.lower().startswith(("http://", "https://")):
        href_match = re.search(r'href=["\'](https?://[^"\'\s<>]+)["\']', cleaned, flags=re.IGNORECASE)
        url_match = re.search(r'(https?://[^"\'\s<>]+)', cleaned, flags=re.IGNORECASE)
        if href_match:
            cleaned = href_match.group(1)
        elif url_match:
            cleaned = url_match.group(1)
        elif re.match(r"^(?:[a-zA-Z0-9-]+\.)+(?:wistia\.com|wistia\.net|wi\.st|youtube\.com|youtu\.be|vimeo\.com)/", cleaned, flags=re.IGNORECASE):
            cleaned = "https://" + cleaned
        else:
            return "", False

    lower_url = cleaned.lower()
    streaming_domains = (
        "youtube.com",
        "youtu.be",
        "vimeo.com",
        "wistia.com",
        "wistia.net",
        "wi.st",
    )
    is_streaming = any(d in lower_url for d in streaming_domains)
    return cleaned, is_streaming


def download_or_build_demo(demo_url: str, raw_demo_path: Path, fallback_slide: Path):
    target_url, is_streaming = normalize_demo_url(demo_url)
    if target_url:
        print(f"Downloading demo video from: {target_url}")
        raw_demo_path.unlink(missing_ok=True)
        try:
            if is_streaming:
                temp_prefix = raw_demo_path.parent / "ytdlp_demo_raw"
                for old_f in raw_demo_path.parent.glob("ytdlp_demo_raw.*"):
                    old_f.unlink(missing_ok=True)

                cmd = [
                    "yt-dlp",
                    "--no-playlist",
                    "-f", (
                        "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
                        "bestvideo[height<=1080]+bestaudio/"
                        "best[height<=1080][ext=mp4]/"
                        "best[height<=1080]/best"
                    ),
                    "--merge-output-format", "mp4",
                    "-o", f"{temp_prefix}.%(ext)s",
                    target_url
                ]
                subprocess.run(cmd, check=True)

                downloaded = [
                    p for p in raw_demo_path.parent.glob("ytdlp_demo_raw.*")
                    if p.suffix.lower() not in (".part", ".ytdl", ".temp")
                ]
                if downloaded:
                    shutil.move(str(downloaded[0]), str(raw_demo_path))
            else:
                with requests.get(target_url, stream=True, timeout=120) as r:
                    r.raise_for_status()
                    content_type = (r.headers.get("Content-Type") or "").lower()
                    if "text/html" in content_type:
                        raise ValueError(f"URL returned HTML webpage ({content_type}) instead of a direct video stream")
                    with open(raw_demo_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)

            if has_video_stream(raw_demo_path):
                return
            else:
                raw_demo_path.unlink(missing_ok=True)
                print("Warning: Downloaded file did not contain a valid video stream. Falling back to placeholder.")
        except Exception as e:
            raw_demo_path.unlink(missing_ok=True)
            print(f"Warning: Could not download demo_url ({e}). Generating clean placeholder demo segment.")

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", "30", "-i", str(fallback_slide),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", "10",
        "-vf", "scale=1920:1080,setsar=1,fps=30,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        str(raw_demo_path)
    ]
    subprocess.run(cmd, check=True)


def process_demo_break_fingerprint(raw_demo: Path, overlay_png: Path, out_demo: Path) -> float:
    """Applies Digital Fingerprint Modification (color shift, 1.01x tempo, watermark + CTA bar, strip metadata)."""
    v_filter = (
        "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,"
        "eq=contrast=1.02:brightness=0.01:saturation=1.03,"
        "setpts=0.99*PTS[base];"
        "[base][1:v]overlay=0:0,format=yuv420p[outv]"
    )
    if has_audio(raw_demo):
        cmd = [
            "ffmpeg", "-y",
            "-i", str(raw_demo),
            "-i", str(overlay_png),
            "-filter_complex", f"{v_filter};[0:a]atempo=1.01,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[outa]",
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-map_metadata", "-1",
            str(out_demo)
        ]
    else:
        dur = get_media_duration(raw_demo) * 0.99
        cmd = [
            "ffmpeg", "-y",
            "-i", str(raw_demo),
            "-i", str(overlay_png),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", f"{dur:.2f}",
            "-filter_complex", v_filter,
            "-map", "[outv]", "-map", "2:a:0",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-map_metadata", "-1",
            str(out_demo)
        ]
    subprocess.run(cmd, check=True)
    return get_media_duration(out_demo)


def fmt_ts(seconds: float) -> str:
    s = int(round(seconds))
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def main():
    parser = argparse.ArgumentParser(description="Automated Review Video Factory v5")
    parser.add_argument("--product_name", default=os.getenv("PRODUCT_NAME", "AI Secret Image Codebook"))
    parser.add_argument("--main_result", default=os.getenv("MAIN_RESULT", "generate studio-grade commercial graphics using secret style parameters"))
    parser.add_argument("--feature_1", default=os.getenv("FEATURE_1", "Secret Style Reference Matrix & Optical Camera Lighting Tokens"))
    parser.add_argument("--feature_2", default=os.getenv("FEATURE_2", "Multi-Scene Character Consistency Lock & Crisp Typography Syntax"))
    parser.add_argument("--feature_3", default=os.getenv("FEATURE_3", "Print-On-Demand Vector Isolation & Commercial Product Mockup Codes"))
    parser.add_argument("--coupon_code", default=os.getenv("COUPON_CODE", "CODEBOOKVIP"))
    parser.add_argument("--demo_url", default=os.getenv("DEMO_URL", ""))
    parser.add_argument("--affiliate_link", default=os.getenv("AFFILIATE_LINK", "https://otoslinks.com/"))
    parser.add_argument("--voice", default=os.getenv("VOICE_NAME", "en-US-GuyNeural"))
    args = parser.parse_args()

    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    presenter_base = ASSETS_DIR / "presenter_base.png"
    presenter_visemes = ASSETS_DIR / "presenter_visemes.png"
    ensure_presenter_assets(presenter_base)

    # 1. Build High-Converting Script Segments
    script_seg1 = (
        "Hey, welcome back to my channel! Before you grab anything from the regular sales page at full price, "
        "check the first link in the description right below this video. I have unlocked the biggest active discount coupon, "
        "plus 6 massive VIP Bonus Packages waiting for you completely free at checkout."
    )
    script_seg2 = (
        f"Today, we are talking about {args.product_name}, a powerful new system built to help you {args.main_result} "
        f"without guesswork or monthly fees. Right from one organized vault, {args.product_name} gives you: "
        f"First, {args.feature_1}. "
        f"Second, {args.feature_2}. "
        f"And third, {args.feature_3}. "
        f"Down below in the description, you will find the full written review, direct O-T-O upgrade details, "
        f"your special discount code {args.coupon_code}, and the complete list of all 6 VIP Bonus Packages."
    )
    script_seg3 = (
        f"Now, let us skip the hype and check out {args.product_name} from the inside! "
        "Stick around right after this live demo so I can walk you through all 6 VIP Bonus Packages, "
        "and remember, everything you need is in the first link below. Let us dive in!"
    )
    script_seg4_bonuses = (
        f"Now that you have seen {args.product_name} in action, here is a quick look at the 6 exclusive VIP Bonus Packages "
        "you get completely free when you pick it up through the first link in the description below. "
        "You are getting our Rapid Traffic Surge Blueprint, High-Converting Funnel Templates, Commercial Client Acquisition Kit, "
        "YouTube and Google Ranking Accelerator, Automated Email Profit Swipes, and our Priority Scaling Checklist. "
        f"All 6 bonus packages are delivered automatically inside your receipt the moment you check out with coupon code {args.coupon_code}."
    )
    script_seg5_outro = (
        f"That wraps up our full review and live walkthrough of {args.product_name}. "
        f"Click the first link in the description right now to check out the full review, apply discount coupon {args.coupon_code}, "
        "and lock in all 6 VIP Bonus Packages before the launch deal expires. Thanks for watching, and I will see you inside!"
    )

    # 2. Generate Voiceovers via Multi-Layer Studio Neural Engine
    a1 = WORK_DIR / "a1.mp3"
    a2 = WORK_DIR / "a2.mp3"
    a3 = WORK_DIR / "a3.mp3"
    a4 = WORK_DIR / "a4.mp3"
    a5 = WORK_DIR / "a5.mp3"

    async def build_all_audio():
        await synth_voice(script_seg1, args.voice, a1)
        await synth_voice(script_seg2, args.voice, a2)
        await synth_voice(script_seg3, args.voice, a3)
        await synth_voice(script_seg4_bonuses, args.voice, a4)
        await synth_voice(script_seg5_outro, args.voice, a5)

    asyncio.run(build_all_audio())

    # 3. Generate Visual Slides & High-CTR Thumbnail
    s1_img = WORK_DIR / "slide1_hook.png"
    s2_img = WORK_DIR / "slide2_product.png"
    s3_img = WORK_DIR / "slide3_transition.png"
    s4_img = WORK_DIR / "slide4_bonuses.png"
    s5_img = WORK_DIR / "slide5_outro.png"
    demo_overlay = WORK_DIR / "demo_overlay.png"
    thumb_path = OUT_DIR / "youtube_thumbnail.jpg"

    # Segment 1 ONLY: Presenter with lower-third overlay
    create_presenter_slide(
        presenter_base, s1_img,
        badge_top="SPECIAL LAUNCH ALERT",
        headline=f"{args.product_name} Review + Exclusive Coupon",
        subline=f"Use Code: {args.coupon_code} + Claim 6 VIP Bonus Packages (1st Link Below)"
    )
    # Segments 2, 3, 4, 5: Pure clean studio graphics (NO presenter face)
    create_product_cutaway_slide(
        s2_img,
        product_name=args.product_name,
        main_result=args.main_result,
        features=[args.feature_1, args.feature_2, args.feature_3],
        coupon_code=args.coupon_code
    )
    create_transition_slide(s3_img, args.product_name, args.coupon_code)
    create_bonuses_slide(s4_img, args.product_name, args.coupon_code)
    create_outro_slide(s5_img, args.product_name, args.coupon_code)
    create_demo_overlay_png(demo_overlay, args.product_name, args.coupon_code)
    create_youtube_thumbnail(presenter_base, thumb_path, args.product_name, args.coupon_code)

    # 4. Render Video Segments
    v1 = WORK_DIR / "seg1.mp4"
    v2 = WORK_DIR / "seg2.mp4"
    v3 = WORK_DIR / "seg3.mp4"
    v_demo = WORK_DIR / "seg_demo.mp4"
    v4 = WORK_DIR / "seg4.mp4"
    v5 = WORK_DIR / "seg5.mp4"

    # Segment 1: Real audio-synced lip movement + eye blink + lower-third
    d1 = render_talking_presenter_segment(presenter_base, presenter_visemes, s1_img, a1, v1)
    # Segments 2..5: Clean full-screen slides & live demo
    d2 = render_image_audio_segment(s2_img, a2, v2)
    d3 = render_image_audio_segment(s3_img, a3, v3)

    raw_demo = WORK_DIR / "raw_demo.mp4"
    download_or_build_demo(args.demo_url, raw_demo, s2_img)
    d_demo = process_demo_break_fingerprint(raw_demo, demo_overlay, v_demo)

    d4 = render_image_audio_segment(s4_img, a4, v4)
    d5 = render_image_audio_segment(s5_img, a5, v5)

    # 5. Concatenate All Segments Seamlessly
    concat_txt = WORK_DIR / "concat_list.txt"
    segments = [v1, v2, v3, v_demo, v4, v5]
    with open(concat_txt, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(f"file '{seg.resolve().as_posix()}'\n")

    final_mp4 = OUT_DIR / "final_youtube_video.mp4"
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-vf", "fps=30,format=yuv420p,setsar=1",
        "-af", "aresample=44100",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        str(final_mp4)
    ]
    subprocess.run(cmd_concat, check=True)

    # 6. Build YouTube SEO Title, Description & Chapters File
    t0 = 0.0
    t_specs = d1
    t_demo = d1 + d2 + d3
    t_bonus = t_demo + d_demo
    t_outro = t_bonus + d4

    seo_text = f"""=========================================================
YOUTUBE HIGH-CTR TITLES (Playlist Cluster Strategy)
=========================================================
Title 1 (Main Review):
{args.product_name} Review: Full Demo + OTOs 🔴 {args.product_name} Review + Coupon + 6 VIP Bonuses 🔴

Title 2 (OTO & Bundle Angle):
{args.product_name} OTO Links & Bundle Deal 🔴 {args.product_name} Walkthrough + Honest Review

Title 3 (Playlist Name):
{args.product_name} Review & Demo | {args.product_name} OTOs, Coupon & 6 VIP Bonuses

=========================================================
YOUTUBE DESCRIPTION (Copy & Paste)
=========================================================
👉 Grab {args.product_name} + All 6 VIP Bonus Packages Here: {args.affiliate_link}
🔥 Apply Secret Discount Coupon at Checkout: {args.coupon_code}

In this {args.product_name} review and live walkthrough, we jump straight inside the software so you can see how {args.product_name} helps you {args.main_result}—plus a full look at the OTO upgrades, active coupon code, and my 6 exclusive VIP Bonus Packages.

⏱️ Video Chapters:
{fmt_ts(t0)} {args.product_name} Intro & Active Coupon
{fmt_ts(t_specs)} What Is {args.product_name}? (Top 3 Features)
{fmt_ts(t_demo)} {args.product_name} Live Inside Demo Walkthrough
{fmt_ts(t_bonus)} 6 Exclusive VIP Bonus Packages Breakdown
{fmt_ts(t_outro)} Final Verdict & How to Claim Your Deal

#{args.product_name.replace(' ', '')} #{args.product_name.replace(' ', '')}Review #{args.product_name.replace(' ', '')}Demo #{args.product_name.replace(' ', '')}OTOs
"""
    (OUT_DIR / "youtube_seo_pack.txt").write_text(seo_text, encoding="utf-8")
    print("SUCCESS! Video, Thumbnail, and SEO Pack generated in:", OUT_DIR)


if __name__ == "__main__":
    main()

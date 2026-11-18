#!/usr/bin/env python3
import os
import sys
import math
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


def ensure_presenter_assets(presenter_base: Path, presenter_circle: Path):
    """Fallback generator in case assets folder was ever missing an image."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    if not presenter_base.exists():
        img = Image.new("RGB", (1920, 1080), (15, 23, 42))
        img.save(presenter_base, "PNG")
    if not presenter_circle.exists():
        src = Image.open(presenter_base).convert("RGB")
        w, h = src.size
        s = min(w, h)
        crop = src.crop(((w - s) // 2, 0, (w - s) // 2 + s, s)).resize((400, 400), Image.Resampling.LANCZOS)
        pip = Image.new("RGBA", (430, 430), (0, 0, 0, 0))
        d = ImageDraw.Draw(pip)
        d.ellipse((4, 4, 426, 426), fill=(15, 23, 42, 235), outline=(245, 158, 11, 255), width=8)
        mask = Image.new("L", (400, 400), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 400, 400), fill=255)
        pip.paste(crop, (15, 15), mask)
        pip.save(presenter_circle, "PNG")


def create_presenter_slide(presenter_path: Path, out_path: Path, badge_top: str, headline: str, subline: str):
    """Creates 1920x1080 presenter frame with broadcast lower-third banner."""
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

    combined = Image.alpha_composite(base, overlay).convert("RGB")
    combined.save(out_path, "PNG")


def create_product_cutaway_slide(
    presenter_circle_path: Path,
    out_path: Path,
    product_name: str,
    main_result: str,
    features: list,
    coupon_code: str,
):
    """Creates dynamic B-Roll cutaway slide with 3 features, coupon box, and circular presenter PiP."""
    canvas = Image.new("RGBA", (1920, 1080), (11, 17, 32, 255))
    draw = ImageDraw.Draw(canvas)

    draw_rounded_rect(draw, (60, 55, 1860, 1025), radius=28, fill=(19, 28, 49, 255), outline=(51, 65, 85, 255), width=2)
    draw_rounded_rect(draw, (60, 55, 1860, 220), radius=28, fill=(30, 41, 59, 255))

    f_tag = load_font(24, bold=True)
    f_title = load_font(54, bold=True)
    f_sub = load_font(30, bold=False)
    f_feat_title = load_font(34, bold=True)
    f_coupon_lbl = load_font(24, bold=True)
    f_coupon_val = load_font(44, bold=True)

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

    draw_rounded_rect(draw, (1390, 265, 1815, 535), radius=22, fill=(136, 19, 55, 255), outline=(251, 113, 133, 255), width=3)
    draw.text((1430, 295), "ACTIVE DISCOUNT CODE", font=f_coupon_lbl, fill=(254, 205, 211, 255))
    draw_rounded_rect(draw, (1420, 345, 1785, 435), radius=14, fill=(255, 255, 255, 255))
    draw.text((1445, 365), coupon_code[:14].upper(), font=f_coupon_val, fill=(225, 29, 72, 255))
    draw.text((1430, 458), "+ 6 VIP Bonus Packages", font=load_font(26, bold=True), fill=(253, 224, 71, 255))
    draw.text((1430, 492), "First Link in Description", font=load_font(22, bold=False), fill=(255, 255, 255, 230))

    if presenter_circle_path.exists():
        pip = Image.open(presenter_circle_path).convert("RGBA").resize((410, 410), Image.Resampling.LANCZOS)
        canvas.paste(pip, (1398, 575), pip)

    draw_rounded_rect(draw, (105, 885, 1340, 985), radius=16, fill=(30, 58, 138, 255), outline=(96, 165, 250, 255), width=2)
    draw.text((140, 918), "Check Description Below: Full Review + OTO Links + Coupon + 6 VIP Bonuses", font=load_font(29, bold=True), fill=(255, 255, 255, 255))

    canvas.convert("RGB").save(out_path, "PNG")


def create_bonuses_slide(presenter_circle_path: Path, out_path: Path, product_name: str, coupon_code: str):
    """Creates 1920x1080 showcase slide for the 6 VIP Bonus Packages."""
    canvas = Image.new("RGBA", (1920, 1080), (15, 23, 42, 255))
    draw = ImageDraw.Draw(canvas)

    draw_rounded_rect(draw, (60, 50, 1860, 205), radius=24, fill=(30, 41, 59, 255), outline=(245, 158, 11, 255), width=3)
    draw.text((100, 75), f"FREE WITH {product_name.upper()} — 6 VIP BONUS PACKAGES", font=load_font(46, bold=True), fill=(253, 224, 71, 255))
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

    draw_rounded_rect(draw, (1415, 240, 1855, 945), radius=24, fill=(23, 37, 84, 255), outline=(245, 158, 11, 255), width=3)
    draw.text((1455, 275), "HOW TO CLAIM:", font=load_font(34, bold=True), fill=(253, 224, 71, 255))
    steps = [
        "1. Click 1st Link Below",
        f"2. Apply Code: {coupon_code}",
        "3. Bonuses Unlock Inside",
        "   Your Receipt Instantly!"
    ]
    sy = 340
    for s in steps:
        draw.text((1445, sy), s, font=load_font(26, bold=True), fill=(255, 255, 255, 255))
        sy += 45

    if presenter_circle_path.exists():
        pip = Image.open(presenter_circle_path).convert("RGBA").resize((360, 360), Image.Resampling.LANCZOS)
        canvas.paste(pip, (1455, 555), pip)

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
    """Generates high-CTR 1280x720 YouTube thumbnail."""
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

    draw_rounded_rect(draw, (45, 55, 700, 185), radius=18, fill=(37, 99, 235, 255), outline=(255, 255, 255, 255), width=3)
    draw.text((75, 82), product_name[:16].upper(), font=load_font(68, bold=True), fill=(255, 255, 255, 255))

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
        # Brian - Deep, trustworthy American tech reviewer voice
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

        # Studio podcast mastering (warm EQ + broadcast compression + loudness normalization)
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

    # First-run auto-detection cascade
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

    # Ultimate safety fallback if a locked engine had a transient hiccup mid-run
    if _try_piper_studio(text, out_mp3):
        return
    if _try_gtts_broadcast(text, out_mp3):
        return
    _try_espeak_emergency(text, out_mp3)


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


def render_image_audio_segment(img_path: Path, audio_path: Path, out_mp4: Path, optional_talking_mp4: Path = None):
    dur = get_media_duration(audio_path)
    if optional_talking_mp4 and optional_talking_mp4.exists():
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(optional_talking_mp4),
            "-i", str(audio_path),
            "-t", f"{dur:.2f}",
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p",
            "-af", "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,apad",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            str(out_mp4)
        ]
    else:
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


def download_or_build_demo(demo_url: str, raw_demo_path: Path, fallback_slide: Path):
    if demo_url and demo_url.strip().startswith("http"):
        url = demo_url.strip()
        print(f"Downloading demo video from: {url}")
        try:
            if "youtube.com" in url or "youtu.be" in url or "vimeo.com" in url:
                cmd = [
                    "yt-dlp",
                    "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
                    "--merge-output-format", "mp4",
                    "-o", str(raw_demo_path),
                    url
                ]
                subprocess.run(cmd, check=True)
            else:
                with requests.get(url, stream=True, timeout=120) as r:
                    r.raise_for_status()
                    with open(raw_demo_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
            if raw_demo_path.exists() and raw_demo_path.stat().st_size > 10000:
                return
        except Exception as e:
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
    parser = argparse.ArgumentParser(description="Automated Review Video Factory")
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
    presenter_circle = ASSETS_DIR / "presenter_circle.png"
    ensure_presenter_assets(presenter_base, presenter_circle)

    # 1. Build High-Converting Script Segments (Sandwich Avatar Cutaway Structure)
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

    create_presenter_slide(
        presenter_base, s1_img,
        badge_top="SPECIAL LAUNCH ALERT",
        headline=f"{args.product_name} Review + Exclusive Coupon",
        subline=f"Use Code: {args.coupon_code} + Claim 6 VIP Bonus Packages (1st Link Below)"
    )
    create_product_cutaway_slide(
        presenter_circle, s2_img,
        product_name=args.product_name,
        main_result=args.main_result,
        features=[args.feature_1, args.feature_2, args.feature_3],
        coupon_code=args.coupon_code
    )
    create_presenter_slide(
        presenter_base, s3_img,
        badge_top="LIVE WALKTHROUGH NEXT",
        headline=f"Let's Check Out {args.product_name} From The Inside!",
        subline="Watch the Full Demo + Stay Till the End for Your 6 VIP Bonus Packages"
    )
    create_bonuses_slide(presenter_circle, s4_img, args.product_name, args.coupon_code)
    create_presenter_slide(
        presenter_base, s5_img,
        badge_top="CLAIM YOUR DEAL NOW",
        headline=f"Click First Link Below For {args.product_name} + Bonuses",
        subline=f"Active Discount Coupon: {args.coupon_code}  |  Full OTO Breakdown & Review Below"
    )
    create_demo_overlay_png(demo_overlay, args.product_name, args.coupon_code)
    create_youtube_thumbnail(presenter_base, thumb_path, args.product_name, args.coupon_code)

    # 4. Render Video Segments
    v1 = WORK_DIR / "seg1.mp4"
    v2 = WORK_DIR / "seg2.mp4"
    v3 = WORK_DIR / "seg3.mp4"
    v_demo = WORK_DIR / "seg_demo.mp4"
    v4 = WORK_DIR / "seg4.mp4"
    v5 = WORK_DIR / "seg5.mp4"

    d1 = render_image_audio_segment(s1_img, a1, v1, ASSETS_DIR / "intro_hook.mp4")
    d2 = render_image_audio_segment(s2_img, a2, v2, None)
    d3 = render_image_audio_segment(s3_img, a3, v3, ASSETS_DIR / "intro_transition.mp4")

    raw_demo = WORK_DIR / "raw_demo.mp4"
    download_or_build_demo(args.demo_url, raw_demo, s2_img)
    d_demo = process_demo_break_fingerprint(raw_demo, demo_overlay, v_demo)

    d4 = render_image_audio_segment(s4_img, a4, v4, None)
    d5 = render_image_audio_segment(s5_img, a5, v5, ASSETS_DIR / "outro_cta.mp4")

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

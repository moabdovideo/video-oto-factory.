#!/usr/bin/env python3
"""
OTOsLinks Automated Video Factory — v6 (Faceless Motion-Graphics + Real PrimeSite $24K Bonus Vault)
- 100% Photo-Free Motion-Graphics Studio (1080p @ 30 FPS)
- Kinetic Product Intro -> Core Features Spotlight -> Live Demo Stinger -> Live Demo
- Real PrimeSite Bonus Vault Showcase (2 Scenes: 6 Collections [120 Bonuses] + Top 8 Power Bonuses)
- Final Verdict & Animated CTA -> Also exports standalone primesite_bonus_vault_promo.mp4
- Royalty-Free Synthesized Studio Ambient Bed + Transition Whoosh/Chime SFX
- Full Wistia / YouTube / Vimeo / Direct MP4 Support + Make.com repository_dispatch Ready
"""

import os
import re
import sys
import math
import html
import wave
import shutil
import tarfile
import asyncio
import argparse
import subprocess
from pathlib import Path

import numpy as np
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
WORK_DIR = BASE_DIR.parent / "temp_build"
OUT_DIR = BASE_DIR.parent / "review-output-pack"
PIPER_CACHE = Path("/tmp/piper_studio")

W, H = 1920, 1080
FPS = 30

_LOCKED_TTS_ENGINE = None

# ==============================================================================
# REAL PRIMESITE BONUS VAULT DATA (From otoslinks.com/vip-hot-bonuses-value-24k/)
# ==============================================================================

PRIMESITE_COLLECTIONS = [
    ("01", "WordPress Plugins & Themes", "13 BONUSES", "Sales-page layouts, video widgets, popups & lead tools."),
    ("02", "Automation & Store Builders", "14 BONUSES", "SEO tools, site cloners & hands-free automation software."),
    ("03", "Graphics, Video & Research", "17 BONUSES", "300+ logos, visual packs & creative production assets."),
    ("04", "Blueprints & Resell-Rights", "19 BONUSES", "Step-by-step business blueprints & resell-rights training."),
    ("05", "Complete Systems & AI Tools", "9 BONUSES", "100 DFY prompt packs & turnkey agency systems."),
    ("06", "Digital Marketing Master Library", "48 BONUSES", "Full traffic, SEO, email & conversion training vault."),
]

PRIMESITE_TOP8_POWER_BONUSES = [
    ("#01", "20 WP Sales Page Templates", "Templates", "$597", "High-converting WordPress sales page layouts."),
    ("#02", "WP Video Focus", "Software", "$399", "Sticky floating video player while visitors scroll."),
    ("#03", "Google Related Keyword Gen", "Software", "$299", "Multilingual Google Suggest keyword discovery."),
    ("#04", "SEO Monster", "Software", "$297", "Turn SEO guesswork into an actionable ranking plan."),
    ("#05", "WP WebTransformer", "Software", "$297", "Smart WordPress popups, opt-ins & visitor triggers."),
    ("#06", "SiteClone Machine", "Software", "$297", "Save winning page layouts & launch faster."),
    ("#07", "300 Ready-Made Logo Designs", "Templates", "$197", "Instant commercial brand & client logo vault."),
    ("#08", "100 DFY AI Prompts Pack", "Prompt Pack", "VIP", "Proven plug-and-play prompts for fast output."),
]

# ==============================================================================
# TYPOGRAPHY & COLOR PALETTE (Modern Dark-Mode SaaS Broadcast Studio)
# ==============================================================================

COL_PANEL = (15, 23, 42)
COL_BLUE = (59, 130, 246)
COL_GOLD = (250, 204, 21)
COL_AMBER = (245, 158, 11)
COL_ROSE = (225, 29, 72)
COL_GREEN = (34, 197, 94)
COL_WHITE = (248, 250, 252)

_FONT_CACHE = {}
_BG_CACHE = {}


def load_font(size: int, bold: bool = True):
    key = (int(size), bool(bold))
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/GoogleSans-Regular.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    font = None
    for path in candidates:
        if os.path.exists(path):
            font = ImageFont.truetype(path, size=int(size))
            break
    if font is None:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, max_size: int, min_size: int = 16, bold: bool = True):
    for sz in range(max_size, min_size - 1, -2):
        f = load_font(sz, bold=bold)
        tw, _ = text_size(draw, text, f)
        if tw <= max_width:
            return f
    return load_font(min_size, bold=bold)


def wrap_text_px(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int = 2) -> list:
    words = text.split()
    if not words:
        return []
    lines = []
    cur = words[0]
    for w in words[1:]:
        test = f"{cur} {w}"
        tw, _ = text_size(draw, test, font)
        if tw <= max_width:
            cur = test
        else:
            lines.append(cur)
            cur = w
            if len(lines) >= max_lines:
                break
    if len(lines) < max_lines:
        lines.append(cur)
    else:
        last = lines[-1]
        while last and text_size(draw, last + "...", font)[0] > max_width:
            last = last[:-1].rstrip()
        lines[-1] = (last + "...") if last else "..."
    return lines[:max_lines]


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def draw_rrect(draw: ImageDraw.ImageDraw, xy, radius: int, fill=None, outline=None, width: int = 1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def paste_rgba_alpha(base_rgb: Image.Image, patch_rgba: Image.Image, xy: tuple, opacity: float = 1.0):
    if opacity <= 0.01:
        return
    if opacity >= 0.99:
        base_rgb.paste(patch_rgba, xy, patch_rgba)
        return
    _, _, _, a = patch_rgba.split()
    a = a.point(lambda v: int(v * opacity))
    base_rgb.paste(patch_rgba, xy, a)


# ==============================================================================
# STUDIO BACKGROUND & TOP BROADCAST TIMELINE BAR
# ==============================================================================

def make_studio_background(variant: str = "default") -> Image.Image:
    if variant in _BG_CACHE:
        return _BG_CACHE[variant].copy()

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    nx = xx / W
    ny = yy / H

    r = 6.0 + 10.0 * ny + 6.0 * (1.0 - nx)
    g = 10.0 + 14.0 * ny + 5.0 * nx
    b = 24.0 + 22.0 * (1.0 - 0.5 * ny)

    if variant == "intro":
        glows = [
            (0.18, 0.22, 0.42, (35, 95, 220), 0.52),
            (0.84, 0.26, 0.38, (14, 165, 233), 0.38),
            (0.52, 0.88, 0.45, (245, 158, 11), 0.22),
        ]
    elif variant == "bonuses":
        glows = [
            (0.15, 0.20, 0.40, (245, 158, 11), 0.32),
            (0.85, 0.78, 0.42, (59, 130, 246), 0.42),
            (0.55, 0.15, 0.35, (190, 24, 93), 0.26),
        ]
    elif variant == "power8":
        glows = [
            (0.20, 0.75, 0.44, (190, 24, 93), 0.30),
            (0.82, 0.20, 0.40, (245, 158, 11), 0.32),
            (0.50, 0.50, 0.46, (37, 99, 235), 0.34),
        ]
    elif variant == "demo_stinger":
        glows = [
            (0.50, 0.48, 0.48, (37, 99, 235), 0.46),
            (0.20, 0.20, 0.32, (220, 38, 38), 0.28),
            (0.82, 0.82, 0.35, (34, 211, 238), 0.30),
        ]
    elif variant == "outro":
        glows = [
            (0.22, 0.24, 0.44, (225, 29, 72), 0.32),
            (0.80, 0.28, 0.42, (245, 158, 11), 0.30),
            (0.50, 0.85, 0.45, (37, 99, 235), 0.42),
        ]
    else:
        glows = [
            (0.14, 0.18, 0.40, (37, 99, 235), 0.45),
            (0.86, 0.24, 0.36, (34, 211, 238), 0.32),
            (0.82, 0.85, 0.38, (245, 158, 11), 0.24),
        ]

    for gx, gy, rad, (cr, cg, cb), strength in glows:
        dist2 = ((nx - gx) ** 2 + ((ny - gy) * (H / W)) ** 2) / (rad ** 2)
        mask = np.exp(-dist2 * 2.4) * strength
        r += cr * mask
        g += cg * mask
        b += cb * mask

    vig = 1.0 - 0.28 * (((nx - 0.5) * 1.45) ** 2 + ((ny - 0.5) * 1.45) ** 2)
    vig = np.clip(vig, 0.65, 1.0)
    r = np.clip(r * vig, 0, 255).astype(np.uint8)
    g = np.clip(g * vig, 0, 255).astype(np.uint8)
    b = np.clip(b * vig, 0, 255).astype(np.uint8)

    img = Image.fromarray(np.dstack([r, g, b]), mode="RGB").convert("RGBA")

    grid_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grid_layer)
    step = 64
    for x in range(0, W, step):
        gdraw.line([(x, 0), (x, H)], fill=(148, 163, 184, 14), width=1)
    for y in range(0, H, step):
        gdraw.line([(0, y), (W, y)], fill=(148, 163, 184, 14), width=1)
    for x in range(step, W, step * 2):
        for y in range(step, H, step * 2):
            gdraw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(96, 165, 250, 38))

    out = Image.alpha_composite(img, grid_layer).convert("RGB")
    _BG_CACHE[variant] = out
    return out.copy()


def draw_top_timeline_bar(img_rgb: Image.Image, active_step: int, product_name: str, coupon_code: str,
                          vault_mode: bool = False):
    overlay = Image.new("RGBA", (W, 84), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, W, 82), fill=(8, 13, 28, 228))
    draw.line([(0, 82), (W, 82)], fill=(59, 130, 246, 125), width=2)

    # Left pill
    left_label = "PRIMESITE BONUS VAULT" if vault_mode else product_name.upper()[:24]
    draw_rrect(draw, (42, 18, 378, 64), radius=12, fill=(30, 41, 59, 235), outline=(59, 130, 246, 180), width=2)
    draw.ellipse((58, 33, 74, 49), fill=(34, 197, 94, 255))
    f_brand = fit_font(draw, left_label, 280, 20, 14, bold=True)
    _, bh = text_size(draw, left_label, f_brand)
    draw.text((86, 41 - bh // 2 - 1), left_label, font=f_brand, fill=(248, 250, 252, 255))

    # Center roadmap
    steps = (
        ["01 VAULT", "02 6 GROUPS", "03 TOP 8 VIP", "04 120 TOOLS", "05 CLAIM FREE"]
        if vault_mode
        else ["01 INTRO", "02 FEATURES", "03 LIVE DEMO", "04 120 BONUSES", "05 VERDICT"]
    )
    sx = 428
    f_step = load_font(18, bold=True)
    for idx, label in enumerate(steps):
        is_active = (idx == active_step)
        is_done = (idx < active_step)
        pill_w = 200
        if is_active:
            draw_rrect(draw, (sx, 19, sx + pill_w, 63), radius=12, fill=(37, 99, 235, 255), outline=(147, 197, 253, 255), width=2)
            txt_col = (255, 255, 255, 255)
        elif is_done:
            draw_rrect(draw, (sx, 19, sx + pill_w, 63), radius=12, fill=(20, 40, 72, 220), outline=(59, 130, 246, 150), width=1)
            txt_col = (147, 197, 253, 255)
        else:
            draw_rrect(draw, (sx, 19, sx + pill_w, 63), radius=12, fill=(15, 23, 42, 180), outline=(51, 65, 85, 160), width=1)
            txt_col = (148, 163, 184, 210)
        tw, th = text_size(draw, label, f_step)
        draw.text((sx + (pill_w - tw) // 2, 41 - th // 2 - 1), label, font=f_step, fill=txt_col)
        sx += pill_w + 16

    # Right pill
    right_txt = "VALUE: $24,000+ FREE" if vault_mode else f"COUPON: {coupon_code[:12].upper()}"
    draw_rrect(draw, (1535, 18, 1878, 64), radius=12, fill=(136, 19, 55, 245), outline=(250, 204, 21, 245), width=2)
    f_c = fit_font(draw, right_txt, 315, 20, 15, bold=True)
    cw, ch = text_size(draw, right_txt, f_c)
    draw.text((1535 + (343 - cw) // 2, 41 - ch // 2 - 1), right_txt, font=f_c, fill=(254, 240, 138, 255))

    img_rgb.paste(overlay, (0, 0), overlay)


# ==============================================================================
# REAL-TIME AUDIO ENVELOPE & VOICE EQUALIZER
# ==============================================================================

def extract_audio_envelope(audio_path: Path, total_frames: int, fps: int = FPS) -> list:
    tmp_wav = WORK_DIR / f"{audio_path.stem}_env.wav"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(audio_path), "-ac", "1", "-ar", "16000", "-f", "wav", str(tmp_wav)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
        )
        with wave.open(str(tmp_wav), "rb") as wf:
            sr = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    except Exception:
        return [0.35 + 0.25 * abs(math.sin(i * 0.22)) for i in range(total_frames)]
    finally:
        tmp_wav.unlink(missing_ok=True)

    if len(samples) == 0:
        return [0.0] * total_frames

    rms = []
    for f in range(total_frames):
        s0 = int(f * sr / fps)
        s1 = int((f + 1) * sr / fps)
        chunk = samples[s0:s1]
        rms.append(0.0 if len(chunk) == 0 else float(np.sqrt(np.mean(chunk * chunk))))

    voiced = sorted(v for v in rms if v > 60.0)
    peak = max(voiced[int(0.92 * (len(voiced) - 1))] if voiced else 3500.0, 400.0)

    smooth = 0.0
    env = []
    for v in rms:
        target = min(1.0, max(0.0, v / peak))
        smooth = (0.58 * target + 0.42 * smooth) if target > smooth else (0.30 * target + 0.70 * smooth)
        env.append(smooth)
    return env


def draw_voice_equalizer(draw: ImageDraw.ImageDraw, cx: int, cy: int, width: int, max_h: int,
                         energy: float, t_sec: float, num_bars: int = 32):
    gap = 6
    bar_w = max(5, (width - (num_bars - 1) * gap) // num_bars)
    total_w = num_bars * bar_w + (num_bars - 1) * gap
    x0 = cx - total_w // 2

    for i in range(num_bars):
        norm_pos = (i / max(1, num_bars - 1)) * 2.0 - 1.0
        bell = math.exp(-2.4 * norm_pos * norm_pos)
        wave1 = 0.55 + 0.45 * math.sin(t_sec * 11.5 + i * 0.65)
        wave2 = 0.65 + 0.35 * math.cos(t_sec * 7.2 - i * 0.48)
        amp = (0.08 + 0.92 * energy) * bell * (0.45 + 0.55 * wave1 * wave2)
        bh = max(6, int(max_h * min(1.0, amp)))

        bx = x0 + i * (bar_w + gap)
        by0 = cy - bh // 2
        by1 = cy + bh // 2

        ratio = i / max(1, num_bars - 1)
        if ratio < 0.5:
            k = ratio * 2.0
            col = (int(34 + 65 * k), int(211 - 46 * k), int(238 + 12 * k))
        else:
            k = (ratio - 0.5) * 2.0
            col = (int(99 + 151 * k), int(165 + 39 * k), int(250 - 229 * k))
        draw.rounded_rectangle((bx, by0, bx + bar_w, by1), radius=bar_w // 2, fill=col)


# ==============================================================================
# PURE-PYTHON STUDIO AMBIENT BED + TRANSITION WHOOSH SFX (100% ROYALTY-FREE)
# ==============================================================================

def synthesize_ambient_bed_and_sfx(dur: float, out_wav: Path, with_chime: bool = True):
    sr = 44100
    n = max(1, int(round(dur * sr)))
    t = np.linspace(0.0, dur, n, endpoint=False, dtype=np.float32)

    freqs = [130.81, 196.00, 246.94, 293.66, 392.00]
    pad = np.zeros(n, dtype=np.float32)
    for idx, f in enumerate(freqs):
        lfo = 0.72 + 0.28 * np.sin(2.0 * np.pi * (0.14 + 0.05 * idx) * t + idx)
        pad += (0.20 / (1.0 + 0.25 * idx)) * lfo * np.sin(2.0 * np.pi * f * t)

    pulse_env = 0.5 + 0.5 * np.sin(2.0 * np.pi * (110.0 / 60.0) * t)
    pulse = 0.08 * (pulse_env ** 3) * np.sin(2.0 * np.pi * 65.41 * t)
    bed = (pad + pulse) * 0.075

    fade_n = min(int(0.45 * sr), n // 3)
    if fade_n > 1:
        bed[:fade_n] *= np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
        bed[-fade_n:] *= np.linspace(1.0, 0.0, fade_n, dtype=np.float32)

    if with_chime and n > int(0.55 * sr):
        ch_n = int(0.48 * sr)
        ct = np.linspace(0.0, 0.48, ch_n, endpoint=False, dtype=np.float32)
        chime_env = np.exp(-ct * 9.5) * np.minimum(1.0, ct / 0.015)
        chime = chime_env * (0.12 * np.sin(2.0 * np.pi * 587.33 * ct) + 0.08 * np.sin(2.0 * np.pi * 880.0 * ct))
        rng = np.random.default_rng(42)
        soft_noise = np.convolve(rng.standard_normal(ch_n).astype(np.float32), np.ones(15, dtype=np.float32) / 15.0, mode="same")
        whoosh = soft_noise * (np.sin(np.pi * (ct / 0.48)) ** 2) * 0.055
        bed[:ch_n] += chime + whoosh

    left = np.clip(bed, -0.95, 0.95)
    right = np.clip(bed * 0.98, -0.95, 0.95)
    stereo = np.empty(n * 2, dtype=np.int16)
    stereo[0::2] = (left * 32767.0).astype(np.int16)
    stereo[1::2] = (right * 32767.0).astype(np.int16)

    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(stereo.tobytes())


def mix_voice_with_studio_bed(voice_mp3: Path, out_mixed_aac: Path, with_chime: bool = True) -> float:
    dur = get_media_duration(voice_mp3)
    bed_wav = WORK_DIR / f"{voice_mp3.stem}_bed.wav"
    synthesize_ambient_bed_and_sfx(dur + 0.25, bed_wav, with_chime=with_chime)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(voice_mp3),
        "-i", str(bed_wav),
        "-t", f"{dur:.2f}",
        "-filter_complex",
        "[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.06[v];"
        "[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=0.82[b];"
        "[v][b]amix=inputs=2:duration=first:dropout_transition=1,alimiter=limit=0.95[outa]",
        "-map", "[outa]",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        str(out_mixed_aac),
    ]
    subprocess.run(cmd, check=True)
    bed_wav.unlink(missing_ok=True)
    return dur


# ==============================================================================
# MOTION-GRAPHICS PIPELINE ENGINE (1080p @ 30 FPS — 100% FACELESS)
# ==============================================================================

def _pipe_frames_to_ffmpeg(frame_generator, audio_path: Path, dur: float, out_mp4: Path):
    fade_out_start = max(0.2, dur - 0.28)
    vf = (
        f"setsar=1,fps={FPS},"
        f"fade=t=in:st=0:d=0.22,"
        f"fade=t=out:st={fade_out_start:.2f}:d=0.26,"
        f"format=yuv420p"
    )
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-framerate", str(FPS),
        "-i", "-",
        "-i", str(audio_path),
        "-t", f"{dur:.2f}",
        "-vf", vf,
        "-af", f"aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,afade=t=in:st=0:d=0.06,afade=t=out:st={fade_out_start:.2f}:d=0.20,apad",
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        str(out_mp4),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for frame_bytes in frame_generator:
            proc.stdin.write(frame_bytes)
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
        raise RuntimeError(f"FFmpeg motion-graphics render failed for {out_mp4.name} (exit={ret})")


# --- SCENE 1: GENIUS KINETIC HOOK & PRODUCT INTRO ---

def _build_intro_layers(product_name: str, main_result: str, coupon_code: str, bonus_value: str) -> dict:
    badge = Image.new("RGBA", (800, 62), (0, 0, 0, 0))
    bd = ImageDraw.Draw(badge)
    draw_rrect(bd, (2, 2, 798, 60), radius=30, fill=(220, 38, 38, 240), outline=(254, 202, 202, 230), width=2)
    b_txt = "WAIT! WATCH BEFORE YOU PAY FULL PRICE  •  HONEST REVIEW"
    bf = fit_font(bd, b_txt, 740, 22, 16, bold=True)
    bw, bh = text_size(bd, b_txt, bf)
    bd.text(((800 - bw) // 2, (62 - bh) // 2 - 2), b_txt, font=bf, fill=(255, 255, 255, 255))

    hero = Image.new("RGBA", (1660, 270), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hero)
    title_str = product_name.strip()
    tf = fit_font(hd, title_str, 1600, 96, 46, bold=True)
    tw, _ = text_size(hd, title_str, tf)
    hd.text(((1660 - tw) // 2 + 4, 23), title_str, font=tf, fill=(0, 0, 0, 170))
    hd.text(((1660 - tw) // 2, 18), title_str, font=tf, fill=(255, 255, 255, 255))

    sub_str = f"Built to help you {main_result}"
    sf = load_font(34, bold=False)
    sub_lines = wrap_text_px(hd, sub_str, sf, 1460, max_lines=2)
    sy = 148
    for ln in sub_lines:
        lw, _ = text_size(hd, ln, sf)
        hd.text(((1660 - lw) // 2, sy), ln, font=sf, fill=(186, 230, 253, 255))
        sy += 46

    card_specs = [
        ("ACTIVE DISCOUNT CODE", coupon_code[:14].upper(), "Apply at Checkout for Max Savings", (136, 19, 55, 242), (250, 204, 21, 255), (254, 240, 138, 255)),
        ("REAL INSIDE DEMO", "LIVE WALKTHROUGH", "Full Dashboard & Real Output Inside", (23, 37, 84, 242), (56, 189, 248, 255), (125, 211, 252, 255)),
        ("PRIMESITE BONUS VAULT", f"120 BONUSES ({bonus_value})", "6 Collections + Top 8 Power Tools FREE", (30, 41, 59, 246), (245, 158, 11, 255), (253, 224, 71, 255)),
    ]
    cards = []
    cw, ch = 530, 220
    for tag, big_val, desc, bg_col, border_col, val_col in card_specs:
        c = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        cd = ImageDraw.Draw(c)
        draw_rrect(cd, (4, 4, cw - 4, ch - 4), radius=24, fill=bg_col, outline=border_col, width=3)
        f_tag = load_font(20, bold=True)
        tw1, _ = text_size(cd, tag, f_tag)
        cd.text(((cw - tw1) // 2, 28), tag, font=f_tag, fill=(226, 232, 240, 235))
        f_val = fit_font(cd, big_val, cw - 48, 44, 26, bold=True)
        vw, _ = text_size(cd, big_val, f_val)
        cd.text(((cw - vw) // 2, 82), big_val, font=f_val, fill=val_col)
        f_desc = fit_font(cd, desc, cw - 40, 22, 16, bold=False)
        dw, _ = text_size(cd, desc, f_desc)
        cd.text(((cw - dw) // 2, 162), desc, font=f_desc, fill=(241, 245, 249, 230))
        cards.append(c)

    cta = Image.new("RGBA", (1580, 74), (0, 0, 0, 0))
    ctad = ImageDraw.Draw(cta)
    draw_rrect(ctad, (2, 2, 1578, 72), radius=18, fill=(15, 23, 42, 238), outline=(59, 130, 246, 230), width=2)
    cta_txt = f"FIRST LINK IN DESCRIPTION:  FULL REVIEW  •  COUPON [{coupon_code[:14].upper()}]  •  120 BONUSES ({bonus_value} VALUE)"
    cf = fit_font(ctad, cta_txt, 1520, 25, 17, bold=True)
    twc, thc = text_size(ctad, cta_txt, cf)
    ctad.text(((1580 - twc) // 2, (74 - thc) // 2 - 2), cta_txt, font=cf, fill=(253, 224, 71, 255))

    return {"badge": badge, "hero": hero, "cards": cards, "cta": cta}


def render_intro_motion_segment(product_name: str, main_result: str, coupon_code: str, bonus_value: str,
                                audio_path: Path, out_mp4: Path, preview_png: Path = None) -> float:
    dur = get_media_duration(audio_path)
    total_frames = max(30, int(math.ceil(dur * FPS)) + 2)
    env = extract_audio_envelope(audio_path, total_frames, FPS)

    base = make_studio_background("intro")
    draw_top_timeline_bar(base, 0, product_name, coupon_code)
    layers = _build_intro_layers(product_name, main_result, coupon_code, bonus_value)

    def gen():
        for f in range(total_frames):
            t = f / FPS
            frame = base.copy()
            d = ImageDraw.Draw(frame)

            p_badge = ease_out_cubic(t / 0.45)
            paste_rgba_alpha(frame, layers["badge"], (560, int(118 - 35 * (1.0 - p_badge))), p_badge)

            p_hero = ease_out_cubic((t - 0.18) / 0.60)
            paste_rgba_alpha(frame, layers["hero"], (130, int(202 + 48 * (1.0 - p_hero))), p_hero)

            p_line = ease_out_cubic((t - 0.35) / 0.70)
            if p_line > 0.01:
                half_w = int(340 * p_line)
                d.rounded_rectangle((W // 2 - half_w, 336, W // 2 + half_w, 343), radius=3, fill=COL_GOLD)

            card_xs = [115, 695, 1275]
            for idx, card_img in enumerate(layers["cards"]):
                pc = ease_out_cubic((t - (0.65 + idx * 0.28)) / 0.50)
                if pc > 0.01:
                    cy = int(488 + 60 * (1.0 - pc))
                    paste_rgba_alpha(frame, card_img, (card_xs[idx], cy), pc)
                    if t > 2.2:
                        active_card = int(((t - 2.2) / max(1.8, (dur - 2.2) / 3.0))) % 3
                        if active_card == idx:
                            pulse = 0.55 + 0.45 * math.sin(t * 6.0)
                            glow_col = (int(245 + 10 * pulse), int(180 + 50 * pulse), int(30 + 50 * pulse))
                            d.rounded_rectangle((card_xs[idx] + 2, cy + 2, card_xs[idx] + 528, cy + 218), radius=24, outline=glow_col, width=4)

            p_eq = ease_out_cubic((t - 0.40) / 0.50)
            if p_eq > 0.05:
                draw_voice_equalizer(d, W // 2, 825, 920, int(110 * p_eq), env[f], t, num_bars=36)

            p_cta = ease_out_cubic((t - 1.05) / 0.55)
            if p_cta > 0.01:
                paste_rgba_alpha(frame, layers["cta"], (170, int(955 + 40 * (1.0 - p_cta))), p_cta)

            if preview_png is not None and f == min(total_frames - 1, int(FPS * 2.5)):
                frame.save(preview_png, "PNG")
            yield frame.tobytes()

    _pipe_frames_to_ffmpeg(gen(), audio_path, dur, out_mp4)
    return dur


# --- SCENE 2: ANIMATED CORE FEATURES SPOTLIGHT ---

def _build_feature_card(idx: int, text: str, active: bool) -> Image.Image:
    cw, ch = 1230, 198
    card = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    if active:
        fill_c, out_c, bw = (24, 39, 76, 250), (250, 204, 21, 255), 4
        orb_fill, orb_txt, tag_fill, txt_fill = (250, 204, 21, 255), (15, 23, 42, 255), (37, 99, 235, 255), (255, 255, 255, 255)
    else:
        fill_c, out_c, bw = (15, 23, 42, 235), (59, 130, 246, 150), 2
        orb_fill, orb_txt, tag_fill, txt_fill = (30, 58, 138, 255), (191, 219, 254, 255), (30, 41, 59, 255), (203, 213, 225, 235)

    draw_rrect(d, (4, 4, cw - 4, ch - 4), radius=24, fill=fill_c, outline=out_c, width=bw)
    d.ellipse((32, 52, 124, 144), fill=orb_fill)
    nf = load_font(44, bold=True)
    nw, nh = text_size(d, f"0{idx + 1}", nf)
    d.text((78 - nw // 2, 98 - nh // 2 - 4), f"0{idx + 1}", font=nf, fill=orb_txt)

    pill_lbl = f"CORE FEATURE #{idx + 1}" + ("  •  ACTIVE HIGHLIGHT" if active else "")
    pf = load_font(18, bold=True)
    pw, _ = text_size(d, pill_lbl, pf)
    draw_rrect(d, (156, 24, 156 + pw + 32, 56), radius=10, fill=tag_fill)
    d.text((172, 31), pill_lbl, font=pf, fill=(255, 255, 255, 255))

    ff = load_font(33, bold=True)
    lines = wrap_text_px(d, text, ff, cw - 200, max_lines=2)
    ty = 72 if len(lines) == 2 else 92
    for ln in lines:
        d.text((156, ty), ln, font=ff, fill=txt_fill)
        ty += 46
    return card


def render_features_motion_segment(product_name: str, main_result: str, features: list,
                                   coupon_code: str, bonus_value: str, audio_path: Path,
                                   out_mp4: Path, preview_png: Path = None) -> float:
    dur = get_media_duration(audio_path)
    total_frames = max(30, int(math.ceil(dur * FPS)) + 2)
    env = extract_audio_envelope(audio_path, total_frames, FPS)

    base = make_studio_background("default")
    draw_top_timeline_bar(base, 1, product_name, coupon_code)
    bd = ImageDraw.Draw(base)

    draw_rrect(bd, (72, 108, 435, 150), radius=10, fill=(37, 99, 235))
    bd.text((92, 117), "CORE FEATURES BREAKDOWN", font=load_font(21, bold=True), fill=COL_WHITE)

    title_str = f"What Makes {product_name} Different?"
    bd.text((72, 162), title_str, font=fit_font(bd, title_str, 1760, 52, 30, bold=True), fill=COL_WHITE)

    sub_str = f"Engineered to help you {main_result} — zero coding, zero monthly fees."
    bd.text((72, 228), sub_str, font=fit_font(bd, sub_str, 1760, 27, 19, bold=False), fill=(148, 163, 184))

    rx0, ry0, rx1, ry1 = 1355, 286, 1848, 1018
    draw_rrect(bd, (rx0, ry0, rx1, ry1), radius=26, fill=(15, 23, 42), outline=(245, 158, 11), width=3)
    draw_rrect(bd, (rx0, ry0, rx1, ry0 + 82), radius=26, fill=(136, 19, 55))
    hdr_c = "EXCLUSIVE LAUNCH DEAL"
    hf = load_font(26, bold=True)
    hw, _ = text_size(bd, hdr_c, hf)
    bd.text((rx0 + (rx1 - rx0 - hw) // 2, ry0 + 26), hdr_c, font=hf, fill=(254, 205, 211))

    draw_rrect(bd, (rx0 + 28, ry0 + 108, rx1 - 28, ry0 + 210), radius=16, fill=(255, 255, 255))
    code_str = coupon_code[:14].upper()
    cf = fit_font(bd, code_str, rx1 - rx0 - 90, 44, 26, bold=True)
    cw, ch = text_size(bd, code_str, cf)
    bd.text((rx0 + (rx1 - rx0 - cw) // 2, ry0 + 159 - ch // 2 - 2), code_str, font=cf, fill=COL_ROSE)

    perks = [
        "✔  Max Launch Discount Unlocked",
        f"✔  120 VIP Bonuses ({bonus_value})",
        "✔  Top 8 Heavy-Hitter Software",
        "✔  Direct OTO Upgrade Breakdown",
        "✔  Instant Automated Delivery",
    ]
    py = ry0 + 244
    for pk in perks:
        pf = fit_font(bd, pk, rx1 - rx0 - 60, 23, 17, bold=True)
        bd.text((rx0 + 30, py), pk, font=pf, fill=(226, 232, 240))
        py += 58

    draw_rrect(bd, (rx0 + 28, ry1 - 152, rx1 - 28, ry1 - 92), radius=14, fill=(37, 99, 235))
    bcta = "1ST LINK IN DESCRIPTION"
    bf = load_font(23, bold=True)
    bw, bh = text_size(bd, bcta, bf)
    bd.text((rx0 + (rx1 - rx0 - bw) // 2, ry1 - 122 - bh // 2 - 1), bcta, font=bf, fill=COL_WHITE)

    draw_rrect(bd, (72, 935, 1302, 1018), radius=16, fill=(23, 37, 84), outline=(59, 130, 246), width=2)
    bbar = f"Full Review + OTO Links + Coupon [{code_str}] + 120 PrimeSite Bonuses Below"
    bd.text((104, 962), bbar, font=fit_font(bd, bbar, 1180, 26, 18, bold=True), fill=COL_GOLD)

    feats = (features + ["High-Speed Automated Workflow", "Commercial License Included", "Cloud Dashboard Access"])[:3]
    cards_inactive = [_build_feature_card(i, feats[i], False) for i in range(3)]
    cards_active = [_build_feature_card(i, feats[i], True) for i in range(3)]
    ys = [286, 502, 718]

    intro_lead = min(4.0, dur * 0.22)
    tail_hold = min(4.2, dur * 0.22)
    feat_span = max(2.8, (dur - intro_lead - tail_hold) / 3.0)

    def gen():
        for f in range(total_frames):
            t = f / FPS
            frame = base.copy()
            d = ImageDraw.Draw(frame)

            if t < intro_lead + feat_span:
                active_idx = 0
            elif t < intro_lead + 2.0 * feat_span:
                active_idx = 1
            else:
                active_idx = 2

            for idx in range(3):
                p = ease_out_cubic((t - (0.15 + idx * 0.24)) / 0.45)
                if p > 0.01:
                    paste_rgba_alpha(frame, cards_active[idx] if idx == active_idx else cards_inactive[idx],
                                     (int(72 - 70 * (1.0 - p)), ys[idx]), p)

            draw_voice_equalizer(d, (rx0 + rx1) // 2, ry1 - 44, 380, 48, env[f], t, num_bars=22)

            if preview_png is not None and f == min(total_frames - 1, int(FPS * (intro_lead + feat_span * 1.3))):
                frame.save(preview_png, "PNG")
            yield frame.tobytes()

    _pipe_frames_to_ffmpeg(gen(), audio_path, dur, out_mp4)
    return dur


# --- SCENE 3: ENTERING LIVE DEMO BROADCAST STINGER ---

def render_demo_stinger_segment(product_name: str, coupon_code: str, bonus_value: str,
                                audio_path: Path, out_mp4: Path, preview_png: Path = None) -> float:
    dur = get_media_duration(audio_path)
    total_frames = max(30, int(math.ceil(dur * FPS)) + 2)
    env = extract_audio_envelope(audio_path, total_frames, FPS)

    base = make_studio_background("demo_stinger")
    draw_top_timeline_bar(base, 2, product_name, coupon_code)
    bd = ImageDraw.Draw(base)

    draw_rrect(bd, (140, 148, 1780, 995), radius=34, fill=(15, 23, 42), outline=(59, 130, 246), width=3)

    t_str = f"Inside {product_name} — Live Demo"
    tf = fit_font(bd, t_str, 1520, 62, 34, bold=True)
    tw, _ = text_size(bd, t_str, tf)
    bd.text(((W - tw) // 2, 340), t_str, font=tf, fill=COL_WHITE)

    s_str = "Watch the real dashboard, live tools & actual output in action right now"
    sf = fit_font(bd, s_str, 1480, 30, 20, bold=False)
    sw, _ = text_size(bd, s_str, sf)
    bd.text(((W - sw) // 2, 422), s_str, font=sf, fill=(186, 230, 253))

    pillars = [
        ("01", "REAL DASHBOARD TOUR", "Zero hype — pure inside screen"),
        ("02", "STEP-BY-STEP WORKFLOW", "See how fast you get results"),
        ("03", f"120 BONUSES ({bonus_value})", f"Revealed right after demo + [{coupon_code[:10].upper()}]"),
    ]
    px = 215
    for num, p_head, p_sub in pillars:
        draw_rrect(bd, (px, 495, px + 465, 675), radius=20, fill=(22, 34, 62), outline=(71, 85, 105), width=2)
        draw_rrect(bd, (px + 24, 518, px + 88, 560), radius=10, fill=(37, 99, 235))
        bd.text((px + 38, 526), num, font=load_font(24, bold=True), fill=COL_WHITE)
        bd.text((px + 104, 526), p_head, font=fit_font(bd, p_head, 338, 24, 17, bold=True), fill=COL_GOLD)
        bd.text((px + 24, 592), p_sub, font=fit_font(bd, p_sub, 415, 22, 16, bold=False), fill=(226, 232, 240))
        px += 512

    def gen():
        for f in range(total_frames):
            t = f / FPS
            prog = min(1.0, t / max(0.5, dur - 0.25))
            frame = base.copy()
            d = ImageDraw.Draw(frame)

            pulse = 0.5 + 0.5 * math.sin(t * 7.5)
            ring_r = int(58 + 14 * pulse)
            d.ellipse((W // 2 - ring_r, 248 - ring_r, W // 2 + ring_r, 248 + ring_r), outline=(56, 189, 248), width=3)
            d.ellipse((W // 2 - 48, 200, W // 2 + 48, 296), fill=(220, 38, 38), outline=(254, 202, 202), width=3)
            d.polygon([(W // 2 - 14, 224), (W // 2 - 14, 272), (W // 2 + 24, 248)], fill=COL_WHITE)

            dot_col = (239, 68, 68) if pulse > 0.35 else (153, 27, 27)
            draw_rrect(d, (190, 184, 505, 236), radius=14, fill=(30, 41, 59), outline=(239, 68, 68), width=2)
            d.ellipse((212, 201, 230, 219), fill=dot_col)
            d.text((244, 196), "ENTERING LIVE DEMO", font=load_font(22, bold=True), fill=COL_WHITE)

            bar_x0, bar_y0, bar_x1, bar_y1 = 260, 745, 1660, 795
            draw_rrect(d, (bar_x0, bar_y0, bar_x1, bar_y1), radius=24, fill=(30, 41, 59), outline=(71, 85, 105), width=2)
            fill_w = max(48, int((bar_x1 - bar_x0 - 8) * ease_out_cubic(prog)))
            draw_rrect(d, (bar_x0 + 4, bar_y0 + 4, bar_x0 + 4 + fill_w, bar_y1 - 4), radius=20, fill=(37, 99, 235))
            pct_txt = f"LAUNCHING INSIDE WALKTHROUGH...  {int(prog * 100)}%"
            pf = load_font(23, bold=True)
            pw, ph = text_size(d, pct_txt, pf)
            d.text(((W - pw) // 2, bar_y0 + 25 - ph // 2 - 1), pct_txt, font=pf, fill=COL_WHITE)

            draw_voice_equalizer(d, W // 2, 898, 760, 74, env[f], t, num_bars=30)

            if preview_png is not None and f == min(total_frames - 1, int(total_frames * 0.65)):
                frame.save(preview_png, "PNG")
            yield frame.tobytes()

    _pipe_frames_to_ffmpeg(gen(), audio_path, dur, out_mp4)
    return dur


# --- SCENE 5A: REAL PRIMESITE BONUS VAULT — 6 COLLECTIONS (120 RESOURCES) ---

def _build_collection_card(num: str, title: str, count_lbl: str, desc: str, highlight: bool) -> Image.Image:
    cw, ch = 635, 224
    c = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    if highlight:
        fill_c, out_c, bw = (28, 44, 82, 250), (250, 204, 21, 255), 4
    else:
        fill_c, out_c, bw = (18, 28, 52, 240), (71, 85, 105, 210), 2
    draw_rrect(d, (4, 4, cw - 4, ch - 4), radius=20, fill=fill_c, outline=out_c, width=bw)

    draw_rrect(d, (24, 20, 226, 58), radius=10, fill=(37, 99, 235, 255))
    d.text((38, 27), f"COLLECTION {num}", font=load_font(20, bold=True), fill=(255, 255, 255, 255))

    draw_rrect(d, (cw - 195, 20, cw - 24, 58), radius=10, fill=(136, 19, 55, 245), outline=(250, 204, 21, 225), width=1)
    vf = load_font(19, bold=True)
    vw, _ = text_size(d, count_lbl, vf)
    d.text((cw - 195 + (171 - vw) // 2, 28), count_lbl, font=vf, fill=(254, 240, 138, 255))

    tf = fit_font(d, title, cw - 48, 29, 21, bold=True)
    d.text((24, 78), title, font=tf, fill=(255, 255, 255, 255))

    df = load_font(22, bold=False)
    lines = wrap_text_px(d, desc, df, cw - 48, max_lines=2)
    ty = 124
    for ln in lines:
        d.text((24, ty), ln, font=df, fill=(186, 204, 226, 245))
        ty += 32
    return c


def render_primesite_collections_segment(product_name: str, coupon_code: str, bonus_value: str,
                                         audio_path: Path, out_mp4: Path,
                                         vault_mode: bool = False, preview_png: Path = None) -> float:
    dur = get_media_duration(audio_path)
    total_frames = max(30, int(math.ceil(dur * FPS)) + 2)
    env = extract_audio_envelope(audio_path, total_frames, FPS)

    base = make_studio_background("bonuses")
    draw_top_timeline_bar(base, 1 if vault_mode else 3, product_name, coupon_code, vault_mode=vault_mode)
    bd = ImageDraw.Draw(base)

    # Top Banner
    draw_rrect(bd, (64, 102, 1856, 232), radius=24, fill=(20, 31, 58), outline=(245, 158, 11), width=3)
    h1 = (
        "THE PRIMESITE BONUS VAULT — 120 BONUSES IN 6 COLLECTIONS"
        if vault_mode
        else f"FREE WITH {product_name[:24].upper()} — 120 PRIMESITE BONUSES"
    )
    bd.text((98, 120), h1, font=fit_font(bd, h1, 1330, 39, 24, bold=True), fill=COL_GOLD)

    h2 = "Organized by B2B & Software Value: WordPress Plugins, Automation Tools, Graphics, Blueprints & Marketing Vault."
    bd.text((98, 178), h2, font=fit_font(bd, h2, 1330, 23, 17, bold=False), fill=(226, 232, 240))

    draw_rrect(bd, (1475, 120, 1825, 214), radius=18, fill=(136, 19, 55), outline=(250, 204, 21), width=3)
    v1 = f"{bonus_value} VALUE"
    vf1 = fit_font(bd, v1, 320, 33, 22, bold=True)
    vw1, _ = text_size(bd, v1, vf1)
    bd.text((1475 + (350 - vw1) // 2, 132), v1, font=vf1, fill=COL_GOLD)
    f_free = load_font(19, bold=True)
    fw, _ = text_size(bd, "120 RESOURCES FREE", f_free)
    bd.text((1475 + (350 - fw) // 2, 176), "120 RESOURCES FREE", font=f_free, fill=COL_WHITE)

    # Right Sidebar
    sx0, sy0, sx1, sy1 = 1405, 256, 1856, 1026
    draw_rrect(bd, (sx0, sy0, sx1, sy1), radius=24, fill=(15, 23, 42), outline=(245, 158, 11), width=3)
    draw_rrect(bd, (sx0, sy0, sx1, sy0 + 78), radius=24, fill=(30, 58, 138))
    hdr_r = "VAULT HIGHLIGHTS"
    hrf = load_font(30, bold=True)
    hrw, _ = text_size(bd, hdr_r, hrf)
    bd.text((sx0 + (sx1 - sx0 - hrw) // 2, sy0 + 23), hdr_r, font=hrf, fill=COL_GOLD)

    highlights = [
        ("120", "Real Software & Assets"),
        ("6", "Curated Pro Collections"),
        ("TOP 8", "$2,826+ Power Tools First"),
        ("FREE", "Included With Your Order"),
    ]
    ry = sy0 + 102
    for b_s, l_s in highlights:
        draw_rrect(bd, (sx0 + 22, ry, sx1 - 22, ry + 86), radius=14, fill=(24, 36, 66), outline=(59, 130, 246), width=2)
        draw_rrect(bd, (sx0 + 36, ry + 20, sx0 + 132, ry + 66), radius=8, fill=(220, 38, 38))
        bf_b = fit_font(bd, b_s, 84, 20, 14, bold=True)
        bw_b, bh_b = text_size(bd, b_s, bf_b)
        bd.text((sx0 + 36 + (96 - bw_b) // 2, ry + 43 - bh_b // 2 - 1), b_s, font=bf_b, fill=COL_WHITE)
        sf = fit_font(bd, l_s, sx1 - sx0 - 178, 22, 16, bold=True)
        bd.text((sx0 + 148, ry + 30), l_s, font=sf, fill=COL_WHITE)
        ry += 102

    draw_rrect(bd, (sx0 + 22, sy1 - 224, sx1 - 22, sy1 - 96), radius=16, fill=(136, 19, 55), outline=(251, 113, 133), width=2)
    t_auto = "INSTANT VAULT ACCESS"
    taf = fit_font(bd, t_auto, sx1 - sx0 - 70, 22, 16, bold=True)
    taw, _ = text_size(bd, t_auto, taf)
    bd.text((sx0 + (sx1 - sx0 - taw) // 2, sy1 - 204), t_auto, font=taf, fill=(254, 205, 211))

    t_sub = "Search, Filter & Download Anytime"
    tsf = fit_font(bd, t_sub, sx1 - sx0 - 70, 19, 14, bold=False)
    tsw, _ = text_size(bd, t_sub, tsf)
    bd.text((sx0 + (sx1 - sx0 - tsw) // 2, sy1 - 166), t_sub, font=tsf, fill=COL_WHITE)

    draw_rrect(bd, (sx0 + 44, sy1 - 134, sx1 - 44, sy1 - 106), radius=8, fill=COL_WHITE)
    t_btn = "OTOSLINKS.COM VIP VAULT"
    tbf = fit_font(bd, t_btn, sx1 - sx0 - 110, 17, 13, bold=True)
    tbw, _ = text_size(bd, t_btn, tbf)
    bd.text((sx0 + (sx1 - sx0 - tbw) // 2, sy1 - 129), t_btn, font=tbf, fill=COL_ROSE)

    coords = [
        (64, 256), (734, 256),
        (64, 514), (734, 514),
        (64, 772), (734, 772),
    ]
    cards_norm = [_build_collection_card(*col, False) for col in PRIMESITE_COLLECTIONS]
    cards_hi = [_build_collection_card(*col, True) for col in PRIMESITE_COLLECTIONS]

    lead_in = min(3.0, dur * 0.16)
    tail_out = min(2.8, dur * 0.14)
    slot = max(1.4, (dur - lead_in - tail_out) / 6.0)

    def gen():
        for f in range(total_frames):
            t = f / FPS
            frame = base.copy()
            d = ImageDraw.Draw(frame)

            hi_idx = -1 if t < lead_in else min(5, int((t - lead_in) / slot))
            for idx, (cx, cy) in enumerate(coords):
                p = ease_out_cubic((t - (0.12 + idx * 0.16)) / 0.40)
                if p > 0.01:
                    paste_rgba_alpha(frame, cards_hi[idx] if idx == hi_idx else cards_norm[idx],
                                     (cx, int(cy + 34 * (1.0 - p))), p)

            draw_voice_equalizer(d, (sx0 + sx1) // 2, sy1 - 46, 360, 48, env[f], t, num_bars=20)
            if preview_png is not None and f == min(total_frames - 1, int(FPS * (lead_in + slot * 2.5))):
                frame.save(preview_png, "PNG")
            yield frame.tobytes()

    _pipe_frames_to_ffmpeg(gen(), audio_path, dur, out_mp4)
    return dur


# --- SCENE 5B: TOP 8 HEAVY-HITTER POWER BONUSES ($2,826+ VALUE ALONE) ---

def _build_power8_card(rank: str, title: str, fmt: str, val_str: str, desc: str, highlight: bool) -> Image.Image:
    cw, ch = 428, 326
    c = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    if highlight:
        fill_c, out_c, bw = (28, 44, 82, 252), (250, 204, 21, 255), 4
    else:
        fill_c, out_c, bw = (16, 26, 48, 242), (59, 130, 246, 165), 2

    draw_rrect(d, (4, 4, cw - 4, ch - 4), radius=22, fill=fill_c, outline=out_c, width=bw)

    # Top Row: Rank Badge + Format Tag
    draw_rrect(d, (22, 20, 152, 56), radius=10, fill=(245, 158, 11, 255) if highlight else (37, 99, 235, 255))
    rk_txt = f"★ TOP {rank}"
    rkf = load_font(18, bold=True)
    rkw, _ = text_size(d, rk_txt, rkf)
    d.text((22 + (130 - rkw) // 2, 27), rk_txt, font=rkf, fill=(15, 23, 42, 255) if highlight else (255, 255, 255, 255))

    draw_rrect(d, (cw - 154, 20, cw - 22, 56), radius=10, fill=(30, 41, 59, 255), outline=(100, 116, 139, 200), width=1)
    ff = fit_font(d, fmt.upper(), 116, 16, 12, bold=True)
    fw, _ = text_size(d, fmt.upper(), ff)
    d.text((cw - 154 + (132 - fw) // 2, 29), fmt.upper(), font=ff, fill=(186, 230, 253, 255))

    # Title (up to 2 lines)
    tf = load_font(27, bold=True)
    t_lines = wrap_text_px(d, title, tf, cw - 44, max_lines=2)
    ty = 76
    for ln in t_lines:
        d.text((22, ty), ln, font=tf, fill=(255, 255, 255, 255))
        ty += 34

    # Description (up to 2 lines)
    df = load_font(20, bold=False)
    d_lines = wrap_text_px(d, desc, df, cw - 44, max_lines=2)
    dy = 158
    for ln in d_lines:
        d.text((22, dy), ln, font=df, fill=(186, 204, 226, 240))
        dy += 28

    # Bottom Value Strip: Crossed-out Dollar Value -> FREE TODAY
    draw_rrect(d, (20, 236, cw - 20, ch - 20), radius=14, fill=(15, 23, 42, 245), outline=(250, 204, 21, 180) if highlight else (51, 65, 85, 200), width=2)
    if val_str != "VIP":
        v_lbl = f"Value: {val_str}"
        vf = load_font(21, bold=True)
        vw, vh = text_size(d, v_lbl, vf)
        vx, vy = 38, 260
        d.text((vx, vy), v_lbl, font=vf, fill=(148, 163, 184, 230))
        # Red strikethrough line over price
        d.line([(vx + 72, vy + vh // 2 + 2), (vx + vw + 4, vy + vh // 2 + 2)], fill=(239, 68, 68, 255), width=3)
    else:
        d.text((38, 260), "VIP Pack", font=load_font(21, bold=True), fill=(148, 163, 184, 230))

    draw_rrect(d, (cw - 178, 248, cw - 32, ch - 32), radius=10, fill=(22, 163, 74, 255))
    frf = load_font(20, bold=True)
    frw, _ = text_size(d, "FREE ✓", frf)
    d.text((cw - 178 + (146 - frw) // 2, 261), "FREE ✓", font=frf, fill=(255, 255, 255, 255))

    return c


def render_primesite_top8_segment(product_name: str, coupon_code: str, bonus_value: str,
                                  audio_path: Path, out_mp4: Path,
                                  vault_mode: bool = False, preview_png: Path = None) -> float:
    dur = get_media_duration(audio_path)
    total_frames = max(30, int(math.ceil(dur * FPS)) + 2)
    env = extract_audio_envelope(audio_path, total_frames, FPS)

    base = make_studio_background("power8")
    draw_top_timeline_bar(base, 2 if vault_mode else 3, product_name, coupon_code, vault_mode=vault_mode)
    bd = ImageDraw.Draw(base)

    # Top Spotlight Header
    draw_rrect(bd, (64, 100, 1856, 206), radius=22, fill=(20, 31, 58), outline=(250, 204, 21), width=3)
    h1 = "EXECUTIVE POWER SPOTLIGHT — TOP 8 HEAVY-HITTER BONUSES ($2,826+ VALUE ALONE)"
    bd.text((96, 116), h1, font=fit_font(bd, h1, 1730, 35, 22, bold=True), fill=COL_GOLD)
    h2 = f"Real WordPress plugins, SEO & cloning software, 300 logos & 100 DFY prompts — plus 112 more tools inside the {bonus_value} Vault!"
    bd.text((96, 162), h2, font=fit_font(bd, h2, 1730, 22, 16, bold=False), fill=(226, 232, 240))

    # 4 columns x 2 rows grid
    xs = [64, 518, 972, 1426]
    ys = [232, 582]
    coords = [(xs[i % 4], ys[i // 4]) for i in range(8)]

    cards_norm = [_build_power8_card(*item, False) for item in PRIMESITE_TOP8_POWER_BONUSES]
    cards_hi = [_build_power8_card(*item, True) for item in PRIMESITE_TOP8_POWER_BONUSES]

    lead_in = min(2.2, dur * 0.12)
    tail_out = min(2.2, dur * 0.12)
    slot = max(1.1, (dur - lead_in - tail_out) / 8.0)

    def gen():
        for f in range(total_frames):
            t = f / FPS
            frame = base.copy()
            d = ImageDraw.Draw(frame)

            hi_idx = -1 if t < lead_in else min(7, int((t - lead_in) / slot))
            for idx, (cx, cy) in enumerate(coords):
                p = ease_out_cubic((t - (0.08 + idx * 0.11)) / 0.36)
                if p > 0.01:
                    paste_rgba_alpha(frame, cards_hi[idx] if idx == hi_idx else cards_norm[idx],
                                     (cx, int(cy + 28 * (1.0 - p))), p)

            # Bottom sleek broadcast strip + mini voice equalizer
            draw_rrect(d, (64, 938, 1856, 1038), radius=18, fill=(15, 23, 42), outline=(59, 130, 246), width=2)
            bt = (
                "EXPLORE ALL 120 BONUSES FREE  •  OTOSLINKS.COM VIP VAULT  •  FIRST LINK BELOW"
                if vault_mode
                else f"ALL 8 POWER TOOLS + 112 MORE BONUSES FREE  •  COUPON [{coupon_code[:14].upper()}]  •  1ST LINK BELOW"
            )
            bf = fit_font(d, bt, 1280, 26, 18, bold=True)
            _, bth = text_size(d, bt, bf)
            d.text((98, 988 - bth // 2 - 1), bt, font=bf, fill=COL_GOLD)

            draw_voice_equalizer(d, 1650, 988, 340, 56, env[f], t, num_bars=20)

            if preview_png is not None and f == min(total_frames - 1, int(FPS * (lead_in + slot * 3.5))):
                frame.save(preview_png, "PNG")
            yield frame.tobytes()

    _pipe_frames_to_ffmpeg(gen(), audio_path, dur, out_mp4)
    return dur


# --- SCENE 6: FINAL VERDICT & ANIMATED CTA OUTRO ---

def render_outro_motion_segment(product_name: str, coupon_code: str, bonus_value: str,
                                audio_path: Path, out_mp4: Path,
                                vault_mode: bool = False, preview_png: Path = None) -> float:
    dur = get_media_duration(audio_path)
    total_frames = max(30, int(math.ceil(dur * FPS)) + 2)
    env = extract_audio_envelope(audio_path, total_frames, FPS)

    base = make_studio_background("outro")
    draw_top_timeline_bar(base, 4, product_name, coupon_code, vault_mode=vault_mode)
    bd = ImageDraw.Draw(base)

    draw_rrect(bd, (96, 120, 1824, 920), radius=32, fill=(15, 23, 42), outline=(245, 158, 11), width=3)

    pill_left = "HOW TO UNLOCK THE VAULT" if vault_mode else "FINAL VERDICT & DEAL LINK"
    draw_rrect(bd, (148, 162, 575, 214), radius=12, fill=(37, 99, 235))
    bd.text((174, 174), pill_left, font=fit_font(bd, pill_left, 380, 23, 18, bold=True), fill=COL_WHITE)

    draw_rrect(bd, (1330, 162, 1772, 214), radius=12, fill=(30, 41, 59), outline=(250, 204, 21), width=2)
    bd.text((1360, 172), "★★★★★   RECOMMENDED", font=load_font(24, bold=True), fill=COL_GOLD)

    h1 = (
        f"Unlock All 120 PrimeSite Bonuses ({bonus_value} Value)"
        if vault_mode
        else f"Claim {product_name} + All 120 PrimeSite Bonuses"
    )
    bd.text((148, 246), h1, font=fit_font(bd, h1, 1610, 54, 30, bold=True), fill=COL_WHITE)

    h2 = (
        "Instant access to all 6 collections + Top 8 Heavy-Hitter software tools — 100% free with any order through our link."
        if vault_mode
        else f"Lock in launch pricing + the complete {bonus_value} PrimeSite Bonus Vault before the early-bird deal closes."
    )
    bd.text((148, 322), h2, font=fit_font(bd, h2, 1610, 27, 18, bold=False), fill=COL_GOLD)

    draw_rrect(bd, (148, 392, 1215, 780), radius=24, fill=(22, 34, 62), outline=(59, 130, 246), width=2)
    bd.text((186, 426), "YOUR 3-STEP INSTANT ACCESS CHECKLIST:", font=load_font(28, bold=True), fill=COL_WHITE)

    steps = (
        [
            ("1", "Pick up any featured software through our official review link."),
            ("2", "Complete checkout on the vendor's secure page (apply coupon if available)."),
            ("3", "Receive instant access to all 120 PrimeSite Bonuses inside your receipt!"),
        ]
        if vault_mode
        else [
            ("1", "Click the First Link in the Description right below this video."),
            ("2", f"Apply Secret Coupon [{coupon_code[:14].upper()}] on the official checkout page."),
            ("3", f"Unlock {product_name[:22]} + all 120 PrimeSite Bonuses instantly!"),
        ]
    )
    sy = 496
    for num, txt in steps:
        bd.ellipse((186, sy, 238, sy + 52), fill=COL_GOLD)
        bd.text((203, sy + 10), num, font=load_font(28, bold=True), fill=COL_PANEL)
        bd.text((262, sy + 11), txt, font=fit_font(bd, txt, 920, 26, 17, bold=True), fill=(241, 245, 249))
        sy += 88

    draw_rrect(bd, (1255, 392, 1772, 780), radius=24, fill=(136, 19, 55), outline=(250, 204, 21), width=3)
    top_t = "TOTAL VAULT VALUE" if vault_mode else "ACTIVE SECRET COUPON"
    ttf = load_font(26, bold=True)
    ttw, _ = text_size(bd, top_t, ttf)
    bd.text((1255 + (517 - ttw) // 2, 428), top_t, font=ttf, fill=(254, 205, 211))

    draw_rrect(bd, (1292, 488, 1735, 608), radius=18, fill=COL_WHITE)
    c_str = f"{bonus_value}" if vault_mode else coupon_code[:14].upper()
    cf = fit_font(bd, c_str, 410, 50, 28, bold=True)
    cw, ch = text_size(bd, c_str, cf)
    bd.text((1292 + (443 - cw) // 2, 548 - ch // 2 - 2), c_str, font=cf, fill=COL_ROSE)

    b_sub1 = "120 RESOURCES • 6 COLLECTIONS" if vault_mode else f"+ 120 BONUSES ({bonus_value})"
    sf1 = fit_font(bd, b_sub1, 460, 24, 18, bold=True)
    sw1, _ = text_size(bd, b_sub1, sf1)
    bd.text((1255 + (517 - sw1) // 2, 640), b_sub1, font=sf1, fill=COL_GOLD)

    b_sub2 = "Yours 100% FREE at Checkout"
    sf2 = load_font(22, bold=False)
    sw2, _ = text_size(bd, b_sub2, sf2)
    bd.text((1255 + (517 - sw2) // 2, 688), b_sub2, font=sf2, fill=COL_WHITE)

    def gen():
        for f in range(total_frames):
            t = f / FPS
            frame = base.copy()
            d = ImageDraw.Draw(frame)

            draw_voice_equalizer(d, W // 2, 850, 820, 68, env[f], t, num_bars=32)

            bounce = int(9.0 * abs(math.sin(t * 5.2)))
            by0, by1 = 946 + bounce, 1036 + bounce
            draw_rrect(d, (210, by0, 1710, by1), radius=20, fill=(220, 38, 38), outline=(250, 204, 21), width=3)
            cta_str = (
                "▼   BROWSE ALL 120 BONUSES ON THIS PAGE & CLAIM FREE WITH YOUR ORDER   ▼"
                if vault_mode
                else f"▼   CLICK THE FIRST LINK IN THE DESCRIPTION NOW  |  CODE: {coupon_code[:14].upper()}   ▼"
            )
            cf2 = fit_font(d, cta_str, 1440, 29, 19, bold=True)
            cw2, ch2 = text_size(d, cta_str, cf2)
            d.text(((W - cw2) // 2, (by0 + by1) // 2 - ch2 // 2 - 2), cta_str, font=cf2, fill=COL_WHITE)

            if preview_png is not None and f == min(total_frames - 1, int(FPS * 2.0)):
                frame.save(preview_png, "PNG")
            yield frame.tobytes()

    _pipe_frames_to_ffmpeg(gen(), audio_path, dur, out_mp4)
    return dur


# ==============================================================================
# SLEEK DEMO OVERLAY & 100% FACELESS HIGH-CTR YOUTUBE THUMBNAIL
# ==============================================================================

def create_demo_overlay_png(out_path: Path, product_name: str, coupon_code: str, bonus_value: str):
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    top_txt = f"LIVE DEMO  |  {product_name[:20].upper()}"
    tf = load_font(21, bold=True)
    tw, _ = text_size(draw, top_txt, tf)
    px0 = W - tw - 76
    draw_rrect(draw, (px0, 24, W - 28, 74), radius=14, fill=(10, 16, 32, 210), outline=(59, 130, 246, 220), width=2)
    draw.ellipse((px0 + 18, 41, px0 + 34, 57), fill=(239, 68, 68, 255))
    draw.text((px0 + 44, 36), top_txt, font=tf, fill=(248, 250, 252, 245))

    draw_rrect(draw, (140, 1008, 1780, 1066), radius=14, fill=(10, 16, 32, 232), outline=(245, 158, 11, 245), width=2)
    bar_txt = f"GRAB {product_name[:22].upper()}  +  COUPON [{coupon_code[:14].upper()}]  +  120 BONUSES ({bonus_value})   ▸   1ST LINK BELOW"
    bf = fit_font(draw, bar_txt, 1580, 24, 17, bold=True)
    bw, bh = text_size(draw, bar_txt, bf)
    draw.text(((W - bw) // 2, 1037 - bh // 2 - 1), bar_txt, font=bf, fill=(253, 224, 71, 255))

    overlay.save(out_path, "PNG")


def create_faceless_youtube_thumbnail(out_path: Path, product_name: str, coupon_code: str, bonus_value: str):
    TW, TH = 1280, 720
    bg = make_studio_background("intro").resize((TW, TH), Image.Resampling.LANCZOS).convert("RGBA")
    overlay = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    draw.polygon([(780, 0), (1280, 0), (1280, 720), (660, 720)], fill=(15, 23, 42, 175))
    draw.line([(780, 0), (660, 720)], fill=(56, 189, 248, 220), width=5)

    # Right Side: Stylized LIVE INSIDE DEMO Mockup
    mx0, my0, mx1, my1 = 748, 72, 1236, 466
    draw_rrect(draw, (mx0, my0, mx1, my1), radius=24, fill=(15, 23, 42, 245), outline=(59, 130, 246, 255), width=4)
    draw_rrect(draw, (mx0, my0, mx1, my0 + 48), radius=24, fill=(30, 41, 59, 255))
    for i, c in enumerate([(239, 68, 68), (250, 204, 21), (34, 197, 94)]):
        draw.ellipse((mx0 + 22 + i * 24, my0 + 16, mx0 + 38 + i * 24, my0 + 32), fill=c)
    draw.text((mx0 + 106, my0 + 13), "INSIDE DASHBOARD DEMO", font=load_font(19, bold=True), fill=(186, 230, 253, 255))

    draw_rrect(draw, (mx0 + 26, my0 + 72, mx0 + 175, my1 - 28), radius=12, fill=(24, 36, 66, 240))
    for ry in range(my0 + 96, my1 - 60, 44):
        draw_rrect(draw, (mx0 + 44, ry, mx0 + 156, ry + 18), radius=6, fill=(59, 130, 246, 135))
    draw_rrect(draw, (mx0 + 196, my0 + 72, mx1 - 26, my0 + 235), radius=14, fill=(24, 36, 66, 240))
    draw_rrect(draw, (mx0 + 196, my0 + 252, mx1 - 26, my1 - 28), radius=14, fill=(24, 36, 66, 240))

    pcx, pcy = (mx0 + mx1) // 2 + 24, (my0 + my1) // 2 + 16
    draw.ellipse((pcx - 66, pcy - 66, pcx + 66, pcy + 66), fill=(220, 38, 38, 245), outline=(255, 255, 255, 255), width=5)
    draw.polygon([(pcx - 20, pcy - 32), (pcx - 20, pcy + 32), (pcx + 34, pcy)], fill=(255, 255, 255, 255))

    # Bottom-Right: Giant Golden 120 Bonuses Seal
    draw_rrect(draw, (748, 496, 1236, 664), radius=24, fill=(136, 19, 55, 250), outline=(250, 204, 21, 255), width=4)
    b_top = "120 VIP BONUSES"
    btf = fit_font(draw, b_top, 440, 36, 24, bold=True)
    btw, _ = text_size(draw, b_top, btf)
    draw.text((748 + (488 - btw) // 2, 518), b_top, font=btf, fill=(255, 255, 255, 255))

    b_val = f"WORTH {bonus_value}"
    bvf = fit_font(draw, b_val, 440, 52, 30, bold=True)
    bvw, _ = text_size(draw, b_val, bvf)
    draw.text((748 + (488 - bvw) // 2, 574), b_val, font=bvf, fill=(253, 224, 71, 255))

    # Left Side: High-Contrast Click-Magnet Typography
    draw_rrect(draw, (44, 48, 520, 108), radius=14, fill=(220, 38, 38, 255), outline=(254, 202, 202, 240), width=2)
    eyebrow = "★ HONEST REVIEW + DEMO"
    ef = fit_font(draw, eyebrow, 435, 28, 20, bold=True)
    ew, eh = text_size(draw, eyebrow, ef)
    draw.text((44 + (476 - ew) // 2, 78 - eh // 2 - 1), eyebrow, font=ef, fill=(255, 255, 255, 255))

    clean_name = product_name.strip().upper()
    pf = fit_font(draw, clean_name, 645, 86, 48, bold=True)
    lines = wrap_text_px(draw, clean_name, pf, 645, max_lines=2)
    ny = 136 if len(lines) == 2 else 172
    for ln in lines:
        draw.text((48, ny + 5), ln, font=pf, fill=(0, 0, 0, 180))
        draw.text((44, ny), ln, font=pf, fill=(255, 255, 255, 255))
        ny += 94

    # Auto-fitted FULL DEMO + OTOs badge (guaranteed zero overflow)
    draw_rrect(draw, (44, 355, 675, 470), radius=20, fill=(37, 99, 235, 255), outline=(147, 197, 253, 255), width=3)
    d_lbl = "FULL DEMO + OTOs"
    df_b = fit_font(draw, d_lbl, 580, 52, 34, bold=True)
    dw_b, dh_b = text_size(draw, d_lbl, df_b)
    draw.text((44 + (631 - dw_b) // 2, 412 - dh_b // 2 - 2), d_lbl, font=df_b, fill=(255, 255, 255, 255))

    draw_rrect(draw, (44, 502, 675, 664), radius=20, fill=(255, 255, 255, 255), outline=(250, 204, 21, 255), width=5)
    draw.text((74, 520), "SECRET DISCOUNT COUPON:", font=load_font(28, bold=True), fill=(15, 23, 42, 255))
    c_txt = coupon_code[:14].upper()
    cf = fit_font(draw, c_txt, 580, 64, 36, bold=True)
    draw.text((74, 566), c_txt, font=cf, fill=(225, 29, 72, 255))

    Image.alpha_composite(bg, overlay).convert("RGB").save(out_path, "JPEG", quality=95)


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
    piper_bin = PIPER_CACHE / "piper" / "piper"
    model_onnx = PIPER_CACHE / "en_US-ryan-high.onnx"
    model_json = PIPER_CACHE / "en_US-ryan-high.onnx.json"
    PIPER_CACHE.mkdir(parents=True, exist_ok=True)

    if not piper_bin.exists():
        print("[TTS] Installing Offline Studio Neural Engine (Piper Linux x86_64)...")
        tar_path = PIPER_CACHE / "piper_linux.tar.gz"
        if not _download_file(["https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz"], tar_path):
            return None, None
        with tarfile.open(tar_path, "r:gz") as tf:
            tf.extractall(PIPER_CACHE)
        piper_bin.chmod(0o755)

    if not model_onnx.exists() or not model_json.exists():
        print("[TTS] Downloading Studio Broadcaster Neural Model (en_US-ryan-high)...")
        ok_m = _download_file([
            "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/high/en_US-ryan-high.onnx",
            "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx",
        ], model_onnx)
        ok_j = _download_file([
            "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/high/en_US-ryan-high.onnx.json",
            "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx.json",
        ], model_json)
        if not (ok_m and ok_j):
            return None, None
    return piper_bin, model_onnx


def _try_elevenlabs(text: str, out_mp3: Path) -> bool:
    api_key = (os.getenv("ELEVENLABS_API_KEY") or "").strip()
    if not api_key or requests is None:
        return False
    try:
        resp = requests.post(
            "https://api.elevenlabs.io/v1/text-to-speech/nPczCjzI2devNBz1zQrb",
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={"text": text, "model_id": "eleven_multilingual_v2",
                  "voice_settings": {"stability": 0.50, "similarity_boost": 0.78}},
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
        env["LD_LIBRARY_PATH"] = f"{piper_bin.parent.resolve()}:{env.get('LD_LIBRARY_PATH', '')}"
        subprocess.run(
            [str(piper_bin), "--model", str(model_onnx), "--length_scale", "0.96",
             "--sentence_silence", "0.22", "--output_file", str(raw_wav)],
            input=text.encode("utf-8"), env=env, check=True,
        )
        if not raw_wav.exists() or raw_wav.stat().st_size < 1000:
            return False
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(raw_wav),
             "-af", "highpass=f=75,acompressor=threshold=-18dB:ratio=2.2:attack=15:release=120,loudnorm=I=-16:TP=-1.5:LRA=11",
             "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", str(out_mp3)],
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
        gTTS(text=text, lang="en", tld="com", slow=False).save(str(raw_gtts))
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(raw_gtts),
             "-af", "atempo=1.06,highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11",
             "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", str(out_mp3)],
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
    subprocess.run(["ffmpeg", "-y", "-i", str(raw_wav), "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", str(out_mp3)], check=True)
    raw_wav.unlink(missing_ok=True)
    return True


async def synth_voice(text: str, preferred_voice: str, out_mp3: Path):
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
# MEDIA HELPERS & WISTIA / YOUTUBE / VIMEO / MP4 DEMO ENGINE
# ==============================================================================

def get_media_duration(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], text=True).strip()
    return max(float(out), 1.0)


def has_audio(path: Path) -> bool:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index", "-of", "csv=p=0", str(path)
    ], text=True).strip()
    return len(out) > 0


def has_video_stream(path: Path) -> bool:
    if not path.exists() or path.stat().st_size <= 10000:
        return False
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", str(path)
        ], text=True).strip()
        return len(out) > 0
    except Exception:
        return False


def normalize_demo_url(raw_input: str) -> tuple:
    if not raw_input or not raw_input.strip():
        return "", False
    cleaned = html.unescape(raw_input.strip())
    reserved_words = {"iframe", "medias", "external", "popover", "player", "assets", "deliveries", "oembed", "embed", "projects", "channels"}
    for pat in [
        r"wistia\.(?:com|net)/(?:embed/(?:iframe|medias)|medias)/([a-zA-Z0-9]+)",
        r"wi\.st/(?:medias|embed/iframe|embed)/([a-zA-Z0-9]+)",
        r"[?&](?:wvideo|wmediaid)=([a-zA-Z0-9]+)",
        r"wistia_async_([a-zA-Z0-9]+)",
    ]:
        m = re.search(pat, cleaned, flags=re.IGNORECASE)
        if m and m.group(1).lower() not in reserved_words and len(m.group(1)) >= 6:
            return f"https://fast.wistia.net/embed/iframe/{m.group(1)}", True

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

    is_streaming = any(d in cleaned.lower() for d in ("youtube.com", "youtu.be", "vimeo.com", "wistia.com", "wistia.net", "wi.st"))
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
                subprocess.run([
                    "yt-dlp", "--no-playlist",
                    "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080][ext=mp4]/best[height<=1080]/best",
                    "--merge-output-format", "mp4",
                    "-o", f"{temp_prefix}.%(ext)s", target_url
                ], check=True)
                downloaded = [p for p in raw_demo_path.parent.glob("ytdlp_demo_raw.*") if p.suffix.lower() not in (".part", ".ytdl", ".temp")]
                if downloaded:
                    shutil.move(str(downloaded[0]), str(raw_demo_path))
            else:
                with requests.get(target_url, stream=True, timeout=120) as r:
                    r.raise_for_status()
                    if "text/html" in (r.headers.get("Content-Type") or "").lower():
                        raise ValueError("URL returned HTML webpage instead of a direct video stream")
                    with open(raw_demo_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
            if has_video_stream(raw_demo_path):
                return
            raw_demo_path.unlink(missing_ok=True)
            print("Warning: Downloaded file had no valid video stream. Falling back to placeholder.")
        except Exception as e:
            raw_demo_path.unlink(missing_ok=True)
            print(f"Warning: Could not download demo_url ({e}). Generating clean placeholder demo segment.")

    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(fallback_slide),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", "-t", "8",
        "-vf", f"scale={W}:{H},setsar=1,fps={FPS},format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", str(raw_demo_path)
    ], check=True)


def process_demo_break_fingerprint(raw_demo: Path, overlay_png: Path, out_demo: Path) -> float:
    v_filter = (
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS},"
        "eq=contrast=1.02:brightness=0.01:saturation=1.03,"
        "setpts=0.99*PTS[base];"
        "[base][1:v]overlay=0:0,fade=t=in:st=0:d=0.20,format=yuv420p[outv]"
    )
    if has_audio(raw_demo):
        cmd = [
            "ffmpeg", "-y", "-i", str(raw_demo), "-i", str(overlay_png),
            "-filter_complex", f"{v_filter};[0:a]atempo=1.01,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[outa]",
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-map_metadata", "-1", str(out_demo)
        ]
    else:
        dur = get_media_duration(raw_demo) * 0.99
        cmd = [
            "ffmpeg", "-y", "-i", str(raw_demo), "-i", str(overlay_png),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", "-t", f"{dur:.2f}",
            "-filter_complex", v_filter, "-map", "[outv]", "-map", "2:a:0",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-map_metadata", "-1", str(out_demo)
        ]
    subprocess.run(cmd, check=True)
    return get_media_duration(out_demo)


def concat_segments(segments: list, out_mp4: Path):
    concat_txt = WORK_DIR / f"concat_{out_mp4.stem}.txt"
    with open(concat_txt, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(f"file '{seg.resolve().as_posix()}'\n")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt),
        "-vf", f"fps={FPS},format=yuv420p,setsar=1", "-af", "aresample=44100",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart", str(out_mp4)
    ], check=True)


def fmt_ts(seconds: float) -> str:
    s = int(round(seconds))
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h > 0 else f"{m:02d}:{sec:02d}"


def main():
    parser = argparse.ArgumentParser(description="OTOsLinks Automated Video Factory v6 (Faceless + PrimeSite $24K Vault)")
    parser.add_argument("--product_name", default=os.getenv("PRODUCT_NAME", "AI Secret Image Codebook"))
    parser.add_argument("--main_result", default=os.getenv("MAIN_RESULT", "generate studio-grade commercial graphics using secret style parameters"))
    parser.add_argument("--feature_1", default=os.getenv("FEATURE_1", "Secret Style Reference Matrix & Optical Camera Lighting Tokens"))
    parser.add_argument("--feature_2", default=os.getenv("FEATURE_2", "Multi-Scene Character Consistency Lock & Crisp Typography Syntax"))
    parser.add_argument("--feature_3", default=os.getenv("FEATURE_3", "Print-On-Demand Vector Isolation & Commercial Product Mockup Codes"))
    parser.add_argument("--coupon_code", default=os.getenv("COUPON_CODE", "CODEBOOKVIP"))
    parser.add_argument("--bonus_value", default=os.getenv("BONUS_VALUE", "$24,000+"))
    parser.add_argument("--bonus_page_url", default=os.getenv("BONUS_PAGE_URL", "https://otoslinks.com/vip-hot-bonuses-value-24k/"))
    parser.add_argument("--demo_url", default=os.getenv("DEMO_URL", ""))
    parser.add_argument("--affiliate_link", default=os.getenv("AFFILIATE_LINK", "https://otoslinks.com/"))
    parser.add_argument("--voice", default=os.getenv("VOICE_NAME", "en-US-GuyNeural"))
    parser.add_argument("--build_standalone_vault", default=os.getenv("BUILD_STANDALONE_VAULT", "true"))
    args = parser.parse_args()

    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. High-Converting Faceless Scripts (Product -> Features -> Demo -> Real 120-Bonus PrimeSite Vault -> CTA)
    script_seg1 = (
        f"Wait—before you pay full price for {args.product_name}, watch this quick review first! "
        f"Built to help you {args.main_result}, I am about to cover its top core features, "
        f"take you straight inside the real live demo, and unlock secret coupon code {args.coupon_code} "
        f"plus our complete PrimeSite Vault of 120 exclusive bonuses worth over {args.bonus_value}—all waiting in the first link below."
    )
    script_seg2 = (
        f"Let us look at the core features that make {args.product_name} stand out without coding or monthly fees. "
        f"First, you get {args.feature_1}. "
        f"Second, it delivers {args.feature_2}. "
        f"And third, you unlock {args.feature_3}. "
        f"Down in the first link below, you will find our full written review, every O-T-O upgrade breakdown, "
        f"discount code {args.coupon_code}, and the entire 120-bonus PrimeSite Vault."
    )
    script_seg3 = (
        f"Now let us skip the hype and jump straight inside {args.product_name} for the real live demo! "
        "Stay tuned right after this walkthrough so I can show you the Top 8 Power Software Bonuses inside our 120-resource vault. Let us dive in!"
    )
    script_seg4_collections = (
        f"Now that you have seen {args.product_name} in action, here is what you unlock completely free inside the PrimeSite Bonus Vault "
        f"worth over {args.bonus_value} when you grab it through the first link below. "
        "You get 120 real resources organized into 6 curated collections: "
        "13 WordPress plugins and sales-page themes, 14 automation software tools and store builders, "
        "17 ready-made graphics, video, and research assets, 19 business blueprints with resell-rights training, "
        "9 complete business systems, and a 48-part digital marketing master library."
    )
    script_seg4b_top8 = (
        "And here are our Top 8 Executive Power Bonuses—worth over 2,826 dollars by themselves, yours free today: "
        "20 WordPress Sales Page Templates, W-P Video Focus sticky player, Google Related Keyword Generator, "
        "SEO Monster, W-P WebTransformer conversion popups, SiteClone Machine, 300 Ready-Made Logo Designs, "
        "and our 100 Done-For-You AI Prompts Pack—plus 112 more tools waiting inside your vault."
    )
    script_seg5_outro = (
        f"That wraps up our honest review and live demo of {args.product_name}. "
        f"Click the first link in the description right now, apply secret coupon {args.coupon_code} at checkout, "
        f"and unlock all 120 PrimeSite Bonuses before this launch deal expires. Thanks for watching, and see you inside!"
    )
    script_vault_outro = (
        f"Every single one of these 120 resources—organized into 6 searchable collections worth over {args.bonus_value}—"
        "is unlocked 100 percent free the moment you pick up any featured software through our link. "
        "Explore the full library on this page now, and claim your entire PrimeSite Bonus Vault automatically at checkout!"
    )

    # 2. Generate Voiceovers via Multi-Layer Studio Neural Engine
    a1_r, a2_r, a3_r, a4a_r, a4b_r, a5_r, av_r = [
        WORK_DIR / name for name in [
            "a1_raw.mp3", "a2_raw.mp3", "a3_raw.mp3", "a4a_raw.mp3",
            "a4b_raw.mp3", "a5_raw.mp3", "av_outro_raw.mp3"
        ]
    ]
    do_standalone = str(args.build_standalone_vault).strip().lower() in ("1", "true", "yes")

    async def build_all_audio():
        await synth_voice(script_seg1, args.voice, a1_r)
        await synth_voice(script_seg2, args.voice, a2_r)
        await synth_voice(script_seg3, args.voice, a3_r)
        await synth_voice(script_seg4_collections, args.voice, a4a_r)
        await synth_voice(script_seg4b_top8, args.voice, a4b_r)
        await synth_voice(script_seg5_outro, args.voice, a5_r)
        if do_standalone:
            await synth_voice(script_vault_outro, args.voice, av_r)

    asyncio.run(build_all_audio())

    # 3. Mix Voiceovers with Subtle Synthesized Studio Ambient Pad + Transition SFX
    a1, a2, a3, a4a, a4b, a5, av = [
        WORK_DIR / name for name in [
            "a1_mix.m4a", "a2_mix.m4a", "a3_mix.m4a", "a4a_mix.m4a",
            "a4b_mix.m4a", "a5_mix.m4a", "av_outro_mix.m4a"
        ]
    ]
    mix_voice_with_studio_bed(a1_r, a1, with_chime=True)
    mix_voice_with_studio_bed(a2_r, a2, with_chime=True)
    mix_voice_with_studio_bed(a3_r, a3, with_chime=True)
    mix_voice_with_studio_bed(a4a_r, a4a, with_chime=True)
    mix_voice_with_studio_bed(a4b_r, a4b, with_chime=True)
    mix_voice_with_studio_bed(a5_r, a5, with_chime=True)
    if do_standalone:
        mix_voice_with_studio_bed(av_r, av, with_chime=True)

    # 4. Generate Sleek Demo Overlay & 100% Faceless High-CTR Thumbnail
    demo_overlay = WORK_DIR / "demo_overlay.png"
    thumb_path = OUT_DIR / "youtube_thumbnail.jpg"
    fallback_demo_img = WORK_DIR / "fallback_demo_slide.png"

    create_demo_overlay_png(demo_overlay, args.product_name, args.coupon_code, args.bonus_value)
    create_faceless_youtube_thumbnail(thumb_path, args.product_name, args.coupon_code, args.bonus_value)

    # 5. Render All 7 Motion-Graphics Segments (1080p @ 30 FPS)
    v1 = WORK_DIR / "seg1_intro.mp4"
    v2 = WORK_DIR / "seg2_features.mp4"
    v3 = WORK_DIR / "seg3_stinger.mp4"
    v_demo = WORK_DIR / "seg4_demo.mp4"
    v4a = WORK_DIR / "seg5a_vault_collections.mp4"
    v4b = WORK_DIR / "seg5b_vault_top8.mp4"
    v5 = WORK_DIR / "seg6_outro.mp4"

    print("[RENDER] 1/7 Rendering Genius Kinetic Product Intro...")
    d1 = render_intro_motion_segment(args.product_name, args.main_result, args.coupon_code, args.bonus_value, a1, v1)

    print("[RENDER] 2/7 Rendering Animated Core Features Spotlight...")
    d2 = render_features_motion_segment(
        args.product_name, args.main_result, [args.feature_1, args.feature_2, args.feature_3],
        args.coupon_code, args.bonus_value, a2, v2, preview_png=fallback_demo_img
    )

    print("[RENDER] 3/7 Rendering Entering Live Demo Broadcast Stinger...")
    d3 = render_demo_stinger_segment(args.product_name, args.coupon_code, args.bonus_value, a3, v3)

    print("[RENDER] 4/7 Downloading & Processing Live Demo...")
    raw_demo = WORK_DIR / "raw_demo.mp4"
    download_or_build_demo(args.demo_url, raw_demo, fallback_demo_img)
    d_demo = process_demo_break_fingerprint(raw_demo, demo_overlay, v_demo)

    print("[RENDER] 5/7 Rendering PrimeSite Bonus Vault (6 Real Collections — 120 Bonuses)...")
    d4a = render_primesite_collections_segment(args.product_name, args.coupon_code, args.bonus_value, a4a, v4a, vault_mode=False)

    print("[RENDER] 6/7 Rendering PrimeSite Top 8 Heavy-Hitter Power Bonuses ($2,826+ Value)...")
    d4b = render_primesite_top8_segment(args.product_name, args.coupon_code, args.bonus_value, a4b, v4b, vault_mode=False)

    print("[RENDER] 7/7 Rendering Final Verdict & Animated CTA Outro...")
    d5 = render_outro_motion_segment(args.product_name, args.coupon_code, args.bonus_value, a5, v5, vault_mode=False)

    # 6. Concatenate Main Product Review Video
    final_mp4 = OUT_DIR / "final_youtube_video.mp4"
    concat_segments([v1, v2, v3, v_demo, v4a, v4b, v5], final_mp4)

    # 7. Also Export Standalone Reusable PrimeSite Bonus Vault Promo Video (for embedding on bonus page!)
    if do_standalone:
        print("[RENDER] Exporting Standalone PrimeSite Bonus Vault Promo Video...")
        vp1 = WORK_DIR / "vault_promo_1_collections.mp4"
        vp2 = WORK_DIR / "vault_promo_2_top8.mp4"
        vp3 = WORK_DIR / "vault_promo_3_outro.mp4"
        render_primesite_collections_segment("PrimeSite Vault", args.coupon_code, args.bonus_value, a4a, vp1, vault_mode=True)
        render_primesite_top8_segment("PrimeSite Vault", args.coupon_code, args.bonus_value, a4b, vp2, vault_mode=True)
        render_outro_motion_segment("PrimeSite Vault", args.coupon_code, args.bonus_value, av, vp3, vault_mode=True)
        concat_segments([vp1, vp2, vp3], OUT_DIR / "primesite_bonus_vault_promo.mp4")

    # 8. Build YouTube SEO Title, Description & Chapters File
    t0 = 0.0
    t_specs = d1
    t_demo = d1 + d2 + d3
    t_bonus = t_demo + d_demo
    t_top8 = t_bonus + d4a
    t_outro = t_top8 + d4b

    seo_text = f"""=========================================================
YOUTUBE HIGH-CTR TITLES (Playlist Cluster Strategy)
=========================================================
Title 1 (Main Review):
{args.product_name} Review: Full Demo + OTOs 🔴 {args.product_name} Review + Coupon + 120 VIP Bonuses 🔴

Title 2 (OTO & Bundle Angle):
{args.product_name} OTO Links & Bundle Deal 🔴 {args.product_name} Walkthrough + {args.bonus_value} Bonus Vault

Title 3 (Playlist Name):
{args.product_name} Review & Demo | {args.product_name} OTOs, Coupon & 120 PrimeSite Bonuses

=========================================================
YOUTUBE DESCRIPTION (Copy & Paste)
=========================================================
👉 Grab {args.product_name} + All 120 PrimeSite VIP Bonuses ({args.bonus_value} Value) Here: {args.affiliate_link}
🔥 Apply Secret Discount Coupon at Checkout: {args.coupon_code}
🎁 Browse All 120 Bonuses (6 Collections + Top 8 Power Tools): {args.bonus_page_url}

In this {args.product_name} review and live walkthrough, we jump straight inside the software so you can see how {args.product_name} helps you {args.main_result}—plus a full breakdown of its top 3 features, OTO upgrades, active coupon code, and our complete 120-resource PrimeSite Bonus Vault.

⏱️ Video Chapters:
{fmt_ts(t0)} {args.product_name} Intro & Active Coupon
{fmt_ts(t_specs)} What Is {args.product_name}? (Top 3 Core Features)
{fmt_ts(t_demo)} {args.product_name} Live Inside Demo Walkthrough
{fmt_ts(t_bonus)} PrimeSite Bonus Vault — 6 Collections (120 Bonuses)
{fmt_ts(t_top8)} Top 8 Executive Power Bonuses ($2,826+ Value Alone)
{fmt_ts(t_outro)} Final Verdict & How to Claim Your Deal

#{args.product_name.replace(' ', '')} #{args.product_name.replace(' ', '')}Review #{args.product_name.replace(' ', '')}Demo #{args.product_name.replace(' ', '')}OTOs
"""
    (OUT_DIR / "youtube_seo_pack.txt").write_text(seo_text, encoding="utf-8")
    print("SUCCESS! Faceless v6 Review Video + Standalone PrimeSite Vault Video + Thumbnail + SEO Pack generated in:", OUT_DIR)


if __name__ == "__main__":
    main()

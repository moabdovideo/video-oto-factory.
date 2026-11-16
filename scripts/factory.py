import base64
import json
import os
import re
import subprocess
import urllib.request
import requests
from PIL import Image, ImageDraw, ImageFont
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def clean_input_text(text):
    text = re.sub(r"^(Spoken Intro & Funnel Script|1-Sentence Bridge Into Bonus Vault)\s*:\s*", "", text.strip(), flags=re.I)
    return text.strip()

def to_phonetic(text):
    s = clean_input_text(text)
    s = re.sub(r"\bOTOs\b", "O-T-O's", s)
    s = re.sub(r"\bOTO\b", "O-T-O", s)
    s = re.sub(r"\$24K\b", "twenty-four thousand dollars", s, flags=re.I)
    s = re.sub(r"\bFE\b", "Front-End", s)
    return re.sub(r"\bDFY\b", "Done-For-You", s)

def restore_seo_captions(vtt_path):
    if not os.path.exists(vtt_path):
        return
    with open(vtt_path, "r", encoding="utf-8") as f:
        txt = f.read()
    txt = txt.replace("O-T-O's", "OTOs").replace("O-T-O", "OTO")
    with open(vtt_path, "w", encoding="utf-8") as f:
        f.write(txt)

def load_payload():
    raw = os.environ.get("DISPATCH_PAYLOAD", "{}").strip()
    data = json.loads(raw) if raw and raw != "null" else {}
    return {
        "product": (data.get("product") or os.environ.get("INPUT_PRODUCT", "Product")).strip(),
        "demo_url": (data.get("demo_url") or os.environ.get("INPUT_DEMO_URL", "")).strip(),
        "aff_url": (data.get("aff_url") or os.environ.get("INPUT_AFF_URL", "https://otoslinks.com")).strip(),
        "wp_post_id": str(data.get("wp_post_id") or os.environ.get("INPUT_WP_POST_ID", "")).strip(),
        "coupon": (data.get("coupon") or os.environ.get("INPUT_COUPON", "VIPDEAL")).strip(),
        "intro_script": clean_input_text(data.get("intro_script") or os.environ.get("INPUT_INTRO", "")),
        "bridge_script": clean_input_text(data.get("bridge_script") or os.environ.get("INPUT_BRIDGE", "")),
        "review_url": data.get("review_url", "https://otoslinks.com/")
    }

def probe_duration(media_path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", media_path
    ]).decode().strip()
    return float(out)

def write_fallback_vtt(text, duration, vtt_out):
    end_m, end_s = divmod(int(duration), 60)
    vtt_content = f"WEBVTT\n\n00:00:00.000 --> 00:{end_m:02d}:{end_s:02d}.000\n{text}\n"
    with open(vtt_out, "w", encoding="utf-8") as f:
        f.write(vtt_content)
    restore_seo_captions(vtt_out)

def generate_tts(spoken_text, mp3_out, vtt_out=None):
    phonetic_txt = to_phonetic(spoken_text)
    if not phonetic_txt:
        phonetic_txt = "Welcome to this full review and O-T-O breakdown."

    # المحاولة الأولى: الأصوات العصبية من مايكروسوفت
    for voice in ["en-US-ChristopherNeural", "en-US-GuyNeural", "en-US-AriaNeural"]:
        try:
            cmd = ["edge-tts", "--voice", voice, "--text", phonetic_txt, "--write-media", mp3_out]
            if vtt_out:
                cmd.extend(["--write-subtitles", vtt_out])
            subprocess.run(cmd, check=True)
            if os.path.exists(mp3_out) and os.path.getsize(mp3_out) > 500:
                if vtt_out:
                    restore_seo_captions(vtt_out)
                return
        except Exception as e:
            print(f"edge-tts ({voice}) skipped: {e}")

    # البديل التلقائي المضمون 100% في حال حظر السيرفر
    print("Switching to guaranteed Google TTS fallback...")
    subprocess.run(["pip", "install", "-q", "gTTS"], check=True)
    from gtts import gTTS
    raw_mp3 = "raw_" + mp3_out
    gTTS(text=phonetic_txt, lang="en", tld="com").save(raw_mp3)
    subprocess.run([
        "ffmpeg", "-y", "-i", raw_mp3, "-af", "atempo=1.08", "-c:a", "libmp3lame", "-q:a", "2", mp3_out
    ], check=True)
    if vtt_out:
        dur = probe_duration(mp3_out)
        write_fallback_vtt(phonetic_txt, dur, vtt_out)

def draw_wrapped(draw, text, x, y, font, fill, max_chars=32, line_gap=14):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    cy = y
    for ln in lines:
        draw.text((x, cy), ln, font=font, fill=fill)
        bbox = draw.textbbox((x, cy), ln, font=font)
        cy += (bbox[3] - bbox[1]) + line_gap

def make_slide(out_png, badge, title, subtitle, size=(1920, 1080)):
    img = Image.new("RGB", size, "#0f172a")
    draw = ImageDraw.Draw(img)
    f_badge = ImageFont.truetype(FONT_BOLD, 30 if size[0] == 1920 else 24)
    f_title = ImageFont.truetype(FONT_BOLD, 74 if size[0] == 1920 else 56)
    f_sub = ImageFont.truetype(FONT_REG, 40 if size[0] == 1920 else 30)
    draw.rectangle([80, 70, 640, 136], fill="#10b981")
    draw.text((105, 86), badge, font=f_badge, fill="#052e16")
    draw_wrapped(draw, title, 80, 190, f_title, "#ffffff", max_chars=26 if size[0] == 1280 else 32)
    draw_wrapped(draw, subtitle, 80, size[1] - 210, f_sub, "#fbbf24", max_chars=44)
    img.save(out_png)

def encode_unified_segment(inputs_args, filter_args, out_mp4, duration=None):
    cmd = ["ffmpeg", "-y"] + inputs_args
    if duration:
        cmd += ["-t", f"{duration:.2f}"]
    cmd += filter_args + [
        "-r", "30", "-c:v", "libx264", "-profile:v", "high", "-level", "4.1",
        "-preset", "veryfast", "-crf", "22", "-video_track_timescale", "15360",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        out_mp4
    ]
    subprocess.run(cmd, check=True)
    return probe_duration(out_mp4)

def slide_with_voice(slide_png, audio_mp3, out_mp4):
    dur = probe_duration(audio_mp3) + 0.35
    return encode_unified_segment(
        ["-loop", "1", "-i", slide_png, "-i", audio_mp3],
        ["-vf", "scale=1920:1080,format=yuv420p"],
        out_mp4,
        duration=dur
    )

def download_and_shield_demo(demo_url, product, out_mp4):
    raw_demo = "raw_demo.mp4"
    safe_label = re.sub(r"[^A-Za-z0-9 .-]", "", product)
    downloaded = False

    if demo_url.lower().endswith(".mp4"):
        try:
            req = urllib.request.Request(demo_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(raw_demo, "wb") as out_f:
                out_f.write(resp.read())
            downloaded = os.path.exists(raw_demo) and os.path.getsize(raw_demo) > 10000
        except Exception as e:
            print(f"Direct MP4 download failed, trying yt-dlp: {e}")

    if not downloaded:
        try:
            cookies_b64 = os.environ.get("YT_COOKIES_B64", "").strip()
            yt_cmd = [
                "yt-dlp", "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "--merge-output-format", "mp4", "-o", raw_demo
            ]
            if cookies_b64:
                with open("cookies.txt", "wb") as cf:
                    cf.write(base64.b64decode(cookies_b64))
                yt_cmd.extend(["--cookies", "cookies.txt"])
            else:
                yt_cmd.extend(["--extractor-args", "youtube:player_client=ios,web_embedded"])
            yt_cmd.append(demo_url)
            subprocess.run(yt_cmd, check=True)
            downloaded = os.path.exists(raw_demo) and os.path.getsize(raw_demo) > 10000
        except Exception as e:
            print(f"Demo download blocked or unavailable ({e}), generating fallback demo segment...")

    if not downloaded:
        make_slide("demo_fallback.png", "VERIFIED ARCHITECTURE", f"{product} Dashboard & OTO Funnel", "Complete Feature & Upgrade Breakdown")
        generate_tts(f"Inside the {product} dashboard, you get full access to the core engine and automation workflows.", "demo_fb.mp3")
        slide_with_voice("demo_fallback.png", "demo_fb.mp3", raw_demo)

    total_dur = probe_duration(raw_demo)
    for idx, ratio in enumerate([0.2, 0.5, 0.75], start=1):
        ts = max(1, int(total_dur * ratio))
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(ts), "-i", raw_demo, "-frames:v", "1",
            "-vf", f"scale=1200:-1,drawtext=fontfile={FONT_BOLD}:text='{safe_label} - OTOsLinks.com':x=20:y=20:fontsize=24:fontcolor=white:box=1:boxcolor=black@0.6",
            "-q:v", "80", f"screenshot_{idx}.webp"
        ], check=True)

    vf = (
        "setpts=PTS/1.04,scale=1760:990:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=#0f172a,"
        f"drawtext=fontfile={FONT_BOLD}:text='{safe_label} Live UI Audit - OTOsLinks.com':x=80:y=16:fontsize=26:fontcolor=white,"
        "format=yuv420p"
    )
    return encode_unified_segment(["-i", raw_demo], ["-vf", vf, "-af", "atempo=1.04"], out_mp4)

def fmt_chapter(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

def upload_to_youtube(video_path, thumb_path, vtt_path, title, description, tags):
    if not os.environ.get("YT_REFRESH_TOKEN"):
        print("Skipping YouTube upload (no credentials set yet).")
        return None
    creds = Credentials(
        None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.force-ssl"
        ]
    )
    yt = build("youtube", "v3", credentials=creds)
    req = yt.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title[:100],
                "description": description[:4900],
                "tags": tags[:15],
                "categoryId": "28",
                "defaultLanguage": "en",
                "defaultAudioLanguage": "en"
            },
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
        },
        media_body=MediaFileUpload(video_path, chunksize=8 * 1024 * 1024, resumable=True)
    )
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid_id = resp["id"]

    yt.thumbnails().set(videoId=vid_id, media_body=MediaFileUpload(thumb_path)).execute()
    if os.path.exists(vtt_path):
        yt.captions().insert(
            part="snippet",
            body={"snippet": {"videoId": vid_id, "language": "en", "name": "English SEO"}},
            media_body=MediaFileUpload(vtt_path, mimetype="application/octet-stream")
        ).execute()
    return vid_id

def embed_in_wordpress(wp_post_id, video_id, product):
    site = os.environ.get("WP_SITE_URL", "").rstrip("/")
    user = os.environ.get("WP_USER", "")
    app_pw = os.environ.get("WP_APP_PASSWORD", "")
    if not (site and user and app_pw and wp_post_id and video_id):
        return
    endpoint = f"{site}/wp-json/wp/v2/posts/{wp_post_id}"
    r = requests.get(endpoint, params={"context": "edit"}, auth=(user, app_pw), timeout=20)
    if r.status_code != 200:
        return
    raw_html = r.json().get("content", {}).get("raw", "")
    if video_id in raw_html:
        return
    iframe = (
        f'\n<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;border-radius:12px;margin:22px 0;border:2px solid #10b981;">'
        f'<iframe src="https://www.youtube.com/embed/{video_id}" title="{product} Review & OTOs Demo" '
        f'style="position:absolute;top:0;left:0;width:100%;height:100%;border:0;" allowfullscreen loading="lazy"></iframe></div>\n'
    )
    requests.post(endpoint, json={"content": iframe + raw_html}, auth=(user, app_pw), timeout=25)

def main():
    os.makedirs("assets_cache", exist_ok=True)
    p = load_payload()
    prod = p["product"]

    generate_tts(p["intro_script"], "intro.mp3", "intro.vtt")
    make_slide("intro.png", "HONEST LAUNCH AUDIT", f"{prod} Review & All OTOs", f"Active Coupon: {p['coupon']} + $24K VIP Bonus Vault")
    d_intro = slide_with_voice("intro.png", "intro.mp3", "seg1_intro.mp4")

    d_demo = download_and_shield_demo(p["demo_url"], prod, "seg2_demo.mp4")

    generate_tts(p["bridge_script"], "bridge.mp3")
    make_slide("bridge.png", "$24,000 VIP BONUS VAULT", f"6 Free VIP Packages For {prod}", "Delivered Automatically Inside Your Receipt")
    d_bridge = slide_with_voice("bridge.png", "bridge.mp3", "seg3_bridge.mp4")

    clips = ["seg1_intro.mp4", "seg2_demo.mp4", "seg3_bridge.mp4"]
    d_vault = 0.0
    vault_url = os.environ.get("BONUS_VAULT_MP4_URL", "").strip()
    cached_vault = "assets_cache/bonus_vault_norm.mp4"
    if vault_url:
        if not os.path.exists(cached_vault):
            urllib.request.urlretrieve(vault_url, "raw_vault.mp4")
            vf_vault = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=#0f172a,format=yuv420p"
            encode_unified_segment(["-i", "raw_vault.mp4"], ["-vf", vf_vault], cached_vault)
        d_vault = probe_duration(cached_vault)
        clips.append(cached_vault)

    outro_txt = (
        f"Grab {prod} via the first link in the description below, apply coupon code {p['coupon']} "
        f"at checkout, and your $24K VIP Bonus Vault unlocks automatically inside your receipt."
    )
    generate_tts(outro_txt, "outro.mp3")
    make_slide("outro.png", "LOCK IN LAUNCH DEAL", f"Claim {prod} + $24K VIP Bonuses", f"1st Link Below • Coupon: {p['coupon']} • admin@otoslinks.com")
    slide_with_voice("outro.png", "outro.mp3", "seg4_outro.mp4")
    clips.append("seg4_outro.mp4")

    with open("concat.txt", "w", encoding="utf-8") as f:
        for c in clips:
            f.write(f"file '{os.path.abspath(c)}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy", "final_review.mp4"], check=True)

    make_slide("thumb.png", "FULL OTOs + DEMO", f"{prod} Review & Bundle", f"Coupon: {p['coupon']} + Free $24K VIP Vault", size=(1280, 720))

    t_demo = d_intro
    t_bonus = d_intro + d_demo
    t_outro = t_bonus + d_bridge + d_vault
    desc = (
        f"Get {prod} + Coupon ({p['coupon']}) + $24K VIP Bonuses: {p['aff_url']}\n"
        f"Full Written {prod} OTOs & Bundle Review: {p['review_url']}\n\n"
        f"Chapters:\n"
        f"00:00 {prod} Review, Limits & All OTOs Breakdown\n"
        f"{fmt_chapter(t_demo)} {prod} Live UI Demo Walkthrough\n"
        f"{fmt_chapter(t_bonus)} Free $24,000 VIP Bonus Vault (6 Packages)\n"
        f"{fmt_chapter(t_outro)} Coupon {p['coupon']} & Instant Bonus Delivery\n\n"
        f"Support & Bonus Verification: admin@otoslinks.com"
    )
    tags = [
        f"{prod} review", f"{prod} oto", f"{prod} otos", f"all {prod} otos",
        f"{prod} bundle", f"{prod} bundle deal", f"{prod} coupon", f"{prod} demo"
    ]
    title = f"{prod} Review & All OTOs | Live Demo, Bundle Deal, Coupon & $24K Bonuses"
    vid_id = upload_to_youtube("final_review.mp4", "thumb.png", "intro.vtt", title, desc, tags)
    if vid_id:
        embed_in_wordpress(p["wp_post_id"], vid_id, prod)
        print(f"Published: https://youtu.be/{vid_id}")

if __name__ == "__main__":
    main()

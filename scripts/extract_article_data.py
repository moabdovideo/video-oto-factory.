#!/usr/bin/env python3
"""
OTOsLinks Auto-Pilot — Smart WordPress Article & Demo Extractor
Reads GitHub event payload (repository_dispatch from WordPress/Make or workflow_dispatch),
extracts product_name, main_result, top 3 features, and demo_url using Gemini API (optional)
with a 100% bulletproof offline heuristic fallback.
"""

import os
import re
import sys
import json
import html
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

JOB_CONFIG_PATH = Path("/tmp/oto_job_config.json")


def load_event_payload() -> dict:
    """Loads client_payload (repository_dispatch) or inputs (workflow_dispatch) losslessly."""
    ev_path = os.getenv("GITHUB_EVENT_PATH", "").strip()
    if ev_path and Path(ev_path).exists():
        try:
            data = json.loads(Path(ev_path).read_text(encoding="utf-8"))
            if isinstance(data.get("client_payload"), dict) and data["client_payload"]:
                return data["client_payload"]
            if isinstance(data.get("inputs"), dict) and data["inputs"]:
                return data["inputs"]
        except Exception as e:
            print(f"[WARN] Could not parse GITHUB_EVENT_PATH: {e}")
    return {}


def detect_demo_url(text_or_html: str) -> str:
    """Finds Wistia, YouTube, Vimeo, or direct MP4 demo links inside WordPress content."""
    if not text_or_html:
        return ""
    raw = html.unescape(text_or_html)
    patterns = [
        r'https?://[^\s"\'<>]*wistia\.(?:com|net)/(?:embed/(?:iframe|medias)|medias)/[a-zA-Z0-9]+',
        r'https?://[^\s"\'<>]*wi\.st/(?:medias|embed/iframe|embed)/[a-zA-Z0-9]+',
        r'wistia_async_([a-zA-Z0-9]{6,})',
        r'https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|embed/)|youtu\.be/)[a-zA-Z0-9_-]{8,}',
        r'wistia-player[^>]+media-id=["\']([a-zA-Z0-9]{6,})["\']',
        r'https?://(?:player\.)?vimeo\.com/(?:video/)?[0-9]{6,}(?:/[a-fA-F0-9]{6,}|\?[^\s"\'<>]*h=[a-fA-F0-9]{6,}[^\s"\'<>]*)?',
        r'https?://[^\s"\'<>]+\.mp4(?:\?[^\s"\'<>]*)?',
    ]
    for pat in patterns:
        m = re.search(pat, raw, flags=re.IGNORECASE)
        if m:
            if pat.startswith("wistia_async_") or pat.startswith("wistia-player"):
                return f"https://fast.wistia.net/embed/iframe/{m.group(1)}"
            return m.group(0).rstrip(".,;)")
    return ""


def clean_product_name_from_title(title: str) -> str:
    """Extracts a clean software product name from a typical review/OTO/bundle post title."""
    t = html.unescape((title or "").strip())
    if not t:
        return "Featured AI Software"
    # Remove bracketed tags like [2026], (Full Demo), etc.
    t = re.sub(r'[\[\(][^\]\)]*[\]\)]', ' ', t)
    # Cut at separators like :, |, -, –
    t = re.split(r'\s*[:|–—]\s*|\s+-\s+', t)[0].strip()
    # Strip trailing review/affiliate buzzwords
    t = re.sub(
        r'\b(honest\s+review|full\s+review|review|reviews|otos?\s*links?|otos?|bundle\s*deal|bundle|upsells?|demo|walkthrough|bonuses?|bonus|coupon\s*code|coupon|discount|pricing|price|202[4-9])\b.*$',
        '',
        t,
        flags=re.IGNORECASE,
    ).strip(" -:|,•!?.")
    words = t.split()
    if not words:
        return "Featured AI Software"
    return " ".join(words[:5])


def extract_with_gemini(article_title: str, article_text: str) -> dict:
    """Uses Gemini REST API (free tier supported) to extract crisp marketing specs."""
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key or requests is None or not (article_title or article_text):
        return {}

    prompt = f"""You are a SaaS YouTube review producer. Extract structured video metadata from this WordPress software review article.
Return ONLY valid JSON with these exact 5 keys:
- "product_name": Exact software product name (1 to 5 words, no "Review", no "OTO", no year).
- "main_result": Concise benefit phrase (8 to 15 words) starting with a lowercase verb so it completes: "Built to help you {{main_result}}". No period at end.
- "feature_1": Core feature #1 (5 to 11 words, punchy, commercial value).
- "feature_2": Core feature #2 (5 to 11 words, punchy, commercial value).
- "feature_3": Core feature #3 (5 to 11 words, punchy, commercial value).

STRICT RULES:
- NEVER include any coupon codes, promo codes, or dollar prices.
- Output strictly raw JSON only (no markdown fences, no commentary).

ARTICLE TITLE: {article_title[:250]}
ARTICLE CONTENT:
{article_text[:5500]}
"""

    for model in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            resp = requests.post(
                url,
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
                },
                timeout=30,
            )
            if resp.status_code != 200:
                print(f"[INFO] Gemini ({model}) HTTP {resp.status_code}, trying next...")
                continue
            body = resp.json()
            raw_text = body["candidates"][0]["content"]["parts"][0]["text"].strip()
            raw_text = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw_text, flags=re.IGNORECASE | re.DOTALL).strip()
            parsed = json.loads(raw_text)
            if all(isinstance(parsed.get(k), str) and parsed[k].strip() for k in ("product_name", "main_result", "feature_1", "feature_2", "feature_3")):
                print(f"[AI] Extracted article specs cleanly via {model}!")
                return {k: parsed[k].strip() for k in ("product_name", "main_result", "feature_1", "feature_2", "feature_3")}
        except Exception as e:
            print(f"[WARN] Gemini ({model}) extraction error: {e}")
    return {}


def heuristic_extract(article_title: str, article_text: str) -> dict:
    """Zero-API fallback parser that extracts product name, result, and 3 clean features from text."""
    pname = clean_product_name_from_title(article_title)
    skip_words = ("introduction", "conclusion", "verdict", "faq", "pricing", "price", "oto", "upsell", "bonus", "coupon", "promo", "discount", "offer status", "active & working", "checkout", "funnel", "verified official", "% off", "off today", "limited time", "click here", "vip", "refund", "guarantee", "table of contents", "pros and cons")

    candidates = []
    for raw_line in (article_text or "").splitlines():
        line = re.sub(r'^[\-\*\•\✓\✔\👉\🔥\d\.\)\s]+', '', raw_line).strip()
        if 22 <= len(line) <= 95:
            low = line.lower()
            if any(sw in low for sw in skip_words):
                continue
            if "http" in low or "@" in low:
                continue
            if line not in candidates:
                candidates.append(line.rstrip(".:;"))

    default_features = [
        f"Automated All-In-One {pname} Cloud Dashboard & Fast Setup",
        "Done-For-You Templates & Built-In AI Workflow Engine",
        "Full Commercial Rights with Zero Coding or Monthly Fees",
    ]
    feats = (candidates[:3] + default_features)[:3]

    main_result = f"automate your workflow and launch commercial projects faster with {pname}"
    for raw_line in (article_text or "").splitlines():
        m = re.search(r'\b(?:helps?\s+you|allows?\s+you\s+to|lets?\s+you|designed\s+to)\s+([^\.\!\?\n]{18,95})', raw_line, flags=re.IGNORECASE)
        if m:
            candidate_res = m.group(1).strip(" ,;:-")
            if "http" not in candidate_res.lower() and "coupon" not in candidate_res.lower():
                main_result = candidate_res[0].lower() + candidate_res[1:]
                break

    return {
        "product_name": pname,
        "main_result": main_result,
        "feature_1": feats[0],
        "feature_2": feats[1],
        "feature_3": feats[2],
    }


def write_github_env(kv: dict):
    env_file = os.getenv("GITHUB_ENV", "").strip()
    if not env_file:
        return
    with open(env_file, "a", encoding="utf-8") as f:
        for k, v in kv.items():
            val = str(v or "").replace("\r", " ").replace("\n", " ").strip()
            f.write(f"{k}<<OTO_EOF\n{val}\nOTO_EOF\n")


def main():
    payload = load_event_payload()

    def pick(key: str, env_key: str, default: str = "") -> str:
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        ev = os.getenv(env_key, "")
        if ev and ev.strip():
            return ev.strip()
        return default

    article_title = pick("article_title", "ARTICLE_TITLE", "") or pick("post_title", "POST_TITLE", "")
    article_text = pick("article_text", "ARTICLE_TEXT", "")
    post_url = pick("post_url", "POST_URL", "") or pick("affiliate_link", "AFFILIATE_LINK", "https://otoslinks.com/")
    post_id = str(payload.get("post_id") or os.getenv("POST_ID") or "").strip()

    explicit_product = pick("product_name", "PRODUCT_NAME", "")
    explicit_result = pick("main_result", "MAIN_RESULT", "")
    explicit_f1 = pick("feature_1", "FEATURE_1", "")
    explicit_f2 = pick("feature_2", "FEATURE_2", "")
    explicit_f3 = pick("feature_3", "FEATURE_3", "")
    demo_url = pick("demo_url", "DEMO_URL", "") or detect_demo_url(payload.get("article_html", "") + "\n" + article_text)

    # Decide whether we need AI/heuristic extraction from WordPress article
    if article_title or article_text:
        print(f"[EXTRACT] Auto-Pilot Mode triggered from WordPress article: {article_title[:80]}")
        extracted = extract_with_gemini(article_title, article_text)
        if not extracted:
            print("[EXTRACT] Using offline heuristic article parser...")
            extracted = heuristic_extract(article_title, article_text)
        product_name = explicit_product or extracted["product_name"]
        main_result = explicit_result or extracted["main_result"]
        feature_1 = explicit_f1 or extracted["feature_1"]
        feature_2 = explicit_f2 or extracted["feature_2"]
        feature_3 = explicit_f3 or extracted["feature_3"]
    else:
        product_name = explicit_product or "AI Secret Image Codebook"
        main_result = explicit_result or "generate studio-grade commercial graphics using secret style parameters"
        feature_1 = explicit_f1 or "Secret Style Reference Matrix & Optical Camera Lighting Tokens"
        feature_2 = explicit_f2 or "Multi-Scene Character Consistency Lock & Crisp Typography Syntax"
        feature_3 = explicit_f3 or "Print-On-Demand Vector Isolation & Commercial Product Mockup Codes"

    config = {
        "PRODUCT_NAME": product_name,
        "MAIN_RESULT": main_result,
        "FEATURE_1": feature_1,
        "FEATURE_2": feature_2,
        "FEATURE_3": feature_3,
        "DEMO_URL": demo_url,
        "AFFILIATE_LINK": post_url,
        "BONUS_VALUE": pick("bonus_value", "BONUS_VALUE", "$24,000+"),
        "BONUS_PAGE_URL": pick("bonus_page_url", "BONUS_PAGE_URL", "https://otoslinks.com/vip-hot-bonuses-value-24k/"),
        "VOICE_NAME": pick("voice_name", "VOICE_NAME", "en-US-GuyNeural"),
        "BUILD_STANDALONE_VAULT": pick("build_standalone_vault", "BUILD_STANDALONE_VAULT", "false"),
        "YT_PRIVACY_STATUS": pick("yt_privacy_status", "YT_PRIVACY_STATUS", "public"),
        "POST_ID": post_id,
    }

    JOB_CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    write_github_env(config)
    print("[EXTRACT] Resolved Job Config:")
    for k in ("PRODUCT_NAME", "MAIN_RESULT", "FEATURE_1", "FEATURE_2", "FEATURE_3", "DEMO_URL", "AFFILIATE_LINK", "YT_PRIVACY_STATUS"):
        print(f"  - {k}: {config[k]}")


if __name__ == "__main__":
    main()

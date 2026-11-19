#!/usr/bin/env python3
"""
OTOsLinks Auto-Pilot — Direct YouTube Data API v3 Auto-Publisher
Zero bloated SDK dependencies — uses pure requests with resumable upload,
custom thumbnail upload, optional playlist assignment, and optional webhook callback.
"""

import os
import sys
import json
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR.parent / "review-output-pack"
META_PATH = OUT_DIR / "youtube_metadata.json"
RESULT_PATH = OUT_DIR / "youtube_publish_result.json"


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"OAuth token refresh failed (HTTP {resp.status_code}): {resp.text[:400]}")
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError("OAuth response did not include access_token.")
    return token


def upload_video_resumable(access_token: str, video_path: Path, meta: dict) -> str:
    file_size = video_path.stat().st_size
    privacy = (meta.get("privacy_status") or os.getenv("YT_PRIVACY_STATUS") or "public").strip().lower()
    if privacy not in ("public", "unlisted", "private"):
        privacy = "public"

    title = (meta.get("title") or "Software Review & Live Demo").replace("<", "").replace(">", "").strip()[:98]
    description = (meta.get("description") or "").replace("<", "").replace(">", "").strip()[:4800]
    tags = [t.replace("<", "").replace(">", "").strip() for t in (meta.get("tags") or []) if t.strip()][:15]
    category_id = str(meta.get("category_id") or "28")

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    init_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Length": str(file_size),
        "X-Upload-Content-Type": "video/mp4",
    }

    print(f"[YOUTUBE] Initiating resumable upload ({file_size / (1024 * 1024):.1f} MB) | Privacy: {privacy}")
    print(f"[YOUTUBE] Title: {title}")
    init_resp = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers=init_headers,
        json=body,
        timeout=45,
    )
    if init_resp.status_code not in (200, 201):
        raise RuntimeError(f"YouTube upload init failed (HTTP {init_resp.status_code}): {init_resp.text[:500]}")

    upload_url = init_resp.headers.get("Location")
    if not upload_url:
        raise RuntimeError("YouTube resumable upload did not return a Location URL.")

    # Upload video in 8 MB chunks (reliable & fast on GitHub Actions)
    chunk_size = 8 * 1024 * 1024
    video_id = None
    with open(video_path, "rb") as f:
        offset = 0
        while offset < file_size:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            end_byte = offset + len(chunk) - 1
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "video/mp4",
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {offset}-{end_byte}/{file_size}",
            }
            for attempt in range(3):
                r = requests.put(upload_url, headers=headers, data=chunk, timeout=180)
                if r.status_code in (200, 201):
                    video_id = r.json().get("id")
                    break
                if r.status_code == 308:
                    break
                if r.status_code >= 500 and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"Chunk upload failed at byte {offset} (HTTP {r.status_code}): {r.text[:400]}")
            offset = end_byte + 1
            pct = min(100, int(offset * 100 / file_size))
            print(f"[YOUTUBE] Uploaded {pct}% ({offset / (1024 * 1024):.1f}/{file_size / (1024 * 1024):.1f} MB)")

    if not video_id:
        raise RuntimeError("Upload finished but no YouTube video ID was returned.")
    return video_id


def upload_thumbnail(access_token: str, video_id: str, thumb_path: Path):
    if not thumb_path.exists():
        return False
    resp = requests.post(
        f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={video_id}&uploadType=media",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "image/jpeg",
        },
        data=thumb_path.read_bytes(),
        timeout=60,
    )
    if resp.status_code in (200, 201):
        print(f"[YOUTUBE] Custom thumbnail uploaded successfully!")
        return True
    print(f"[WARN] Custom thumbnail skipped (HTTP {resp.status_code} — verify phone on YouTube Studio if 403): {resp.text[:250]}")
    return False


def add_to_playlist(access_token: str, video_id: str, playlist_id: str):
    if not playlist_id:
        return False
    resp = requests.post(
        "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }
        },
        timeout=30,
    )
    if resp.status_code in (200, 201):
        print(f"[YOUTUBE] Added video to playlist {playlist_id}!")
        return True
    print(f"[WARN] Could not add video to playlist (HTTP {resp.status_code}): {resp.text[:250]}")
    return False


def notify_callback(webhook_url: str, result: dict):
    if not webhook_url:
        return
    try:
        r = requests.post(webhook_url, json=result, timeout=20)
        print(f"[WEBHOOK] Callback notified -> HTTP {r.status_code}")
    except Exception as e:
        print(f"[WARN] Callback webhook error: {e}")


def main():
    client_id = (os.getenv("YT_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("YT_CLIENT_SECRET") or "").strip()
    refresh_token = (os.getenv("YT_REFRESH_TOKEN") or "").strip()

    if not (client_id and client_secret and refresh_token):
        print("[YOUTUBE] YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN not set in GitHub Secrets yet.")
        print("[YOUTUBE] Skipping direct upload — your finished video & thumbnail are ready in Artifacts!")
        return

    if not META_PATH.exists():
        raise FileNotFoundError(f"Missing metadata file: {META_PATH}")

    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    video_path = OUT_DIR / "final_youtube_video.mp4"
    thumb_path = OUT_DIR / "youtube_thumbnail.jpg"
    if not video_path.exists():
        raise FileNotFoundError(f"Missing video file: {video_path}")

    access_token = refresh_access_token(client_id, client_secret, refresh_token)
    video_id = upload_video_resumable(access_token, video_path, meta)
    thumb_ok = upload_thumbnail(access_token, video_id, thumb_path)

    playlist_id = (os.getenv("YT_PLAYLIST_ID") or "").strip()
    if playlist_id:
        add_to_playlist(access_token, video_id, playlist_id)

    yt_url = f"https://www.youtube.com/watch?v={video_id}"
    result = {
        "status": "published",
        "video_id": video_id,
        "youtube_url": yt_url,
        "studio_url": f"https://studio.youtube.com/video/{video_id}/edit",
        "title": meta.get("title", ""),
        "thumbnail_uploaded": thumb_ok,
        "post_id": meta.get("post_id", ""),
        "post_url": meta.get("post_url", ""),
    }
    RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[YOUTUBE] SUCCESS! Video uploaded: {yt_url}")

    webhook_url = (os.getenv("CALLBACK_WEBHOOK_URL") or "").strip()
    if webhook_url:
        notify_callback(webhook_url, result)


if __name__ == "__main__":
    main()

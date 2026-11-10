#!/usr/bin/env python3
"""
The Home Organizer — Pinterest API v5 integration (free, official API).

What this does:
  * Exchanges an OAuth authorization code for tokens (or refreshes a token).
  * Lists the owner's boards (to find a board_id — NEVER guessed).
  * Creates image pins via POST /v5/pins (media_source: image_base64, so no
    public image hosting is needed; image_url is supported as an option).
  * Creates video pins via the /v5/media flow: register -> upload to the
    presigned S3 upload_url -> poll GET /v5/media/{id} until "succeeded"
    -> POST /v5/pins with media_source source_type "video_id" + a
    mandatory cover_image_url (must be a publicly reachable image URL).
  * Dry-run mode validates a pins CSV and prints the exact payloads
    without calling Pinterest at all.

What this does NOT do:
  * No password, no login, no scraping, no browser automation, no bypass.
  * No token/secret is ever hard-coded here. Credentials come from
    environment variables or a local .env file (see .env.example).
    .env is git-ignored and must never be shared or committed.
  * Nothing is submitted to Pinterest by running this file with no
    arguments — it only shows usage. Use --dry-run first, then a real
    run only after Standard access is granted (Trial pins are visible
    only to the creator).

Scopes required: boards:read, boards:write, pins:read, pins:write
Token lifetime (per Pinterest docs): access token 30 days,
refresh token 60 days, rotating on each refresh.
Rate limits (Standard): ~100 writes/min/user, ~1000 reads/min.

Usage:
  python3 pinterest_api.py --dry-run --csv pins.csv
  python3 pinterest_api.py --auth-url
  python3 pinterest_api.py --exchange-code CODE
  python3 pinterest_api.py --refresh
  python3 pinterest_api.py --list-boards
  python3 pinterest_api.py --publish --csv pins.csv --board-id BOARD_ID [--day 1]
  python3 pinterest_api.py --publish-one --media media/pin-v01-...webp \
      --title "..." --description "..." --link "https://..." --board-id BOARD_ID

Env vars (or .env in this folder):
  PINTEREST_APP_ID, PINTEREST_APP_SECRET, PINTEREST_REDIRECT_URI,
  PINTEREST_ACCESS_TOKEN, PINTEREST_REFRESH_TOKEN
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import mimetypes
import os
import sys
import time
import urllib.parse
import urllib.request

API_BASE = "https://api.pinterest.com/v5"
AUTH_URL = "https://www.pinterest.com/oauth/"
TOKEN_URL = f"{API_BASE}/oauth/token"
SCOPES = "boards:read,boards:write,pins:read,pins:write"
MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")


def load_dotenv(path: str = ".env") -> None:
    """Tiny .env loader (KEY=VALUE lines, no external dependency)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"Missing {name}. Set it in the environment or .env (see .env.example).")
    return value


def http_json(method: str, url: str, token: str | None = None,
              payload: dict | None = None, timeout: int = 60) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise SystemExit(f"{method} {url} -> HTTP {exc.code}: {body}") from exc


# ---------------------------------------------------------------- OAuth

def auth_url() -> str:
    params = {
        "client_id": env("PINTEREST_APP_ID"),
        "redirect_uri": env("PINTEREST_REDIRECT_URI"),
        "response_type": "code",
        "scope": SCOPES,
        "state": "thehomeorganizer",
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(params)


def exchange_code(code: str) -> dict:
    """Exchange an authorization code for access + refresh tokens.

    Pinterest requires HTTP Basic auth with base64(app_id:app_secret).
    """
    basic = base64.b64encode(
        f"{env('PINTEREST_APP_ID')}:{env('PINTEREST_APP_SECRET')}".encode()
    ).decode()
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": env("PINTEREST_REDIRECT_URI"),
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, method="POST")
    req.add_header("Authorization", f"Basic {basic}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Token exchange -> HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc


def refresh_token() -> dict:
    basic = base64.b64encode(
        f"{env('PINTEREST_APP_ID')}:{env('PINTEREST_APP_SECRET')}".encode()
    ).decode()
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": env("PINTEREST_REFRESH_TOKEN"),
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, method="POST")
    req.add_header("Authorization", f"Basic {basic}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Token refresh -> HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc


# ---------------------------------------------------------------- Pins

def list_boards(token: str) -> dict:
    return http_json("GET", f"{API_BASE}/user_account/boards?page_size=25", token)


def validate_pin(title: str, description: str, link: str) -> list[str]:
    errors = []
    if not title or len(title) > 100:
        errors.append(f"title must be 1-100 chars (got {len(title)})")
    if len(description) > 800:
        errors.append(f"description must be <=800 chars (got {len(description)})")
    if not link.startswith("https://"):
        errors.append("link must be an https URL")
    if "tag=aurokids-20" not in link:
        errors.append("link is missing tag=aurokids-20")
    if "As an Amazon Associate I earn from qualifying purchases" not in description:
        errors.append("description is missing the Associates disclosure")
    return errors


def create_image_pin(token: str, board_id: str, title: str, description: str,
                     link: str, media_path: str, image_url: str | None = None) -> dict:
    if image_url:
        media_source = {"source_type": "image_url", "url": image_url}
    else:
        with open(media_path, "rb") as fh:
            data = base64.b64encode(fh.read()).decode()
        content_type, _ = mimetypes.guess_type(media_path)
        if content_type not in ("image/jpeg", "image/png"):
            # Pinterest image_base64 accepts jpeg/png; .webp files must be
            # converted to jpg/png first (see test-pin-plan.md).
            raise SystemExit(f"{media_path}: image_base64 needs image/jpeg or image/png, got {content_type}. Convert .webp to .jpg first.")
        media_source = {"source_type": "image_base64", "content_type": content_type, "data": data}
    payload = {
        "board_id": board_id,
        "title": title,
        "description": description,
        "link": link,
        "media_source": media_source,
    }
    return http_json("POST", f"{API_BASE}/pins", token, payload)


def register_video(token: str) -> dict:
    return http_json("POST", f"{API_BASE}/media", token, {"media_type": "video"})


def upload_video_to_s3(upload_url: str, upload_parameters: dict, video_path: str) -> None:
    """Multipart POST to the presigned S3 URL. No bearer token here."""
    import requests  # only needed for the multipart S3 upload
    with open(video_path, "rb") as fh:
        files = {"file": (os.path.basename(video_path), fh, "video/mp4")}
        resp = requests.post(upload_url, data=upload_parameters, files=files, timeout=300)
    if resp.status_code not in (200, 201, 204):
        raise SystemExit(f"S3 upload -> HTTP {resp.status_code}: {resp.text[:500]}")


def poll_media(token: str, media_id: str, timeout_s: int = 600) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        result = http_json("GET", f"{API_BASE}/media/{media_id}", token)
        if result.get("status") == "succeeded":
            return result
        if result.get("status") == "failed":
            raise SystemExit(f"Media {media_id} failed: {result}")
        time.sleep(10)
    raise SystemExit(f"Media {media_id} did not reach 'succeeded' within {timeout_s}s")


def create_video_pin(token: str, board_id: str, title: str, description: str,
                     link: str, media_id: str, cover_image_url: str) -> dict:
    payload = {
        "board_id": board_id,
        "title": title,
        "description": description,
        "link": link,
        "media_source": {
            "source_type": "video_id",
            "media_id": media_id,
            "cover_image_url": cover_image_url,
        },
    }
    return http_json("POST", f"{API_BASE}/pins", token, payload)


# ---------------------------------------------------------------- CSV / CLI

def read_pins(csv_path: str) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for i, row in enumerate(rows, start=1):
        errs = validate_pin(row["Title"], row["Description"], row["Link"])
        if errs:
            raise SystemExit(f"Row {i} ({row.get('Media_File','?')}): " + "; ".join(errs))
    return rows


def resolve_media(filename: str) -> str:
    candidates = [
        filename,
        os.path.join(MEDIA_DIR, filename),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                     "thehomeorganizerdaily", "tailwind-pack-2026-11-04", "media", filename),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise SystemExit(f"Media file not found: {filename} (looked in {candidates})")


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(description="The Home Organizer — Pinterest API v5")
    ap.add_argument("--dry-run", action="store_true", help="Validate CSV, print payloads, call nothing")
    ap.add_argument("--csv", default="pins.csv", help="Pins CSV (default: pins.csv)")
    ap.add_argument("--auth-url", action="store_true", help="Print the OAuth authorize URL")
    ap.add_argument("--exchange-code", metavar="CODE", help="Exchange an OAuth code for tokens")
    ap.add_argument("--refresh", action="store_true", help="Refresh the access token")
    ap.add_argument("--list-boards", action="store_true", help="List the owner's boards")
    ap.add_argument("--publish", action="store_true", help="Publish pins from --csv")
    ap.add_argument("--publish-one", action="store_true", help="Publish a single pin")
    ap.add_argument("--board-id", help="Board ID from --list-boards (never guess it)")
    ap.add_argument("--day", type=int, default=0, help="Only publish rows with Day == this value (0 = all)")
    ap.add_argument("--media", help="Media file for --publish-one")
    ap.add_argument("--image-url", help="Public image URL instead of a local file")
    ap.add_argument("--cover-url", help="Public cover image URL for a video pin (required)")
    ap.add_argument("--title", help="Title for --publish-one")
    ap.add_argument("--description", help="Description for --publish-one")
    ap.add_argument("--link", help="Link for --publish-one")
    args = ap.parse_args()

    if args.auth_url:
        print(auth_url())
        return
    if args.exchange_code:
        print(json.dumps(exchange_code(args.exchange_code), indent=2))
        print("SAVE the refresh_token in .env as PINTEREST_REFRESH_TOKEN. Never share it.")
        return
    if args.refresh:
        print(json.dumps(refresh_token(), indent=2))
        print("SAVE the new access_token and refresh_token (refresh rotates on each use).")
        return

    if args.dry_run:
        rows = read_pins(args.csv)
        print(f"DRY RUN OK: {len(rows)} rows validated, no API calls made.")
        for row in rows:
            print(f"  - {row['Media_File']} | {row['Title'][:60]} | {row['Link']}")
        return

    token = env("PINTEREST_ACCESS_TOKEN")
    if args.list_boards:
        print(json.dumps(list_boards(token), indent=2))
        return

    if args.publish_one:
        if not args.board_id or not args.title or not args.description or not args.link:
            ap.error("--publish-one needs --board-id, --title, --description, --link")
        errs = validate_pin(args.title, args.description, args.link)
        if errs:
            raise SystemExit("; ".join(errs))
        media_path = resolve_media(args.media) if args.media else None
        if media_path and media_path.lower().endswith((".mp4", ".mov")):
            if not args.cover_url:
                raise SystemExit("Video pins need --cover-url (a public image URL).")
            reg = register_video(token)
            upload_video_to_s3(reg["upload_url"], reg["upload_parameters"], media_path)
            poll_media(token, reg["media_id"])
            result = create_video_pin(token, args.board_id, args.title, args.description,
                                      args.link, reg["media_id"], args.cover_url)
        else:
            result = create_image_pin(token, args.board_id, args.title, args.description,
                                      args.link, media_path or "", args.image_url)
        print(json.dumps(result, indent=2))
        return

    if args.publish:
        if not args.board_id:
            raise SystemExit("--publish needs --board-id (get it from --list-boards).")
        rows = read_pins(args.csv)
        published = []
        for row in rows:
            if args.day and int(row.get("Day", 0)) != args.day:
                continue
            media_path = resolve_media(row["Media_File"])
            if media_path.lower().endswith((".mp4", ".mov")):
                cover = row.get("Cover_URL", "").strip()
                if not cover:
                    print(f"SKIP {row['Media_File']}: video needs Cover_URL in the CSV.")
                    continue
                reg = register_video(token)
                upload_video_to_s3(reg["upload_url"], reg["upload_parameters"], media_path)
                poll_media(token, reg["media_id"])
                result = create_video_pin(token, args.board_id, row["Title"], row["Description"],
                                          row["Link"], reg["media_id"], cover)
            else:
                result = create_image_pin(token, args.board_id, row["Title"], row["Description"],
                                          row["Link"], media_path, row.get("Media_URL") or None)
            published.append(result.get("id"))
            print(f"Published {row['Media_File']} -> pin {result.get('id')}")
            time.sleep(2)  # gentle pace; never burst
        print(json.dumps({"published_pin_ids": published}, indent=2))
        return

    ap.print_help()


if __name__ == "__main__":
    main()

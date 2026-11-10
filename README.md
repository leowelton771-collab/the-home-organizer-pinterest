# The Home Organizer — Free Pinterest API solution

**Goal:** Nova uploads pins herself, daily, via Pinterest's official API v5 — free, no Muse-browser bot wall, no paid scheduler. Leo does no daily work.

**Status (5 Nov 2026): everything Nova can build is built. Nothing submitted, nothing published, no account created, no password/code entered.**

## What is in this folder

| File | What it is |
|---|---|
| `index.html` | The Home Organizer landing page for the free GitHub Pages site: DIY home organization for small spaces, pantry/kitchen/closet/renter-friendly, Pinterest board link, no prices, no claims. |
| `privacy.html` | Privacy policy for the Pinterest app. States exactly what the app does: OAuth only, boards/pins read/write for the owner's own account, no passwords/cookies/scraping, no data sale. Contact leowelton771@gmail.com. Company name "The Home Organizer" appears in the page; when published on GitHub Pages its URL will be `https://<github-user>.github.io/thehomeorganizerdaily/privacy.html` — same host as the site, company name in the path, different URL from the site. |
| `pinterest_api.py` | Python integration (stdlib + `requests` only for the S3 video upload). OAuth URL / token exchange / refresh, `--list-boards`, image pins (`image_base64` or `image_url`), video pins (`/v5/media` register → S3 upload → poll → pin with `video_id` + mandatory cover), `--dry-run`, `--publish --day N`. Validates every pin: title ≤100, description ≤800, https link, `tag=aurokids-20`, Associates disclosure present. |
| `pins.csv` | The 14 viral pins, keyword-rewritten titles/descriptions (5 Nov 2026), with Day 1/2/3 drip columns. Board_ID blank until `--list-boards`. Video `Cover_URL` blank until stills are hosted (see test plan). |
| `test-pin-plan.md` | Drip plan (Day 1: 5, Day 2: 5, Day 3: 4), verification steps, Trial sandbox test. |
| `.env.example` | Credential template. Copy to `.env`, never commit it, never share it. |
| `requirements.txt` | `requests` only. |

## Step 1 — Publish the free site (Nova, needs a GitHub decision from Leo)

GitHub Pages is free for public repos. The site must live in a repo named `thehomeorganizerdaily` so the URLs are:
- Site: `https://<github-user>.github.io/thehomeorganizerdaily/`
- Privacy: `https://<github-user>.github.io/thehomeorganizerdaily/privacy.html`

**Leo's decision needed (one-time, his account):** whose GitHub account hosts the repo — his, or a new one created for The Home Organizer. Nova cannot create a GitHub account for him. Once he says which account, Nova prepares the repo files (these two HTML files, plus `media/` stills/covers if image_url is used) and he (or Nova, if he grants repo access) publishes them via GitHub Pages (Settings → Pages → Deploy from branch). Cost: $0.

## Step 2 — Create the Pinterest app (Leo, in his own browser)

1. Go to https://developers.pinterest.com and sign in with the Pinterest business account (The Home Organizer, leowelton771@gmail.com).
2. Create an app. Fill in:
   - Company website: the GitHub Pages site URL from Step 1.
   - Privacy policy URL: the `privacy.html` URL from Step 1.
   - Redirect URI: must match `PINTEREST_REDIRECT_URI` in `.env` (use a simple one, e.g. `https://<github-user>.github.io/thehomeorganizerdaily/` — Pinterest accepts it as the redirect target; the code is copied from the URL bar, never pasted to anyone).
   - Scopes: `boards:read, boards:write, pins:read, pins:write`.
3. The app starts on **Trial access**. Trial approval is typically 1–3 business days.
4. Copy the App ID and App Secret into `.env` (Leo only — never send them in chat).

## Step 3 — Trial sandbox test (Nova + Leo's one-time OAuth)

1. `python3 pinterest_api.py --dry-run --csv pins.csv` — validates all 14 rows, calls nothing.
2. Leo opens the URL from `python3 pinterest_api.py --auth-url` in his own browser, authorizes on Pinterest's screen, and gives Nova the `code` from the redirect URL (a one-time code, given by Leo himself — never a password).
3. Nova runs `--exchange-code CODE`, saves the tokens in `.env`, runs `--list-boards` and records the real board ID for "DIY Home Organization Ideas".
4. Publish **one** sandbox image pin only, on Trial. Trial pins are visible only to the creator — that is expected.
5. Record the demo video for Standard: OAuth authorize screen → token exchange → board list → sandbox pin created → pin visible to the creator. The video must show a live integration, not wireframes.

## Step 4 — Apply for Standard access (Leo submits, Pinterest reviews)

Submit the Standard upgrade in the developer dashboard with the demo video, the site URL and the privacy URL. **No published review timeline** — Pinterest reviews in batches. Do not promise a date. Common denial reasons to avoid: privacy policy inaccessible/inaccurate, vague app description, demo not showing OAuth, non-OAuth auth, wireframes instead of a live integration. If denied, fix the named reason and resubmit.

## Step 5 — Publish the 14 pins (Nova, after Standard is granted)

1. Fill `Board_ID` in `pins.csv` from `--list-boards`. Fill video `Cover_URL`s from the GitHub Pages-hosted stills.
2. Convert `.webp` statics to `.jpg` if using `image_base64` (Pinterest base64 accepts jpeg/png only), or use `image_url` with the GitHub Pages-hosted files.
3. Run one day at a time (see `test-pin-plan.md`):
   - `python3 pinterest_api.py --publish --csv pins.csv --board-id <ID> --day 1`
   - Day 2, then Day 3. Never a 13+ burst.
4. Verify every pin's Visit link (exact ASIN + `tag=aurokids-20`), record pin IDs, then per-pin analytics after 48–72h (saves first, clicks second).

## What still needs Leo (one-time only — no daily work)

1. GitHub account decision for the free site (Step 1).
2. Create the Pinterest app in his own browser (Step 2).
3. One-time OAuth authorize + hand Nova the one-time code (Step 3).
4. Submit the Standard upgrade (Step 4).

After that, Nova uploads, verifies and reports daily via the API. No browser bot wall, no paid service, $0/month.

## What NOT to do

- No VPN/proxy/mirror, no repeated Muse-browser Pinterest retries, no password/code in chat (the OAuth code is the one exception, given by Leo himself after he authorizes), no handing the Pinterest password to any tool.
- Do not publish the 14 pins on Trial (sandbox only). Do not guess a Board_ID. Do not invent media/cover URLs.
- Do not promise 20 pins/day free on day one — the API itself is unlimited once Standard is granted, but the honest drip is 3–5/day, matching the viral-research pace.

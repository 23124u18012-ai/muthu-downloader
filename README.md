# MUTHU Downloader — Render Web Service

A Flask web service that fetches and streams **direct media-file URLs** to the user's browser.

## Scope and limitations
- Supports direct media files with extensions such as MP4, WebM, MP3, M4A, AAC, OGG, WAV and FLAC.
- Does not extract media from YouTube watch pages or other webpage URLs.
- Does not bypass DRM, login walls, paywalls, anti-bot protections, or source-site restrictions.
- MP3 means a direct audio file; this project does not transcode video to MP3.
- The service rejects private/reserved IP destinations and limits downloads to 500 MB by default.
- The browser receives the file through the Flask service. Large files consume Render bandwidth and can be constrained by free-tier limits.
- Only download content you own or are authorized to download.

## Files
- `app.py` — Flask backend and direct media streaming
- `templates/index.html` — responsive MUTHU interface
- `requirements.txt` — Python dependencies
- `Procfile` — Render start command

## Deploy to Render
1. Extract this ZIP.
2. Create a GitHub repository named `muthu-downloader`.
3. Upload all project files and folders, preserving `templates/index.html`.
4. On Render, choose **New + → Web Service**.
5. Connect the GitHub repository.
6. Configure:
   - Runtime: Python 3
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
   - Instance: Free (if available for your account)
7. Deploy and open the generated `onrender.com` URL.
8. Test `/health`; it should return `{"status":"ok","app":"MUTHU Downloader"}`.

## Optional environment variable
`MAX_DOWNLOAD_MB` defaults to `500`. You can lower it, for example to `100`, in Render → Environment.

## Local test
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Then open `http://127.0.0.1:10000`.

## Operational note
This is a minimal personal-use starter. Before exposing it publicly, add authentication, per-IP rate limiting, abuse monitoring, and stronger outbound network controls. Free hosting is not guaranteed to handle large concurrent downloads.

import ipaddress
import os
import re
import socket
from urllib.parse import urlparse, unquote

import requests
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024  # URL form only

MAX_DOWNLOAD_BYTES = int(os.environ.get("MAX_DOWNLOAD_MB", "500")) * 1024 * 1024
CONNECT_TIMEOUT = 12
READ_TIMEOUT = 45
MAX_REDIRECTS = 4

ALLOWED_EXTENSIONS = {
    ".mp4", ".m4v", ".mov", ".webm", ".mkv",
    ".mp3", ".m4a", ".aac", ".ogg", ".wav", ".flac"
}
ALLOWED_CONTENT_PREFIXES = ("video/", "audio/")
GENERIC_TYPES = ("application/octet-stream", "binary/octet-stream")


def validate_public_http_url(url):
    """Reject non-HTTP URLs and hosts resolving to private/reserved IP ranges."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("Only valid HTTP or HTTPS direct media URLs are supported.")
        if parsed.username or parsed.password:
            raise ValueError("URLs containing embedded credentials are not supported.")
        host = parsed.hostname.rstrip(".")
        if host.lower() in ("localhost",) or host.lower().endswith(".localhost"):
            raise ValueError("Local network URLs are not allowed.")

        # Resolve all addresses and reject the host if any address is not globally routable.
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror:
            raise ValueError("The URL host could not be resolved.")
        if not infos:
            raise ValueError("The URL host could not be resolved.")
        for info in infos:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
            if not ip.is_global:
                raise ValueError("Private, local, or reserved network addresses are not allowed.")
        return parsed
    except (ValueError, TypeError) as exc:
        raise ValueError(str(exc))


def safe_filename(url, content_type):
    parsed = urlparse(url)
    name = unquote(parsed.path.rsplit("/", 1)[-1]) or "download"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120].strip("._")
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        guessed = {
            "video/mp4": ".mp4", "video/webm": ".webm",
            "audio/mpeg": ".mp3", "audio/mp4": ".m4a",
            "audio/aac": ".aac", "audio/ogg": ".ogg",
            "audio/wav": ".wav", "audio/flac": ".flac"
        }.get(content_type.lower(), "")
        name = (os.path.splitext(name)[0] or "media") + guessed
    return name or "media-download"


def get_upstream(url):
    """Fetch a URL while validating each redirect target."""
    current = url
    session = requests.Session()
    session.trust_env = False
    for _ in range(MAX_REDIRECTS + 1):
        validate_public_http_url(current)
        response = session.get(
            current, stream=True, allow_redirects=False,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            headers={"User-Agent": "MUTHU-Downloader/1.0"}
        )
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("The media server returned an invalid redirect.")
            from urllib.parse import urljoin
            current = urljoin(current, location)
            continue
        return response, current
    raise ValueError("Too many redirects from the media host.")


@app.get("/")
def home():
    return render_template("index.html")


@app.post("/download")
def download():
    data = request.get_json(silent=True) or request.form
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify(error="Paste a direct media-file URL first."), 400

    upstream = None
    try:
        validate_public_http_url(url)
        upstream, final_url = get_upstream(url)
        if upstream.status_code < 200 or upstream.status_code >= 300:
            upstream.close()
            return jsonify(error=f"Source server returned HTTP {upstream.status_code}."), 502

        content_type = upstream.headers.get("Content-Type", "application/octet-stream").split(";")[0].strip().lower()
        path_ext = os.path.splitext(urlparse(final_url).path)[1].lower()
        if not (content_type.startswith(ALLOWED_CONTENT_PREFIXES) or content_type in GENERIC_TYPES or path_ext in ALLOWED_EXTENSIONS):
            upstream.close()
            return jsonify(error="The URL does not appear to point to a supported audio or video file."), 415

        length = upstream.headers.get("Content-Length")
        if length:
            try:
                if int(length) > MAX_DOWNLOAD_BYTES:
                    upstream.close()
                    return jsonify(error=f"File exceeds the {MAX_DOWNLOAD_BYTES // (1024*1024)} MB limit."), 413
            except ValueError:
                pass

        filename = safe_filename(final_url, content_type)

        def generate():
            sent = 0
            try:
                for chunk in upstream.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    sent += len(chunk)
                    if sent > MAX_DOWNLOAD_BYTES:
                        # Stop the transfer if the source did not provide a usable Content-Length.
                        break
                    yield chunk
            finally:
                upstream.close()

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        }
        if length and length.isdigit() and int(length) <= MAX_DOWNLOAD_BYTES:
            headers["Content-Length"] = length
        return Response(stream_with_context(generate()), content_type=content_type, headers=headers)

    except requests.exceptions.Timeout:
        if upstream:
            upstream.close()
        return jsonify(error="The source server took too long to respond."), 504
    except requests.RequestException:
        if upstream:
            upstream.close()
        return jsonify(error="Could not fetch this media link. The source may block server-side access."), 502
    except ValueError as exc:
        if upstream:
            upstream.close()
        return jsonify(error=str(exc)), 400
    except Exception:
        if upstream:
            upstream.close()
        app.logger.exception("Unexpected download error")
        return jsonify(error="Unexpected server error. Check the Render logs."), 500


@app.get("/health")
def health():
    return jsonify(status="ok", app="MUTHU Downloader")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))

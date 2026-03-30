"""Cloud Function: download PDF from Drive, optimize, upload back using caller's token."""

import json
import os

import functions_framework
import google.auth
import google.oauth2.credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from pdfsimpler import optimize


def _get_drive_service(token=None):
    if token:
        creds = google.oauth2.credentials.Credentials(token)
    else:
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/drive"]
        )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _cleanup(*paths):
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass


@functions_framework.http
def handle_request(request):
    # Auth check
    expected = os.environ.get("AUTH_TOKEN", "")
    if not expected or request.headers.get("X-Auth-Token") != expected:
        return ("Unauthorized", 401)

    data = request.get_json(silent=True)
    if not data or "file_id" not in data or "file_name" not in data:
        return ('{"error": "file_id and file_name required"}', 400)

    file_id = data["file_id"]
    file_name = data["file_name"]
    folder_id = data["folder_id"]
    upload_token = data.get("upload_token")

    input_path = "/tmp/input.pdf"
    output_path = "/tmp/output.pdf"
    _cleanup(input_path, output_path)

    # Download using service account (read-only access to shared folder)
    dl_service = _get_drive_service()
    request_dl = dl_service.files().get_media(fileId=file_id)
    with open(input_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request_dl)
        done = False
        while not done:
            _, done = downloader.next_chunk()

    in_size = os.path.getsize(input_path)

    # Optimize
    optimize(input_path, output_path, precision=2)

    out_size = os.path.getsize(output_path)

    # Upload using caller's OAuth token (full Drive access)
    stem = file_name.rsplit(".pdf", 1)[0]
    out_name = f"{stem}_optimized.pdf"
    ul_service = _get_drive_service(token=upload_token)
    media = MediaFileUpload(output_path, mimetype="application/pdf")
    ul_service.files().create(
        body={"name": out_name, "parents": [folder_id]},
        media_body=media,
        fields="id",
    ).execute()

    _cleanup(input_path, output_path)

    ratio = in_size / out_size if out_size else 0
    return json.dumps({
        "name": out_name,
        "in_size_mb": round(in_size / 1024 / 1024, 1),
        "out_size_mb": round(out_size / 1024 / 1024, 1),
        "ratio": round(ratio, 1),
    })

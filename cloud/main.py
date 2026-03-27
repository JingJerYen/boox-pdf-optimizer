"""Cloud Function entry point: download PDF from Drive, optimize, upload back."""

import json
import os
import tempfile

import functions_framework
import google.auth
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from pdfsimpler import optimize


def _get_drive_service():
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

    input_path = "/tmp/input.pdf"
    output_path = "/tmp/output.pdf"
    _cleanup(input_path, output_path)

    service = _get_drive_service()

    # Download from Drive
    request_dl = service.files().get_media(fileId=file_id)
    with open(input_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request_dl)
        done = False
        while not done:
            _, done = downloader.next_chunk()

    in_size = os.path.getsize(input_path)

    # Optimize
    optimize(input_path, output_path, precision=2)

    out_size = os.path.getsize(output_path)

    # Get parent folder
    file_meta = service.files().get(
        fileId=file_id, fields="parents"
    ).execute()
    parent_id = file_meta["parents"][0]

    # Upload optimized version
    stem = file_name.rsplit(".pdf", 1)[0]
    out_name = f"{stem}_optimized.pdf"
    media = MediaFileUpload(output_path, mimetype="application/pdf")
    uploaded = service.files().create(
        body={"name": out_name, "parents": [parent_id]},
        media_body=media,
        fields="id",
    ).execute()

    _cleanup(input_path, output_path)

    ratio = in_size / out_size if out_size else 0
    return json.dumps({
        "name": out_name,
        "uploaded_id": uploaded["id"],
        "in_size_mb": round(in_size / 1024 / 1024, 1),
        "out_size_mb": round(out_size / 1024 / 1024, 1),
        "ratio": round(ratio, 1),
    })

"""
TechSerenia UpTime - Backup Client Helper
Place this file in your project and call upload_backup() from cron, Celery, or a management command.
Requires: requests (pip install requests)
"""

import os
import requests
from pathlib import Path


def upload_backup(
    file_path,
    api_key=None,
    base_url=None,
    website_id=None,
    notes=None,
    source="flask-client",
    timeout=120,
):
    """
    Upload a file to TechSerenia UpTime backup storage.

    Args:
        file_path: Path to the file to upload (str or Path)
        api_key: Your TSUT API key (or set TSUT_API_KEY env var)
        base_url: TSUT base URL without trailing slash (or set TSUT_BASE_URL)
        website_id: Optional website id to associate the backup with
        notes: Optional short description
        source: Label for the upload source
        timeout: Request timeout in seconds

    Returns:
        dict with success payload or raises requests.HTTPError / ValueError
    """
    api_key = api_key or os.environ.get("TSUT_API_KEY")
    base_url = (base_url or os.environ.get("TSUT_BASE_URL") or "").rstrip("/")
    if not api_key:
        raise ValueError("API key required (argument or TSUT_API_KEY env)")
    if not base_url:
        raise ValueError("Base URL required (argument or TSUT_BASE_URL env)")

    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    url = f"{base_url}/api/v1/backup"
    headers = {"X-API-Key": api_key}
    data = {"source": source}
    if website_id is not None:
        data["website_id"] = str(website_id)
    if notes:
        data["notes"] = notes

    with open(path, "rb") as f:
        files = {"file": (path.name, f)}
        resp = requests.post(url, headers=headers, data=data, files=files, timeout=timeout)

    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python tsut_backup.py <file_path> [notes]")
        sys.exit(1)
    result = upload_backup(
        sys.argv[1],
        notes=sys.argv[2] if len(sys.argv) > 2 else "CLI upload",
    )
    print("Uploaded:", result)

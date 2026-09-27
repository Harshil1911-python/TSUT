# TechSerenia UpTime (TSUT)

Full-stack website uptime monitoring and data backup platform built with Python Flask, HTML, CSS, and SQLite (or MySQL).

## Features

- User registration, login, and profile management
- Add websites with custom ping intervals (1–60 minutes)
- Background scheduled HTTP checks with response time, status code, and error recording
- Dashboard, per-site detail, analytics, and filterable history
- Export history to CSV and Excel
- API-key authenticated backup upload (multipart or raw body)
- Downloadable Python Flask helper and HTML upload client for loose integration
- Light and dark mode (fixed white + light blue palette, no gradients, no emojis)
- Terms and Conditions page, sitemap.xml, robots.txt

## Requirements

- Python 3.10+
- Packages in `requirements.txt`
- Optional: MySQL if you set `DATABASE_URL` (default is SQLite)

## Quick Start

1. Install dependencies:

```bash
cd TechSerenia-UpTime
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Optional `.env`:

```
SECRET_KEY=change-me-to-a-long-random-string
# DATABASE_URL=mysql+pymysql://user:pass@host:3306/techserenia_uptime?charset=utf8mb4
```

3. Run:

```bash
python app.py
```

Open http://127.0.0.1:5000 — tables are created automatically.

## Production (Render / Gunicorn)

Recommended start command (single worker is best with the built-in scheduler + SQLite):

```bash
gunicorn -w 1 -b 0.0.0.0:$PORT app:app
```

Set `SECRET_KEY` (required). Leave `DATABASE_URL` unset to use SQLite.

Tables are created automatically on first start.

## Backup Client

1. Sign in and open **Backup Client**.
2. Copy your API key.
3. Download `tsut_backup.py` or `upload.html`.
4. Call the helper from your project, or POST to `/api/v1/backup` with header `X-API-Key`.

## Project Layout

```
TechSerenia-UpTime/
  app.py
  config.py
  models.py
  requirements.txt
  sitemap.xml
  robots.txt
  static/
  templates/
  backup_client/
  backups/          (created at runtime)
  tsut.db           (SQLite, created at runtime)
```

## License

Use and modify as needed for your TechSerenia deployment.

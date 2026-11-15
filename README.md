# SOLA PORTAL

SOLA services hub built with Flask.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Deployment

Render build command: `pip install -r requirements.txt`
Render start command: `gunicorn app:app`

Set `SECRET_KEY` to a secure random value, and `DATABASE_URL` to a persistent PostgreSQL database before using accounts or announcements in production.

## Design

The portal is separate from SOLA CHAT and SOLA TALK. Portal administrator credentials do not grant administrator access to the other services.

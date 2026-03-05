# StudyHub

StudyHub is a Django application for creating and joining study sessions.

## Features

- Create virtual or in-person study sessions
- Join/leave sessions with capacity limits
- Waitlist support for full sessions
- Session chat/messages
- Subject tagging and feed filters
- Attendance tracking for session owners/leaders
- REST API endpoints for sessions and tags

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

## Useful Commands

```bash
python manage.py createsuperuser
python manage.py create_sample_data
python manage.py check
python manage.py test
```

## Project Structure

- `core/` - main app (models, views, forms, templates, API)
- `studyhub/` - Django project settings and URL config
- `templates/registration/` - auth templates
- `static/` - static assets

## Deployment

- `Procfile` and `start.sh` are included for deployment workflows.

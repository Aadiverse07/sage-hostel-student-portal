# SAGE Hostel Student Portal

A Flask-based hostel management portal demonstrating student authentication, dashboard, attendance, fee status, room booking, payment submission/verification, profile management, notices, and receipts.

## Tech stack
- Python / Flask
- SQLite
- HTML, CSS, JavaScript
- Jinja templates
- Gunicorn

## Local run
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5000`.

### Demo student
Email: `demo.student@example.com`
Password: `Demo@12345`

Admin credentials are supplied through environment variables. Never publish real credentials.

## Deploy on Render
1. Push this project to a GitHub repository.
2. Create a **Web Service** on Render and connect the repository.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Add `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and `ADMIN_SESSION_KEY` as environment variables.
6. Deploy and open the generated URL.

### SQLite note
SQLite is fine for a portfolio/demo deployment. Hosting platforms with ephemeral storage can lose database changes on rebuild/restart. For a production hostel system, use PostgreSQL or another managed database.

## Security
- Do not commit `.env`, real credentials, private QR/payment details, or real student records.
- Change all default environment values before deployment.
- The original admin verification text file is intentionally excluded from this public-ready package.

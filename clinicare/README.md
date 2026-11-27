# CliniCare – clinic management web app (Flask + Supabase + Vercel)

Roles: Administrateur, Réceptionniste, Médecin, Pharmacien, Patient.
Covers F1–F12 of the spec: login, patient sign-up, staff/specialty/tariff admin, patient registry with
duplicate detection, appointment booking with free slots only, e-mail confirmation (optional SMTP),
doctor agenda + consultation + prescriptions, invoicing + partial/full payments, patient portal, reports,
an access log for every patient-file view, and a pharmacy module (medicine stock, dispensing from
prescriptions after consultation, pharmacy invoices and payments, done by the Pharmacien role).

## Run locally (SQLite, no setup)
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # leave DATABASE_URL empty for SQLite
flask --app run seed                                   # roles, specialties, tariffs, demo staff
flask --app run run --debug                            # http://127.0.0.1:5000
```
Windows/PowerShell: use `.venv\Scripts\Activate.ps1`, and run the commands from inside the folder that contains `requirements.txt`.
If `psycopg2-binary` fails to install, upgrade pip first (`python -m pip install -U pip`); it is only needed for Supabase, not for local SQLite.

Demo accounts (password `Clinic@2026`): admin@clinicare.bi, accueil@clinicare.bi, pharma@clinicare.bi (pharmacist), alain@clinicare.bi (doctor).
Change or delete them before going live: `flask --app run create-admin you@mail.com StrongPassword`.

## Deploy: Supabase + Vercel
1. Supabase: create a project, click **Connect** (top of the dashboard), choose **Transaction pooler**, copy the string
   (host `...pooler.supabase.com`, port 6543) and put your database password in it. URL-encode special characters
   in the password (`@` becomes `%40`). The string must start with `postgresql://`.
2. Push this folder to GitHub (the `.env` file is git-ignored) and import the repo in Vercel.
   The entry point is `index.py` (exposes `app`); static files are in `public/static`.
3. Vercel > Settings > Environment Variables: `SECRET_KEY` (long random string), `DATABASE_URL`, optionally the
   `CLINIC_*` and `MAIL_*` variables. Deploy.
4. Tables and roles are created on the first request. From your machine, create the first admin and load the
   specialties, tariffs and medicines against the same database:
   `set DATABASE_URL=postgresql://...` (PowerShell: `$env:DATABASE_URL="postgresql://..."`), then
   `flask --app run create-admin you@mail.com StrongPassword` and `flask --app run seed`.

Vercel's filesystem is read-only/ephemeral, so production must use Supabase Postgres (SQLite is for local only).

## Public site
`/` is a public landing page that pushes visitors to book an appointment (CTA goes through sign-up, then straight to the booking page).
The app itself lives at `/tableau-de-bord`. Clinic name, phone, e-mail, address and hours come from `app/config.py`
(or the env vars `CLINIC_NAME`, `CLINIC_CITY`, `CLINIC_PHONE`, `CLINIC_EMAIL`, `CLINIC_ADDRESS`, `CLINIC_HOURS`).
Photos are in `public/static/img/`.

## Structure
```
index.py            Vercel entry point
app/__init__.py     app factory, filters, error pages
app/models.py       12 spec tables + access_logs (partial unique index: one active appointment per doctor/slot)
app/auth.py         login/logout/register, lockout after 5 failures (15 min), safe redirects
app/patients.py rdv.py consultations.py billing.py admin.py   blueprints (controllers)
app/utils.py        RBAC decorator, slot generation, e-mail, access log
app/templates/      Jinja views   public/static/      CSS and images   (style.css = app design system) (teal, Inter, 8 px grid)
```
Security: bcrypt hashes, role checks on every route, CSRF tokens on every POST, SQLAlchemy parameterised
queries, Jinja auto-escaping, HttpOnly + Secure + SameSite cookies, 30 min inactivity timeout.
Agenda hours (08:00–17:00, lunch 12–14, Sundays closed, 30 min slots) live in `app/config.py`.

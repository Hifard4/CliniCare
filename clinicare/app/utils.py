import smtplib
from datetime import datetime, timedelta, time
from email.message import EmailMessage
from functools import wraps
from flask import abort, current_app
from flask_login import current_user, login_required
from .extensions import db
from .models import AccessLog, RendezVous, Patient


def roles_required(*roles):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapper(*a, **kw):
            if current_user.role_name not in roles:
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco


def log_access(patient, action="Consultation du dossier"):
    db.session.add(AccessLog(user_id=current_user.id, patient_id=patient.id, action=action))
    db.session.commit()


def can_view_patient(patient):
    r = current_user.role_name
    if r in ("Administrateur", "Réceptionniste"):
        return True
    if r == "Patient":
        return patient.user_id == current_user.id
    if r == "Médecin" and current_user.medecin:
        return db.session.query(RendezVous.id).filter_by(
            patient_id=patient.id, medecin_id=current_user.medecin.id).first() is not None
    return False


def new_numero_dossier():
    prefix = f"P{datetime.now().year}-"
    last = (Patient.query.filter(Patient.numero_dossier.like(prefix + "%"))
            .order_by(Patient.numero_dossier.desc()).first())
    n = int(last.numero_dossier.split("-")[1]) + 1 if last else 1
    return f"{prefix}{n:05d}"


def free_slots(medecin_id, day, exclude_rdv_id=None):
    c = current_app.config
    step = timedelta(minutes=c["SLOT_MINUTES"])
    cur = datetime.combine(day, time(c["DAY_START"]))
    end = datetime.combine(day, time(c["DAY_END"]))
    if day.weekday() == 6:
        return []
    q = RendezVous.query.filter(
        RendezVous.medecin_id == medecin_id, RendezVous.statut != "Annulé",
        RendezVous.date_heure >= datetime.combine(day, time(0)),
        RendezVous.date_heure < datetime.combine(day, time(0)) + timedelta(days=1))
    if exclude_rdv_id:
        q = q.filter(RendezVous.id != exclude_rdv_id)
    taken = {r.date_heure for r in q}
    out, now = [], datetime.now()
    while cur < end:
        in_lunch = c["LUNCH"][0] <= cur.hour < c["LUNCH"][1]
        if not in_lunch and cur > now and cur not in taken:
            out.append(cur)
        cur += step
    return out


def send_confirmation(rdv, kind="confirmé"):
    """F7 : e-mail de confirmation (SMTP si configuré, sinon journal)."""
    cfg = current_app.config
    user = rdv.patient.user
    if not (cfg["MAIL_SERVER"] and user):
        current_app.logger.info("Confirmation RDV #%s (%s): pas d'e-mail envoyé", rdv.id, kind)
        return False
    msg = EmailMessage()
    msg["Subject"] = f"CliniCare – rendez-vous {kind}"
    msg["From"], msg["To"] = cfg["MAIL_FROM"], user.email
    msg.set_content(
        f"Bonjour {rdv.patient.prenom},\n\nVotre rendez-vous avec Dr {rdv.medecin.user.nom} "
        f"({rdv.medecin.specialite.libelle}) est {kind} pour le "
        f"{rdv.date_heure:%d/%m/%Y à %H:%M}.\n\nCliniCare")
    try:
        with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=8) as s:
            s.starttls()
            if cfg["MAIL_USERNAME"]:
                s.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            s.send_message(msg)
        return True
    except Exception as e:
        current_app.logger.warning("Échec e-mail: %s", e)
        return False


def parse_date(s, default=None):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default

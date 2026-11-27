from datetime import datetime, date, time, timedelta
from flask import Blueprint, render_template
from flask_login import login_required, current_user
from sqlalchemy import func
from .extensions import db
from .models import RendezVous, Patient, Facture, Paiement, Consultation, VentePharmacie, PaiementPharmacie, Medicament

bp = Blueprint("main", __name__)


def _day_range(d=None):
    d = d or date.today()
    s = datetime.combine(d, time(0))
    return s, s + timedelta(days=1)


@bp.route("/tableau-de-bord")
@login_required
def dashboard():
    role = current_user.role_name
    s, e = _day_range()
    ctx = {}
    if role in ("Administrateur", "Réceptionniste"):
        today = (RendezVous.query.filter(RendezVous.date_heure >= s, RendezVous.date_heure < e,
                                         RendezVous.statut != "Annulé").order_by(RendezVous.date_heure).all())
        month_start = datetime.combine(date.today().replace(day=1), time(0))
        revenus = db.session.query(func.coalesce(func.sum(Paiement.montant), 0)).filter(
            Paiement.date_paiement >= month_start).scalar()
        ctx = dict(today=today, n_patients=Patient.query.count(), revenus=revenus,
                   a_facturer=Consultation.query.outerjoin(Facture).filter(Facture.id.is_(None)).count())
    elif role == "Médecin":
        med = current_user.medecin
        today = (RendezVous.query.filter(RendezVous.medecin_id == med.id, RendezVous.date_heure >= s,
                                         RendezVous.date_heure < e, RendezVous.statut != "Annulé")
                 .order_by(RendezVous.date_heure).all()) if med else []
        ctx = dict(today=today)
    elif role == "Pharmacien":
        month_start = datetime.combine(date.today().replace(day=1), time(0))
        ctx = dict(
            a_delivrer=Consultation.query.filter(Consultation.prescriptions.any())
            .outerjoin(VentePharmacie).filter(VentePharmacie.id.is_(None)).count(),
            stock_bas=Medicament.query.filter(Medicament.stock <= Medicament.seuil).count(),
            revenus=db.session.query(func.coalesce(func.sum(PaiementPharmacie.montant), 0)).filter(
                PaiementPharmacie.date_paiement >= month_start).scalar(),
            impayees=VentePharmacie.query.filter(VentePharmacie.statut != "Payée").count())
    else:
        p = current_user.patient
        upcoming = (RendezVous.query.filter(RendezVous.patient_id == p.id, RendezVous.statut == "Planifié",
                                            RendezVous.date_heure >= datetime.now())
                    .order_by(RendezVous.date_heure).limit(5).all()) if p else []
        ctx = dict(upcoming=upcoming, patient=p)
    return render_template("dashboard.html", **ctx)

from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from .extensions import db
from .models import RendezVous, Medecin, Specialite, Patient
from .utils import free_slots, parse_date, send_confirmation

bp = Blueprint("rdv", __name__, url_prefix="/rendez-vous")


def _can_manage(r):
    role = current_user.role_name
    if role in ("Administrateur", "Réceptionniste"):
        return True
    if role == "Patient":
        return current_user.patient and r.patient_id == current_user.patient.id
    return False


@bp.route("/")
@login_required
def liste():
    role = current_user.role_name
    if role not in ("Administrateur", "Réceptionniste", "Médecin", "Patient"):
        abort(403)
    q = RendezVous.query
    if role == "Patient":
        q = q.filter_by(patient_id=current_user.patient.id)
    elif role == "Médecin":
        q = q.filter_by(medecin_id=current_user.medecin.id)
    d = parse_date(request.args.get("date"))
    if d:
        from datetime import time, timedelta
        s = datetime.combine(d, time(0))
        q = q.filter(RendezVous.date_heure >= s, RendezVous.date_heure < s + timedelta(days=1))
    rdvs = q.order_by(RendezVous.date_heure.desc()).limit(200).all()
    return render_template("rdv/liste.html", rdvs=rdvs, d=d, can_manage=_can_manage)


@bp.route("/nouveau", methods=["GET", "POST"])
@login_required
def nouveau():
    role = current_user.role_name
    if role not in ("Administrateur", "Réceptionniste", "Patient"):
        abort(403)
    args = request.values
    spec_id = args.get("specialite_id", type=int)
    med_id = args.get("medecin_id", type=int)
    day = parse_date(args.get("date"))
    patient = current_user.patient if role == "Patient" else (
        db.session.get(Patient, args.get("patient_id", type=int)) if args.get("patient_id") else None)

    specialites = Specialite.query.order_by(Specialite.libelle).all()
    medecins = Medecin.query.filter_by(specialite_id=spec_id).all() if spec_id else []
    if day and day < date.today():
        flash("Choisissez une date à venir.", "error")
        day = None
    slots = free_slots(med_id, day) if (med_id and day) else []

    if request.method == "POST" and request.form.get("action") == "reserver":
        creneau = request.form.get("creneau")
        try:
            dh = datetime.strptime(creneau, "%Y-%m-%dT%H:%M")
        except (TypeError, ValueError):
            dh = None
        if not patient:
            flash("Sélectionnez un patient.", "error")
        elif not dh or dh not in slots:
            flash("Ce créneau n'est plus disponible. Choisissez-en un autre.", "error")
        else:
            r = RendezVous(patient_id=patient.id, medecin_id=med_id, date_heure=dh,
                           motif=request.form.get("motif", "").strip()[:200] or None)
            db.session.add(r)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("Ce créneau vient d'être pris. Choisissez-en un autre.", "error")
                return redirect(url_for("rdv.nouveau", specialite_id=spec_id, medecin_id=med_id,
                                        date=day, patient_id=patient.id))
            sent = send_confirmation(r)
            flash("Rendez-vous planifié" + (" ; confirmation envoyée par e-mail." if sent else "."), "success")
            return redirect(url_for("rdv.liste"))
    return render_template("rdv/nouveau.html", specialites=specialites, medecins=medecins, slots=slots,
                           spec_id=spec_id, med_id=med_id, day=day, patient=patient, role=role)


@bp.route("/<int:rid>/modifier", methods=["GET", "POST"])
@login_required
def modifier(rid):
    r = db.get_or_404(RendezVous, rid)
    if not _can_manage(r):
        abort(403)
    if r.statut != "Planifié":
        flash("Seul un rendez-vous planifié peut être modifié.", "error")
        return redirect(url_for("rdv.liste"))
    day = parse_date(request.values.get("date"), r.date_heure.date())
    slots = [] if day < date.today() else free_slots(r.medecin_id, day, exclude_rdv_id=r.id)
    if request.method == "POST" and request.form.get("action") == "reserver":
        try:
            dh = datetime.strptime(request.form.get("creneau", ""), "%Y-%m-%dT%H:%M")
        except ValueError:
            dh = None
        if dh and dh in slots:
            r.date_heure = dh
            r.motif = request.form.get("motif", "").strip()[:200] or r.motif
            try:
                db.session.commit()
                send_confirmation(r, "modifié")
                flash("Rendez-vous modifié.", "success")
                return redirect(url_for("rdv.liste"))
            except IntegrityError:
                db.session.rollback()
        flash("Ce créneau n'est plus disponible.", "error")
    return render_template("rdv/modifier.html", r=r, day=day, slots=slots)


@bp.route("/<int:rid>/annuler", methods=["POST"])
@login_required
def annuler(rid):
    r = db.get_or_404(RendezVous, rid)
    if not _can_manage(r):
        abort(403)
    if r.statut == "Planifié":
        r.statut = "Annulé"
        db.session.commit()
        send_confirmation(r, "annulé")
        flash("Rendez-vous annulé.", "success")
    return redirect(url_for("rdv.liste"))

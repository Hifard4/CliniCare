from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user, login_required
from sqlalchemy import or_
from .extensions import db
from .models import Patient, RendezVous
from .utils import roles_required, log_access, can_view_patient, new_numero_dossier, parse_date

bp = Blueprint("patients", __name__, url_prefix="/patients")


@bp.route("/")
@roles_required("Administrateur", "Réceptionniste")
def liste():
    q = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    query = Patient.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Patient.nom.ilike(like), Patient.prenom.ilike(like),
                                 Patient.telephone.ilike(like), Patient.numero_dossier.ilike(like)))
    pag = query.order_by(Patient.nom, Patient.prenom).paginate(page=page, per_page=15, error_out=False)
    return render_template("patients/liste.html", pag=pag, q=q)


@bp.route("/nouveau", methods=["GET", "POST"])
@roles_required("Réceptionniste", "Administrateur")
def nouveau():
    f = request.form
    if request.method == "POST":
        nom, prenom = f.get("nom", "").strip(), f.get("prenom", "").strip()
        tel, dn, sexe = f.get("telephone", "").strip(), parse_date(f.get("date_naissance")), f.get("sexe")
        if not (nom and prenom and tel and dn and sexe in ("M", "F")):
            flash("Nom, prénom, date de naissance, sexe et téléphone sont obligatoires.", "error")
        elif sum(c.isdigit() for c in tel) < 8:
            flash("Numéro de téléphone invalide (8 chiffres minimum).", "error")
        else:
            dup = Patient.query.filter(Patient.nom.ilike(nom), Patient.prenom.ilike(prenom),
                                       Patient.date_naissance == dn, Patient.telephone == tel).first()
            if dup:
                flash(f"Doublon : ce patient existe déjà (dossier {dup.numero_dossier}).", "error")
                return redirect(url_for("patients.fiche", pid=dup.id))
            p = Patient(numero_dossier=new_numero_dossier(), nom=nom, prenom=prenom, date_naissance=dn,
                        sexe=sexe, telephone=tel, adresse=f.get("adresse", "").strip() or None)
            db.session.add(p)
            db.session.commit()
            flash(f"Dossier {p.numero_dossier} créé pour {p.nom_complet}.", "success")
            return redirect(url_for("patients.fiche", pid=p.id))
    return render_template("patients/nouveau.html", f=f)


@bp.route("/<int:pid>")
@login_required
def fiche(pid):
    p = db.get_or_404(Patient, pid)
    if not can_view_patient(p):
        abort(403)
    log_access(p)
    rdvs = RendezVous.query.filter_by(patient_id=p.id).order_by(RendezVous.date_heure.desc()).all()
    return render_template("patients/fiche.html", p=p, rdvs=rdvs)

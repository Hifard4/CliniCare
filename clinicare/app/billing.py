from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user, login_required
from .extensions import db
from .models import Consultation, Facture, LigneFacture, Acte, Paiement
from .utils import roles_required, log_access

bp = Blueprint("billing", __name__)
MODES = ("Espèces", "Mobile money", "Carte", "Virement")


@bp.route("/facturation")
@roles_required("Réceptionniste", "Administrateur")
def liste():
    a_facturer = (Consultation.query.outerjoin(Facture).filter(Facture.id.is_(None))
                  .order_by(Consultation.date_creation.desc()).all())
    factures = Facture.query.order_by(Facture.date_emission.desc()).limit(100).all()
    return render_template("billing/liste.html", a_facturer=a_facturer, factures=factures)


@bp.route("/facturation/nouvelle/<int:cid>", methods=["GET", "POST"])
@roles_required("Réceptionniste", "Administrateur")
def nouvelle(cid):
    c = db.get_or_404(Consultation, cid)
    if c.facture:
        return redirect(url_for("billing.voir", fid=c.facture.id))
    actes = Acte.query.order_by(Acte.libelle).all()
    if request.method == "POST":
        lignes = []
        for a in actes:
            try:
                q = int(request.form.get(f"qte_{a.id}", "0") or 0)
            except ValueError:
                q = 0
            if q > 0:
                lignes.append(LigneFacture(acte_id=a.id, quantite=q, prix_unitaire=a.prix))
        if not lignes:
            flash("Sélectionnez au moins un acte.", "error")
        else:
            f = Facture(consultation_id=c.id, lignes=lignes)
            f.recalculer()
            db.session.add(f)
            db.session.commit()
            flash("Facture générée.", "success")
            return redirect(url_for("billing.voir", fid=f.id))
    return render_template("billing/nouvelle.html", c=c, actes=actes)


@bp.route("/facture/<int:fid>", methods=["GET", "POST"])
@login_required
def voir(fid):
    f = db.get_or_404(Facture, fid)
    patient = f.consultation.rendez_vous.patient
    role = current_user.role_name
    if role == "Patient":
        if patient.user_id != current_user.id:
            abort(403)
    elif role not in ("Réceptionniste", "Administrateur"):
        abort(403)
    if request.method == "POST":
        if role == "Patient":
            abort(403)
        try:
            m = Decimal(request.form.get("montant", "0").replace(" ", ""))
        except InvalidOperation:
            m = Decimal(0)
        mode = request.form.get("mode")
        if m <= 0 or mode not in MODES:
            flash("Montant et mode de paiement valides requis.", "error")
        elif m > f.solde:
            flash(f"Le montant dépasse le solde restant ({int(f.solde)} FBu).", "error")
        else:
            f.paiements.append(Paiement(montant=m, mode=mode))
            db.session.flush()
            f.recalculer()
            db.session.commit()
            flash("Paiement enregistré." + (" Facture soldée." if f.statut == "Payée" else ""), "success")
        return redirect(url_for("billing.voir", fid=f.id))
    return render_template("billing/voir.html", f=f, patient=patient, modes=MODES)


@bp.route("/mes-factures")
@roles_required("Patient")
def mes_factures():
    p = current_user.patient
    from .models import RendezVous
    factures = (Facture.query.join(Consultation).join(RendezVous)
                .filter(RendezVous.patient_id == p.id).order_by(Facture.date_emission.desc()).all())
    from .models import VentePharmacie
    ventes = (VentePharmacie.query.join(Consultation).join(RendezVous)
              .filter(RendezVous.patient_id == p.id).order_by(VentePharmacie.date.desc()).all())
    return render_template("billing/mes_factures.html", factures=factures, ventes=ventes)

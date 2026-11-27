from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user, login_required
from .extensions import db
from .models import Medicament, VentePharmacie, LigneVente, PaiementPharmacie, Consultation
from .utils import roles_required, log_access
from .billing import MODES

bp = Blueprint("pharmacie", __name__, url_prefix="/pharmacie")


def _a_delivrer():
    return (Consultation.query.filter(Consultation.prescriptions.any())
            .outerjoin(VentePharmacie).filter(VentePharmacie.id.is_(None))
            .order_by(Consultation.date_creation.desc()))


@bp.route("/")
@roles_required("Pharmacien", "Administrateur")
def index():
    ventes = VentePharmacie.query.order_by(VentePharmacie.date.desc()).limit(50).all()
    bas = Medicament.query.filter(Medicament.stock <= Medicament.seuil).order_by(Medicament.stock).all()
    return render_template("pharmacie/index.html", ordonnances=_a_delivrer().all(), ventes=ventes, bas=bas)


@bp.route("/stock", methods=["GET", "POST"])
@roles_required("Pharmacien", "Administrateur")
def stock():
    if request.method == "POST":
        f = request.form
        try:
            if f.get("kind") == "nouveau":
                nom = f.get("nom", "").strip()
                prix, qte, seuil = int(f.get("prix", "")), int(f.get("stock", "0") or 0), int(f.get("seuil", "10") or 10)
                if not nom or prix < 0 or qte < 0 or seuil < 0:
                    raise ValueError
                if Medicament.query.filter(db.func.lower(Medicament.nom) == nom.lower()).first():
                    flash("Ce médicament existe déjà.", "error")
                else:
                    db.session.add(Medicament(nom=nom, forme=f.get("forme", "").strip() or None, prix=prix, stock=qte, seuil=seuil))
                    db.session.commit()
                    flash("Médicament ajouté au stock.", "success")
            elif f.get("kind") == "maj":
                m = db.get_or_404(Medicament, f.get("id", type=int))
                prix, ajout, seuil = int(f.get("prix", "")), int(f.get("ajout", "0") or 0), int(f.get("seuil", "")) 
                if prix < 0 or seuil < 0 or m.stock + ajout < 0:
                    raise ValueError
                m.prix, m.seuil, m.stock = prix, seuil, m.stock + ajout
                db.session.commit()
                flash(f"{m.nom} mis à jour.", "success")
        except ValueError:
            db.session.rollback()
            flash("Valeurs invalides : nombres entiers positifs requis (l'ajustement ne peut pas rendre le stock négatif).", "error")
        return redirect(url_for("pharmacie.stock"))
    return render_template("pharmacie/stock.html", meds=Medicament.query.order_by(Medicament.nom).all())


@bp.route("/delivrer/<int:cid>", methods=["GET", "POST"])
@roles_required("Pharmacien")
def delivrer(cid):
    c = db.get_or_404(Consultation, cid)
    if not c.prescriptions:
        flash("Cette consultation n'a pas d'ordonnance.", "error")
        return redirect(url_for("pharmacie.index"))
    if c.vente_pharmacie:
        flash("Les médicaments de cette ordonnance ont déjà été délivrés.", "error")
        return redirect(url_for("pharmacie.vente", vid=c.vente_pharmacie.id))
    patient = c.rendez_vous.patient
    log_access(patient, "Délivrance de médicaments")
    meds = Medicament.query.order_by(Medicament.nom).all()

    def suggestion(presc):  # médicament du stock dont le nom ressemble à la prescription
        mot = presc.medicament.strip().lower().split(" ")[0]
        return next((m.id for m in meds if mot and mot in m.nom.lower()), None)

    if request.method == "POST":
        lignes, erreurs = [], []
        for pr in c.prescriptions:
            mid = request.form.get(f"med_{pr.id}", type=int)
            if not mid:
                continue
            m = db.session.get(Medicament, mid)
            try:
                q = int(request.form.get(f"qte_{pr.id}", "0") or 0)
            except ValueError:
                q = 0
            if not m or q <= 0:
                erreurs.append(f"Quantité invalide pour « {pr.medicament} ».")
            else:
                lignes.append((pr, m, q))
        if not lignes and not erreurs:
            erreurs.append("Sélectionnez au moins un médicament à délivrer.")
        if erreurs:
            for e in erreurs:
                flash(e, "error")
        else:
            vente = VentePharmacie(consultation_id=c.id, pharmacien_id=current_user.id)
            db.session.add(vente)
            ok = True
            for pr, m, q in lignes:
                # décrément atomique : échoue si le stock est insuffisant
                n = Medicament.query.filter(Medicament.id == m.id, Medicament.stock >= q).update(
                    {Medicament.stock: Medicament.stock - q}, synchronize_session=False)
                if not n:
                    flash(f"Stock insuffisant pour {m.nom} (disponible : {db.session.get(Medicament, m.id).stock}).", "error")
                    ok = False
                    break
                vente.lignes.append(LigneVente(medicament_id=m.id, prescription_id=pr.id, quantite=q, prix_unitaire=m.prix))
            if ok:
                vente.recalculer()
                db.session.commit()
                flash("Médicaments délivrés et facture créée.", "success")
                return redirect(url_for("pharmacie.vente", vid=vente.id))
            db.session.rollback()
    posted = request.method == "POST"
    sel = {pr.id: (request.form.get(f"med_{pr.id}", type=int) if posted else suggestion(pr)) for pr in c.prescriptions}
    qte = {pr.id: (request.form.get(f"qte_{pr.id}", "1") if posted else "1") for pr in c.prescriptions}
    return render_template("pharmacie/delivrer.html", c=c, patient=patient, meds=meds, sel=sel, qte=qte)


@bp.route("/vente/<int:vid>", methods=["GET", "POST"])
@login_required
def vente(vid):
    v = db.get_or_404(VentePharmacie, vid)
    role = current_user.role_name
    if role == "Patient":
        if v.patient.user_id != current_user.id:
            abort(403)
    elif role not in ("Pharmacien", "Administrateur"):
        abort(403)
    if request.method == "POST":
        if role != "Pharmacien":
            abort(403)
        try:
            m = Decimal(request.form.get("montant", "0").replace(" ", ""))
        except InvalidOperation:
            m = Decimal(0)
        mode = request.form.get("mode")
        if m <= 0 or mode not in MODES:
            flash("Montant et mode de paiement valides requis.", "error")
        elif m > v.solde:
            flash(f"Le montant dépasse le solde restant ({int(v.solde)} FBu).", "error")
        else:
            v.paiements.append(PaiementPharmacie(montant=m, mode=mode))
            db.session.flush()
            v.recalculer()
            db.session.commit()
            flash("Paiement enregistré." + (" Facture soldée." if v.statut == "Payée" else ""), "success")
        return redirect(url_for("pharmacie.vente", vid=v.id))
    return render_template("pharmacie/vente.html", v=v, modes=MODES)

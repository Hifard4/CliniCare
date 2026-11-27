from datetime import datetime, date, time, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy import func
from .extensions import db, bcrypt
from .models import User, Role, Medecin, Specialite, Acte, Consultation, RendezVous, Paiement, PaiementPharmacie, AccessLog, ROLES
from .utils import roles_required, parse_date

bp = Blueprint("admin", __name__, url_prefix="/admin")
STAFF_ROLES = ("Administrateur", "Réceptionniste", "Médecin", "Pharmacien")


@bp.route("/utilisateurs")
@roles_required("Administrateur")
def utilisateurs():
    users = User.query.order_by(User.nom).all()
    return render_template("admin/utilisateurs.html", users=users)


@bp.route("/utilisateurs/nouveau", methods=["GET", "POST"])
@roles_required("Administrateur")
def utilisateur_nouveau():
    specs = Specialite.query.order_by(Specialite.libelle).all()
    f = request.form
    if request.method == "POST":
        nom, email, pwd, role = f.get("nom", "").strip(), f.get("email", "").strip().lower(), f.get("password", ""), f.get("role")
        if not (nom and "@" in email and role in STAFF_ROLES):
            flash("Nom, e-mail valide et rôle sont obligatoires.", "error")
        elif len(pwd) < 8:
            flash("Mot de passe : 8 caractères minimum.", "error")
        elif User.query.filter_by(email=email).first():
            flash("Cette adresse e-mail est déjà utilisée.", "error")
        elif role == "Médecin" and not f.get("specialite_id"):
            flash("Choisissez une spécialité pour le médecin.", "error")
        else:
            u = User(nom=nom, email=email, role_id=Role.query.filter_by(libelle=role).one().id,
                     mot_de_passe_hash=bcrypt.generate_password_hash(pwd).decode())
            db.session.add(u)
            db.session.flush()
            if role == "Médecin":
                db.session.add(Medecin(user_id=u.id, specialite_id=int(f["specialite_id"]),
                                       numero_ordre=f.get("numero_ordre", "").strip() or None))
            db.session.commit()
            flash("Compte créé.", "success")
            return redirect(url_for("admin.utilisateurs"))
    return render_template("admin/utilisateur_form.html", specs=specs, roles=STAFF_ROLES, f=f, u=None)


@bp.route("/utilisateurs/<int:uid>", methods=["GET", "POST"])
@roles_required("Administrateur")
def utilisateur_modifier(uid):
    u = db.get_or_404(User, uid)
    specs = Specialite.query.order_by(Specialite.libelle).all()
    if request.method == "POST":
        f = request.form
        u.nom = f.get("nom", u.nom).strip() or u.nom
        if u.role_name != "Patient" and f.get("role") in STAFF_ROLES and u.id != current_user.id:
            u.role_id = Role.query.filter_by(libelle=f["role"]).one().id
        if f.get("password"):
            if len(f["password"]) < 8:
                flash("Mot de passe : 8 caractères minimum.", "error")
                return redirect(url_for("admin.utilisateur_modifier", uid=u.id))
            u.mot_de_passe_hash = bcrypt.generate_password_hash(f["password"]).decode()
        if u.role_name == "Médecin":
            if not u.medecin and f.get("specialite_id"):
                db.session.add(Medecin(user_id=u.id, specialite_id=int(f["specialite_id"])))
            elif u.medecin:
                if f.get("specialite_id"):
                    u.medecin.specialite_id = int(f["specialite_id"])
                u.medecin.numero_ordre = f.get("numero_ordre", "").strip() or None
        db.session.commit()
        flash("Compte mis à jour.", "success")
        return redirect(url_for("admin.utilisateurs"))
    return render_template("admin/utilisateur_form.html", specs=specs, roles=STAFF_ROLES, f={}, u=u)


@bp.route("/utilisateurs/<int:uid>/basculer", methods=["POST"])
@roles_required("Administrateur")
def utilisateur_basculer(uid):
    u = db.get_or_404(User, uid)
    if u.id == current_user.id:
        flash("Vous ne pouvez pas désactiver votre propre compte.", "error")
    else:
        u.actif = not u.actif
        db.session.commit()
        flash("Compte " + ("activé." if u.actif else "désactivé."), "success")
    return redirect(url_for("admin.utilisateurs"))


@bp.route("/referentiels", methods=["GET", "POST"])
@roles_required("Administrateur")
def referentiels():
    if request.method == "POST":
        kind = request.form.get("kind")
        if kind == "specialite":
            lib = request.form.get("libelle", "").strip()
            if lib and not Specialite.query.filter(func.lower(Specialite.libelle) == lib.lower()).first():
                db.session.add(Specialite(libelle=lib))
                db.session.commit()
                flash("Spécialité ajoutée.", "success")
            else:
                flash("Libellé vide ou déjà existant.", "error")
        elif kind == "acte":
            lib = request.form.get("libelle", "").strip()
            try:
                prix = int(request.form.get("prix", ""))
            except ValueError:
                prix = -1
            if lib and prix >= 0:
                db.session.add(Acte(libelle=lib, prix=prix))
                db.session.commit()
                flash("Acte ajouté.", "success")
            else:
                flash("Libellé et prix (entier ≥ 0) requis.", "error")
        elif kind == "acte_prix":
            a = db.session.get(Acte, request.form.get("id", type=int))
            try:
                prix = int(request.form.get("prix", ""))
            except ValueError:
                prix = -1
            if a and prix >= 0:
                a.prix = prix
                db.session.commit()
                flash("Tarif mis à jour (les factures existantes ne changent pas).", "success")
        return redirect(url_for("admin.referentiels"))
    return render_template("admin/referentiels.html", specs=Specialite.query.order_by(Specialite.libelle).all(),
                           actes=Acte.query.order_by(Acte.libelle).all())


@bp.route("/rapports")
@roles_required("Administrateur")
def rapports():
    today = date.today()
    d1 = parse_date(request.args.get("du"), today.replace(day=1))
    d2 = parse_date(request.args.get("au"), today)
    s, e = datetime.combine(d1, time(0)), datetime.combine(d2, time(0)) + timedelta(days=1)
    par_medecin = (db.session.query(User.nom, Specialite.libelle, func.count(Consultation.id))
                   .select_from(Consultation).join(RendezVous).join(Medecin, RendezVous.medecin_id == Medecin.id)
                   .join(User, Medecin.user_id == User.id).join(Specialite, Medecin.specialite_id == Specialite.id)
                   .filter(Consultation.date_creation >= s, Consultation.date_creation < e)
                   .group_by(User.nom, Specialite.libelle).order_by(func.count(Consultation.id).desc()).all())
    paiements = Paiement.query.filter(Paiement.date_paiement >= s, Paiement.date_paiement < e).all()
    par_jour = {}
    for p in paiements:
        k = p.date_paiement.date().isoformat()
        par_jour[k] = par_jour.get(k, 0) + int(p.montant)
    jours = sorted(par_jour)
    pharma_total = int(db.session.query(func.coalesce(func.sum(PaiementPharmacie.montant), 0)).filter(
        PaiementPharmacie.date_paiement >= s, PaiementPharmacie.date_paiement < e).scalar())
    return render_template("admin/rapports.html", d1=d1, d2=d2, par_medecin=par_medecin, pharma_total=pharma_total,
                           jours=jours, montants=[par_jour[j] for j in jours], total=sum(par_jour.values()))


@bp.route("/journal")
@roles_required("Administrateur")
def journal():
    logs = AccessLog.query.order_by(AccessLog.date.desc()).limit(200).all()
    return render_template("admin/journal.html", logs=logs)

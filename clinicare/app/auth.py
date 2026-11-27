from datetime import datetime, timedelta
from urllib.parse import urlparse
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, current_user, login_required
from .extensions import db, bcrypt
from .models import User, Role, Patient
from .utils import new_numero_dossier, parse_date

bp = Blueprint("auth", __name__)
MAX_ATTEMPTS, LOCK_MIN = 5, 15


def _safe_next(target):
    if not target:
        return None
    u = urlparse(target)
    return target if not u.netloc and not u.scheme and target.startswith("/") else None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pwd = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.locked_until and user.locked_until > datetime.now():
            flash("Compte verrouillé temporairement après trop d'échecs. Réessayez dans quelques minutes.", "error")
        elif user and user.actif and bcrypt.check_password_hash(user.mot_de_passe_hash, pwd):
            user.failed_attempts, user.locked_until = 0, None
            db.session.commit()
            session.permanent = True
            login_user(user)
            return redirect(_safe_next(request.args.get("next")) or url_for("main.dashboard"))
        else:
            if user:
                user.failed_attempts += 1
                if user.failed_attempts >= MAX_ATTEMPTS:
                    user.locked_until = datetime.now() + timedelta(minutes=LOCK_MIN)
                    user.failed_attempts = 0
                db.session.commit()
            flash("E-mail ou mot de passe incorrect, ou compte désactivé.", "error")
    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Vous êtes déconnecté.", "success")
    return redirect(url_for("public.home"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    f = request.form
    if request.method == "POST":
        nom, prenom = f.get("nom", "").strip(), f.get("prenom", "").strip()
        email, pwd = f.get("email", "").strip().lower(), f.get("password", "")
        dn, sexe, tel = parse_date(f.get("date_naissance")), f.get("sexe"), f.get("telephone", "").strip()
        errors = []
        if not (nom and prenom and tel and dn and sexe in ("M", "F")):
            errors.append("Nom, prénom, date de naissance, sexe et téléphone sont obligatoires.")
        if "@" not in email:
            errors.append("Adresse e-mail invalide.")
        if len(pwd) < 8:
            errors.append("Le mot de passe doit contenir au moins 8 caractères.")
        if pwd != f.get("confirm", ""):
            errors.append("Les mots de passe ne correspondent pas.")
        if User.query.filter_by(email=email).first():
            errors.append("Cette adresse e-mail est déjà utilisée.")
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            role = Role.query.filter_by(libelle="Patient").one()
            u = User(nom=f"{prenom} {nom}", email=email, role_id=role.id,
                     mot_de_passe_hash=bcrypt.generate_password_hash(pwd).decode())
            db.session.add(u)
            db.session.flush()
            # Rattache un dossier créé à l'accueil s'il existe (même nom + naissance + tél.)
            p = Patient.query.filter_by(nom=nom, prenom=prenom, date_naissance=dn, telephone=tel, user_id=None).first()
            if p:
                p.user_id = u.id
            else:
                db.session.add(Patient(user_id=u.id, numero_dossier=new_numero_dossier(), nom=nom,
                                       prenom=prenom, date_naissance=dn, sexe=sexe, telephone=tel))
            db.session.commit()
            flash("Compte créé. Connectez-vous pour continuer.", "success")
            return redirect(url_for("auth.login", next=_safe_next(request.args.get("next"))))
    return render_template("auth/register.html", f=f)

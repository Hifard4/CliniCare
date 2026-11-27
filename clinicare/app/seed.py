import click
from datetime import datetime, timedelta
from .extensions import db, bcrypt
from .models import User, Role, Specialite, Medecin, Acte, Medicament


def _user(nom, email, role, pwd="Clinic@2026"):
    u = User.query.filter_by(email=email).first()
    if not u:
        u = User(nom=nom, email=email, role_id=Role.query.filter_by(libelle=role).one().id,
                 mot_de_passe_hash=bcrypt.generate_password_hash(pwd).decode())
        db.session.add(u)
        db.session.flush()
    return u


def seed_data():
    for lib in ("Médecine générale", "Pédiatrie", "Gynécologie", "Cardiologie"):
        if not Specialite.query.filter_by(libelle=lib).first():
            db.session.add(Specialite(libelle=lib))
    for lib, prix in (("Consultation générale", 15000), ("Consultation spécialisée", 25000),
                      ("Test rapide paludisme", 5000), ("Analyse de sang", 12000), ("Injection", 3000)):
        if not Acte.query.filter_by(libelle=lib).first():
            db.session.add(Acte(libelle=lib, prix=prix))
    db.session.flush()
    _user("Administrateur CliniCare", "admin@clinicare.bi", "Administrateur")
    _user("Accueil", "accueil@clinicare.bi", "Réceptionniste")
    _user("Pharmacie", "pharma@clinicare.bi", "Pharmacien")
    for nom, forme, prix, stock in (("Paracétamol 500 mg", "Comprimé", 200, 500), ("Amoxicilline 500 mg", "Gélule", 500, 300),
                                    ("Artéméther-Luméfantrine", "Comprimé", 3500, 120), ("Ibuprofène 400 mg", "Comprimé", 300, 200),
                                    ("Sels de réhydratation (SRO)", "Sachet", 800, 80)):
        if not Medicament.query.filter_by(nom=nom).first():
            db.session.add(Medicament(nom=nom, forme=forme, prix=prix, stock=stock, seuil=20))
    for nom, email, spec, ordre in (("Nkurunziza Alain", "alain@clinicare.bi", "Médecine générale", "BI-001"),
                                    ("Niyonsaba Claire", "claire@clinicare.bi", "Pédiatrie", "BI-002")):
        u = _user(nom, email, "Médecin")
        if not u.medecin:
            db.session.add(Medecin(user_id=u.id, specialite_id=Specialite.query.filter_by(libelle=spec).one().id,
                                   numero_ordre=ordre))
    db.session.commit()


def register_cli(app):
    @app.cli.command("seed")
    def seed_cmd():
        """Crée rôles, spécialités, actes et comptes de démonstration."""
        seed_data()
        click.echo("OK. Comptes : admin@clinicare.bi / accueil@clinicare.bi / pharma@clinicare.bi / alain@clinicare.bi (mdp Clinic@2026)")

    @app.cli.command("create-admin")
    @click.argument("email")
    @click.argument("password")
    def create_admin(email, password):
        """Crée un administrateur : flask create-admin email motdepasse"""
        _user("Administrateur", email.lower(), "Administrateur", password)
        db.session.commit()
        click.echo("Administrateur créé.")

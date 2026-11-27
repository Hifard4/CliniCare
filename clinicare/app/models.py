from datetime import datetime, date
from flask_login import UserMixin
from sqlalchemy import CheckConstraint, Index, text
from .extensions import db

STATUTS_RDV = ("Planifié", "Terminé", "Annulé")
STATUTS_FACTURE = ("Impayée", "Partielle", "Payée")
ROLES = ("Administrateur", "Réceptionniste", "Médecin", "Pharmacien", "Patient")


class Role(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    libelle = db.Column(db.String(40), unique=True, nullable=False)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False)
    mot_de_passe_hash = db.Column(db.String(200), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    actif = db.Column(db.Boolean, default=True, nullable=False)
    failed_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime)
    role = db.relationship("Role")
    medecin = db.relationship("Medecin", back_populates="user", uselist=False)
    patient = db.relationship("Patient", back_populates="user", uselist=False)

    @property
    def role_name(self):
        return self.role.libelle

    @property
    def is_active(self):
        return self.actif


class Specialite(db.Model):
    __tablename__ = "specialites"
    id = db.Column(db.Integer, primary_key=True)
    libelle = db.Column(db.String(80), unique=True, nullable=False)


class Medecin(db.Model):
    __tablename__ = "medecins"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    specialite_id = db.Column(db.Integer, db.ForeignKey("specialites.id"), nullable=False)
    numero_ordre = db.Column(db.String(40))
    user = db.relationship("User", back_populates="medecin")
    specialite = db.relationship("Specialite")


class Patient(db.Model):
    __tablename__ = "patients"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    numero_dossier = db.Column(db.String(20), unique=True, nullable=False)
    nom = db.Column(db.String(80), nullable=False)
    prenom = db.Column(db.String(80), nullable=False)
    date_naissance = db.Column(db.Date, nullable=False)
    sexe = db.Column(db.String(1), nullable=False)
    telephone = db.Column(db.String(30), nullable=False)
    adresse = db.Column(db.String(200))
    user = db.relationship("User", back_populates="patient")
    __table_args__ = (CheckConstraint("sexe in ('M','F')", name="ck_patient_sexe"),)

    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom}"

    @property
    def age(self):
        t, d = date.today(), self.date_naissance
        return t.year - d.year - ((t.month, t.day) < (d.month, d.day))


class RendezVous(db.Model):
    __tablename__ = "rendez_vous"
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    medecin_id = db.Column(db.Integer, db.ForeignKey("medecins.id"), nullable=False)
    date_heure = db.Column(db.DateTime, nullable=False)
    motif = db.Column(db.String(200))
    statut = db.Column(db.String(20), default="Planifié", nullable=False)
    patient = db.relationship("Patient")
    medecin = db.relationship("Medecin")
    consultation = db.relationship("Consultation", back_populates="rendez_vous", uselist=False)
    __table_args__ = (
        # un seul RDV actif par médecin et par créneau (un RDV annulé libère le créneau)
        Index("uq_medecin_creneau", "medecin_id", "date_heure", unique=True,
              postgresql_where=text("statut <> 'Annulé'"), sqlite_where=text("statut <> 'Annulé'")),
        CheckConstraint("statut in ('Planifié','Terminé','Annulé')", name="ck_rdv_statut"),
    )


class Consultation(db.Model):
    __tablename__ = "consultations"
    id = db.Column(db.Integer, primary_key=True)
    rendez_vous_id = db.Column(db.Integer, db.ForeignKey("rendez_vous.id"), unique=True, nullable=False)
    diagnostic = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text)
    date_creation = db.Column(db.DateTime, default=datetime.now)
    rendez_vous = db.relationship("RendezVous", back_populates="consultation")
    prescriptions = db.relationship("Prescription", cascade="all, delete-orphan")
    facture = db.relationship("Facture", back_populates="consultation", uselist=False)
    vente_pharmacie = db.relationship("VentePharmacie", back_populates="consultation", uselist=False)


class Prescription(db.Model):
    __tablename__ = "prescriptions"
    id = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"), nullable=False)
    medicament = db.Column(db.String(120), nullable=False)
    posologie = db.Column(db.String(160), nullable=False)
    duree = db.Column(db.String(60), nullable=False)


class Acte(db.Model):
    __tablename__ = "actes"
    id = db.Column(db.Integer, primary_key=True)
    libelle = db.Column(db.String(120), nullable=False)
    prix = db.Column(db.Numeric(12, 0), nullable=False)


class Facture(db.Model):
    __tablename__ = "factures"
    id = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"), unique=True, nullable=False)
    date_emission = db.Column(db.DateTime, default=datetime.now)
    total = db.Column(db.Numeric(12, 0), default=0, nullable=False)
    statut = db.Column(db.String(20), default="Impayée", nullable=False)
    consultation = db.relationship("Consultation", back_populates="facture")
    lignes = db.relationship("LigneFacture", cascade="all, delete-orphan")
    paiements = db.relationship("Paiement", cascade="all, delete-orphan")
    __table_args__ = (CheckConstraint("statut in ('Impayée','Partielle','Payée')", name="ck_facture_statut"),)

    @property
    def paye(self):
        return sum((p.montant for p in self.paiements), 0)

    @property
    def solde(self):
        return self.total - self.paye

    def recalculer(self):
        self.total = sum(l.quantite * l.prix_unitaire for l in self.lignes)
        if self.total > 0 and self.solde <= 0:
            self.statut = "Payée"
        elif self.paye > 0:
            self.statut = "Partielle"
        else:
            self.statut = "Impayée"


class LigneFacture(db.Model):
    __tablename__ = "lignes_facture"
    id = db.Column(db.Integer, primary_key=True)
    facture_id = db.Column(db.Integer, db.ForeignKey("factures.id"), nullable=False)
    acte_id = db.Column(db.Integer, db.ForeignKey("actes.id"), nullable=False)
    quantite = db.Column(db.Integer, default=1, nullable=False)
    prix_unitaire = db.Column(db.Numeric(12, 0), nullable=False)
    acte = db.relationship("Acte")


class Paiement(db.Model):
    __tablename__ = "paiements"
    id = db.Column(db.Integer, primary_key=True)
    facture_id = db.Column(db.Integer, db.ForeignKey("factures.id"), nullable=False)
    montant = db.Column(db.Numeric(12, 0), nullable=False)
    mode = db.Column(db.String(30), nullable=False)
    date_paiement = db.Column(db.DateTime, default=datetime.now)


class AccessLog(db.Model):
    """Journal des consultations de dossiers (confidentialité)."""
    __tablename__ = "access_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    action = db.Column(db.String(40), nullable=False)
    date = db.Column(db.DateTime, default=datetime.now)
    user = db.relationship("User")
    patient = db.relationship("Patient")


class Medicament(db.Model):
    """Stock de la pharmacie."""
    __tablename__ = "medicaments"
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), unique=True, nullable=False)
    forme = db.Column(db.String(40))
    prix = db.Column(db.Numeric(12, 0), nullable=False)
    stock = db.Column(db.Integer, default=0, nullable=False)
    seuil = db.Column(db.Integer, default=10, nullable=False)
    __table_args__ = (CheckConstraint("stock >= 0", name="ck_medicament_stock"),)

    @property
    def stock_bas(self):
        return self.stock <= self.seuil


class VentePharmacie(db.Model):
    """Délivrance de médicaments après consultation + facture associée (1 par consultation)."""
    __tablename__ = "ventes_pharmacie"
    id = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"), unique=True, nullable=False)
    pharmacien_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    date = db.Column(db.DateTime, default=datetime.now)
    total = db.Column(db.Numeric(12, 0), default=0, nullable=False)
    statut = db.Column(db.String(20), default="Impayée", nullable=False)
    consultation = db.relationship("Consultation", back_populates="vente_pharmacie")
    pharmacien = db.relationship("User")
    lignes = db.relationship("LigneVente", cascade="all, delete-orphan")
    paiements = db.relationship("PaiementPharmacie", cascade="all, delete-orphan")
    __table_args__ = (CheckConstraint("statut in ('Impayée','Partielle','Payée')", name="ck_vente_statut"),)

    @property
    def patient(self):
        return self.consultation.rendez_vous.patient

    @property
    def paye(self):
        return sum((p.montant for p in self.paiements), 0)

    @property
    def solde(self):
        return self.total - self.paye

    def recalculer(self):
        self.total = sum(l.quantite * l.prix_unitaire for l in self.lignes)
        if self.total > 0 and self.solde <= 0:
            self.statut = "Payée"
        elif self.paye > 0:
            self.statut = "Partielle"
        else:
            self.statut = "Impayée"


class LigneVente(db.Model):
    __tablename__ = "lignes_vente"
    id = db.Column(db.Integer, primary_key=True)
    vente_id = db.Column(db.Integer, db.ForeignKey("ventes_pharmacie.id"), nullable=False)
    medicament_id = db.Column(db.Integer, db.ForeignKey("medicaments.id"), nullable=False)
    prescription_id = db.Column(db.Integer, db.ForeignKey("prescriptions.id"))
    quantite = db.Column(db.Integer, nullable=False)
    prix_unitaire = db.Column(db.Numeric(12, 0), nullable=False)
    medicament = db.relationship("Medicament")
    prescription = db.relationship("Prescription")


class PaiementPharmacie(db.Model):
    __tablename__ = "paiements_pharmacie"
    id = db.Column(db.Integer, primary_key=True)
    vente_id = db.Column(db.Integer, db.ForeignKey("ventes_pharmacie.id"), nullable=False)
    montant = db.Column(db.Numeric(12, 0), nullable=False)
    mode = db.Column(db.String(30), nullable=False)
    date_paiement = db.Column(db.DateTime, default=datetime.now)

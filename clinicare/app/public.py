from flask import Blueprint, render_template
from .models import Medecin, Specialite

bp = Blueprint("public", __name__)


@bp.route("/")
def home():
    medecins = (Medecin.query.join(Medecin.user).filter_by(actif=True)
                .order_by(Medecin.id).limit(8).all())
    specialites = Specialite.query.order_by(Specialite.libelle).all()
    return render_template("public/home.html", medecins=medecins, specialites=specialites)

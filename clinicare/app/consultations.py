from datetime import datetime, date, time, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user
from .extensions import db
from .models import RendezVous, Consultation, Prescription
from .utils import roles_required, log_access, parse_date

bp = Blueprint("consultations", __name__)


@bp.route("/agenda")
@roles_required("Médecin")
def agenda():
    d = parse_date(request.args.get("date"), date.today())
    s = datetime.combine(d, time(0))
    rdvs = (RendezVous.query.filter(RendezVous.medecin_id == current_user.medecin.id,
                                    RendezVous.date_heure >= s, RendezVous.date_heure < s + timedelta(days=1),
                                    RendezVous.statut != "Annulé").order_by(RendezVous.date_heure).all())
    return render_template("consultations/agenda.html", rdvs=rdvs, d=d,
                           prev=d - timedelta(days=1), nxt=d + timedelta(days=1))


@bp.route("/consultation/<int:rid>", methods=["GET", "POST"])
@roles_required("Médecin")
def saisir(rid):
    r = db.get_or_404(RendezVous, rid)
    if r.medecin_id != current_user.medecin.id:
        abort(403)
    log_access(r.patient, "Ouverture pour consultation")
    if r.statut == "Annulé":
        flash("Ce rendez-vous est annulé.", "error")
        return redirect(url_for("consultations.agenda"))
    if r.consultation:
        return render_template("consultations/voir.html", r=r, c=r.consultation)
    if request.method == "POST":
        diag = request.form.get("diagnostic", "").strip()
        if not diag:
            flash("Le diagnostic est obligatoire.", "error")
        else:
            c = Consultation(rendez_vous_id=r.id, diagnostic=diag, notes=request.form.get("notes", "").strip() or None)
            meds = request.form.getlist("medicament")
            pos = request.form.getlist("posologie")
            dur = request.form.getlist("duree")
            for m, p, d in zip(meds, pos, dur):
                if m.strip():
                    if not (p.strip() and d.strip()):
                        flash("Chaque prescription doit avoir une posologie et une durée.", "error")
                        return render_template("consultations/saisir.html", r=r, f=request.form)
                    c.prescriptions.append(Prescription(medicament=m.strip(), posologie=p.strip(), duree=d.strip()))
            r.statut = "Terminé"
            db.session.add(c)
            db.session.commit()
            flash("Consultation enregistrée ; rendez-vous terminé.", "success")
            return redirect(url_for("consultations.agenda"))
    return render_template("consultations/saisir.html", r=r, f=request.form)

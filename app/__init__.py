from datetime import datetime
from flask import Flask, render_template, flash, redirect, request, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from .config import Config
from .extensions import db, login_manager, csrf, bcrypt


def create_app(config=None):
    # Les fichiers statiques vivent dans public/ : Vercel les sert depuis son CDN, Flask en local.
    app = Flask(__name__, static_folder="../public/static", static_url_path="/static")
    app.config.from_object(Config)
    if config:
        app.config.update(config)

    # Diagnostic : indique la cible de connexion SANS le mot de passe (visible dans les Runtime Logs).
    try:
        from sqlalchemy.engine import make_url
        u = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
        app.logger.warning("DB target: driver=%s user=%s host=%s port=%s db=%s password_length=%s",
                           u.drivername, u.username, u.host, u.port, u.database, len(u.password or ""))
    except Exception as e:
        app.logger.warning("DB target illisible: %s", e)

    db.init_app(app)
    csrf.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Connectez-vous pour accéder à cette page."

    from .models import User, Role, ROLES

    @login_manager.user_loader
    def load_user(uid):
        return db.session.get(User, int(uid))

    from . import auth, main, patients, rdv, consultations, billing, admin, pharmacie, public
    for m in (auth, main, patients, rdv, consultations, billing, admin, pharmacie, public):
        app.register_blueprint(m.bp)

    app.jinja_env.globals["zip_"] = zip

    @app.template_filter("money")
    def money(v):
        return f"{int(v or 0):,}".replace(",", " ") + " FBu"

    @app.template_filter("dt")
    def dt(v, fmt="%d/%m/%Y %H:%M"):
        return v.strftime(fmt) if v else ""

    @app.after_request
    def secure_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        flash("Votre session a expiré ou la page était périmée. Reconnectez-vous ou rechargez la page, puis réessayez.", "error")
        if current_user.is_authenticated:
            return redirect(request.referrer or url_for("main.dashboard"))
        return redirect(url_for("auth.login"))

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403, msg="Vous n'avez pas accès à cette page."), 403

    @app.errorhandler(404)
    def notfound(e):
        return render_template("error.html", code=404, msg="Page introuvable."), 404

    def book_url(**kw):
        """Lien « Prendre rendez-vous » : direct si connecté, sinon via la création de compte."""
        target = url_for("rdv.nouveau", **kw)
        return target if current_user.is_authenticated else url_for("auth.register", next=target)

    @app.context_processor
    def inject():
        c = app.config
        return {"now": datetime.now(), "book_url": book_url,
                "clinic": {k[7:].lower(): c[k] for k in c if k.startswith("CLINIC_")}}

    with app.app_context():
        try:
            db.create_all()
            for r in ROLES:
                if not Role.query.filter_by(libelle=r).first():
                    db.session.add(Role(libelle=r))
            db.session.commit()
        except Exception as e:  # base injoignable: l'app démarre quand même
            db.session.rollback()
            app.logger.error("Initialisation de la base impossible: %s", e)

    from .seed import register_cli
    register_cli(app)
    return app

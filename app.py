"""
app.py — Zagadat Capital Fund Management System
================================================
Application factory. Extensions live in extensions.py to avoid
circular imports:
  extensions.py → models.py → routes/*.py → app.py
"""

from flask import Flask
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import os


def create_app():
    app = Flask(__name__)

    # ── CONFIG ────────────────────────────────────────────────────────────
    app.config['SECRET_KEY'] = os.environ.get(
        'SECRET_KEY', 'zagadat-capital-secret-2026-xk9'
    )

    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///zagadat.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    app.config['UPLOAD_FOLDER'] = os.path.join(
        os.path.dirname(__file__), 'uploads'
    )
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    for sub in ('signatures', 'documents', 'photos'):
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], sub), exist_ok=True)

    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get(
        'MAIL_DEFAULT_SENDER', 'noreply@zagadatcapital.com'
    )

    # ── EXTENSIONS ────────────────────────────────────────────────────────
    from extensions import db, login_manager, bcrypt, mail

    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    mail.init_app(app)
    CORS(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = ''

    # ── BLUEPRINTS ────────────────────────────────────────────────────────
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.user import user_bp
    from routes.api import api_bp
    from routes.reports import reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(user_bp, url_prefix='/portal')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(reports_bp, url_prefix='/reports')

    # ── DB + SEED + SCHEDULER ─────────────────────────────────────────────
    with app.app_context():
        db.create_all()

        from utils.seed import seed_defaults
        seed_defaults()

        from utils.stock_sync import sync_gse_prices

        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            sync_gse_prices,
            'interval',
            minutes=5,
            id='gse_sync',
            replace_existing=True
        )

        if not scheduler.running:
            scheduler.start()
            sync_gse_prices()  # run immediately on startup

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
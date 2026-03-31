"""
extensions.py
=============
Flask extension instances are defined here — NOT in app.py — so that
models.py can import them without triggering a circular import.

Import order:
  extensions.py  ← models.py  ← routes/*.py  ← app.py
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_mail import Mail

db            = SQLAlchemy()
login_manager = LoginManager()
bcrypt        = Bcrypt()
mail          = Mail()

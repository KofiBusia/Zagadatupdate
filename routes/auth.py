from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from models import AdminUser, ClientUser, ClientAccount, db
from utils.notifications import audit
from datetime import datetime
import os, uuid

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def index():
    return redirect(url_for('auth.login'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_type = request.form.get('login_type', 'client')

        if login_type == 'admin':
            staff_id = request.form.get('staff_id', '').strip()
            password = request.form.get('password', '')
            user = AdminUser.query.filter_by(staff_id=staff_id).first()
            if user and user.check_password(password) and user.is_active:
                user.last_login = datetime.utcnow()
                db.session.commit()
                login_user(user, remember=True)
                session['user_type'] = 'admin'
                session['user_role'] = user.role
                audit('LOGIN', target=f'admin:{staff_id}')
                return redirect(url_for('admin.dashboard'))
            flash('Invalid staff ID or password.', 'error')

        else:
            account_number = request.form.get('account_number', '').strip().upper()
            phone = request.form.get('phone', '').strip()
            user = ClientUser.query.filter_by(account_number=account_number, phone=phone).first()
            if user and user.is_active:
                acc = ClientAccount.query.filter_by(account_number=account_number).first()
                if acc and acc.status == 'APPROVED':
                    user.last_login = datetime.utcnow()
                    db.session.commit()
                    login_user(user, remember=True)
                    session['user_type'] = 'client'
                    audit('LOGIN', target=f'client:{account_number}', actor=user)
                    return redirect(url_for('user.dashboard'))
                elif acc and acc.status == 'PENDING':
                    flash('Your account is pending approval. You will be notified once approved.', 'error')
                elif acc and acc.status == 'SUSPENDED':
                    flash('Your account has been suspended. Please contact your relationship manager.', 'error')
                else:
                    flash('Account not found or not approved.', 'error')
            else:
                flash('Invalid account number or phone number.', 'error')

    return render_template('login.html')

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """Public self-service account registration"""
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone     = request.form.get('phone', '').strip()
        email     = request.form.get('email', '').strip()
        password  = request.form.get('password', '')
        confirm   = request.form.get('confirm_password', '')
        acc_type  = request.form.get('account_type', 'Individual')

        if not full_name or not phone or not password:
            flash('Name, phone and password are required.', 'error')
            return render_template('signup.html')

        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('signup.html')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('signup.html')

        if ClientUser.query.filter_by(phone=phone).first():
            flash('An account with this phone number already exists.', 'error')
            return render_template('signup.html')

        # Generate account number
        last   = ClientAccount.query.order_by(ClientAccount.id.desc()).first()
        acc_no = f'ZC-{(last.id+1 if last else 1):05d}'

        acc = ClientAccount(
            account_number=acc_no,
            full_name=full_name,
            phone=phone,
            email=email,
            account_type=acc_type,
            status='PENDING',
            online_signup=True,
            base_currency='GHS',
            created_by=0,
        )
        db.session.add(acc)
        db.session.flush()

        cu = ClientUser(account_number=acc_no, phone=phone, signup_name=full_name)
        cu.set_password(password)
        db.session.add(cu)
        db.session.commit()

        flash(f'Registration successful! Your account number is {acc_no}. '
              f'Please complete your profile by logging in once approved.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('signup.html')

@auth_bp.route('/logout')
@login_required
def logout():
    try:
        audit('LOGOUT')
    except Exception:
        pass
    logout_user()
    session.clear()
    return redirect(url_for('auth.login'))

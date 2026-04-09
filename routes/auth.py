from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from models import AdminUser, ClientUser, ClientAccount, db
from utils.notifications import audit, email_login_alert
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
                    # Send real-time login security alert email
                    try:
                        ip  = request.remote_addr
                        ua  = request.user_agent.string[:120] if request.user_agent else None
                        email_login_alert(acc, ip_address=ip, user_agent=ua)
                    except Exception:
                        pass
                    # Security reminder flash — shown once per login
                    flash(
                        f'Welcome back. You are signed in as '
                        f'<strong>{acc.full_name}</strong> '
                        f'({account_number}). '
                        f'Keep your account number strictly confidential — '
                        f'never share it with any third party.',
                        'login_security'
                    )
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
    """
    Public self-service account registration.

    Flow for Individual / Individual ITF / Joint / Pension / Provident:
      Step 1 — Enter Ghana Card number (GHA-000000000-0)
               System calls NIA API to pre-populate:
               Surname, First Names, Nationality, Sex, Date of Birth
               Height is entered manually (not returned by NIA API)
      Step 2 — Complete remaining KYC fields + set password

    Corporate / Institutional accounts skip Ghana Card step.
    """
    from datetime import datetime as _dt

    if request.method == 'POST':
        acc_type  = request.form.get('account_type', 'Individual')
        phone     = request.form.get('phone', '').strip()
        email     = request.form.get('email', '').strip()
        password  = request.form.get('password', '')
        confirm   = request.form.get('confirm_password', '')
        rm_id_raw = request.form.get('relationship_manager_id', '').strip()
        rm_id     = int(rm_id_raw) if rm_id_raw.isdigit() else None

        # ── Identity fields (optional at signup — collected during KYC) ──
        ghana_card       = request.form.get('ghana_card_number', '').strip().upper()
        is_ghanaian      = request.form.get('is_ghanaian', '1').strip() == '1'
        passport_num     = request.form.get('passport_number', '').strip().upper()
        passport_country = request.form.get('passport_country', '').strip()
        nationality      = request.form.get('nationality', '').strip()
        gender           = request.form.get('gender', '').strip()
        dob_str          = request.form.get('date_of_birth', '').strip()
        height           = request.form.get('height', '').strip()

        # Build full_name — support both single-field and split-field forms
        surname     = request.form.get('surname', '').strip()
        first_names = request.form.get('first_names', '').strip()
        if surname or first_names:
            full_name = f"{surname} {first_names}".strip()
        else:
            full_name = request.form.get('full_name', '').strip()

        # Basic validation
        if not full_name or not phone or not password:
            flash('Please complete all required fields (name, phone, password).', 'error')
            return render_template('signup.html')

        # Duplicate Ghana Card / Passport check (only if provided)
        if ghana_card and ClientAccount.query.filter_by(ghana_card_number=ghana_card).first():
            flash('A registration with this Ghana Card number already exists.', 'error')
            return render_template('signup.html')
        if passport_num and ClientAccount.query.filter_by(id_number=passport_num).first():
            flash('A registration with this passport number already exists.', 'error')
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

        # Parse date of birth
        dob = None
        if dob_str:
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
                try:
                    dob = _dt.strptime(dob_str, fmt).date()
                    break
                except ValueError:
                    pass

        # Generate account number
        last   = ClientAccount.query.order_by(ClientAccount.id.desc()).first()
        acc_no = f'ZC-{(last.id + 1 if last else 1):05d}'

        # Determine ID type from whatever was provided
        corporate_types = {'Corporate', 'Institutional'}
        if acc_type in corporate_types:
            id_type_val = None
            id_num_val  = None
        elif ghana_card:
            id_type_val = 'Ghana Card'
            id_num_val  = ghana_card
        elif passport_num:
            id_type_val = 'Passport' if not passport_country else f'Passport ({passport_country})'
            id_num_val  = passport_num
        else:
            id_type_val = None
            id_num_val  = None

        acc = ClientAccount(
            account_number   = acc_no,
            full_name        = full_name,
            phone            = phone,
            email            = email,
            account_type     = acc_type,
            status           = 'PENDING',
            online_signup    = True,
            base_currency    = 'GHS',
            created_by       = 0,
            # Identity fields
            ghana_card_number= ghana_card or None,
            is_ghanaian      = is_ghanaian,
            nationality          = nationality or (passport_country if not is_ghanaian else None) or None,
            gender               = gender or None,
            date_of_birth        = dob,
            height               = height or None,
            id_type              = id_type_val,
            id_number            = id_num_val,
            country_of_origin    = passport_country if not is_ghanaian else 'Ghana',
            relationship_manager_id = rm_id,
        )
        db.session.add(acc)
        db.session.flush()

        cu = ClientUser(account_number=acc_no, phone=phone, signup_name=full_name)
        cu.set_password(password)
        db.session.add(cu)
        db.session.commit()

        audit('SIGNUP', target=f'account:{acc_no}',
              detail=f'type={acc_type} ghanaian={is_ghanaian} id={ghana_card or passport_num or "N/A"}')

        flash(
            f'Registration successful! Your account number is <strong>{acc_no}</strong>. '
            f'Our team will review your application and notify you once approved.',
            'success'
        )
        return redirect(url_for('auth.login'))

    from models import AdminUser as _AU
    rm_list = _AU.query.filter_by(is_rm=True, is_active=True).order_by(_AU.full_name).all()
    return render_template('signup.html', rm_list=rm_list)

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

from flask import Blueprint, render_template, redirect, url_for, request, flash, session, current_app
from flask_login import login_required, current_user
from models import ClientAccount, Investment, Transaction, ClientRequest, db
from utils.notifications import audit
from datetime import datetime, date
import os, uuid

user_bp = Blueprint('user', __name__)

def client_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or session.get('user_type') != 'client':
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def get_account():
    return ClientAccount.query.filter_by(account_number=current_user.account_number).first()

@user_bp.route('/')
@client_required
def dashboard():
    acc = get_account()
    investments  = Investment.query.filter_by(account_number=acc.account_number, status='APPROVED').all()
    transactions = Transaction.query.filter_by(account_number=acc.account_number)\
                              .order_by(Transaction.txn_date.desc()).limit(20).all()
    requests = ClientRequest.query.filter_by(account_number=acc.account_number)\
                            .order_by(ClientRequest.created_at.desc()).limit(5).all()

    total_value     = sum(i.computed_mkt_value for i in investments)
    cash            = acc.cash_balance
    portfolio_value = total_value + cash

    by_class = {}
    for inv in investments:
        lbl = inv.asset_class.replace('_', ' ').title()
        by_class[lbl] = by_class.get(lbl, 0) + inv.computed_mkt_value

    return render_template('user/dashboard.html',
        acc=acc, investments=investments, transactions=transactions,
        requests=requests, total_value=total_value, cash=cash,
        portfolio_value=portfolio_value, by_class=by_class)

@user_bp.route('/profile', methods=['GET', 'POST'])
@client_required
def profile():
    acc = get_account()
    if request.method == 'POST':
        # Allow updating non-sensitive fields
        for field in ['email','phone2','address','city','postal_address','digital_address',
                      'spouse_name','spouse_phone','spouse_email',
                      'emergency_contact_name','emergency_contact_relation','emergency_contact_phone',
                      'bank_name','bank_branch','bank_account_name','bank_account_number',
                      'statement_mode','statement_frequency']:
            val = request.form.get(field)
            if val is not None:
                setattr(acc, field, val)
        acc.dividend_reinvest = bool(request.form.get('dividend_reinvest'))

        # Handle signature upload
        sig_file = request.files.get('signature')
        if sig_file and sig_file.filename:
            ext = os.path.splitext(sig_file.filename)[1].lower()
            if ext in ('.png', '.jpg', '.jpeg', '.gif'):
                fname = f'sig_{acc.account_number}_{uuid.uuid4().hex}{ext}'
                path  = os.path.join(current_app.config['UPLOAD_FOLDER'], 'signatures', fname)
                sig_file.save(path)
                acc.signature_path = f'signatures/{fname}'

        # Handle ID document upload
        id_file = request.files.get('id_document')
        if id_file and id_file.filename:
            ext = os.path.splitext(id_file.filename)[1].lower()
            if ext in ('.pdf', '.png', '.jpg', '.jpeg'):
                fname = f'id_{acc.account_number}_{uuid.uuid4().hex}{ext}'
                path  = os.path.join(current_app.config['UPLOAD_FOLDER'], 'documents', fname)
                id_file.save(path)
                acc.id_document_path = f'documents/{fname}'

        # Handle passport photo upload
        photo_file = request.files.get('passport_photo')
        if photo_file and photo_file.filename:
            ext = os.path.splitext(photo_file.filename)[1].lower()
            if ext in ('.png', '.jpg', '.jpeg'):
                fname = f'photo_{acc.account_number}_{uuid.uuid4().hex}{ext}'
                path  = os.path.join(current_app.config['UPLOAD_FOLDER'], 'photos', fname)
                photo_file.save(path)
                acc.passport_photo_path = f'photos/{fname}'

        db.session.commit()
        audit('PROFILE_UPDATE', target=acc.account_number, actor=current_user)
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('user.profile'))

    from models import ClientUser
    cu = ClientUser.query.filter_by(account_number=current_user.account_number).first()
    return render_template('user/profile.html', acc=acc, cu=cu)

@user_bp.route('/statement')
@client_required
def statement():
    acc = get_account()
    transactions = Transaction.query.filter_by(account_number=acc.account_number)\
                              .order_by(Transaction.txn_date.asc()).all()
    return render_template('user/statement.html', acc=acc, transactions=transactions)

@user_bp.route('/requests', methods=['GET', 'POST'])
@client_required
def requests_page():
    acc = get_account()
    if request.method == 'POST':
        req_type = request.form.get('request_type')
        amount   = request.form.get('amount')
        desc     = request.form.get('description', '')

        try:
            amount_f = float(str(amount).replace(',', '')) if amount else None
        except:
            amount_f = None

        # For withdrawal: check cash balance
        if req_type == 'WITHDRAWAL' and amount_f:
            if acc.cash_balance < amount_f:
                flash(f'Insufficient cash balance. Available: GHS {acc.cash_balance:,.2f}', 'error')
                return redirect(request.url)

        currency = request.form.get('currency', 'GHS')
        from utils.market_data import get_fx_rate
        fx_rate  = get_fx_rate(currency, 'GHS') if currency != 'GHS' else 1.0
        ghs_equiv = round(amount_f * fx_rate, 2) if amount_f else None

        # Additional check: withdrawal must not exceed available balance
        if req_type == 'WITHDRAWAL' and amount_f and ghs_equiv:
            if acc.cash_balance < ghs_equiv:
                flash(
                    f'Insufficient balance. Available: GHS {acc.cash_balance:,.2f} | '
                    f'Requested: {currency} {amount_f:,.2f} ≈ GHS {ghs_equiv:,.2f}',
                    'error'
                )
                return redirect(request.url)

        cr = ClientRequest(
            account_number=acc.account_number,
            request_type=req_type,
            amount=amount_f,
            currency=currency,
            asset_class=request.form.get('asset_class'),
            description=desc,
            status='PENDING'
        )
        db.session.add(cr)
        db.session.commit()
        audit('CLIENT_REQUEST', target=acc.account_number,
              detail=f'{req_type} {amount_f}', actor=current_user)
        flash('Your request has been submitted. An admin will review it shortly.', 'success')
        return redirect(url_for('user.requests_page'))

    reqs = ClientRequest.query.filter_by(account_number=acc.account_number)\
                        .order_by(ClientRequest.created_at.desc()).all()
    return render_template('user/requests.html', acc=acc, requests=reqs)

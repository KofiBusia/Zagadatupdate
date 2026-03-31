from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, session, Response
from flask_login import login_required, current_user
from models import (AdminUser, ClientAccount, ClientUser, Investment, Transaction,
                    MigrationLog, StockPrice, FXRate, db, ADMIN_ROLES)
from utils.market_data import fetch_fx_rates, fetch_gse_prices, fetch_global_prices
from datetime import datetime, date
import csv, io

admin_bp = Blueprint('admin', __name__)

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or session.get('user_type') != 'admin':
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def permission_required(permission):
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated or session.get('user_type') != 'admin':
                return redirect(url_for('auth.login'))
            if not current_user.has_permission(permission):
                flash('Insufficient permissions.', 'error')
                return redirect(url_for('admin.dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator

@admin_bp.route('/')
@admin_required
def dashboard():
    total_accounts      = ClientAccount.query.filter_by(status='APPROVED').count()
    pending_accounts    = ClientAccount.query.filter_by(status='PENDING').count()
    total_investments   = Investment.query.filter_by(status='APPROVED').count()
    pending_investments = Investment.query.filter_by(status='PENDING').count()
    investments = Investment.query.filter_by(status='APPROVED').all()
    aum = sum(i.computed_mkt_value for i in investments)
    recent_txns = Transaction.query.order_by(Transaction.created_at.desc()).limit(10).all()
    by_class = {}
    for inv in investments:
        lbl = inv.asset_class.replace('_', ' ').title()
        by_class[lbl] = by_class.get(lbl, 0) + inv.computed_mkt_value
    return render_template('admin/dashboard.html',
        total_accounts=total_accounts, pending_accounts=pending_accounts,
        total_investments=total_investments, pending_investments=pending_investments,
        aum=aum, recent_txns=recent_txns, now=date.today(), by_class=by_class)

@admin_bp.route('/accounts')
@admin_required
def accounts():
    q = request.args.get('q', '')
    status = request.args.get('status', '')
    query = ClientAccount.query
    if q:
        query = query.filter(
            (ClientAccount.account_number.ilike(f'%{q}%')) |
            (ClientAccount.full_name.ilike(f'%{q}%')) |
            (ClientAccount.phone.ilike(f'%{q}%')))
    if status:
        query = query.filter_by(status=status)
    return render_template('admin/accounts.html',
        accounts=query.order_by(ClientAccount.created_at.desc()).all(), q=q, status=status)

@admin_bp.route('/accounts/new', methods=['GET', 'POST'])
@permission_required('create_account')
def new_account():
    if request.method == 'POST':
        last = ClientAccount.query.order_by(ClientAccount.id.desc()).first()
        acc_no = f'ZC-{(last.id+1 if last else 1):05d}'
        acc = ClientAccount(
            account_number=acc_no,
            full_name=request.form.get('full_name'),
            date_of_birth=_parse_date(request.form.get('date_of_birth')),
            gender=request.form.get('gender'),
            marital_status=request.form.get('marital_status'),
            nationality=request.form.get('nationality'),
            residential_status=request.form.get('residential_status'),
            country_of_origin=request.form.get('country_of_origin'),
            country_of_residence=request.form.get('country_of_residence'),
            place_of_birth=request.form.get('place_of_birth'),
            digital_address=request.form.get('digital_address'),
            tin=request.form.get('tin'),
            phone=request.form.get('phone'),
            phone2=request.form.get('phone2'),
            email=request.form.get('email'),
            address=request.form.get('address'),
            postal_address=request.form.get('postal_address'),
            city=request.form.get('city'),
            country=request.form.get('country'),
            id_type=request.form.get('id_type'),
            id_number=request.form.get('id_number'),
            id_issue_date=_parse_date(request.form.get('id_issue_date')),
            id_expiry_date=_parse_date(request.form.get('id_expiry_date')),
            id_place_of_issue=request.form.get('id_place_of_issue'),
            occupation=request.form.get('occupation'),
            employer=request.form.get('employer'),
            employer_address=request.form.get('employer_address'),
            employer_city=request.form.get('employer_city'),
            nature_of_business=request.form.get('nature_of_business'),
            employment_status=request.form.get('employment_status'),
            years_employed=request.form.get('years_employed'),
            office_phone=request.form.get('office_phone'),
            office_email=request.form.get('office_email'),
            annual_income_range=request.form.get('annual_income_range'),
            source_of_funds=request.form.get('source_of_funds'),
            anticipated_investment=request.form.get('anticipated_investment'),
            topup_frequency=request.form.get('topup_frequency'),
            withdrawal_frequency=request.form.get('withdrawal_frequency'),
            regular_topup_amount=_float(request.form.get('regular_topup_amount')),
            regular_withdrawal_amount=_float(request.form.get('regular_withdrawal_amount')),
            bank_name=request.form.get('bank_name'),
            bank_branch=request.form.get('bank_branch'),
            bank_account_name=request.form.get('bank_account_name'),
            bank_account_number=request.form.get('bank_account_number'),
            account_type=request.form.get('account_type', 'Individual'),
            mandate=request.form.get('mandate'),
            regulatory_body=request.form.get('regulatory_body'),
            fund_type=request.form.get('fund_type'),
            investment_objective=request.form.get('investment_objective'),
            risk_profile=request.form.get('risk_profile'),
            investment_horizon=request.form.get('investment_horizon'),
            investment_knowledge=request.form.get('investment_knowledge'),
            base_currency=request.form.get('base_currency', 'GHS'),
            custodian=request.form.get('custodian'),
            csd_number=request.form.get('csd_number'),
            statement_mode=request.form.get('statement_mode'),
            statement_frequency=request.form.get('statement_frequency'),
            category_of_investment=request.form.get('category_of_investment'),
            client_first_contact=request.form.get('client_first_contact'),
            management_fee_rate=_float(request.form.get('management_fee_rate')),
            relationship_manager_id=_int(request.form.get('relationship_manager_id')),
            aml_status=request.form.get('aml_status'),
            is_pep=bool(request.form.get('is_pep')),
            pep_details=request.form.get('pep_details'),
            pep_foreign=bool(request.form.get('pep_foreign')),
            pep_foreign_details=request.form.get('pep_foreign_details'),
            risk_score=_int(request.form.get('risk_score')),
            risk_score_label=request.form.get('risk_score_label'),
            beneficiary1_name=request.form.get('beneficiary1_name'),
            beneficiary1_pct=_float(request.form.get('beneficiary1_pct')),
            beneficiary1_relation=request.form.get('beneficiary1_relation'),
            beneficiary1_dob=_parse_date(request.form.get('beneficiary1_dob')),
            beneficiary2_name=request.form.get('beneficiary2_name'),
            beneficiary2_pct=_float(request.form.get('beneficiary2_pct')),
            beneficiary2_relation=request.form.get('beneficiary2_relation'),
            beneficiary2_dob=_parse_date(request.form.get('beneficiary2_dob')),
            nominee_name=request.form.get('nominee_name'),
            nominee_phone=request.form.get('nominee_phone'),
            nominee_relation=request.form.get('nominee_relation'),
            spouse_name=request.form.get('spouse_name'),
            spouse_phone=request.form.get('spouse_phone'),
            spouse_email=request.form.get('spouse_email'),
            emergency_contact_name=request.form.get('emergency_contact_name'),
            emergency_contact_relation=request.form.get('emergency_contact_relation'),
            emergency_contact_phone=request.form.get('emergency_contact_phone'),
            itf_name=request.form.get('itf_name'),
            itf_relationship=request.form.get('itf_relationship'),
            itf_dob=_parse_date(request.form.get('itf_dob')),
            itf_gender=request.form.get('itf_gender'),
            itf_id_type=request.form.get('itf_id_type'),
            itf_id_number=request.form.get('itf_id_number'),
            is_foreign_citizen=bool(request.form.get('is_foreign_citizen')),
            foreign_country=request.form.get('foreign_country'),
            foreign_address=request.form.get('foreign_address'),
            foreign_tin=request.form.get('foreign_tin'),
            dividend_reinvest=bool(request.form.get('dividend_reinvest')),
            status='APPROVED' if current_user.is_super_admin else 'PENDING',
            created_by=current_user.id,
            approved_by=current_user.id if current_user.is_super_admin else None,
            approved_at=datetime.utcnow() if current_user.is_super_admin else None,
        )
        db.session.add(acc)
        db.session.flush()
        cu = ClientUser(account_number=acc_no, phone=acc.phone or '0000')
        cu.set_password(acc.phone or '0000')
        db.session.add(cu)
        db.session.commit()
        flash(f'Account {acc_no} created. Default login password = phone number.', 'success')
        return redirect(url_for('admin.view_account', acc_id=acc.id))
    return render_template('admin/account_form.html', account=None,
                           rm_list=AdminUser.query.filter_by(is_rm=True, is_active=True).all())

@admin_bp.route('/accounts/<int:acc_id>/approve', methods=['POST'])
@permission_required('approve_account')
def approve_account(acc_id):
    acc = ClientAccount.query.get_or_404(acc_id)
    acc.status = 'APPROVED'
    acc.approved_by = current_user.id
    acc.approved_at = datetime.utcnow()
    db.session.commit()
    from utils.notifications import email_account_approved, audit as _audit
    email_account_approved(acc)
    _audit('ACCOUNT_APPROVED', target=acc.account_number)
    flash('Account approved and client notified.', 'success')
    return redirect(url_for('admin.accounts'))

@admin_bp.route('/accounts/<int:acc_id>/edit', methods=['GET', 'POST'])
@permission_required('create_account')
def edit_account(acc_id):
    acc = ClientAccount.query.get_or_404(acc_id)
    if request.method == 'POST':
        for field in ['full_name','gender','nationality','id_type','id_number','phone','email',
                      'address','city','country','occupation','employer','account_type',
                      'regulatory_body','fund_type','investment_objective','risk_profile',
                      'base_currency','custodian','nominee_name','nominee_phone','nominee_relation']:
            setattr(acc, field, request.form.get(field))
        acc.date_of_birth = _parse_date(request.form.get('date_of_birth'))
        db.session.commit()
        flash('Account updated.', 'success')
        return redirect(url_for('admin.view_account', acc_id=acc_id))
    return render_template('admin/account_form.html', account=acc,
                           rm_list=AdminUser.query.filter_by(is_rm=True, is_active=True).all())

@admin_bp.route('/accounts/<int:acc_id>')
@admin_required
def view_account(acc_id):
    acc = ClientAccount.query.get_or_404(acc_id)
    investments  = Investment.query.filter_by(account_number=acc.account_number, status='APPROVED').all()
    transactions = Transaction.query.filter_by(account_number=acc.account_number)\
                              .order_by(Transaction.txn_date.asc()).all()
    return render_template('admin/account_view.html',
                           acc=acc, investments=investments, transactions=transactions)

@admin_bp.route('/investments')
@admin_required
def investments():
    q = request.args.get('q', '')
    asset_class = request.args.get('asset_class', '')
    status = request.args.get('status', '')
    query = Investment.query
    if q:
        query = query.filter(
            (Investment.account_number.ilike(f'%{q}%')) |
            (Investment.security_name.ilike(f'%{q}%')) |
            (Investment.issuer.ilike(f'%{q}%')))
    if asset_class:
        query = query.filter_by(asset_class=asset_class)
    if status:
        query = query.filter_by(status=status)
    return render_template('admin/investments.html',
        investments=query.order_by(Investment.created_at.desc()).all(),
        q=q, asset_class=asset_class, status=status)

@admin_bp.route('/investments/new', methods=['GET', 'POST'])
@permission_required('enter_investment')
def new_investment():
    accounts = ClientAccount.query.filter_by(status='APPROVED').order_by(ClientAccount.full_name).all()
    if request.method == 'POST':
        acc_no = request.form.get('account_number')
        acc = ClientAccount.query.filter_by(account_number=acc_no).first()
        if not acc:
            flash('Account not found.', 'error')
            return redirect(request.url)
        total_cost = _float(request.form.get('total_cost')) or 0.0
        asset_class = request.form.get('asset_class')
        if total_cost > 0:
            cash = acc.cash_balance
            if cash < total_cost:
                flash(f'Insufficient cash. Available: {cash:,.2f} | Required: {total_cost:,.2f}', 'error')
                return redirect(request.url)
        inv = Investment(
            account_number=acc_no, asset_class=asset_class,
            sub_type=request.form.get('sub_type'),
            issuer=request.form.get('issuer'),
            security_name=request.form.get('security_name'),
            symbol=request.form.get('symbol'),
            isin=request.form.get('isin'),
            exchange=request.form.get('exchange'),
            sector=request.form.get('sector'),
            trade_date=_parse_date(request.form.get('trade_date')),
            issue_date=_parse_date(request.form.get('issue_date')),
            maturity_date=_parse_date(request.form.get('maturity_date')),
            tenor=_int(request.form.get('tenor')),
            quantity=_float(request.form.get('quantity')),
            face_value=_float(request.form.get('face_value')),
            coupon_rate=_float(request.form.get('coupon_rate')),
            coupon_freq=_int(request.form.get('coupon_freq')) or 2,
            interest_rate=_float(request.form.get('interest_rate')),
            clean_price=_float(request.form.get('clean_price')),
            unit_cost=_float(request.form.get('unit_cost')),
            total_cost=total_cost,
            currency=request.form.get('currency', 'GHS'),
            current_price=_float(request.form.get('current_price')),
            last_coupon_date=_parse_date(request.form.get('last_coupon_date')),
            vintage_year=_int(request.form.get('vintage_year')),
            geography=request.form.get('geography'),
            stage=request.form.get('stage'),
            committed=_float(request.form.get('committed')),
            called=_float(request.form.get('called')),
            distributions=_float(request.form.get('distributions')),
            moic=_float(request.form.get('moic')),
            irr=_float(request.form.get('irr')),
            nav=_float(request.form.get('nav')),
            outstanding=_float(request.form.get('outstanding')),
            rating=request.form.get('rating'),
            pik=bool(request.form.get('pik')),
            country_of_issue=request.form.get('country_of_issue'),
            notes=request.form.get('notes'),
            status='APPROVED' if current_user.is_super_admin else 'PENDING',
            created_by=current_user.id,
            approved_by=current_user.id if current_user.is_super_admin else None,
            approved_at=datetime.utcnow() if current_user.is_super_admin else None,
        )
        db.session.add(inv)
        db.session.flush()
        if total_cost > 0:
            txn = Transaction(
                account_number=acc_no,
                txn_date=inv.trade_date or date.today(),
                txn_type='BUY',
                description=f'Purchase: {inv.security_name or asset_class}',
                amount=total_cost, currency=inv.currency,
                investment_id=inv.id, status='APPROVED',
                created_by=current_user.id)
            db.session.add(txn)
        db.session.commit()
        flash('Investment recorded.', 'success')
        return redirect(url_for('admin.view_account', acc_id=acc.id))
    return render_template('admin/investment_form.html', accounts=accounts, investment=None)

@admin_bp.route('/investments/<int:inv_id>/approve', methods=['POST'])
@permission_required('approve_investment')
def approve_investment(inv_id):
    inv = Investment.query.get_or_404(inv_id)
    inv.status = 'APPROVED'
    inv.approved_by = current_user.id
    inv.approved_at = datetime.utcnow()
    db.session.commit()
    flash('Investment approved.', 'success')
    return redirect(request.referrer or url_for('admin.investments'))

@admin_bp.route('/investments/<int:inv_id>/edit', methods=['GET', 'POST'])
@permission_required('enter_investment')
def edit_investment(inv_id):
    inv = Investment.query.get_or_404(inv_id)
    accounts = ClientAccount.query.filter_by(status='APPROVED').all()
    if request.method == 'POST':
        for f in ['sub_type','issuer','security_name','symbol','isin','exchange','sector',
                  'currency','notes','geography','stage','rating','country_of_issue']:
            setattr(inv, f, request.form.get(f))
        for f in ['quantity','face_value','coupon_rate','interest_rate','clean_price',
                  'unit_cost','total_cost','current_price','committed','called',
                  'distributions','moic','irr','nav','outstanding']:
            setattr(inv, f, _float(request.form.get(f)))
        for f in ['tenor','coupon_freq','vintage_year']:
            setattr(inv, f, _int(request.form.get(f)))
        for f in ['trade_date','issue_date','maturity_date','last_coupon_date']:
            setattr(inv, f, _parse_date(request.form.get(f)))
        db.session.commit()
        flash('Investment updated.', 'success')
        return redirect(url_for('admin.view_account', acc_id=inv.account.id))
    return render_template('admin/investment_form.html', accounts=accounts, investment=inv)

@admin_bp.route('/transactions')
@admin_required
def transactions():
    q = request.args.get('q', '')
    query = Transaction.query
    if q:
        query = query.filter(Transaction.account_number.ilike(f'%{q}%'))
    return render_template('admin/transactions.html',
        transactions=query.order_by(Transaction.txn_date.desc()).limit(500).all(), q=q)

@admin_bp.route('/transactions/new', methods=['GET', 'POST'])
@permission_required('enter_investment')
def new_transaction():
    accounts = ClientAccount.query.filter_by(status='APPROVED').order_by(ClientAccount.full_name).all()
    if request.method == 'POST':
        acc_no = request.form.get('account_number')
        txn_type = request.form.get('txn_type')
        amount = _float(request.form.get('amount')) or 0
        acc = ClientAccount.query.filter_by(account_number=acc_no).first()
        if not acc:
            flash('Account not found.', 'error')
            return redirect(request.url)
        if txn_type in ('WITHDRAWAL', 'TRANSFER_OUT', 'FEE') and acc.cash_balance < amount:
            flash(f'Insufficient cash. Balance: {acc.cash_balance:,.2f}', 'error')
            return redirect(request.url)
        txn = Transaction(
            account_number=acc_no,
            txn_date=_parse_date(request.form.get('txn_date')) or date.today(),
            txn_type=txn_type,
            description=request.form.get('description'),
            amount=amount,
            currency=request.form.get('currency', 'GHS'),
            reference=request.form.get('reference'),
            status='APPROVED',
            created_by=current_user.id)
        db.session.add(txn)
        db.session.commit()
        flash('Transaction recorded.', 'success')
        return redirect(url_for('admin.view_account', acc_id=acc.id))
    preselect = request.args.get('acc', '')
    return render_template('admin/transaction_form.html', accounts=accounts, preselect=preselect)

@admin_bp.route('/users')
@permission_required('manage_all')
def admin_users():
    users = AdminUser.query.order_by(AdminUser.created_at.desc()).all()
    return render_template('admin/admin_users.html', users=users, roles=ADMIN_ROLES)

@admin_bp.route('/users/new', methods=['GET', 'POST'])
@permission_required('create_admin')
def new_admin_user():
    if request.method == 'POST':
        role = request.form.get('role')
        if role == 'SUPER_ADMIN' and not current_user.is_super_admin:
            flash('Only Super Admin can create other Super Admins.', 'error')
            return redirect(request.url)
        last = AdminUser.query.order_by(AdminUser.id.desc()).first()
        staff_id = f'SA{(last.id+1 if last else 1):03d}'
        u = AdminUser(staff_id=staff_id, full_name=request.form.get('full_name'),
                      email=request.form.get('email'), role=role, created_by=current_user.id,
                      is_rm=bool(request.form.get('is_rm')),
                      rm_commission_rate=float(request.form.get('rm_commission_rate') or 1.0))
        u.set_password(request.form.get('password'))
        db.session.add(u)
        db.session.commit()
        flash(f'Staff {staff_id} created.', 'success')
        return redirect(url_for('admin.admin_users'))
    return render_template('admin/admin_user_form.html', roles=ADMIN_ROLES, user=None)

@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@permission_required('manage_all')
def toggle_admin_user(user_id):
    u = AdminUser.query.get_or_404(user_id)
    if u.id != current_user.id:
        u.is_active = not u.is_active
        db.session.commit()
        flash(f'Account {"activated" if u.is_active else "deactivated"}.', 'success')
    return redirect(url_for('admin.admin_users'))

@admin_bp.route('/migration', methods=['GET', 'POST'])
@permission_required('migrate_data')
def migration():
    logs = MigrationLog.query.order_by(MigrationLog.executed_at.desc()).all()
    if request.method == 'POST':
        migrate_type = request.form.get('migrate_type')
        file = request.files.get('file')
        if not file:
            flash('No file uploaded.', 'error')
            return redirect(request.url)
        content = file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content))
        records_in = records_ok = records_err = 0
        errors = []
        for row in reader:
            records_in += 1
            try:
                if migrate_type == 'accounts':
                    acc_no = row.get('account_number','').strip()
                    if not acc_no:
                        last = ClientAccount.query.order_by(ClientAccount.id.desc()).first()
                        acc_no = f'ZC-{(last.id+1 if last else 1):05d}'
                    if ClientAccount.query.filter_by(account_number=acc_no).first():
                        errors.append(f'Row {records_in}: {acc_no} exists')
                        records_err += 1; continue
                    acc = ClientAccount(account_number=acc_no, full_name=row.get('full_name','').strip(),
                        phone=row.get('phone','').strip(), email=row.get('email','').strip(),
                        account_type=row.get('account_type','Individual'), country=row.get('country','Ghana'),
                        base_currency=row.get('base_currency','GHS'), status='APPROVED', created_by=current_user.id)
                    db.session.add(acc)
                    db.session.flush()
                    cu = ClientUser(account_number=acc_no, phone=acc.phone or '0000')
                    cu.set_password(acc.phone or '0000')
                    db.session.add(cu)
                elif migrate_type == 'transactions':
                    txn = Transaction(account_number=row.get('account_number','').strip(),
                        txn_date=_parse_date(row.get('txn_date')) or date.today(),
                        txn_type=row.get('txn_type','DEPOSIT').upper(),
                        description=row.get('description',''), amount=abs(float(row.get('amount',0))),
                        currency=row.get('currency','GHS'), reference=row.get('reference',''),
                        status='APPROVED', created_by=current_user.id)
                    db.session.add(txn)
                elif migrate_type == 'investments':
                    inv = Investment(account_number=row.get('account_number','').strip(),
                        asset_class=row.get('asset_class','GOVT_SECURITIES'),
                        security_name=row.get('security_name',''), issuer=row.get('issuer',''),
                        sub_type=row.get('sub_type',''),
                        trade_date=_parse_date(row.get('trade_date')),
                        maturity_date=_parse_date(row.get('maturity_date')),
                        face_value=_float(row.get('face_value')), coupon_rate=_float(row.get('coupon_rate')),
                        interest_rate=_float(row.get('interest_rate')), total_cost=_float(row.get('total_cost')),
                        currency=row.get('currency','GHS'), tenor=_int(row.get('tenor')),
                        status='APPROVED', created_by=current_user.id)
                    db.session.add(inv)
                records_ok += 1
            except Exception as e:
                errors.append(f'Row {records_in}: {str(e)}')
                records_err += 1
                db.session.rollback()
        log = MigrationLog(filename=file.filename, records_in=records_in,
            records_ok=records_ok, records_err=records_err,
            errors='\n'.join(errors[:50]), executed_by=current_user.id,
            status='COMPLETED' if not records_err else 'PARTIAL')
        db.session.add(log)
        db.session.commit()
        flash(f'Migration: {records_ok} OK, {records_err} errors.', 'success')
        return redirect(url_for('admin.migration'))
    return render_template('admin/migration.html', logs=logs)

@admin_bp.route('/migration/template/<template_type>')
@permission_required('migrate_data')
def migration_template(template_type):
    templates = {
        'accounts':     ['account_number','full_name','phone','email','account_type','country','base_currency'],
        'transactions': ['account_number','txn_date','txn_type','description','amount','currency','reference'],
        'investments':  ['account_number','asset_class','security_name','issuer','sub_type',
                         'trade_date','maturity_date','face_value','coupon_rate','interest_rate',
                         'total_cost','currency','tenor'],
    }
    headers = templates.get(template_type, [])
    return Response(','.join(headers)+'\n', mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename={template_type}_template.csv'})

@admin_bp.route('/refresh-market-data', methods=['POST'])
@admin_required
def refresh_market_data():
    fx_ok = fetch_fx_rates()
    gse   = fetch_gse_prices()
    glb   = fetch_global_prices()
    return jsonify({'fx': fx_ok, 'gse': gse, 'global': glb})

@admin_bp.route('/stocks', methods=['GET', 'POST'])
@permission_required('manage_all')
def manage_stocks():
    from models import StockPrice
    if request.method == 'POST':
        symbol = request.form.get('symbol','').upper()
        price  = _float(request.form.get('price'))
        if symbol and price:
            sp = StockPrice.query.filter_by(symbol=symbol).first()
            if sp:
                sp.price = price
                sp.change_pct = _float(request.form.get('change_pct')) or 0
                sp.updated_at = datetime.utcnow()
            else:
                sp = StockPrice(symbol=symbol, name=request.form.get('name',symbol),
                    price=price, exchange=request.form.get('exchange','GSE'),
                    change_pct=_float(request.form.get('change_pct')) or 0)
                db.session.add(sp)
            db.session.commit()
            flash(f'{symbol} updated.', 'success')
    stocks = StockPrice.query.order_by(StockPrice.exchange, StockPrice.symbol).all()
    return render_template('admin/stocks.html', stocks=stocks)

@admin_bp.route('/fx-rates', methods=['GET', 'POST'])
@permission_required('manage_all')
def manage_fx():
    if request.method == 'POST':
        base = request.form.get('base','').upper()
        rate = _float(request.form.get('rate'))
        if base and rate:
            r = FXRate.query.filter_by(base=base, quote='GHS').first()
            if r:
                r.rate = rate; r.updated_at = datetime.utcnow()
            else:
                db.session.add(FXRate(base=base, quote='GHS', rate=rate))
            db.session.commit()
            flash(f'1 {base} = GHS {rate:.4f}', 'success')
    rates = FXRate.query.all()
    return render_template('admin/fx_rates.html', rates=rates)

def _parse_date(s):
    if not s: return None
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%m/%d/%Y'):
        try: return datetime.strptime(s.strip(), fmt).date()
        except: pass
    return None

def _float(s):
    try: return float(str(s).replace(',','').strip())
    except: return None

def _int(s):
    try: return int(str(s).replace(',','').strip())
    except: return None

# ── FEES MANAGEMENT ────────────────────────────────────────────────────────────
@admin_bp.route('/fees')
@permission_required('approve_account')
def fees():
    from models import FeeType, AccountFee, FeeTransaction
    fee_types = FeeType.query.filter_by(is_active=True).all()
    recent_fees = FeeTransaction.query.order_by(FeeTransaction.created_at.desc()).limit(50).all()
    # Totals
    total_earned = sum(f.amount for f in FeeTransaction.query.filter_by(status='APPLIED').all())
    by_type = {}
    for f in FeeTransaction.query.filter_by(status='APPLIED').all():
        name = f.fee_type.name if f.fee_type else 'Unknown'
        by_type[name] = by_type.get(name, 0) + f.amount
    return render_template('admin/fees.html', fee_types=fee_types,
                           recent_fees=recent_fees, total_earned=total_earned, by_type=by_type)

@admin_bp.route('/fees/types/new', methods=['POST'])
@permission_required('manage_all')
def new_fee_type():
    from models import FeeType
    name = request.form.get('name','').strip()
    desc = request.form.get('description','').strip()
    if name and not FeeType.query.filter_by(name=name).first():
        db.session.add(FeeType(name=name, description=desc, created_by=current_user.id))
        db.session.commit()
        flash(f'Fee type "{name}" created.', 'success')
    return redirect(url_for('admin.fees'))

@admin_bp.route('/fees/assign/<int:acc_id>', methods=['GET', 'POST'])
@permission_required('approve_account')
def assign_fee(acc_id):
    from models import FeeType, AccountFee
    acc = ClientAccount.query.get_or_404(acc_id)
    fee_types = FeeType.query.filter_by(is_active=True).all()
    if request.method == 'POST':
        ft_id = _int(request.form.get('fee_type_id'))
        rate  = _float(request.form.get('rate'))
        freq  = request.form.get('frequency', 'Quarterly')
        if ft_id and rate is not None:
            existing = AccountFee.query.filter_by(
                account_number=acc.account_number, fee_type_id=ft_id).first()
            if existing:
                existing.rate = rate; existing.frequency = freq
            else:
                db.session.add(AccountFee(account_number=acc.account_number,
                    fee_type_id=ft_id, rate=rate, frequency=freq,
                    effective_date=date.today(), created_by=current_user.id))
            db.session.commit()
            flash('Fee assigned.', 'success')
        return redirect(url_for('admin.view_account', acc_id=acc_id))
    return render_template('admin/assign_fee.html', acc=acc, fee_types=fee_types)

@admin_bp.route('/fees/charge/<int:acc_id>', methods=['POST'])
@permission_required('approve_account')
def charge_fee(acc_id):
    from models import FeeTransaction, AccountFee
    acc = ClientAccount.query.get_or_404(acc_id)
    ft_id = _int(request.form.get('fee_type_id'))
    rate  = _float(request.form.get('rate'))
    aum   = acc.total_portfolio_value
    amount = aum * (rate / 100) if rate else 0
    if amount > 0:
        ft = FeeTransaction(account_number=acc.account_number, fee_type_id=ft_id,
            amount=amount, aum_at_time=aum, rate_applied=rate,
            period_from=_parse_date(request.form.get('period_from')),
            period_to=_parse_date(request.form.get('period_to')),
            status='APPLIED', created_by=current_user.id)
        db.session.add(ft)
        # Deduct from cash
        txn = Transaction(account_number=acc.account_number, txn_date=date.today(),
            txn_type='FEE', description=f'Fee charge: {request.form.get("fee_name","")}',
            amount=amount, currency='GHS', status='APPROVED', created_by=current_user.id)
        db.session.add(txn)
        db.session.commit()
        flash(f'Fee of GHS {amount:,.2f} charged.', 'success')
    return redirect(url_for('admin.view_account', acc_id=acc_id))

# ── RELATIONSHIP MANAGERS ──────────────────────────────────────────────────────
@admin_bp.route('/rm')
@permission_required('manage_all')
def relationship_managers():
    rms = AdminUser.query.filter_by(is_rm=True).all()
    rm_data = []
    for rm in rms:
        accounts = ClientAccount.query.filter_by(relationship_manager_id=rm.id, status='APPROVED').all()
        rm_data.append({
            'rm': rm,
            'account_count': len(accounts),
            'portfolio_value': rm.rm_portfolio_value,
            'earnings': rm.rm_earnings,
        })
    return render_template('admin/rm.html', rm_data=rm_data)

# ── AUDIT LOG ──────────────────────────────────────────────────────────────────
@admin_bp.route('/audit')
@permission_required('manage_all')
def audit_log():
    from models import AuditLog
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(500).all()
    return render_template('admin/audit.html', logs=logs)

# ── CLIENT REQUESTS ────────────────────────────────────────────────────────────
@admin_bp.route('/requests')
@admin_required
def client_requests():
    from models import ClientRequest
    status = request.args.get('status','')
    query = ClientRequest.query
    if status:
        query = query.filter_by(status=status)
    reqs = query.order_by(ClientRequest.created_at.desc()).all()
    return render_template('admin/client_requests.html', requests=reqs, status=status)

@admin_bp.route('/requests/<int:req_id>/action', methods=['POST'])
@permission_required('approve_investment')
def action_request(req_id):
    from models import ClientRequest
    from utils.notifications import email_request_update
    cr = ClientRequest.query.get_or_404(req_id)
    action = request.form.get('action')  # APPROVED | REJECTED
    note   = request.form.get('note','')
    cr.status = action
    cr.admin_note = note
    cr.reviewed_by = current_user.id
    cr.reviewed_at = datetime.utcnow()
    db.session.commit()
    # Notify client
    acc = ClientAccount.query.filter_by(account_number=cr.account_number).first()
    if acc:
        email_request_update(acc, cr.request_type, action, note)
    flash(f'Request {action.lower()}.', 'success')
    return redirect(url_for('admin.client_requests'))

# ── ACCOUNT REJECT ─────────────────────────────────────────────────────────────
@admin_bp.route('/accounts/<int:acc_id>/reject', methods=['POST'])
@permission_required('approve_account')
def reject_account(acc_id):
    from utils.notifications import email_account_rejected
    acc = ClientAccount.query.get_or_404(acc_id)
    reason = request.form.get('reason','')
    acc.status = 'REJECTED'
    acc.rejection_reason = reason
    db.session.commit()
    email_account_rejected(acc, reason)
    flash('Account rejected and client notified.', 'success')
    return redirect(url_for('admin.accounts'))

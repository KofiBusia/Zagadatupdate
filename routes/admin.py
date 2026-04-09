from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, session, Response, send_file
from flask_login import login_required, current_user
from models import (AdminUser, ClientAccount, ClientUser, Investment, Transaction,
                    MigrationLog, StockPrice, FXRate, db, ADMIN_ROLES)
from utils.market_data import fetch_fx_rates, fetch_gse_prices, fetch_global_prices
from datetime import datetime, date
import csv, io

def _to_ghs(amount, currency):
    """Convert amount in given currency to GHS using current FX rates."""
    if not amount or currency == 'GHS':
        return amount
    from utils.market_data import get_fx_rate
    rate = get_fx_rate(currency, 'GHS')
    return round(amount * rate, 4)

def _approve_transaction(txn, approver_id):
    """
    Mark a transaction APPROVED and set amount_ghs via current FX rate.
    Sends email alert to client. This is the single canonical approval function.
    """
    if txn.status == 'APPROVED':
        return
    from utils.market_data import get_fx_rate
    rate = get_fx_rate(txn.currency, 'GHS') if txn.currency != 'GHS' else 1.0
    txn.amount_ghs   = round(txn.amount * rate, 4)
    txn.fx_rate_used = rate
    txn.status       = 'APPROVED'
    txn.approved_by  = approver_id
    txn.approved_at  = datetime.utcnow()
    # Send email alert to client
    try:
        from models import ClientAccount
        from utils.notifications import email_transaction_approved
        acc = ClientAccount.query.filter_by(account_number=txn.account_number).first()
        if acc and acc.email:
            email_transaction_approved(acc, txn)
    except Exception as _e:
        print(f'[TXN EMAIL] Failed: {_e}')

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
    from models import ClientRequest
    total_accounts      = ClientAccount.query.filter_by(status='APPROVED').count()
    pending_accounts    = ClientAccount.query.filter_by(status='PENDING').count()
    total_investments   = Investment.query.filter_by(status='APPROVED').count()
    pending_investments = Investment.query.filter_by(status='PENDING').count()
    pending_transactions= Transaction.query.filter_by(status='PENDING').count()
    pending_requests    = ClientRequest.query.filter_by(status='PENDING').count()
    investments = Investment.query.filter_by(status='APPROVED').all()
    aum = sum(i.computed_mkt_value for i in investments)
    # Total cash across all accounts (GHS)
    total_cash = sum(acc.cash_balance for acc in ClientAccount.query.filter_by(status='APPROVED').all())
    total_aum  = aum + total_cash
    recent_txns = Transaction.query.order_by(Transaction.created_at.desc()).limit(10).all()
    by_class = {}
    for inv in investments:
        lbl = inv.asset_class.replace('_', ' ').title()
        by_class[lbl] = by_class.get(lbl, 0) + inv.computed_mkt_value
    # Live FX rates summary
    from utils.market_data import get_all_fx
    fx = get_all_fx()
    return render_template('admin/dashboard.html',
        total_accounts=total_accounts, pending_accounts=pending_accounts,
        total_investments=total_investments, pending_investments=pending_investments,
        pending_transactions=pending_transactions, pending_requests=pending_requests,
        aum=aum, total_cash=total_cash, total_aum=total_aum,
        recent_txns=recent_txns, now=date.today(), by_class=by_class, fx=fx)

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

@admin_bp.route('/transactions/<int:txn_id>/approve', methods=['POST'])
@permission_required('approve_investment')
def approve_transaction(txn_id):
    """
    Approve a PENDING transaction.
    - Computes GHS equivalent using current FX rate at time of approval.
    - For BUY/WITHDRAWAL/TRANSFER_OUT: checks cash balance is sufficient.
    - For investment-linked BUY transactions: activates the investment too if it was waiting.
    """
    txn = Transaction.query.get_or_404(txn_id)
    acc = ClientAccount.query.filter_by(account_number=txn.account_number).first_or_404()

    if txn.status != 'PENDING':
        flash('Transaction is not in PENDING status.', 'error')
        return redirect(request.referrer or url_for('admin.transactions'))

    # ── Maker-checker: entrant cannot approve their own entry ─────────
    if not current_user.is_super_admin and txn.created_by == current_user.id:
        flash('Maker-checker violation: you cannot approve a transaction you entered. '
              'Another authorised staff member must approve it.', 'error')
        return redirect(request.referrer or url_for('admin.view_account', acc_id=acc.id))
    # ─────────────────────────────────────────────────────────────────

    # For outflows: validate sufficient approved cash balance
    outflow_types = ('WITHDRAWAL', 'TRANSFER_OUT', 'FEE', 'BUY')
    if txn.txn_type in outflow_types:
        from utils.market_data import get_fx_rate
        rate = get_fx_rate(txn.currency, 'GHS') if txn.currency != 'GHS' else 1.0
        needed_ghs = txn.amount * rate
        if acc.cash_balance < needed_ghs:
            flash(
                f'Insufficient approved cash. '
                f'Available: GHS {acc.cash_balance:,.2f} | '
                f'Required: GHS {needed_ghs:,.2f} '
                f'({txn.amount:,.2f} {txn.currency} @ {rate:.4f})',
                'error'
            )
            return redirect(request.referrer or url_for('admin.view_account', acc_id=acc.id))

    _approve_transaction(txn, current_user.id)

    # If this is a BUY linked to an investment still PENDING, approve the investment too
    if txn.investment_id and txn.txn_type == 'BUY':
        inv = Investment.query.get(txn.investment_id)
        if inv and inv.status == 'PENDING':
            inv.status      = 'APPROVED'
            inv.approved_by = current_user.id
            inv.approved_at = datetime.utcnow()

    # If this is a SELL: mark the investment as SOLD
    if txn.investment_id and txn.txn_type == 'SELL':
        inv = Investment.query.get(txn.investment_id)
        if inv and inv.status == 'APPROVED':
            inv.status = 'SOLD'
            inv.notes  = (inv.notes or '') + f' | Sold {txn.txn_date} approved {datetime.utcnow().date()}'

    db.session.commit()
    from utils.notifications import audit as _audit
    _audit('TXN_APPROVED', target=f'{txn.account_number}', detail=f'id={txn.id} {txn.txn_type} {txn.amount} {txn.currency}')
    flash(f'Transaction approved. Cash balance updated (GHS {txn.amount_ghs:,.2f}).', 'success')
    return redirect(request.referrer or url_for('admin.view_account', acc_id=acc.id))


@admin_bp.route('/transactions/<int:txn_id>/reject', methods=['POST'])
@permission_required('approve_investment')
def reject_transaction(txn_id):
    txn = Transaction.query.get_or_404(txn_id)
    if txn.status != 'PENDING':
        flash('Transaction is not in PENDING status.', 'error')
        return redirect(request.referrer or url_for('admin.transactions'))

    # ── Maker-checker ─────────────────────────────────────────────────
    if not current_user.is_super_admin and txn.created_by == current_user.id:
        flash('Maker-checker violation: you cannot reject a transaction you entered.', 'error')
        return redirect(request.referrer or url_for('admin.transactions'))
    # ─────────────────────────────────────────────────────────────────

    note = request.form.get('note', '')
    txn.status         = 'REJECTED'
    txn.rejection_note = note
    txn.approved_by    = current_user.id
    txn.approved_at    = datetime.utcnow()
    # If this was a BUY linked to an investment, reject the investment too
    if txn.investment_id and txn.txn_type == 'BUY':
        inv = Investment.query.get(txn.investment_id)
        if inv and inv.status == 'PENDING':
            inv.status = 'REJECTED'
    db.session.commit()
    from utils.notifications import audit as _audit
    _audit('TXN_REJECTED', target=txn.account_number, detail=f'id={txn.id} note={note}')
    flash('Transaction rejected.', 'success')
    return redirect(request.referrer or url_for('admin.view_account', acc_id=txn.account_number))


@admin_bp.route('/accounts/<int:acc_id>/approve', methods=['POST'])
@permission_required('approve_account')
def approve_account(acc_id):
    acc = ClientAccount.query.get_or_404(acc_id)

    # ── Maker-checker ─────────────────────────────────────────────────
    if not current_user.is_super_admin and acc.created_by == current_user.id:
        flash('Maker-checker violation: you cannot approve an account you created. '
              'Another authorised staff member must approve it.', 'error')
        return redirect(url_for('admin.accounts'))
    # ─────────────────────────────────────────────────────────────────

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
    investments   = Investment.query.filter_by(account_number=acc.account_number, status='APPROVED').all()
    sold_invs     = Investment.query.filter_by(account_number=acc.account_number, status='SOLD').all()
    pending_invs  = Investment.query.filter_by(account_number=acc.account_number, status='PENDING').all()
    all_txns      = Transaction.query.filter_by(account_number=acc.account_number)\
                       .order_by(Transaction.txn_date.asc(), Transaction.id.asc()).all()
    pending_txns  = [t for t in all_txns if t.status == 'PENDING']
    from models import ClientRequest
    pending_reqs  = ClientRequest.query.filter_by(account_number=acc.account_number, status='PENDING').all()
    from utils.market_data import get_all_fx
    fx = get_all_fx()
    rm_list = AdminUser.query.filter_by(is_rm=True, is_active=True).order_by(AdminUser.full_name).all()
    return render_template('admin/account_view.html',
        acc=acc,
        investments=investments,
        sold_invs=sold_invs,
        pending_invs=pending_invs,
        transactions=all_txns,
        pending_txns=pending_txns,
        pending_reqs=pending_reqs,
        fx=fx,
        rm_list=rm_list,
    )

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

        asset_class = request.form.get('asset_class', '').upper()

        # ── Read prefixed fields by asset class to avoid collision ────────────
        # Each panel uses field names prefixed with the class code
        # (e.g. mm_face_value, gs_interest_rate, bond_coupon_rate etc.)
        def pf(field, fallback=''):
            """Get prefixed field, fallback to non-prefixed."""
            prefix_map = {
                'MONEY_MARKET':   'mm',
                'GOVT_SECURITIES':'gs',
                'BONDS':          'bond',
                'EUROBONDS':      'euro',
                'GSE_EQUITIES':   'gse',
                'GLOBAL_EQUITIES':'gl',
                'PRIVATE_EQUITY': 'pe',
                'PRIVATE_DEBT':   'pd',
                'MUTUAL_FUNDS':   'mf',
            }
            pfx = prefix_map.get(asset_class, '')
            val = request.form.get(f'{pfx}_{field}') if pfx else None
            if val is None or val == '':
                val = request.form.get(field, fallback)
            return val

        def pff(field):   return _float(pf(field))
        def pfi(field):   return _int(pf(field))
        def pfb(field):   return bool(pf(field))
        def pfd(field):   return _parse_date(pf(field))
        def pfs(field):   return pf(field) or None

        total_cost = pff('total_cost') or 0.0
        trade_date_val = pfd('trade_date')
        # ── Date rule: only Super Admin can backdate investments ───────
        if trade_date_val and trade_date_val != date.today() and not current_user.is_super_admin:
            flash('Only the Super Admin can backdate investment entries. Use today\'s date.', 'error')
            return redirect(request.url)
        # ──────────────────────────────────────────────────────────────
        tenor_val = pfi('tenor')
        face_val  = pff('face_value') or 0.0
        rate_val  = pff('interest_rate') or pff('coupon_rate') or 0.0

        # ── Server-side maturity auto-calculation ─────────────────────────────
        # Always compute from trade_date + tenor, regardless of what the client sent
        maturity_date = pfd('maturity_date')
        if trade_date_val and tenor_val:
            from datetime import timedelta
            if asset_class in ('BONDS', 'EUROBONDS'):
                # tenor in YEARS
                try:
                    from dateutil.relativedelta import relativedelta
                    computed_mat = trade_date_val + relativedelta(years=int(tenor_val))
                except ImportError:
                    computed_mat = trade_date_val + timedelta(days=int(tenor_val * 365))
            elif asset_class in ('GOVT_SECURITIES', 'MONEY_MARKET', 'PRIVATE_DEBT'):
                # tenor in DAYS for GS/MM, YEARS for PD
                if asset_class == 'PRIVATE_DEBT':
                    try:
                        from dateutil.relativedelta import relativedelta
                        computed_mat = trade_date_val + relativedelta(years=int(tenor_val))
                    except ImportError:
                        computed_mat = trade_date_val + timedelta(days=int(tenor_val * 365))
                else:
                    computed_mat = trade_date_val + timedelta(days=int(tenor_val))
            else:
                computed_mat = None
            if computed_mat:
                maturity_date = computed_mat  # Always use server-computed value

        # ── Server-side total_cost calculation ────────────────────────────────
        # If client didn't auto-fill, compute server-side
        from datetime import date as _today_date
        today = _today_date.today()

        if total_cost == 0.0 and face_val > 0:
            if asset_class in ('GOVT_SECURITIES', 'MONEY_MARKET'):
                # Discount formula: Cost = Face / (1 + rate/100 * tenor_days/basis)
                basis = 364 if asset_class == 'GOVT_SECURITIES' else 365
                tenor_days = tenor_val or (maturity_date - trade_date_val).days if maturity_date and trade_date_val else 0
                if tenor_days > 0 and rate_val > 0:
                    total_cost = face_val / (1 + (rate_val / 100) * tenor_days / basis)
                else:
                    total_cost = face_val
            elif asset_class in ('BONDS', 'EUROBONDS'):
                clean_px = pff('clean_price') or 100.0
                # Accrued interest
                last_cpn = pfd('last_coupon_date') or trade_date_val
                acc_days = (today - last_cpn).days if last_cpn else 0
                cpn_rate = pff('coupon_rate') or 0.0
                accrued = (face_val * (cpn_rate / 100) * acc_days) / 365
                total_cost = (clean_px / 100) * face_val + accrued
            elif asset_class == 'PRIVATE_EQUITY':
                # Cost = called amount
                called = pff('called') or 0.0
                total_cost = called
            elif asset_class == 'PRIVATE_DEBT':
                # Cost = amount drawn
                total_cost = pff('outstanding') or face_val

        # For PE: cost is always the called amount
        if asset_class == 'PRIVATE_EQUITY':
            pe_called = pff('called') or 0.0
            if pe_called > 0:
                total_cost = pe_called

        # ── Cash check ────────────────────────────────────────────────────────
        if total_cost > 0:
            cash = acc.cash_balance
            if cash < total_cost:
                flash(
                    f'Insufficient approved cash. '
                    f'Available: GHS {cash:,.2f} | Required: GHS {total_cost:,.2f}. '
                    f'Please approve a deposit first.',
                    'error'
                )
                return redirect(request.url)

        # ── Auto-fill outstanding for private debt ────────────────────────────
        outstanding_val = pff('outstanding') or total_cost or 0.0

        inv = Investment(
            account_number=acc_no, asset_class=asset_class,
            sub_type=pfs('sub_type'),
            issuer=pfs('issuer'),
            security_name=pfs('security_name'),
            symbol=pfs('symbol'),
            isin=pfs('isin'),
            exchange=pfs('exchange'),
            sector=pfs('sector'),
            trade_date=trade_date_val,
            issue_date=pfd('issue_date'),
            maturity_date=maturity_date,
            tenor=tenor_val,
            quantity=pff('quantity'),
            face_value=pff('face_value'),
            coupon_rate=pff('coupon_rate'),
            coupon_freq=pfi('coupon_freq') or 2,
            interest_rate=pff('interest_rate'),
            clean_price=pff('clean_price'),
            unit_cost=pff('unit_cost'),
            total_cost=total_cost,
            currency=request.form.get('currency', 'GHS'),
            current_price=pff('current_price'),
            last_coupon_date=pfd('last_coupon_date'),
            vintage_year=pfi('vintage_year'),
            geography=pfs('geography'),
            stage=pfs('stage'),
            committed=pff('committed'),
            called=pff('called'),
            distributions=pff('distributions'),
            moic=pff('moic'),
            irr=pff('irr'),
            nav=pff('nav'),
            outstanding=outstanding_val,
            rating=pfs('rating'),
            pik=pfb('pik'),
            country_of_issue=pfs('country_of_issue'),
            notes=pfs('notes'),
            status='APPROVED' if current_user.is_super_admin else 'PENDING',
            created_by=current_user.id,
            approved_by=current_user.id if current_user.is_super_admin else None,
            approved_at=datetime.utcnow() if current_user.is_super_admin else None,
        )
        db.session.add(inv)
        db.session.flush()
        if total_cost > 0:
            # For super admin: immediately approved. For others: PENDING (maker-checker).
            is_sa = current_user.is_super_admin
            from utils.market_data import get_fx_rate
            currency = inv.currency or 'GHS'
            rate     = get_fx_rate(currency, 'GHS') if currency != 'GHS' else 1.0
            buy_txn  = Transaction(
                account_number = acc_no,
                txn_date       = inv.trade_date or date.today(),
                txn_type       = 'BUY',
                description    = f'Purchase: {inv.security_name or asset_class}',
                amount         = total_cost,
                amount_ghs     = round(total_cost * rate, 4) if is_sa else None,
                fx_rate_used   = rate,
                currency       = currency,
                investment_id  = inv.id,
                status         = 'APPROVED' if is_sa else 'PENDING',
                approved_by    = current_user.id if is_sa else None,
                approved_at    = datetime.utcnow() if is_sa else None,
                created_by     = current_user.id)
            db.session.add(buy_txn)
        db.session.commit()
        from utils.notifications import audit as _audit
        _audit('INV_ENTRY', target=acc_no, detail=f'{asset_class} cost={total_cost} status={inv.status}')
        flash('Investment recorded.' + (
            ' Awaiting approver sign-off.' if not current_user.is_super_admin else ' Approved immediately.'
        ), 'success')
        return redirect(url_for('admin.view_account', acc_id=acc.id))
    return render_template('admin/investment_form.html', accounts=accounts, investment=None)

@admin_bp.route('/investments/<int:inv_id>/approve', methods=['POST'])
@permission_required('approve_investment')
def approve_investment(inv_id):
    """
    Approve an investment.
    If the linked BUY transaction is PENDING, approve it first (checking cash).
    The cash deduction only occurs when the BUY transaction is approved.
    """
    inv = Investment.query.get_or_404(inv_id)
    acc = ClientAccount.query.filter_by(account_number=inv.account_number).first()

    # ── Maker-checker ─────────────────────────────────────────────────
    if not current_user.is_super_admin and inv.created_by == current_user.id:
        flash('Maker-checker violation: you cannot approve an investment you entered. '
              'Another authorised staff member must approve it.', 'error')
        return redirect(request.referrer or url_for('admin.investments'))
    # ─────────────────────────────────────────────────────────────────

    # Find linked BUY transaction
    buy_txn = Transaction.query.filter_by(
        investment_id=inv.id, txn_type='BUY').first()

    if buy_txn and buy_txn.status == 'PENDING':
        # Check cash is sufficient before approving
        from utils.market_data import get_fx_rate
        rate = get_fx_rate(buy_txn.currency, 'GHS') if buy_txn.currency != 'GHS' else 1.0
        needed_ghs = buy_txn.amount * rate
        if acc and acc.cash_balance < needed_ghs:
            flash(
                f'Insufficient approved cash to fund this investment. '
                f'Available: GHS {acc.cash_balance:,.2f} | '
                f'Required: GHS {needed_ghs:,.2f}. '
                f'Approve a deposit first.',
                'error'
            )
            return redirect(request.referrer or url_for('admin.investments'))
        _approve_transaction(buy_txn, current_user.id)

    inv.status      = 'APPROVED'
    inv.approved_by = current_user.id
    inv.approved_at = datetime.utcnow()
    db.session.commit()
    from utils.notifications import audit as _audit
    _audit('INV_APPROVED', target=inv.account_number, detail=f'id={inv.id} {inv.asset_class}')
    flash('Investment approved and cash balance updated.', 'success')
    return redirect(request.referrer or url_for('admin.investments'))

@admin_bp.route('/investments/<int:inv_id>/edit', methods=['GET', 'POST'])
@permission_required('enter_investment')
def edit_investment(inv_id):
    inv = Investment.query.get_or_404(inv_id)
    accounts = ClientAccount.query.filter_by(status='APPROVED').all()
    if request.method == 'POST':
        asset_class = request.form.get('asset_class', inv.asset_class or '').upper()

        # Use same prefix system as new_investment
        PREFIX_MAP = {
            'MONEY_MARKET':'mm','GOVT_SECURITIES':'gs','BONDS':'bond',
            'EUROBONDS':'euro','GSE_EQUITIES':'gse','GLOBAL_EQUITIES':'gl',
            'PRIVATE_EQUITY':'pe','PRIVATE_DEBT':'pd','MUTUAL_FUNDS':'mf',
        }
        def pf(field, fallback=''):
            pfx = PREFIX_MAP.get(asset_class, '')
            val = request.form.get(f'{pfx}_{field}') if pfx else None
            if val is None or val == '':
                val = request.form.get(field, fallback)
            return val
        def pff(f): return _float(pf(f))
        def pfi(f): return _int(pf(f))
        def pfs(f): return pf(f) or None
        def pfd(f): return _parse_date(pf(f))

        # Maturity date: auto-calculate from tenor if not provided
        maturity_date = pfd('maturity_date')
        trade_date_val = pfd('trade_date')
        tenor_val = pfi('tenor')
        if not maturity_date and trade_date_val and tenor_val:
            if asset_class in ('BONDS','EUROBONDS','PRIVATE_DEBT'):
                try:
                    from dateutil.relativedelta import relativedelta
                    maturity_date = trade_date_val + relativedelta(years=tenor_val)
                except ImportError:
                    from datetime import timedelta
                    maturity_date = trade_date_val + timedelta(days=tenor_val * 365)
            elif asset_class in ('GOVT_SECURITIES','MONEY_MARKET'):
                from datetime import timedelta
                maturity_date = trade_date_val + timedelta(days=tenor_val)

        for f in ['sub_type','issuer','security_name','symbol','isin','exchange',
                  'sector','currency','notes','geography','stage','rating','country_of_issue']:
            setattr(inv, f, pfs(f))
        for f in ['quantity','face_value','coupon_rate','interest_rate','clean_price',
                  'unit_cost','total_cost','current_price','committed','called',
                  'distributions','moic','irr','nav','outstanding']:
            val = pff(f)
            if val is not None:
                setattr(inv, f, val)
        for f in ['tenor','coupon_freq','vintage_year']:
            val = pfi(f)
            if val is not None:
                setattr(inv, f, val)
        inv.trade_date = trade_date_val
        inv.issue_date = pfd('issue_date')
        inv.maturity_date = maturity_date
        inv.last_coupon_date = pfd('last_coupon_date')
        if pf('pik'):
            inv.pik = bool(pf('pik'))

        db.session.commit()
        flash('Investment updated.', 'success')
        return redirect(url_for('admin.view_account', acc_id=inv.account.id))
    return render_template('admin/investment_form.html', accounts=accounts, investment=inv)



@admin_bp.route('/investments/<int:inv_id>/sell', methods=['GET', 'POST'])
@permission_required('enter_investment')
def sell_investment(inv_id):
    """
    Record a sale/redemption/disinvestment for an approved investment.
    Creates a PENDING SELL transaction that, when approved:
      - Adds the proceeds to cash
      - Marks the investment as SOLD
    """
    inv = Investment.query.get_or_404(inv_id)
    acc = ClientAccount.query.filter_by(account_number=inv.account_number).first_or_404()

    if inv.status != 'APPROVED':
        flash('Only approved investments can be sold.', 'error')
        return redirect(url_for('admin.view_account', acc_id=acc.id))

    if request.method == 'POST':
        sell_date    = _parse_date(request.form.get('sell_date')) or date.today()
        currency     = request.form.get('currency', inv.currency or 'GHS')
        sell_amount  = _float(request.form.get('sell_amount')) or 0   # proceeds in currency
        sell_qty     = _float(request.form.get('sell_qty'))            # shares/units sold (equities/MF)
        sell_face    = _float(request.form.get('sell_face'))           # face value redeemed (bonds/GS)
        description  = request.form.get('description','').strip() or f'Sale: {inv.security_name or inv.asset_class}'
        reference    = request.form.get('reference','').strip() or f'SELL-{inv.id:06d}'
        partial      = request.form.get('partial') == '1'

        if sell_amount <= 0:
            flash('Sale proceeds must be greater than zero.', 'error')
            return redirect(request.url)

        from utils.market_data import get_fx_rate
        rate  = get_fx_rate(currency, 'GHS') if currency != 'GHS' else 1.0
        is_sa = current_user.is_super_admin

        # Determine if this is a full or partial sell
        is_partial = False
        remaining_qty = None
        remaining_face = None

        if inv.asset_class in ('GSE_EQUITIES','GLOBAL_EQUITIES','MUTUAL_FUNDS') and sell_qty and inv.quantity:
            if sell_qty < inv.quantity:
                is_partial = True
                remaining_qty = inv.quantity - sell_qty

        if inv.asset_class in ('GOVT_SECURITIES','BONDS','EUROBONDS','MONEY_MARKET') and sell_face and inv.face_value:
            if sell_face < inv.face_value:
                is_partial = True
                remaining_face = inv.face_value - sell_face

        # Description with quantity detail
        if sell_qty:
            description += f' — {sell_qty:,.4f} units @ {currency} {(sell_amount/sell_qty):.4f}'
        elif sell_face:
            description += f' — Face {sell_face:,.2f} {currency}'

        sell_txn = Transaction(
            account_number = inv.account_number,
            txn_date       = sell_date,
            txn_type       = 'SELL',
            description    = description,
            amount         = sell_amount,
            amount_ghs     = round(sell_amount * rate, 4) if is_sa else None,
            fx_rate_used   = rate,
            currency       = currency,
            reference      = reference,
            investment_id  = inv.id,
            status         = 'APPROVED' if is_sa else 'PENDING',
            approved_by    = current_user.id if is_sa else None,
            approved_at    = datetime.utcnow() if is_sa else None,
            created_by     = current_user.id,
        )
        db.session.add(sell_txn)

        if is_sa:
            if is_partial:
                # Partial sell: reduce quantity/face value
                if remaining_qty is not None:
                    inv.quantity   = remaining_qty
                    inv.total_cost = remaining_qty * (inv.unit_cost or 0)
                    inv.notes = (inv.notes or '') + f' | Partial sale {sell_date}: {sell_qty:,.4f} units @ {sell_amount:,.2f} {currency}'
                elif remaining_face is not None:
                    inv.face_value = remaining_face
                    inv.total_cost = remaining_face  # approx
                    inv.notes = (inv.notes or '') + f' | Partial redemption {sell_date}: Face {sell_face:,.2f} → {remaining_face:,.2f}'
            else:
                # Full sell
                inv.status = 'SOLD'
                inv.notes  = (inv.notes or '') + f' | Full sale {sell_date} @ {currency} {sell_amount:,.2f}'

        db.session.commit()

        from utils.notifications import audit as _audit
        _audit('INV_SELL', target=inv.account_number,
               detail=f'inv={inv.id} {inv.asset_class} {currency} {sell_amount:,.2f} partial={is_partial}')

        if is_partial:
            flash_msg = (f'Partial sale recorded: {sell_qty or sell_face:,.4f} units. '
                         f'Remaining holding updated. '
                         + ('Cash updated.' if is_sa else 'Awaiting approval.'))
        else:
            flash_msg = (f'Full sale of {inv.security_name or inv.asset_class} recorded. '
                         + ('Proceeds added to cash.' if is_sa else 'Awaiting approval.'))
        flash(flash_msg, 'success')
        return redirect(url_for('admin.view_account', acc_id=acc.id))

    return render_template('admin/sell_investment.html', inv=inv, acc=acc, today=date.today())

@admin_bp.route('/transactions')
@admin_required
def transactions():
    q      = request.args.get('q', '')
    status = request.args.get('status', '')
    query  = Transaction.query
    if q:
        query = query.filter(Transaction.account_number.ilike(f'%{q}%'))
    if status:
        query = query.filter_by(status=status)
    all_txns     = query.order_by(Transaction.txn_date.desc()).limit(500).all()
    pending_count = Transaction.query.filter_by(status='PENDING').count()
    return render_template('admin/transactions.html',
        transactions=all_txns, q=q, status=status, pending_count=pending_count)

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
        # ── Date rule: only Super Admin can backdate ───────────────────
        txn_date_val = _parse_date(request.form.get('txn_date')) or date.today()
        if txn_date_val != date.today() and not current_user.is_super_admin:
            flash('Only the Super Admin can backdate transactions. Use today\'s date.', 'error')
            return redirect(request.url)
        # ──────────────────────────────────────────────────────────────
        currency = request.form.get('currency', 'GHS')
        from utils.market_data import get_fx_rate
        fx_rate  = get_fx_rate(currency, 'GHS') if currency != 'GHS' else 1.0
        amount_ghs = round(amount * fx_rate, 4)
        # Immediate approval for SUPER_ADMIN; others go PENDING
        is_immediate = current_user.is_super_admin
        txn = Transaction(
            account_number=acc_no,
            txn_date=txn_date_val,
            txn_type=txn_type,
            description=request.form.get('description'),
            amount=amount,
            amount_ghs=amount_ghs if is_immediate else None,
            fx_rate_used=fx_rate,
            currency=currency,
            reference=request.form.get('reference'),
            status='APPROVED' if is_immediate else 'PENDING',
            approved_by=current_user.id if is_immediate else None,
            approved_at=datetime.utcnow() if is_immediate else None,
            created_by=current_user.id)
        db.session.add(txn)
        db.session.commit()
        from utils.notifications import audit as _audit
        _audit('TXN_ENTRY', target=acc_no, detail=f'{txn_type} {amount} {currency} status={txn.status}')
        if is_immediate:
            flash(f'Transaction recorded and approved. Cash balance updated.', 'success')
        else:
            flash(f'Transaction recorded as PENDING — awaiting approval by an authorised approver.', 'success')
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
        role     = request.form.get('role')
        password = request.form.get('password', '')
        if role == 'SUPER_ADMIN' and not current_user.is_super_admin:
            flash('Only Super Admin can create other Super Admins.', 'error')
            return redirect(request.url)
        # ── Strong password enforcement ────────────────────────────────
        import re as _re
        pw_errors = []
        if len(password) < 10:
            pw_errors.append('at least 10 characters')
        if not _re.search(r'[A-Z]', password):
            pw_errors.append('one uppercase letter')
        if not _re.search(r'[a-z]', password):
            pw_errors.append('one lowercase letter')
        if not _re.search(r'\d', password):
            pw_errors.append('one number')
        if not _re.search(r'[!@#$%^&*(),.?":{}|<>_\-]', password):
            pw_errors.append('one special character (!@#$%^&*...)')
        if pw_errors:
            flash(f'Password too weak — must contain: {", ".join(pw_errors)}.', 'error')
            return redirect(request.url)
        # ──────────────────────────────────────────────────────────────
        last = AdminUser.query.order_by(AdminUser.id.desc()).first()
        staff_id = f'SA{(last.id+1 if last else 1):03d}'
        u = AdminUser(staff_id=staff_id, full_name=request.form.get('full_name'),
                      email=request.form.get('email'), role=role, created_by=current_user.id,
                      is_rm=bool(request.form.get('is_rm')),
                      rm_commission_rate=float(request.form.get('rm_commission_rate') or 1.0))
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        _audit('STAFF_CREATE', target=f'staff:{staff_id}', detail=f'role={role}')
        flash(f'Staff {staff_id} created.', 'success')
        return redirect(url_for('admin.admin_users'))
    return render_template('admin/admin_user_form.html', roles=ADMIN_ROLES, user=None)


@admin_bp.route('/accounts/<int:acc_id>/assign-rm', methods=['POST'])
@permission_required('approve_account')
def assign_rm(acc_id):
    acc = ClientAccount.query.get_or_404(acc_id)
    rm_id = _int(request.form.get('relationship_manager_id')) or None
    acc.relationship_manager_id = rm_id
    db.session.commit()
    rm = AdminUser.query.get(rm_id) if rm_id else None
    _audit('RM_ASSIGN', target=acc.account_number,
           detail=f'rm={"None" if not rm else rm.full_name}')
    flash(f'RM {"removed" if not rm else f"assigned: {rm.full_name}"}.', 'success')
    return redirect(url_for('admin.view_account', acc_id=acc.id))

@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@permission_required('manage_all')
def toggle_admin_user(user_id):
    if not current_user.is_super_admin:
        flash('Only the Super Admin can activate or deactivate staff accounts.', 'error')
        return redirect(url_for('admin.admin_users'))
    u = AdminUser.query.get_or_404(user_id)
    if u.id == current_user.id:
        flash('You cannot deactivate your own account.', 'error')
        return redirect(url_for('admin.admin_users'))
    u.is_active = not u.is_active
    db.session.commit()
    _audit('STAFF_TOGGLE', target=f'staff:{u.staff_id}',
           detail=f'{"activated" if u.is_active else "deactivated"} by {current_user.staff_id}')
    flash(f'Staff account {"activated" if u.is_active else "deactivated"}.', 'success')
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


@admin_bp.route('/migration/excel/<category>/<subtype>')
@permission_required('migrate_data')
def migration_excel_template(category, subtype):
    """Comprehensive Excel migration templates matching the Zagadat data model."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from io import BytesIO
    from datetime import datetime as dt

    NAVY   = 'FF0F1B3C'; GOLD   = 'FFC9A84C'; TEAL   = 'FF0E5F73'
    GREEN  = 'FF0F3D20'; PURPLE = 'FF2D1B69'; BROWN  = 'FF4A2000'; RED2 = 'FF4A0000'
    DARK   = 'FF16161F'; SURFACE= 'FF1A1A2E'
    thin   = Side(style='thin', color='FF2A2A3E')
    today  = dt.now().strftime('%d %b %Y')

    # ── SHARED HELPERS ────────────────────────────────────────────────────

    def _hdr_row(ws, title, subtitle, n_cols, color):
        last_col = get_column_letter(n_cols)
        ws.merge_cells(f'A1:{last_col}1')
        ws['A1'] = title
        ws['A1'].font      = Font(name='Calibri', bold=True, size=12, color='FFF5F5F0')
        ws['A1'].fill      = PatternFill('solid', fgColor=color)
        ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 28
        ws.merge_cells(f'A2:{last_col}2')
        ws['A2'] = subtitle
        ws['A2'].font      = Font(name='Calibri', size=8, italic=True, color='FF8A8A9A')
        ws['A2'].fill      = PatternFill('solid', fgColor=SURFACE)
        ws['A2'].alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        ws.row_dimensions[2].height = 22

    def _col_hdr(ws, cols):
        """Write column headers in row 3. cols = list of (label, width)."""
        for i, (lbl, w) in enumerate(cols):
            c = ws.cell(3, i+1, lbl)
            c.font = Font(name='Calibri', bold=True, size=9, color='FFF5F5F0')
            c.fill = PatternFill('solid', fgColor=TEAL)
            c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            ws.column_dimensions[get_column_letter(i+1)].width = w
        ws.row_dimensions[3].height = 30

    def _data_rows(ws, n_cols, start=4, n_rows=50):
        for r in range(start, start+n_rows):
            for c in range(1, n_cols+1):
                cell = ws.cell(r, c)
                cell.fill   = PatternFill('solid', fgColor=DARK if r%2==0 else SURFACE)
                cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
                cell.font   = Font(name='Calibri', size=9, color='FFF5F5F0')
                cell.alignment = Alignment(vertical='center')
            ws.row_dimensions[r].height = 16

    def _note(ws, row, text, n_cols):
        ws.merge_cells(f'A{row}:{get_column_letter(n_cols)}{row}')
        ws.cell(row, 1, text).font = Font(name='Calibri', size=8, italic=True, color='FF8A8A9A')
        ws.cell(row, 1).fill = PatternFill('solid', fgColor=SURFACE)
        ws.row_dimensions[row].height = 16

    # ── ACCOUNT KYC SHEETS ────────────────────────────────────────────────

    def _build_main_account_sheet(wb, label, color, extra_cols=None):
        """Sheet 1: Main ClientAccount fields."""
        ws = wb.create_sheet(f'{label} — Main')
        base_cols = [
            ('account_number',16),('full_name',28),('date_of_birth',14),
            ('gender',10),('marital_status',14),('nationality',14),
            ('country_of_origin',16),('country_of_residence',16),
            ('residential_status',16),('place_of_birth',18),
            ('digital_address',16),('tin',16),
            ('phone',14),('phone2',14),('email',24),
            ('address',28),('city',14),('country',14),('postal_address',18),
            ('id_type',18),('id_number',18),('id_issue_date',14),
            ('id_expiry_date',14),('id_place_of_issue',18),
            ('permit_number',16),('permit_issue_date',14),('permit_expiry_date',14),
            ('occupation',18),('employer',22),('employer_address',22),
            ('employer_city',14),('nature_of_business',20),
            ('employment_status',16),('years_employed',12),
            ('office_phone',14),('office_email',22),
            ('annual_income_range',18),('source_of_funds',22),
            ('anticipated_investment',20),('topup_frequency',16),
            ('withdrawal_frequency',16),('regular_topup_amount',18),
            ('regular_withdrawal_amount',20),
            ('bank_name',20),('bank_branch',18),('bank_account_name',22),
            ('bank_account_number',18),
            ('account_type',18),('mandate',16),('regulatory_body',18),
            ('fund_type',14),('investment_objective',22),
            ('risk_profile',14),('investment_horizon',18),
            ('investment_knowledge',18),('portfolio_preference',22),
            ('other_investments',22),('base_currency',12),
            ('custodian',18),('csd_number',14),
            ('statement_mode',14),('statement_frequency',16),
            ('category_of_investment',22),('client_first_contact',18),
            ('is_pep',10),('pep_details',22),
            ('is_foreign_citizen',16),('foreign_country',16),
            ('foreign_tin',16),('dividend_reinvest',16),
            ('management_fee_rate',18),
            ('beneficiary1_name',24),('beneficiary1_pct',14),
            ('beneficiary1_relation',18),('beneficiary1_dob',14),
            ('beneficiary2_name',24),('beneficiary2_pct',14),
            ('beneficiary2_relation',18),('beneficiary2_dob',14),
            ('nominee_name',22),('nominee_phone',14),('nominee_relation',16),
            ('spouse_name',22),('spouse_phone',14),('spouse_email',22),
            ('emergency_contact_name',24),('emergency_contact_relation',16),
            ('emergency_contact_phone',16),
            ('status',12),
        ]
        cols = base_cols + (extra_cols or [])
        _hdr_row(ws, f'CLIENT ACCOUNT — {label.upper()} — MIGRATION TEMPLATE',
                 f'[REQUIRED] * Mandatory fields.  account_type value: "{label}"  |  Migration Date: {today}  |  All dates: YYYY-MM-DD',
                 len(cols), color)
        _col_hdr(ws, cols)
        _data_rows(ws, len(cols))
        _note(ws, 54, 'account_type options: Individual | Individual ITF | Joint | Corporate | Pension Fund | NGO  |  '
                      'gender: Male/Female  |  marital_status: Single/Married/Divorced/Widowed  |  '
                      'risk_profile: Conservative/Moderate/Aggressive  |  '
                      'investment_horizon: Short-term/Medium-term/Long-term  |  '
                      'is_pep / is_foreign_citizen / dividend_reinvest: TRUE / FALSE  |  '
                      'statement_mode: Email/Post/Both  |  statement_frequency: Monthly/Quarterly/Annually', len(cols))
        return ws

    def _build_itf_sheet(wb):
        ws = wb.create_sheet('ITF Beneficiary Details')
        cols = [
            ('account_number',18),('itf_name',28),('itf_relationship',20),
            ('itf_dob',14),('itf_gender',10),('itf_id_type',18),('itf_id_number',18),
            ('itf_guardian_name',24),('release_conditions',32),
        ]
        _hdr_row(ws,'IN TRUST FOR (ITF) — BENEFICIARY DETAILS',
                 f'Person for whom the account is held  |  Link to main sheet via account_number  |  {today}',
                 len(cols),PURPLE)
        _col_hdr(ws,cols); _data_rows(ws,len(cols))
        _note(ws,54,'itf_relationship: Parent/Guardian/Spouse/Other  |  itf_gender: Male/Female  |  '
                    'release_conditions: e.g. On reaching age 18 / On marriage / Unconditional',len(cols))
        return ws

    def _build_joint_holders_sheet(wb):
        ws = wb.create_sheet('Joint Holders')
        cols = [
            ('account_number',18),('holder_sequence',12),
            ('full_name',28),('date_of_birth',14),('nationality',14),
            ('phone',14),('email',22),('address',28),
            ('id_type',18),('id_number',18),('id_expiry_date',14),
            ('occupation',18),('signing_mandate',18),
        ]
        _hdr_row(ws,'JOINT ACCOUNT — ADDITIONAL HOLDER DETAILS',
                 f'One row per additional holder  |  holder_sequence: 2, 3…  |  {today}',
                 len(cols),TEAL)
        _col_hdr(ws,cols); _data_rows(ws,len(cols))
        _note(ws,54,'signing_mandate per row: Either to Sign / Both to Sign / Primary Only',len(cols))
        return ws

    def _build_corporate_sheet(wb):
        ws = wb.create_sheet('Corporate Details')
        cols = [
            ('account_number',18),('company_name',28),
            ('registration_number',20),('date_of_incorporation',18),
            ('country_of_incorporation',20),('registered_address',32),
            ('business_address',32),('nature_of_business',28),
            ('website',22),('contact_person_name',24),
            ('contact_person_title',18),('contact_person_phone',16),
            ('contact_person_email',24),
            ('authorized_signatory1',26),('authorized_signatory2',26),
        ]
        _hdr_row(ws,'CORPORATE ENTITY — SUPPLEMENTARY DETAILS',
                 f'Link via account_number to main account sheet  |  {today}',
                 len(cols),GREEN)
        _col_hdr(ws,cols); _data_rows(ws,len(cols))
        return ws

    def _build_directors_sheet(wb):
        ws = wb.create_sheet('Directors & Beneficial Owners')
        cols = [
            ('account_number',18),('role',20),('full_name',28),
            ('nationality',14),('date_of_birth',14),
            ('id_type',18),('id_number',18),
            ('ownership_pct',14),('is_pep',10),
        ]
        _hdr_row(ws,'DIRECTORS & BENEFICIAL OWNERS (≥ 10%)',
                 f'List ALL directors + persons with ≥10% ownership  |  One row per person  |  {today}',
                 len(cols),DARK)
        _col_hdr(ws,cols); _data_rows(ws,len(cols))
        _note(ws,54,'role: Director / Chairman / CEO / Beneficial Owner / Authorized Signatory  |  is_pep: TRUE/FALSE',len(cols))
        return ws

    # ── INVESTMENT SHEETS ─────────────────────────────────────────────────

    COMMON_INV = [
        ('account_number',16),('asset_class',20),('sub_type',18),
        ('issuer',22),('security_name',28),('symbol',12),('isin',18),
        ('exchange',14),('sector',18),('currency',10),
        ('trade_date',14),('issue_date',14),('maturity_date',14),
        ('tenor',10),('total_cost',16),('notes',24),
    ]

    def _inv_sheet(wb, title, subtitle, extra_cols, color, asset_cls_hint):
        cols = COMMON_INV + extra_cols
        safe_title = title.replace('/', '-').replace('\\', '-')[:31]
        ws = wb.create_sheet(safe_title)
        _hdr_row(ws, f'{title.upper()} — MIGRATION TEMPLATE',
                 f'{subtitle}  |  asset_class value: {asset_cls_hint}  |  {today}', len(cols), color)
        _col_hdr(ws, cols)
        _data_rows(ws, len(cols))
        return ws

    # ── PORTFOLIO SUMMARY SHEET ───────────────────────────────────────────

    def _portfolio_summary(wb):
        ws = wb.create_sheet('Portfolio Summary')
        ws.move_to_end = False
        ws.sheet_properties.tabColor = 'FFC9A84C'
        cols = [
            ('account_number',18),('asset_class',22),('security_name',28),
            ('total_cost',16),('current_value',16),
            ('unrealized_gl',18),('pct_of_portfolio',16),('currency',10),
        ]
        _hdr_row(ws,'PORTFOLIO MIGRATION SUMMARY — OVERVIEW',
                 f'Auto-populated reference. Complete the individual asset class sheets below.  |  {today}',
                 len(cols),NAVY)
        _col_hdr(ws,cols)
        r=4
        for cls in ['GOVT_SECURITIES','BONDS','EUROBONDS','GSE_EQUITIES',
                    'GLOBAL_EQUITIES','MONEY_MARKET','MUTUAL_FUNDS','PRIVATE_EQUITY','PRIVATE_DEBT']:
            c=ws.cell(r,2,cls)
            c.font=Font(name='Calibri',size=9,color='FFF5F5F0')
            c.fill=PatternFill('solid',fgColor=SURFACE if r%2==0 else DARK)
            for col in range(1,len(cols)+1):
                ws.cell(r,col).fill=PatternFill('solid',fgColor=SURFACE if r%2==0 else DARK)
                ws.cell(r,col).border=Border(left=thin,right=thin,top=thin,bottom=thin)
                ws.cell(r,col).font=Font(name='Calibri',size=9,color='FFF5F5F0')
            ws.row_dimensions[r].height=16; r+=1
        return ws

    # ── TRANSACTION SHEET ─────────────────────────────────────────────────

    def _txn_sheet(wb):
        cols = [
            ('account_number',18),('txn_date',14),('txn_type',18),
            ('description',32),('amount',14),('currency',10),
            ('reference',20),('investment_id',16),
        ]
        ws = wb.create_sheet('Transactions')
        _hdr_row(ws,'TRANSACTION HISTORY — MIGRATION TEMPLATE',
                 f'txn_type: DEPOSIT / WITHDRAWAL / BUY / SELL / DIVIDEND / COUPON / FEE / TRANSFER_IN / TRANSFER_OUT  |  Dates: YYYY-MM-DD  |  {today}',
                 len(cols),DARK)
        _col_hdr(ws,cols); _data_rows(ws,len(cols))
        _note(ws,54,'amount: always positive (system uses txn_type to determine direction)  |  '
                    'investment_id: optional, links transaction to an investment record  |  '
                    'status defaults to APPROVED on import',len(cols))
        return ws

    # ── BUILD WORKBOOKS ────────────────────────────────────────────────────

    wb = openpyxl.Workbook(); wb.remove(wb.active)

    if category == 'account':
        if subtype == 'individual':
            _build_main_account_sheet(wb,'Individual',NAVY)
            fname='KYC_Individual'
        elif subtype == 'individual_itf':
            _build_main_account_sheet(wb,'Individual ITF',PURPLE)
            _build_itf_sheet(wb)
            fname='KYC_Individual_ITF'
        elif subtype == 'joint':
            _build_main_account_sheet(wb,'Joint',TEAL)
            _build_joint_holders_sheet(wb)
            fname='KYC_Joint'
        elif subtype == 'corporate':
            _build_main_account_sheet(wb,'Corporate',GREEN)
            _build_corporate_sheet(wb)
            _build_directors_sheet(wb)
            fname='KYC_Corporate'
        elif subtype == 'pension':
            _build_main_account_sheet(wb,'Pension Fund',BROWN,
                extra_cols=[('npra_reg_number',22),('trust_deed_reference',22),
                            ('fund_administrator',24),('fund_custodian',24),
                            ('principal_sponsor',24),('num_members',14)])
            fname='KYC_PensionFund'
        elif subtype == 'ngo':
            _build_main_account_sheet(wb,'NGO',RED2,
                extra_cols=[('registration_body',22),('date_of_registration',18),
                            ('executive_chairman',24),('secretary',24),('treasurer',24)])
            fname='KYC_NGO_Association'
        else:
            return 'Unknown account subtype', 404

    elif category == 'portfolio':
        if subtype == 'full':
            _portfolio_summary(wb)
            _inv_sheet(wb,'Govt Securities','T-Bills, Govt bonds, notes',
                       [('face_value',16),('interest_rate',16),('tenor',10),
                        ('mkt_value_htm',18),('mkt_value_mtm',18)],NAVY,'GOVT_SECURITIES')
            _inv_sheet(wb,'Bonds (Corporate)','Corporate bonds, debentures, notes',
                       [('face_value',16),('coupon_rate',14),('coupon_freq',12),
                        ('clean_price',14),('mkt_value_mtm',18),
                        ('last_coupon_date',16),('rating',12)],GREEN,'BONDS')
            _inv_sheet(wb,'Eurobonds','USD/EUR international bonds',
                       [('face_value',16),('coupon_rate',14),('coupon_freq',12),
                        ('clean_price',14),('mkt_value_mtm',18),
                        ('country_of_issue',18),('rating',12)],TEAL,'EUROBONDS')
            _inv_sheet(wb,'GSE Equities','Ghana Stock Exchange listed shares',
                       [('quantity',14),('unit_cost',14),('current_price',14),
                        ('csd_number',16)],PURPLE,'GSE_EQUITIES')
            _inv_sheet(wb,'Global Equities','NYSE, LSE & other exchanges',
                       [('quantity',14),('unit_cost',14),('current_price',14)],BROWN,'GLOBAL_EQUITIES')
            _inv_sheet(wb,'Money Market','Deposits, call accounts, commercial paper',
                       [('face_value',16),('interest_rate',16),('tenor',10)],RED2,'MONEY_MARKET')
            _inv_sheet(wb,'Mutual Funds - CIS','Unit trusts, mutual funds, ETFs',
                       [('quantity',14),('unit_cost',14),('current_price',14),
                        ('nav',14)],DARK,'MUTUAL_FUNDS')
            _inv_sheet(wb,'Private Equity','PE funds, direct investments',
                       [('vintage_year',12),('geography',14),('stage',14),
                        ('committed',14),('called',14),('distributions',14),
                        ('moic',10),('irr',10),('nav',14)],GREEN,'PRIVATE_EQUITY')
            _inv_sheet(wb,'Private Debt','Direct lending, mezzanine, distressed',
                       [('face_value',16),('coupon_rate',14),('outstanding',16),
                        ('pik',8),('rating',12)],BROWN,'PRIVATE_DEBT')
            fname='Portfolio_Full_Master'
        elif subtype == 'GOVT_SECURITIES':
            _inv_sheet(wb,'Govt Securities','',
                       [('face_value',16),('interest_rate',16),('tenor',10),
                        ('mkt_value_htm',18),('mkt_value_mtm',18)],NAVY,'GOVT_SECURITIES')
            fname='Portfolio_GovtSecurities'
        elif subtype == 'BONDS':
            _inv_sheet(wb,'Bonds (Corporate)','',
                       [('face_value',16),('coupon_rate',14),('coupon_freq',12),
                        ('clean_price',14),('mkt_value_mtm',18),
                        ('last_coupon_date',16),('rating',12)],GREEN,'BONDS')
            fname='Portfolio_Bonds'
        elif subtype == 'EUROBONDS':
            _inv_sheet(wb,'Eurobonds','',
                       [('face_value',16),('coupon_rate',14),('coupon_freq',12),
                        ('clean_price',14),('mkt_value_mtm',18),
                        ('country_of_issue',18),('rating',12)],TEAL,'EUROBONDS')
            fname='Portfolio_Eurobonds'
        elif subtype == 'GSE_EQUITIES':
            _inv_sheet(wb,'GSE Equities','',
                       [('quantity',14),('unit_cost',14),('current_price',14),
                        ('csd_number',16)],PURPLE,'GSE_EQUITIES')
            fname='Portfolio_GSE_Equities'
        elif subtype == 'GLOBAL_EQUITIES':
            _inv_sheet(wb,'Global Equities','',
                       [('quantity',14),('unit_cost',14),('current_price',14)],BROWN,'GLOBAL_EQUITIES')
            fname='Portfolio_Global_Equities'
        elif subtype == 'MONEY_MARKET':
            _inv_sheet(wb,'Money Market','',
                       [('face_value',16),('interest_rate',16),('tenor',10)],RED2,'MONEY_MARKET')
            fname='Portfolio_MoneyMarket'
        elif subtype == 'MUTUAL_FUNDS':
            _inv_sheet(wb,'Mutual Funds - CIS','',
                       [('quantity',14),('unit_cost',14),('current_price',14),
                        ('nav',14)],DARK,'MUTUAL_FUNDS')
            fname='Portfolio_MutualFunds'
        elif subtype == 'PRIVATE_EQUITY':
            _inv_sheet(wb,'Private Equity','',
                       [('vintage_year',12),('geography',14),('stage',14),
                        ('committed',14),('called',14),('distributions',14),
                        ('moic',10),('irr',10),('nav',14)],GREEN,'PRIVATE_EQUITY')
            fname='Portfolio_PrivateEquity'
        elif subtype == 'PRIVATE_DEBT':
            _inv_sheet(wb,'Private Debt','',
                       [('face_value',16),('coupon_rate',14),('outstanding',16),
                        ('pik',8),('rating',12)],BROWN,'PRIVATE_DEBT')
            fname='Portfolio_PrivateDebt'
        else:
            return 'Unknown portfolio subtype', 404

    elif category == 'transactions':
        _txn_sheet(wb)
        fname = 'Transactions'
    else:
        return 'Unknown category', 404

    buf = BytesIO(); wb.save(buf); buf.seek(0)
    filename = f'Zagadat_Migration_{fname}_{dt.now().strftime("%Y%m%d")}.xlsx'
    return send_file(buf, as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

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

@admin_bp.route('/rm/<int:rm_id>/commission', methods=['POST'])
@permission_required('manage_all')
def edit_rm_commission(rm_id):
    """Update RM commission rate."""
    rm = AdminUser.query.get_or_404(rm_id)
    if not rm.is_rm:
        flash('This staff member is not an RM.', 'error')
        return redirect(url_for('admin.relationship_managers'))
    try:
        new_rate = float(request.form.get('commission_rate', rm.rm_commission_rate))
        if new_rate < 0 or new_rate > 100:
            flash('Commission rate must be between 0 and 100%.', 'error')
        else:
            old_rate = rm.rm_commission_rate
            rm.rm_commission_rate = new_rate
            db.session.commit()
            from utils.notifications import audit as _audit
            _audit('RM_COMMISSION_EDIT', target=rm.staff_id,
                   detail=f'rate changed {old_rate:.4f}% → {new_rate:.4f}%')
            flash(f'Commission rate for {rm.full_name} updated to {new_rate:.4f}%.', 'success')
    except (ValueError, TypeError):
        flash('Invalid commission rate.', 'error')
    return redirect(url_for('admin.relationship_managers'))

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
    """
    Approve or reject a client request.
    When APPROVED:
      DEPOSIT / TOPUP → creates an APPROVED DEPOSIT Transaction (increases cash)
      WITHDRAWAL      → checks cash, creates an APPROVED WITHDRAWAL Transaction (decreases cash)
      INVESTMENT      → creates a PENDING BUY Transaction (admin still needs to enter the investment)
    """
    from models import ClientRequest
    from utils.notifications import email_request_update, audit as _audit
    cr     = ClientRequest.query.get_or_404(req_id)
    action = request.form.get('action', '').upper()   # APPROVED | REJECTED
    note   = request.form.get('note', '')
    acc    = ClientAccount.query.filter_by(account_number=cr.account_number).first()

    if action == 'APPROVED' and acc:
        currency    = cr.currency or 'GHS'
        amount      = cr.amount or 0.0
        from utils.market_data import get_fx_rate
        fx_rate     = get_fx_rate(currency, 'GHS') if currency != 'GHS' else 1.0
        amount_ghs  = round(amount * fx_rate, 4)

        if cr.request_type in ('DEPOSIT', 'TOPUP'):
            # Create APPROVED deposit transaction → cash balance increases immediately
            txn = Transaction(
                account_number = cr.account_number,
                txn_date       = date.today(),
                txn_type       = 'DEPOSIT',
                description    = f'{cr.request_type} approved — {note or cr.description or ""}',
                amount         = amount,
                amount_ghs     = amount_ghs,
                fx_rate_used   = fx_rate,
                currency       = currency,
                reference      = f'REQ-{cr.id:06d}',
                status         = 'APPROVED',
                approved_by    = current_user.id,
                approved_at    = datetime.utcnow(),
                created_by     = current_user.id,
            )
            db.session.add(txn)
            flash_msg = f'Deposit of {currency} {amount:,.2f} (GHS {amount_ghs:,.2f}) approved. Cash balance updated.'

        elif cr.request_type == 'WITHDRAWAL':
            # Check sufficient approved cash before creating withdrawal
            if acc.cash_balance < amount_ghs:
                flash(
                    f'Insufficient cash to process withdrawal. '
                    f'Available: GHS {acc.cash_balance:,.2f} | '
                    f'Requested: GHS {amount_ghs:,.2f} ({amount:,.2f} {currency} @ {fx_rate:.4f})',
                    'error'
                )
                return redirect(url_for('admin.client_requests'))
            txn = Transaction(
                account_number = cr.account_number,
                txn_date       = date.today(),
                txn_type       = 'WITHDRAWAL',
                description    = f'Withdrawal approved — {note or cr.description or ""}',
                amount         = amount,
                amount_ghs     = amount_ghs,
                fx_rate_used   = fx_rate,
                currency       = currency,
                reference      = f'REQ-{cr.id:06d}',
                status         = 'APPROVED',
                approved_by    = current_user.id,
                approved_at    = datetime.utcnow(),
                created_by     = current_user.id,
            )
            db.session.add(txn)
            flash_msg = f'Withdrawal of {currency} {amount:,.2f} approved. Cash balance updated.'

        elif cr.request_type == 'INVESTMENT':
            # Do NOT auto-create investment — just notify admin to enter the investment.
            # A note is added to the request for the admin to proceed.
            flash_msg = (
                f'Investment request approved. Please enter the investment details via '
                f'<a href="{url_for("admin.new_investment")}?acc={cr.account_number}">New Investment</a>.'
            )

        else:
            flash_msg = f'Request approved.'

    else:
        flash_msg = f'Request rejected.'

    cr.status      = action
    cr.admin_note  = note
    cr.reviewed_by = current_user.id
    cr.reviewed_at = datetime.utcnow()
    db.session.commit()
    _audit('REQ_ACTION', target=cr.account_number, detail=f'req={cr.id} {cr.request_type} {action}')
    if acc:
        email_request_update(acc, cr.request_type, action, note)
    flash(flash_msg, 'success')
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

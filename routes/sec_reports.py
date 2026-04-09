"""
routes/sec_reports.py — SEC Regulatory Report Module
Auto-populates from live investment data daily.
"""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, send_file, jsonify)
from flask_login import login_required, current_user
from extensions import db
from models import (SECReport, SECClientTypeRow, SECClientClassRow,
                    SECPortfolioHolding, SECCISInflow, SECCISOutflow,
                    SEC_CLIENT_TYPES, SEC_CLIENT_CLASSIFICATIONS,
                    SEC_PORTFOLIO_SECURITIES, SEC_REGULATORY_BODIES,
                    Investment, ClientAccount, Transaction, FeeTransaction)
from datetime import datetime, date
import io

sec_bp = Blueprint('sec', __name__)


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _flt(v, default=0.0):
    try:
        return float(str(v).replace(',', '')) if v not in (None, '', 'None') else default
    except Exception:
        return default


def _int(v, default=0):
    try:
        return int(str(v).replace(',', '')) if v not in (None, '', 'None') else default
    except Exception:
        return default


def _current_quarter():
    m = date.today().month
    return f'Q{(m - 1) // 3 + 1}'


def _quarter_date_range(year, quarter):
    """Return (start_date, end_date) for a given quarter."""
    q = int(quarter[1])
    start_month = (q - 1) * 3 + 1
    end_month   = q * 3
    import calendar
    last_day = calendar.monthrange(year, end_month)[1]
    return date(year, start_month, 1), date(year, end_month, last_day)


# ── INVESTMENT → SEC SECURITY TYPE MAPPING ────────────────────────────────────

def _map_to_sec_type(inv):
    """Map one Investment to its SEC Portfolio Holdings security type label."""
    ac    = (inv.asset_class  or '').upper()
    st    = (inv.sub_type     or '').upper()
    geo   = (inv.geography    or '').upper()
    exch  = (inv.exchange     or '').upper()
    name  = ((inv.issuer or '') + ' ' + (inv.security_name or '')).upper()

    # ── Money Market ──────────────────────────────────────────────────────────
    if ac == 'MONEY_MARKET':
        if 'CALL' in st:                                return 'Call Investment'
        if any(k in st for k in ('FIXED','FD','DEPOSIT')): return 'Fixed Deposit'
        if any(k in st for k in ('COMMERCIAL','PAPER','CP')): return 'Commercial Paper'
        return 'Bank Balance'

    # ── Government Securities ─────────────────────────────────────────────────
    if ac == 'GOVT_SECURITIES':
        tenor = inv.tenor or 0          # stored in days for GOVT_SECURITIES
        if '91' in st  or tenor <= 91:   return '91 Day Treasury Bills'
        if '182' in st or tenor <= 182:  return '182 Day Treasury Bills'
        return '1-2 Year Notes'         # 364-day bill or longer-dated note

    # ── Bonds & Eurobonds ─────────────────────────────────────────────────────
    if ac in ('BONDS', 'EUROBONDS'):
        if ac == 'EUROBONDS':           return 'GoG Euro Bonds (value in GHS)'
        # Check GoG eurobond stored as BOND
        if any(k in name for k in ('EURO BOND','EUROBOND','GOG','GOVERNMENT OF GHANA')):
            return 'GoG Euro Bonds (value in GHS)'
        is_local   = (not geo) or 'LOCAL' in geo or exch in ('GSE','GH','GHA','')
        is_foreign = 'FOREIGN' in geo or (exch and exch not in ('GSE','GH','GHA',''))
        is_listed  = bool(inv.exchange)
        if is_foreign:
            return 'Foreign Listed Corporate Bonds' if is_listed else 'Foreign Unlisted Corporate Bonds'
        # Default: local
        if is_listed: return 'Local Listed Corporate Bonds'
        # Tenor-based classification for local unlisted
        tenor_yrs = inv.tenor or 0      # stored in years for BONDS
        if tenor_yrs <= 2:  return '1-2 Year Notes'
        if tenor_yrs <= 5:  return '3-5 Year Bonds'
        return '5+ Year Bonds' if tenor_yrs > 5 else 'Local Unlisted Corporate Bonds'

    # ── GSE Equities (local) ──────────────────────────────────────────────────
    if ac == 'GSE_EQUITIES':
        if 'PREF' in st:                return 'Preference Shares'
        if inv.exchange:                return 'Local Listed Equity'
        return 'Local Unlisted Equity'

    # ── Global Equities (foreign) ─────────────────────────────────────────────
    if ac == 'GLOBAL_EQUITIES':
        if 'PREF' in st:               return 'Preference Shares'
        if inv.exchange:               return 'Foreign Listed Equity'
        return 'Foreign Unlisted Equity'

    # ── Private Equity ────────────────────────────────────────────────────────
    if ac == 'PRIVATE_EQUITY':
        if 'REIT' in st:               return 'REIT'
        return 'Venture Capital'

    # ── Mutual Funds / CIS ────────────────────────────────────────────────────
    if ac == 'MUTUAL_FUNDS':
        if 'REIT' in st:               return 'REIT'
        return 'CIS'

    return 'Others'


def _htm_value(inv):
    """Book / HTM value of an investment (cost basis)."""
    if inv.mkt_value_htm is not None:
        return float(inv.mkt_value_htm)
    ac = (inv.asset_class or '').upper()
    if ac in ('GOVT_SECURITIES', 'BONDS', 'EUROBONDS'):
        return float(inv.face_value or inv.total_cost or 0)
    if ac == 'MONEY_MARKET':
        return float(inv.face_value or inv.total_cost or 0)
    if ac in ('GSE_EQUITIES', 'GLOBAL_EQUITIES'):
        qty  = float(inv.quantity  or 0)
        cost = float(inv.unit_cost or 0)
        return qty * cost if qty and cost else float(inv.total_cost or 0)
    if ac == 'PRIVATE_EQUITY':
        return float(inv.called or inv.committed or inv.total_cost or 0)
    if ac == 'PRIVATE_DEBT':
        return float(inv.outstanding or inv.total_cost or 0)
    if ac == 'MUTUAL_FUNDS':
        qty  = float(inv.quantity  or 0)
        cost = float(inv.unit_cost or 0)
        return qty * cost if qty and cost else float(inv.total_cost or 0)
    return float(inv.total_cost or 0)


def _mtm_value(inv):
    """Market / MTM value using the Investment model's computed property."""
    try:
        v = inv.computed_mkt_value
        return float(v) if v is not None else _htm_value(inv)
    except Exception:
        return _htm_value(inv)


def _classify_client_type(acc):
    """Local-Institution | Local-Retail | Foreign-Institution | Foreign-Retail"""
    is_local = (
        getattr(acc, 'is_ghanaian', True) or
        (acc.country or '').upper() in ('GHANA', 'GH', '') or
        (acc.nationality or '').upper() in ('GHANAIAN', 'GHANA', '')
    )
    acct_type = (acc.account_type or 'Individual').upper()
    is_inst   = any(k in acct_type for k in
                    ('CORP', 'INST', 'TRUST', 'COMPANY', 'LTD', 'INC', 'PENSION', 'FUND'))
    if is_local and is_inst:     return 'Local-Institution'
    if is_local and not is_inst: return 'Local-Retail'
    if not is_local and is_inst: return 'Foreign-Institution'
    return 'Foreign-Retail'


def _classify_gender_type(acc):
    """Male | Female | Joint | Institutional"""
    acct_type = (acc.account_type or 'Individual').upper()
    if 'JOINT' in acct_type:
        return 'Joint'
    if any(k in acct_type for k in
           ('CORP', 'INST', 'TRUST', 'COMPANY', 'LTD', 'INC', 'PENSION', 'FUND')):
        return 'Institutional'
    gender = (acc.gender or '').upper()
    if gender in ('F', 'FEMALE'):
        return 'Female'
    return 'Male'  # default for individual accounts


# ── CORE AUTO-POPULATE ────────────────────────────────────────────────────────

def _auto_populate(report):
    """
    Read all APPROVED investments + accounts and refresh the three
    auto-calculated tables (Portfolio Holdings, Client Type, Client Classification).
    CIS Inflow / Outflow are always entered manually.
    Called on every page load and via the Refresh button.
    """
    year    = report.year
    quarter = report.quarter
    q_start, q_end = _quarter_date_range(year, quarter)

    approved_accounts = ClientAccount.query.filter_by(status='APPROVED').all()
    approved_investments = Investment.query.filter_by(status='APPROVED').all()

    # ── Portfolio Holdings ────────────────────────────────────────────────────
    # Build current HTM/MTM sums per SEC security type
    htm_by_type  = {s: 0.0 for s in SEC_PORTFOLIO_SECURITIES}
    mtm_by_type  = {s: 0.0 for s in SEC_PORTFOLIO_SECURITIES}

    for inv in approved_investments:
        sec_type = _map_to_sec_type(inv)
        if sec_type not in htm_by_type:
            sec_type = 'Others'
        htm_by_type[sec_type] += _htm_value(inv)
        mtm_by_type[sec_type] += _mtm_value(inv)

    # Cash Balance from all approved accounts
    total_cash = sum(acc.cash_balance for acc in approved_accounts)
    htm_by_type['Cash Balance'] += total_cash
    mtm_by_type['Cash Balance'] += total_cash

    # Update or create portfolio holding rows
    # Keep previous_htm = current_htm from the last SUBMITTED report for this quarter
    prev_report = (SECReport.query
                   .filter(SECReport.id != report.id,
                           SECReport.status == 'SUBMITTED')
                   .order_by(SECReport.year.desc(), SECReport.quarter.desc())
                   .first())
    prev_map = {}
    if prev_report:
        for ph in prev_report.portfolio_holdings:
            prev_map[ph.security_type] = ph.current_htm or 0.0

    for sec_type in SEC_PORTFOLIO_SECURITIES:
        row = SECPortfolioHolding.query.filter_by(
            report_id=report.id, security_type=sec_type).first()
        if not row:
            row = SECPortfolioHolding(report_id=report.id, security_type=sec_type)
            db.session.add(row)
        row.current_htm  = round(htm_by_type.get(sec_type, 0.0), 2)
        row.previous_htm = round(prev_map.get(sec_type, 0.0),    2)

    # ── Client Type Summary ───────────────────────────────────────────────────
    ct_data = {ct: {'no': set(), 'htm': 0.0, 'mtm': 0.0,
                    'sub': 0.0, 'red': 0.0, 'fee': 0.0}
               for ct in SEC_CLIENT_TYPES}

    # Group investments by account → client type
    inv_by_acc = {}
    for inv in approved_investments:
        inv_by_acc.setdefault(inv.account_number, []).append(inv)

    acc_map = {a.account_number: a for a in approved_accounts}

    for acc in approved_accounts:
        ct  = _classify_client_type(acc)
        bkt = ct_data.get(ct)
        if not bkt:
            continue
        bkt['no'].add(acc.account_number)

        for inv in inv_by_acc.get(acc.account_number, []):
            bkt['htm'] += _htm_value(inv)
            bkt['mtm'] += _mtm_value(inv)
        bkt['htm'] += acc.cash_balance
        bkt['mtm'] += acc.cash_balance

        # Subscription (deposits) in the quarter
        for txn in acc.transactions:
            if txn.status != 'APPROVED':
                continue
            txn_date = txn.created_at.date() if txn.created_at else None
            if txn_date and q_start <= txn_date <= q_end:
                amt = float(txn.amount_ghs if txn.amount_ghs is not None else txn.amount or 0)
                if txn.txn_type in ('DEPOSIT', 'TRANSFER_IN'):
                    bkt['sub'] += amt
                elif txn.txn_type in ('WITHDRAWAL', 'TRANSFER_OUT'):
                    bkt['red'] += amt

        # Management fees applied in the quarter
        try:
            from models import FeeTransaction
            for ft in FeeTransaction.query.filter_by(
                    account_number=acc.account_number, status='APPLIED').all():
                ft_date = ft.created_at.date() if ft.created_at else None
                if ft_date and q_start <= ft_date <= q_end:
                    bkt['fee'] += float(ft.amount or 0)
        except Exception:
            pass

    for ct in SEC_CLIENT_TYPES:
        bkt = ct_data[ct]
        row = SECClientTypeRow.query.filter_by(
            report_id=report.id, client_type=ct).first()
        if not row:
            row = SECClientTypeRow(report_id=report.id, client_type=ct)
            db.session.add(row)
        row.no_clients         = len(bkt['no'])
        row.htm_value          = round(bkt['htm'], 2)
        row.mtm_value          = round(bkt['mtm'], 2)
        row.value_subscription = round(bkt['sub'], 2)
        row.value_redemption   = round(bkt['red'], 2)
        row.effective_mgt_fees = round(bkt['fee'], 2)

    # ── Client Classification ─────────────────────────────────────────────────
    cc_data = {cc: {'no': set(), 'htm': 0.0, 'mtm': 0.0,
                    'sub': 0.0, 'red': 0.0, 'fee': 0.0}
               for cc in SEC_CLIENT_CLASSIFICATIONS}

    for acc in approved_accounts:
        cc  = _classify_gender_type(acc)
        bkt = cc_data.get(cc)
        if not bkt:
            continue
        bkt['no'].add(acc.account_number)
        for inv in inv_by_acc.get(acc.account_number, []):
            bkt['htm'] += _htm_value(inv)
            bkt['mtm'] += _mtm_value(inv)
        bkt['htm'] += acc.cash_balance
        bkt['mtm'] += acc.cash_balance

        for txn in acc.transactions:
            if txn.status != 'APPROVED':
                continue
            txn_date = txn.created_at.date() if txn.created_at else None
            if txn_date and q_start <= txn_date <= q_end:
                amt = float(txn.amount_ghs if txn.amount_ghs is not None else txn.amount or 0)
                if txn.txn_type in ('DEPOSIT', 'TRANSFER_IN'):
                    bkt['sub'] += amt
                elif txn.txn_type in ('WITHDRAWAL', 'TRANSFER_OUT'):
                    bkt['red'] += amt

        try:
            from models import FeeTransaction
            for ft in FeeTransaction.query.filter_by(
                    account_number=acc.account_number, status='APPLIED').all():
                ft_date = ft.created_at.date() if ft.created_at else None
                if ft_date and q_start <= ft_date <= q_end:
                    bkt['fee'] += float(ft.amount or 0)
        except Exception:
            pass

    for cc in SEC_CLIENT_CLASSIFICATIONS:
        bkt = cc_data[cc]
        row = SECClientClassRow.query.filter_by(
            report_id=report.id, classification=cc).first()
        if not row:
            row = SECClientClassRow(report_id=report.id, classification=cc)
            db.session.add(row)
        row.no_clients         = len(bkt['no'])
        row.htm_value          = round(bkt['htm'], 2)
        row.mtm_value          = round(bkt['mtm'], 2)
        row.value_subscription = round(bkt['sub'], 2)
        row.value_redemption   = round(bkt['red'], 2)
        row.effective_mgt_fees = round(bkt['fee'], 2)

    report.updated_at = datetime.utcnow()
    db.session.commit()


def _get_or_create_report(year, quarter):
    rep = SECReport.query.filter_by(year=year, quarter=quarter).first()
    if not rep:
        rep = SECReport(year=year, quarter=quarter,
                        status='DRAFT',
                        created_by=current_user.id if current_user.is_authenticated else None)
        db.session.add(rep)
        db.session.flush()
        # Seed fixed rows (values filled by auto-populate)
        for ct in SEC_CLIENT_TYPES:
            db.session.add(SECClientTypeRow(report_id=rep.id, client_type=ct))
        for cc in SEC_CLIENT_CLASSIFICATIONS:
            db.session.add(SECClientClassRow(report_id=rep.id, classification=cc))
        for s in SEC_PORTFOLIO_SECURITIES:
            db.session.add(SECPortfolioHolding(report_id=rep.id, security_type=s))
        db.session.commit()
    return rep


# ── MAIN PAGE ─────────────────────────────────────────────────────────────────

@sec_bp.route('/')
@login_required
def index():
    year    = int(request.args.get('year',    date.today().year))
    quarter = request.args.get('quarter', _current_quarter())
    report  = _get_or_create_report(year, quarter)

    # Auto-populate from live data every time the page loads (unless submitted)
    if report.status != 'SUBMITTED':
        try:
            _auto_populate(report)
        except Exception as e:
            flash(f'Auto-populate warning: {e}', 'info')

    all_reports = SECReport.query.order_by(
        SECReport.year.desc(), SECReport.quarter).all()

    cur_year = date.today().year
    return render_template(
        'admin/sec_report.html',
        report=report,
        all_reports=all_reports,
        year=year, quarter=quarter,
        client_types=SEC_CLIENT_TYPES,
        classifications=SEC_CLIENT_CLASSIFICATIONS,
        securities=SEC_PORTFOLIO_SECURITIES,
        reg_bodies=SEC_REGULATORY_BODIES,
        years=list(range(cur_year + 1, 2020, -1)),  # current+1 down to 2021
    )


# ── MANUAL REFRESH ────────────────────────────────────────────────────────────

@sec_bp.route('/<int:report_id>/refresh', methods=['POST'])
@login_required
def refresh(report_id):
    rep = SECReport.query.get_or_404(report_id)
    if rep.status == 'SUBMITTED':
        flash('Cannot refresh a submitted report.', 'error')
    else:
        try:
            _auto_populate(rep)
            flash('Data refreshed from live investments.', 'success')
        except Exception as e:
            flash(f'Refresh error: {e}', 'error')
    return redirect(url_for('sec.index', year=rep.year, quarter=rep.quarter))


# ── SAVE CLIENT TYPE SUMMARY (manual overrides) ──────────────────────────────

@sec_bp.route('/<int:report_id>/save-client-type', methods=['POST'])
@login_required
def save_client_type(report_id):
    rep = SECReport.query.get_or_404(report_id)
    if rep.status == 'SUBMITTED':
        flash('Cannot edit a submitted report.', 'error')
        return redirect(url_for('sec.index', year=rep.year, quarter=rep.quarter))
    for ct in SEC_CLIENT_TYPES:
        key = ct.replace(' ', '_').replace('-', '_')
        row = SECClientTypeRow.query.filter_by(report_id=report_id, client_type=ct).first()
        if not row:
            row = SECClientTypeRow(report_id=report_id, client_type=ct)
            db.session.add(row)
        row.no_clients         = _int(request.form.get(f'ct_no_{key}'))
        row.htm_value          = _flt(request.form.get(f'ct_htm_{key}'))
        row.mtm_value          = _flt(request.form.get(f'ct_mtm_{key}'))
        row.value_redemption   = _flt(request.form.get(f'ct_red_{key}'))
        row.value_subscription = _flt(request.form.get(f'ct_sub_{key}'))
        row.effective_mgt_fees = _flt(request.form.get(f'ct_fee_{key}'))
    rep.updated_at = datetime.utcnow()
    db.session.commit()
    flash('Client Type Summary saved.', 'success')
    return redirect(url_for('sec.index', year=rep.year, quarter=rep.quarter) + '#tab-client-type')


# ── SAVE CLIENT CLASSIFICATION ────────────────────────────────────────────────

@sec_bp.route('/<int:report_id>/save-client-class', methods=['POST'])
@login_required
def save_client_class(report_id):
    rep = SECReport.query.get_or_404(report_id)
    if rep.status == 'SUBMITTED':
        flash('Cannot edit a submitted report.', 'error')
        return redirect(url_for('sec.index', year=rep.year, quarter=rep.quarter))
    for cc in SEC_CLIENT_CLASSIFICATIONS:
        key = cc.replace(' ', '_').replace('-', '_')
        row = SECClientClassRow.query.filter_by(report_id=report_id, classification=cc).first()
        if not row:
            row = SECClientClassRow(report_id=report_id, classification=cc)
            db.session.add(row)
        row.no_clients         = _int(request.form.get(f'cc_no_{key}'))
        row.htm_value          = _flt(request.form.get(f'cc_htm_{key}'))
        row.mtm_value          = _flt(request.form.get(f'cc_mtm_{key}'))
        row.value_redemption   = _flt(request.form.get(f'cc_red_{key}'))
        row.value_subscription = _flt(request.form.get(f'cc_sub_{key}'))
        row.effective_mgt_fees = _flt(request.form.get(f'cc_fee_{key}'))
    rep.updated_at = datetime.utcnow()
    db.session.commit()
    flash('Client Classification saved.', 'success')
    return redirect(url_for('sec.index', year=rep.year, quarter=rep.quarter) + '#tab-client-class')


# ── SAVE PORTFOLIO HOLDINGS (manual overrides) ────────────────────────────────

@sec_bp.route('/<int:report_id>/save-portfolio', methods=['POST'])
@login_required
def save_portfolio(report_id):
    rep = SECReport.query.get_or_404(report_id)
    if rep.status == 'SUBMITTED':
        flash('Cannot edit a submitted report.', 'error')
        return redirect(url_for('sec.index', year=rep.year, quarter=rep.quarter))
    for i, sec_type in enumerate(SEC_PORTFOLIO_SECURITIES):
        row = SECPortfolioHolding.query.filter_by(
            report_id=report_id, security_type=sec_type).first()
        if not row:
            row = SECPortfolioHolding(report_id=report_id, security_type=sec_type)
            db.session.add(row)
        row.current_htm  = _flt(request.form.get(f'ph_cur_{i}'))
        row.previous_htm = _flt(request.form.get(f'ph_prev_{i}'))
    rep.updated_at = datetime.utcnow()
    db.session.commit()
    flash('Portfolio Holdings saved.', 'success')
    return redirect(url_for('sec.index', year=rep.year, quarter=rep.quarter) + '#tab-portfolio')


# ── CIS INFLOW ────────────────────────────────────────────────────────────────

@sec_bp.route('/<int:report_id>/cis-inflow/save', methods=['POST'])
@login_required
def save_cis_inflow(report_id):
    rep = SECReport.query.get_or_404(report_id)
    if rep.status == 'SUBMITTED':
        flash('Cannot edit a submitted report.', 'error')
        return redirect(url_for('sec.index', year=rep.year, quarter=rep.quarter))
    rec_id = request.form.get('rec_id')
    rec = SECCISInflow.query.get(int(rec_id)) if rec_id else None
    if not rec:
        rec = SECCISInflow(report_id=report_id)
        db.session.add(rec)
    rec.regulatory_body   = request.form.get('regulatory_body', '')
    rec.customer_category = request.form.get('customer_category', '')
    rec.no_clients        = _int(request.form.get('no_clients'))
    rec.beginning_fum     = _flt(request.form.get('beginning_fum'))
    rec.total_inflow      = _flt(request.form.get('total_inflow'))
    rec.total_outflow     = _flt(request.form.get('total_outflow'))
    rec.total_gains_loss  = _flt(request.form.get('total_gains_loss'))
    rep.updated_at        = datetime.utcnow()
    db.session.commit()
    flash('CIS Inflow record saved.', 'success')
    return redirect(url_for('sec.index', year=rep.year, quarter=rep.quarter) + '#tab-cis-inflow')


@sec_bp.route('/<int:report_id>/cis-inflow/<int:rec_id>/delete', methods=['POST'])
@login_required
def delete_cis_inflow(report_id, rec_id):
    rec = SECCISInflow.query.get_or_404(rec_id)
    rep = SECReport.query.get_or_404(report_id)
    db.session.delete(rec)
    db.session.commit()
    flash('Record deleted.', 'success')
    return redirect(url_for('sec.index', year=rep.year, quarter=rep.quarter) + '#tab-cis-inflow')


# ── CIS OUTFLOW ───────────────────────────────────────────────────────────────

@sec_bp.route('/<int:report_id>/cis-outflow/save', methods=['POST'])
@login_required
def save_cis_outflow(report_id):
    rep = SECReport.query.get_or_404(report_id)
    if rep.status == 'SUBMITTED':
        flash('Cannot edit a submitted report.', 'error')
        return redirect(url_for('sec.index', year=rep.year, quarter=rep.quarter))
    rec_id = request.form.get('rec_id')
    rec = SECCISOutflow.query.get(int(rec_id)) if rec_id else None
    if not rec:
        rec = SECCISOutflow(report_id=report_id)
        db.session.add(rec)
    rec.regulatory_body     = request.form.get('regulatory_body', '')
    rec.customer_category   = request.form.get('customer_category', '')
    rec.total_fum_beginning = _flt(request.form.get('total_fum_beginning'))
    rec.fund_outflow        = _flt(request.form.get('fund_outflow'))
    rec.total_repayments    = _flt(request.form.get('total_repayments'))
    rec.gains_loss          = _flt(request.form.get('gains_loss'))
    rep.updated_at          = datetime.utcnow()
    db.session.commit()
    flash('CIS Outflow record saved.', 'success')
    return redirect(url_for('sec.index', year=rep.year, quarter=rep.quarter) + '#tab-cis-outflow')


@sec_bp.route('/<int:report_id>/cis-outflow/<int:rec_id>/delete', methods=['POST'])
@login_required
def delete_cis_outflow(report_id, rec_id):
    rec = SECCISOutflow.query.get_or_404(rec_id)
    rep = SECReport.query.get_or_404(report_id)
    db.session.delete(rec)
    db.session.commit()
    flash('Record deleted.', 'success')
    return redirect(url_for('sec.index', year=rep.year, quarter=rep.quarter) + '#tab-cis-outflow')


# ── SUBMIT / REOPEN ───────────────────────────────────────────────────────────

@sec_bp.route('/<int:report_id>/submit', methods=['POST'])
@login_required
def submit_report(report_id):
    rep = SECReport.query.get_or_404(report_id)
    rep.status       = 'SUBMITTED'
    rep.submitted_at = datetime.utcnow()
    rep.updated_at   = datetime.utcnow()
    db.session.commit()
    flash(f'SEC Report {rep.label} submitted successfully.', 'success')
    return redirect(url_for('sec.index', year=rep.year, quarter=rep.quarter))


@sec_bp.route('/<int:report_id>/reopen', methods=['POST'])
@login_required
def reopen_report(report_id):
    rep = SECReport.query.get_or_404(report_id)
    rep.status       = 'DRAFT'
    rep.submitted_at = None
    rep.updated_at   = datetime.utcnow()
    db.session.commit()
    flash(f'Report {rep.label} reopened as Draft.', 'success')
    return redirect(url_for('sec.index', year=rep.year, quarter=rep.quarter))


# ── EXPORT PDF ────────────────────────────────────────────────────────────────

@sec_bp.route('/<int:report_id>/export/pdf')
@login_required
def export_pdf(report_id):
    rep  = SECReport.query.get_or_404(report_id)
    buf  = _generate_pdf(rep)
    fname = f'SEC_Report_{rep.quarter}_{rep.year}.pdf'
    return send_file(buf, mimetype='application/pdf',
                     as_attachment=request.args.get('download') == '1',
                     download_name=fname)


# ── EXPORT EXCEL ─────────────────────────────────────────────────────────────

@sec_bp.route('/<int:report_id>/export/excel')
@login_required
def export_excel(report_id):
    rep  = SECReport.query.get_or_404(report_id)
    buf  = _generate_excel(rep)
    fname = f'SEC_Report_{rep.quarter}_{rep.year}.xlsx'
    return send_file(
        buf,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=fname,
    )


# ── PDF GENERATOR ─────────────────────────────────────────────────────────────

def _generate_pdf(rep):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer, PageBreak)
    from reports.pdf_reports import (make_styles, tbl_style,
                                     DARK, GOLD, GOLD2, WHITE, LIGHT, GREY,
                                     GREEN, RED, DARK2)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=2.4*cm, bottomMargin=1.8*cm)
    S = make_styles()

    def hdr_footer(c, d):
        import os
        w, h = landscape(A4)
        c.saveState()
        c.setFillColor(DARK2); c.rect(0, h-1.9*cm, w, 1.9*cm, fill=1, stroke=0)
        c.setFillColor(GOLD);  c.rect(0, h-1.92*cm, w, 0.07*cm, fill=1, stroke=0)
        logo = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'img', 'logo.png')
        if os.path.exists(logo):
            c.drawImage(logo, 0.8*cm, h-1.7*cm, 1.3*cm, 1.3*cm,
                        preserveAspectRatio=True, mask='auto')
        c.setFont('Helvetica-Bold', 13); c.setFillColor(WHITE)
        c.drawString(2.6*cm, h-1.05*cm, 'ZAGADAT CAPITAL')
        c.setFont('Helvetica', 9); c.setFillColor(GOLD)
        c.drawString(2.6*cm, h-1.55*cm, f'SEC Regulatory Report — {rep.label}')
        c.setFont('Helvetica', 8); c.setFillColor(GREY)
        c.drawRightString(w-1.5*cm, h-1.15*cm, f'Status: {rep.status}')
        c.drawRightString(w-1.5*cm, h-1.55*cm,
                          f'Generated: {date.today().strftime("%d %b %Y")}')
        c.setFillColor(DARK2); c.rect(0, 0, w, 1.2*cm, fill=1, stroke=0)
        c.setFillColor(GOLD);  c.rect(0, 1.2*cm, w, 0.05*cm, fill=1, stroke=0)
        c.setFont('Helvetica', 7); c.setFillColor(LIGHT)
        c.drawString(0.8*cm, 0.42*cm,
                     'ZAGADAT CAPITAL — STRICTLY CONFIDENTIAL — FOR REGULATORY USE ONLY')
        c.setFont('Helvetica', 7); c.setFillColor(GREY)
        c.drawRightString(w-0.8*cm, 0.42*cm, f'Page {d.page}')
        c.restoreState()

    def sec_hdr(txt):
        return Paragraph(txt, S['section'])

    def fmtn(v):
        try:    return f'{float(v or 0):,.2f}'
        except: return '—'

    def build_table(headers, rows, col_widths, total_row=None):
        data = [headers] + rows
        if total_row:
            data.append(total_row)
        t  = Table(data, colWidths=col_widths, repeatRows=1)
        ts = tbl_style()
        ts.add('ALIGN',       (1, 0),  (-1, -1),  'RIGHT')
        ts.add('FONTSIZE',    (0, 0),  (-1, -1),  7)
        ts.add('ROWBACKGROUNDS', (0, 1), (-1, -2 if total_row else -1),
               [colors.HexColor('#1E1E2E'), colors.HexColor('#16161F')])
        if total_row:
            last = len(data) - 1
            ts.add('BACKGROUND', (0, last), (-1, last), DARK)
            ts.add('TEXTCOLOR',  (0, last), (-1, last), GOLD)
            ts.add('FONTNAME',   (0, last), (-1, last), 'Helvetica-Bold')
        t.setStyle(ts)
        return t

    story = []
    story.append(Paragraph(f'SEC REGULATORY REPORT — {rep.label}', S['title']))
    story.append(Paragraph(
        f'Period: {rep.quarter} {rep.year}  |  Status: {rep.status}  |  '
        f'Auto-populated: {rep.updated_at.strftime("%d %b %Y %H:%M")}  |  '
        f'Generated: {date.today().strftime("%d %b %Y")}', S['subtitle']))
    story.append(Spacer(1, 0.4*cm))

    col_hdrs = ['Client/Entity Type', 'No. of Clients', 'Ending Value (HTM)',
                'Market Value (MTM)', 'Value of Redemption',
                'Value of Subscription', 'Effective Mgt Fees']
    cw = [4.2*cm, 2*cm, 3.8*cm, 3.8*cm, 3.8*cm, 3.8*cm, 3.2*cm]

    # Table 1: Client Type
    story.append(sec_hdr('1. CLIENT TYPE SUMMARY  (All values in GHS)'))
    story.append(Spacer(1, 0.15*cm))
    ct_map = {r.client_type: r for r in rep.client_type_rows}
    ct_rows, tot = [], [0]*6
    for ct in SEC_CLIENT_TYPES:
        r = ct_map.get(ct)
        v = [(r.no_clients or 0), (r.htm_value or 0), (r.mtm_value or 0),
             (r.value_redemption or 0), (r.value_subscription or 0),
             (r.effective_mgt_fees or 0)] if r else [0]*6
        for i, x in enumerate(v): tot[i] += x
        ct_rows.append([ct, f'{v[0]:,}', fmtn(v[1]), fmtn(v[2]),
                        fmtn(v[3]), fmtn(v[4]), fmtn(v[5])])
    story.append(build_table(col_hdrs, ct_rows,
                             cw, ['TOTAL', f'{tot[0]:,}'] + [fmtn(x) for x in tot[1:]]))
    story.append(Spacer(1, 0.5*cm))

    # Table 2: Client Classification
    story.append(sec_hdr('2. CLIENT CLASSIFICATION  (All values in GHS)'))
    story.append(Spacer(1, 0.15*cm))
    cc_map = {r.classification: r for r in rep.client_class_rows}
    cc_rows, tot2 = [], [0]*6
    for cc in SEC_CLIENT_CLASSIFICATIONS:
        r = cc_map.get(cc)
        v = [(r.no_clients or 0), (r.htm_value or 0), (r.mtm_value or 0),
             (r.value_redemption or 0), (r.value_subscription or 0),
             (r.effective_mgt_fees or 0)] if r else [0]*6
        for i, x in enumerate(v): tot2[i] += x
        cc_rows.append([cc, f'{v[0]:,}', fmtn(v[1]), fmtn(v[2]),
                        fmtn(v[3]), fmtn(v[4]), fmtn(v[5])])
    story.append(build_table(col_hdrs, cc_rows,
                             cw, ['TOTAL', f'{tot2[0]:,}'] + [fmtn(x) for x in tot2[1:]]))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        f'HTM Placement Total: GHS {tot2[1]:,.2f}   |   '
        f'MTM Placement Total: GHS {tot2[2]:,.2f}', S['subtitle']))
    story.append(PageBreak())

    # Table 3: Portfolio Holdings
    story.append(sec_hdr('3. PORTFOLIO HOLDINGS'))
    story.append(Spacer(1, 0.15*cm))
    ph_map = {r.security_type: r for r in rep.portfolio_holdings}
    ph_rows, tot_cur, tot_prev = [], 0, 0
    for s in SEC_PORTFOLIO_SECURITIES:
        r = ph_map.get(s)
        cur  = float(r.current_htm  or 0) if r else 0
        prev = float(r.previous_htm or 0) if r else 0
        tot_cur += cur; tot_prev += prev
        ph_rows.append([s, fmtn(cur), fmtn(prev)])
    story.append(build_table(
        ['Security Type', 'Current Amount (HTM)', 'Previous Amount (HTM)'],
        ph_rows, [10*cm, 5*cm, 5*cm],
        ['TOTAL', fmtn(tot_cur), fmtn(tot_prev)]))
    story.append(PageBreak())

    # Table 4: CIS Inflow
    story.append(sec_hdr('4. CIS INTERCONNECTEDNESS — INFLOW REPORT'))
    story.append(Spacer(1, 0.15*cm))
    if rep.cis_inflows:
        in_hdrs = ['Regulatory Body', 'Customer Category', 'No.',
                   'Beginning FUM', 'Total Inflow', 'Total Outflow',
                   'Gains/Loss', 'Net Inflow/Outflow', 'Balance FUM']
        story.append(build_table(in_hdrs,
            [[r.regulatory_body, r.customer_category or '—',
              f'{r.no_clients or 0:,}', fmtn(r.beginning_fum),
              fmtn(r.total_inflow), fmtn(r.total_outflow),
              fmtn(r.total_gains_loss), fmtn(r.net_inflow_outflow),
              fmtn(r.balance_fum)] for r in rep.cis_inflows],
            [4.5*cm,3*cm,1.2*cm,3*cm,2.8*cm,2.8*cm,2.8*cm,3*cm,3*cm]))
    else:
        story.append(Paragraph('No inflow records for this period.', S['subtitle']))
    story.append(Spacer(1, 0.5*cm))

    # Table 5: CIS Outflow
    story.append(sec_hdr('5. CIS INTERCONNECTEDNESS — OUTFLOW REPORT'))
    story.append(Spacer(1, 0.15*cm))
    if rep.cis_outflows:
        out_hdrs = ['Regulatory Body', 'Customer Category',
                    'FUM Beginning', 'Fund Outflow', 'Total Repayments',
                    'Gains/Loss', 'Net Inflow/Outflow', 'FUM End of Period']
        story.append(build_table(out_hdrs,
            [[r.regulatory_body, r.customer_category or '—',
              fmtn(r.total_fum_beginning), fmtn(r.fund_outflow),
              fmtn(r.total_repayments), fmtn(r.gains_loss),
              fmtn(r.net_inflow_outflow), fmtn(r.total_fum_end)]
             for r in rep.cis_outflows],
            [4.5*cm,3*cm,3.2*cm,3.2*cm,3.2*cm,3*cm,3*cm,3.2*cm]))
    else:
        story.append(Paragraph('No outflow records for this period.', S['subtitle']))

    doc.build(story, onFirstPage=hdr_footer, onLaterPages=hdr_footer)
    buf.seek(0)
    return buf


# ── EXCEL GENERATOR ───────────────────────────────────────────────────────────

def _generate_excel(rep):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb    = openpyxl.Workbook()
    NAVY  = '0F2044'
    GOLD  = 'C9A84C'
    TEAL  = '0E7490'
    WHITE = 'F5F5F0'
    thin  = Side(style='thin', color='CBD5E1')
    bdr   = Border(left=thin, right=thin, top=thin, bottom=thin)

    def hf(bold=True, sz=10, color=WHITE): return Font(name='Calibri', bold=bold, size=sz, color=color)
    def fill(c): return PatternFill('solid', fgColor=c)
    def al(h='left', v='center', wrap=False):
        return Alignment(horizontal=h, vertical=v, wrap_text=wrap)

    def write_section(ws, title, headers, rows, total_row=None, start_row=1):
        r = start_row
        # Title row
        ws.merge_cells(start_row=r, start_column=1,
                       end_row=r, end_column=len(headers))
        c = ws.cell(r, 1, title)
        c.font      = hf(sz=11, color=GOLD)
        c.fill      = fill(NAVY)
        c.alignment = al('left')
        ws.row_dimensions[r].height = 22
        r += 1

        # Header row
        for ci, h in enumerate(headers, 1):
            c = ws.cell(r, ci, h)
            c.font      = hf(color=WHITE)
            c.fill      = fill(TEAL)
            c.alignment = al('center', wrap=True)
            c.border    = bdr
        ws.row_dimensions[r].height = 28
        r += 1

        # Data rows
        stripe = ['F0F4F8', 'FFFFFF']
        for ri, row in enumerate(rows):
            for ci, val in enumerate(row, 1):
                c = ws.cell(r, ci)
                c.border    = bdr
                c.fill      = fill(stripe[ri % 2])
                c.alignment = al('right')
                if ci == 1:
                    c.value     = str(val) if val is not None else ''
                    c.alignment = al('left')
                    c.font      = Font(name='Calibri', size=9, color='1E293B')
                elif isinstance(val, (int, float)):
                    c.value         = val
                    c.number_format = ('#,##0' if isinstance(val, int) and
                                       not isinstance(val, bool) else '#,##0.00')
                    c.font          = Font(name='Calibri', size=9, color='1E293B')
                else:
                    try:
                        fv = float(str(val).replace(',', ''))
                        c.value         = fv
                        c.number_format = '#,##0.00'
                        c.font          = Font(name='Calibri', size=9, color='1E293B')
                    except (ValueError, TypeError):
                        c.value     = str(val) if val is not None else ''
                        c.font      = Font(name='Calibri', size=9, color='1E293B')
                        c.alignment = al('left')
            ws.row_dimensions[r].height = 16
            r += 1

        # Total row
        if total_row is not None:
            for ci, val in enumerate(total_row, 1):
                c = ws.cell(r, ci)
                c.border = bdr
                c.fill   = fill(NAVY)
                c.font   = hf(sz=9, color=GOLD)
                if ci == 1:
                    c.value     = str(val) if val is not None else ''
                    c.alignment = al('left')
                else:
                    try:
                        fv = float(str(val).replace(',', ''))
                        c.value         = fv
                        c.number_format = '#,##0.00'
                        c.alignment     = al('right')
                    except (ValueError, TypeError):
                        c.value     = str(val) if val is not None else ''
                        c.alignment = al('right')
            ws.row_dimensions[r].height = 18
            r += 1

        return r + 1  # blank row after section

    col_hdrs = ['Client Type / Classification', 'No. of Clients',
                'Ending Value (HTM) GHS', 'Market Value (MTM) GHS',
                'Value of Redemption GHS', 'Value of Subscription GHS',
                'Effective Mgt Fees GHS']

    def col_widths_ct(ws):
        ws.column_dimensions['A'].width = 24
        for col in 'BCDEFG': ws.column_dimensions[col].width = 20

    def col_widths_ph(ws):
        ws.column_dimensions['A'].width = 38
        ws.column_dimensions['B'].width = 24
        ws.column_dimensions['C'].width = 24

    def col_widths_cis(ws, ncols):
        ws.column_dimensions['A'].width = 32
        ws.column_dimensions['B'].width = 24
        for col in [chr(67 + i) for i in range(ncols - 2)]:
            ws.column_dimensions[col].width = 20

    # ── Sheet 1: Client Type Summary ─────────────────────────────────────────
    ws1 = wb.active
    ws1.title = 'Client Type Summary'
    col_widths_ct(ws1)
    ct_map = {r.client_type: r for r in rep.client_type_rows}
    rows1, tots = [], [0]*6
    for ct in SEC_CLIENT_TYPES:
        r = ct_map.get(ct)
        v = [(r.no_clients or 0), (r.htm_value or 0), (r.mtm_value or 0),
             (r.value_redemption or 0), (r.value_subscription or 0),
             (r.effective_mgt_fees or 0)] if r else [0]*6
        for i, x in enumerate(v): tots[i] += x
        rows1.append([ct] + v)
    write_section(ws1, f'CLIENT TYPE SUMMARY — {rep.label}',
                  col_hdrs, rows1,
                  ['TOTAL'] + tots, 1)

    # ── Sheet 2: Client Classification ───────────────────────────────────────
    ws2 = wb.create_sheet('Client Classification')
    col_widths_ct(ws2)
    cc_map = {r.classification: r for r in rep.client_class_rows}
    rows2, tots2 = [], [0]*6
    for cc in SEC_CLIENT_CLASSIFICATIONS:
        r = cc_map.get(cc)
        v = [(r.no_clients or 0), (r.htm_value or 0), (r.mtm_value or 0),
             (r.value_redemption or 0), (r.value_subscription or 0),
             (r.effective_mgt_fees or 0)] if r else [0]*6
        for i, x in enumerate(v): tots2[i] += x
        rows2.append([cc] + v)
    nxt = write_section(ws2, f'CLIENT CLASSIFICATION — {rep.label}',
                        col_hdrs, rows2, ['TOTAL'] + tots2, 1)
    # HTM/MTM placement totals
    for offset, label, val in [(0, 'HTM Placement Total (GHS)', tots2[1]),
                               (1, 'MTM Placement Total (GHS)', tots2[2])]:
        c1 = ws2.cell(nxt + offset, 1, label)
        c1.font = Font(name='Calibri', bold=True, size=10, color=NAVY)
        c2 = ws2.cell(nxt + offset, 2, val)
        c2.font         = Font(name='Calibri', bold=True, size=10, color=TEAL)
        c2.number_format = '#,##0.00'

    # ── Sheet 3: Portfolio Holdings ───────────────────────────────────────────
    ws3 = wb.create_sheet('Portfolio Holdings')
    col_widths_ph(ws3)
    ph_map = {r.security_type: r for r in rep.portfolio_holdings}
    rows3, tot_cur, tot_prev = [], 0.0, 0.0
    for s in SEC_PORTFOLIO_SECURITIES:
        r = ph_map.get(s)
        cur  = float(r.current_htm  or 0) if r else 0.0
        prev = float(r.previous_htm or 0) if r else 0.0
        tot_cur += cur; tot_prev += prev
        rows3.append([s, cur, prev])
    write_section(ws3, f'PORTFOLIO HOLDINGS — {rep.label}',
                  ['Security Type', 'Current Amount (HTM) GHS', 'Previous Amount (HTM) GHS'],
                  rows3, ['TOTAL', tot_cur, tot_prev], 1)

    # ── Sheet 4: CIS Inflow ───────────────────────────────────────────────────
    ws4 = wb.create_sheet('CIS Inflow')
    col_widths_cis(ws4, 9)
    in_hdrs = ['Regulatory Body', 'Customer Category', 'No. in Category',
               'Beginning FUM (GHS)', 'Total Inflow (GHS)', 'Total Outflow (GHS)',
               'Gains/Loss (GHS)', 'Net Inflow/Outflow (GHS)', 'Balance FUM (GHS)']
    rows4 = []
    for r in rep.cis_inflows:
        rows4.append([
            r.regulatory_body,
            r.customer_category or '',
            int(r.no_clients or 0),
            float(r.beginning_fum    or 0),
            float(r.total_inflow     or 0),
            float(r.total_outflow    or 0),
            float(r.total_gains_loss or 0),
            float(r.net_inflow_outflow),
            float(r.balance_fum),
        ])
    write_section(ws4, f'CIS INTERCONNECTEDNESS INFLOW — {rep.label}',
                  in_hdrs, rows4, None, 1)

    # ── Sheet 5: CIS Outflow ──────────────────────────────────────────────────
    ws5 = wb.create_sheet('CIS Outflow')
    col_widths_cis(ws5, 8)
    out_hdrs = ['Regulatory Body', 'Customer Category',
                'FUM Beginning (GHS)', 'Fund Outflow (GHS)',
                'Total Repayments (GHS)', 'Gains/Loss (GHS)',
                'Net Inflow/Outflow (GHS)', 'FUM End of Period (GHS)']
    rows5 = []
    for r in rep.cis_outflows:
        rows5.append([
            r.regulatory_body,
            r.customer_category or '',
            float(r.total_fum_beginning or 0),
            float(r.fund_outflow        or 0),
            float(r.total_repayments    or 0),
            float(r.gains_loss          or 0),
            float(r.net_inflow_outflow),
            float(r.total_fum_end),
        ])
    write_section(ws5, f'CIS INTERCONNECTEDNESS OUTFLOW — {rep.label}',
                  out_hdrs, rows5, None, 1)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf

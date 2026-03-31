from flask import Blueprint, jsonify, request
from flask_login import login_required
from models import StockPrice, FXRate, Investment, ClientAccount, Transaction, db
from utils.market_data import get_all_stocks, get_all_fx, fetch_fx_rates, fetch_gse_prices, fetch_global_prices
from datetime import date, datetime

api_bp = Blueprint('api', __name__)

@api_bp.route('/stocks')
def stocks():
    return jsonify(get_all_stocks())

@api_bp.route('/fx')
def fx_rates():
    return jsonify(get_all_fx())

@api_bp.route('/refresh-fx')
def refresh_fx():
    ok = fetch_fx_rates()
    return jsonify({'ok': ok, 'rates': get_all_fx()})

@api_bp.route('/refresh-prices')
def refresh_prices():
    gse = fetch_gse_prices()
    glb = fetch_global_prices()
    return jsonify({'gse': gse, 'global': glb})

@api_bp.route('/bond-calc')
def bond_calc():
    """Calculate bond MTM value, accrued interest, YTM"""
    face = float(request.args.get('face', 0))
    clean_px = float(request.args.get('clean_px', 100))  # percentage
    coupon = float(request.args.get('coupon', 0))
    trade_date_str = request.args.get('trade_date', '')
    maturity_str = request.args.get('maturity', '')
    last_cpn_str = request.args.get('last_cpn', '')
    sub_type = request.args.get('sub_type', 'BOND').upper()
    tenor_str = request.args.get('tenor', '')

    try:
        from datetime import datetime
        def pd(s):
            for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
                try: return datetime.strptime(s, fmt).date()
                except: pass
            return None

        trade_date = pd(trade_date_str) or date.today()
        maturity = pd(maturity_str)

        # Auto-compute maturity from trade_date + tenor if not given
        if not maturity and tenor_str:
            from dateutil.relativedelta import relativedelta
            tenor = int(tenor_str)
            basis = 364 if 'BILL' in sub_type else 365
            from datetime import timedelta
            maturity = trade_date + timedelta(days=tenor)

        last_cpn = pd(last_cpn_str) or trade_date
        today = date.today()
        days_run = (today - trade_date).days
        days_to_mat = max(0, (maturity - today).days) if maturity else 0

        basis = 364 if 'BILL' in sub_type else 365
        accrued = (face * (coupon / 100) * (today - last_cpn).days) / basis if coupon else 0
        mkt_value = (clean_px / 100) * face + accrued if face else 0

        return jsonify({
            'mkt_value': round(mkt_value, 2),
            'accrued': round(accrued, 2),
            'days_run': days_run,
            'days_to_mat': days_to_mat,
            'maturity_date': maturity.isoformat() if maturity else None
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@api_bp.route('/tbill-calc')
def tbill_calc():
    """Calculate T-Bill investment details"""
    face = float(request.args.get('face', 0))
    rate = float(request.args.get('rate', 0))
    tenor = int(request.args.get('tenor', 91))
    trade_date_str = request.args.get('trade_date', '')
    sub_type = request.args.get('sub_type', 'BILL').upper()

    try:
        from datetime import datetime, timedelta
        def pd(s):
            for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
                try: return datetime.strptime(s, fmt).date()
                except: pass
            return None

        trade_date = pd(trade_date_str) or date.today()
        basis = 364 if 'BILL' in sub_type or 'TREASURY' in sub_type else 365
        maturity = trade_date + timedelta(days=tenor)
        today = date.today()
        days_run = (today - trade_date).days
        days_to_mat = max(0, (maturity - today).days)

        # Price (cost) = Face / (1 + rate * tenor/basis)
        principal = face / (1 + (rate / 100) * tenor / basis) if face else 0
        # Current MTM = Face / (1 + rate * days_to_mat/basis)
        mtm = face / (1 + (rate / 100) * days_to_mat / basis) if face else 0
        accrued = mtm - principal

        return jsonify({
            'principal': round(principal, 2),
            'mkt_value': round(mtm, 2),
            'accrued': round(accrued, 2),
            'days_run': days_run,
            'days_to_mat': days_to_mat,
            'maturity_date': maturity.isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@api_bp.route('/portfolio-summary/<account_number>')
@login_required
def portfolio_summary(account_number):
    investments = Investment.query.filter_by(account_number=account_number, status='APPROVED').all()
    acc = ClientAccount.query.filter_by(account_number=account_number).first()
    if not acc:
        return jsonify({'error': 'Account not found'}), 404

    by_class = {}
    total = 0
    for inv in investments:
        mv = inv.computed_mkt_value
        total += mv
        by_class[inv.asset_class] = by_class.get(inv.asset_class, 0) + mv

    cash = acc.cash_balance
    total_portfolio = total + cash

    return jsonify({
        'account_number': account_number,
        'full_name': acc.full_name,
        'total_investments': round(total, 2),
        'cash_balance': round(cash, 2),
        'total_portfolio': round(total_portfolio, 2),
        'by_class': {k: round(v, 2) for k, v in by_class.items()},
        'currency': acc.base_currency
    })

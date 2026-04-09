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
            tenor_val = float(tenor_str)
            # For bonds/eurobonds: tenor is in YEARS; for bills/FD: tenor is in DAYS
            if 'BILL' in sub_type or sub_type in ('FD','MM','MONEY'):
                from datetime import timedelta
                maturity = trade_date + timedelta(days=int(tenor_val))
            else:
                # BOND / EUROBOND — tenor in years, use relativedelta
                try:
                    from dateutil.relativedelta import relativedelta
                    whole_years = int(tenor_val)
                    frac = tenor_val - whole_years
                    maturity = trade_date + relativedelta(years=whole_years)
                    if frac > 0:
                        from datetime import timedelta
                        maturity += timedelta(days=int(frac * 365))
                except ImportError:
                    from datetime import timedelta
                    maturity = trade_date + timedelta(days=int(tenor_val * 365))

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

@api_bp.route('/verify-ghana-card', methods=['POST'])
def verify_ghana_card():
    """
    Ghana Card NIA Verification Endpoint.
    Called from the signup page Step 1 (AJAX).
    Supports: NIA Direct (Persus), QoreID, SourceID, or DEMO mode.

    Request JSON: { "card_number": "GHA-000000000-0" }
    Response JSON: {
        "ok": true,
        "surname": "...", "first_names": "...",
        "nationality": "...", "gender": "...",
        "date_of_birth": "YYYY-MM-DD",
        "card_expiry": "YYYY-MM-DD"
    }
    NOTE: Height is NOT returned by any NIA API — it must be entered manually.
    """
    import os, re, requests as rq
    from flask import current_app

    data = request.get_json(silent=True) or {}
    card_number = (data.get('card_number') or '').strip().upper()

    # Validate format: GHA-000000000-0
    if not re.match(r'^GHA-\d{9}-\d$', card_number):
        return jsonify({'ok': False,
                        'error': 'Invalid Ghana Card format. Expected: GHA-000000000-0'}), 400

    provider  = os.environ.get('NIA_PROVIDER',  'qoreid').lower()
    api_url   = os.environ.get('NIA_API_URL',   '').strip()
    api_key   = os.environ.get('NIA_API_KEY',   '').strip()
    nia_token = os.environ.get('NIA_TOKEN',      '').strip()

    # ── DEMO MODE (no API key configured) ────────────────────────────────
    # Returns realistic placeholder data so the UI flow can be tested
    # without a live NIA contract.
    if not api_key:
        return jsonify({
            'ok':           True,
            'demo':         True,
            'surname':      'DEMO-SURNAME',
            'first_names':  'DEMO FIRSTNAME',
            'nationality':  'Ghanaian',
            'gender':       'Male',
            'date_of_birth':'1990-01-01',
            'card_expiry':  '2035-01-01',
            'message':      'Demo mode — configure NIA_API_KEY in .env for live verification.',
        })

    try:
        # ── OPTION A: NIA Direct (Persus) ────────────────────────────────
        if provider == 'nia_direct':
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}',
            }
            payload = {'idNumber': card_number}
            resp = rq.post(api_url, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            rd = resp.json()
            # NIA Persus response structure
            person = rd.get('data', rd)
            return jsonify({
                'ok':           True,
                'surname':      person.get('surname') or person.get('lastName', ''),
                'first_names':  (person.get('firstNames') or
                                 f"{person.get('firstName','')} {person.get('otherName','')}".strip()),
                'nationality':  person.get('nationality', 'Ghanaian'),
                'gender':       person.get('gender', ''),
                'date_of_birth':str(person.get('dateOfBirth') or person.get('dob') or ''),
                'card_expiry':  str(person.get('expiryDate') or person.get('dateOfExpiry') or ''),
            })

        # ── OPTION B: QoreID ─────────────────────────────────────────────
        elif provider == 'qoreid':
            # QoreID uses Bearer token auth
            auth_token = nia_token or api_key
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {auth_token}',
            }
            url = f"{api_url.rstrip('/')}/{card_number}"
            # QoreID requires firstName + lastName for matching (use wildcards)
            payload = {'firstname': '', 'lastname': ''}
            resp = rq.post(url, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            rd = resp.json()
            ghana_id = rd.get('ghana_id', rd.get('data', {}))
            fn = ghana_id.get('firstName', '')
            on = ghana_id.get('otherName', '')
            first_names = f"{fn} {on}".strip() if on else fn
            return jsonify({
                'ok':           True,
                'surname':      ghana_id.get('lastName', ''),
                'first_names':  first_names,
                'nationality':  ghana_id.get('nationality', 'Ghanaian'),
                'gender':       ghana_id.get('gender', ''),
                'date_of_birth':str(ghana_id.get('dateOfBirth') or ''),
                'card_expiry':  str(ghana_id.get('dateOfExpiry') or ''),
            })

        # ── OPTION C: SourceID ───────────────────────────────────────────
        else:  # sourceid
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': api_key,
            }
            payload = {
                'country': 'GHA',
                'cardNumber': card_number,
                'verificationLevel': 'basic',
                'reference': card_number.replace('-', ''),
            }
            resp = rq.post(api_url, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            rd = resp.json()
            person = rd.get('data', {})
            fn = person.get('firstName', '')
            ln = person.get('lastName', '')
            return jsonify({
                'ok':           True,
                'surname':      ln,
                'first_names':  fn,
                'nationality':  person.get('nationality', 'Ghanaian'),
                'gender':       person.get('gender', ''),
                'date_of_birth':str(person.get('dateOfBirth') or ''),
                'card_expiry':  str(person.get('expiryDate') or ''),
            })

    except rq.exceptions.Timeout:
        return jsonify({'ok': False,
                        'error': 'NIA verification service timed out. Please try again.'}), 504
    except rq.exceptions.RequestException as e:
        return jsonify({'ok': False,
                        'error': f'NIA verification unavailable: {str(e)[:120]}. '
                                  'You may enter your details manually.'}), 502
    except Exception as e:
        current_app.logger.error(f'Ghana Card verify error: {e}')
        return jsonify({'ok': False,
                        'error': 'Unexpected error during verification. Please enter details manually.'}), 500

# ── FACE ID ENDPOINTS ─────────────────────────────────────────────────────────

@api_bp.route('/face/descriptor', methods=['GET'])
@login_required
def get_face_descriptor():
    """Return stored face descriptor for the logged-in client (for comparison in browser)."""
    from flask_login import current_user
    from models import ClientUser
    if not hasattr(current_user, 'account_number'):
        return jsonify({'ok': False, 'error': 'Client access only'}), 403
    user = ClientUser.query.filter_by(account_number=current_user.account_number).first()
    if not user or not user.face_descriptor:
        return jsonify({'ok': False, 'enrolled': False})
    return jsonify({'ok': True, 'enrolled': True, 'descriptor': user.face_descriptor,
                    'enrolled_at': user.face_enrolled_at.isoformat() if user.face_enrolled_at else None})


@api_bp.route('/face/enroll', methods=['POST'])
@login_required
def enroll_face():
    """
    Enroll a face descriptor for the logged-in client.
    Receives a JSON-encoded 128-dimension Float32Array from the browser.
    No raw image data is stored — only the mathematical face vector.
    """
    from flask_login import current_user
    from models import ClientUser
    from datetime import datetime
    import json

    if not hasattr(current_user, 'account_number'):
        return jsonify({'ok': False, 'error': 'Client access only'}), 403

    data = request.get_json(silent=True) or {}
    descriptor = data.get('descriptor')  # Array of 128 floats

    if not descriptor or not isinstance(descriptor, list) or len(descriptor) != 128:
        return jsonify({'ok': False, 'error': 'Invalid face descriptor — expected 128-element array'}), 400

    # Validate all elements are numbers
    if not all(isinstance(v, (int, float)) for v in descriptor):
        return jsonify({'ok': False, 'error': 'Descriptor must contain numeric values'}), 400

    user = ClientUser.query.filter_by(account_number=current_user.account_number).first()
    if not user:
        return jsonify({'ok': False, 'error': 'User not found'}), 404

    user.face_descriptor  = json.dumps(descriptor)
    user.face_enrolled_at = datetime.utcnow()
    db.session.commit()

    from utils.notifications import audit
    audit('FACE_ENROLL', target=f'client:{current_user.account_number}')

    return jsonify({'ok': True, 'message': 'Face ID enrolled successfully.'})


@api_bp.route('/face/unenroll', methods=['POST'])
@login_required
def unenroll_face():
    """Remove Face ID enrollment for the logged-in client."""
    from flask_login import current_user
    from models import ClientUser

    if not hasattr(current_user, 'account_number'):
        return jsonify({'ok': False, 'error': 'Client access only'}), 403

    user = ClientUser.query.filter_by(account_number=current_user.account_number).first()
    if not user:
        return jsonify({'ok': False, 'error': 'User not found'}), 404

    user.face_descriptor  = None
    user.face_enrolled_at = None
    db.session.commit()

    from utils.notifications import audit
    audit('FACE_UNENROLL', target=f'client:{current_user.account_number}')

    return jsonify({'ok': True, 'message': 'Face ID has been removed.'})


@api_bp.route('/face/check-enrolled', methods=['GET'])
def face_check_enrolled():
    """
    Public endpoint: check if a given account has Face ID enrolled.
    Used by the login page to decide whether to offer Face ID login option.
    Only returns boolean — no biometric data exposed.
    """
    account_number = request.args.get('account', '').strip().upper()
    if not account_number:
        return jsonify({'enrolled': False})
    from models import ClientUser
    user = ClientUser.query.filter_by(account_number=account_number).first()
    enrolled = bool(user and user.face_descriptor)
    return jsonify({'enrolled': enrolled})


@api_bp.route('/face/descriptor-for-login', methods=['POST'])
def face_descriptor_for_login():
    """
    Semi-public endpoint: returns face descriptor for login verification.
    Requires account_number + phone (same credentials as normal login) to
    authenticate the request before returning the biometric data.
    The actual comparison happens entirely in the browser — never on server.
    """
    from models import ClientUser, ClientAccount
    import json

    data = request.get_json(silent=True) or {}
    account_number = (data.get('account_number') or '').strip().upper()
    phone          = (data.get('phone') or '').strip()

    if not account_number or not phone:
        return jsonify({'ok': False, 'error': 'Account number and phone required'}), 400

    # Verify credentials first
    user = ClientUser.query.filter_by(account_number=account_number, phone=phone).first()
    acc  = ClientAccount.query.filter_by(account_number=account_number).first()

    if not user or not acc or acc.status != 'APPROVED':
        return jsonify({'ok': False, 'error': 'Invalid credentials or account not approved'}), 401

    if not user.face_descriptor:
        return jsonify({'ok': False, 'error': 'Face ID not enrolled for this account'}), 404

    return jsonify({'ok': True, 'descriptor': user.face_descriptor})

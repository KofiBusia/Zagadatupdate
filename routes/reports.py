from flask import Blueprint, send_file, request, redirect, url_for, flash, render_template
from flask_login import login_required, current_user
from models import ClientAccount, Investment, Transaction
from reports.pdf_reports import generate_pvr, generate_statement, generate_global_report, tbl_style, lhf, DARK, GOLD, WHITE, LIGHT, GREEN, RED, GREY, DARK2
from datetime import datetime, date
import io

reports_bp = Blueprint('reports', __name__)

def _parse_date(s):
    if not s: return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try: return datetime.strptime(s, fmt).date()
        except: pass
    return None

@reports_bp.route('/pvr/<account_number>')
@login_required
def pvr(account_number):
    """Portfolio Valuation Report — accessible by admin and the account's own client."""
    from flask import session
    from models import ClientAccount
    # Client access: only own account
    if session.get('user_type') == 'client':
        if current_user.account_number != account_number:
            flash('Access denied.', 'error')
            return redirect(url_for('user.dashboard'))
    currency = request.args.get('currency', 'GHS').upper()
    # Validate currency
    valid_currencies = ['GHS','USD','EUR','GBP','CNY','NGN']
    if currency not in valid_currencies:
        currency = 'GHS'
    try:
        buf = generate_pvr(account_number, currency)
        fname = f'PVR_{account_number.replace("-","_")}_{date.today().strftime("%Y-%m-%d")}_{currency}.pdf'
        return send_file(buf, mimetype='application/pdf',
                         as_attachment=request.args.get('download') == '1',
                         download_name=fname)
    except Exception as e:
        flash(f'Report error: {e}', 'error')
        redirect_url = url_for('user.dashboard') if session.get('user_type') == 'client' else url_for('admin.dashboard')
        return redirect(request.referrer or redirect_url)

@reports_bp.route('/statement/<account_number>')
@login_required
def statement(account_number):
    """Transaction Statement — admin or own client; supports currency conversion."""
    from flask import session
    from models import ClientAccount
    if session.get('user_type') == 'client':
        if current_user.account_number != account_number:
            flash('Access denied.', 'error')
            return redirect(url_for('user.dashboard'))
    date_from = _parse_date(request.args.get('from'))
    date_to   = _parse_date(request.args.get('to'))
    currency  = request.args.get('currency', 'GHS').upper()
    valid_currencies = ['GHS','USD','EUR','GBP','CNY','NGN']
    if currency not in valid_currencies:
        currency = 'GHS'
    try:
        buf = generate_statement(account_number, date_from, date_to, currency=currency)
        fname = f'Statement_{account_number.replace("-","_")}_{date.today().strftime("%Y-%m-%d")}_{currency}.pdf'
        return send_file(buf, mimetype='application/pdf',
                         as_attachment=request.args.get('download') == '1',
                         download_name=fname)
    except Exception as e:
        flash(f'Statement error: {e}', 'error')
        redirect_url = url_for('user.dashboard') if session.get('user_type') == 'client' else url_for('admin.dashboard')
        return redirect(request.referrer or redirect_url)

@reports_bp.route('/global')
@login_required
def global_report():
    asset_class = request.args.get('asset_class')
    currency    = request.args.get('currency', 'GHS').upper()
    valid_currencies = ['GHS','USD','EUR','GBP','CNY','NGN']
    if currency not in valid_currencies:
        currency = 'GHS'
    try:
        buf = generate_global_report(asset_class, currency=currency)
        fname = f'GlobalReport_{date.today().strftime("%Y-%m-%d")}_{currency}.pdf'
        return send_file(buf, mimetype='application/pdf',
                         as_attachment=request.args.get('download') == '1',
                         download_name=fname)
    except Exception as e:
        flash(f'Report error: {e}', 'error')
        return redirect(request.referrer or url_for('admin.dashboard'))

@reports_bp.route('/menu')
@login_required
def menu():
    accounts = ClientAccount.query.filter_by(status='APPROVED').order_by(ClientAccount.full_name).all()
    return render_template('admin/reports_menu.html', accounts=accounts)

@reports_bp.route('/fees')
@login_required
def fees_report():
    from models import FeeTransaction, FeeType, ClientAccount
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.lib.pagesizes import A4, landscape
    from reports.pdf_reports import make_styles, tbl_style, lhf
    from datetime import date
    import io

    fee_txns = FeeTransaction.query.filter_by(status='APPLIED').all()
    accs     = {a.account_number: a for a in ClientAccount.query.all()}

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=2.2*cm, bottomMargin=1.8*cm)
    S = make_styles()
    story = []
    story.append(Paragraph('FEES REPORT — ALL ACCOUNTS', S['title']))
    story.append(Paragraph(f'Generated: {date.today().strftime("%d %b %Y")}', S['normal']))
    story.append(Spacer(1, 0.3*cm))

    # Summary by fee type
    by_type = {}
    for f in fee_txns:
        name = f.fee_type.name if f.fee_type else 'Unknown'
        by_type[name] = by_type.get(name, 0) + f.amount
    total_fees = sum(by_type.values())

    sum_hdr = ['Fee Type', 'Total Charged (GHS)', 'No. of Charges']
    sum_rows = [sum_hdr]
    for name, amt in sorted(by_type.items(), key=lambda x: -x[1]):
        count = sum(1 for f in fee_txns if (f.fee_type.name if f.fee_type else '') == name)
        sum_rows.append([name, f'{amt:,.2f}', str(count)])
    sum_rows.append(['TOTAL', f'{total_fees:,.2f}', str(len(fee_txns))])
    t_idx = len(sum_rows) - 1
    tbl = Table(sum_rows, colWidths=[8*cm, 7*cm, 4*cm])
    ts = tbl_style()
    ts.add('ALIGN', (1,0), (-1,-1), 'RIGHT')
    
    tbl.setStyle(ts)
    story.append(Paragraph('SUMMARY BY FEE TYPE', S['section']))
    story.append(tbl)
    story.append(Spacer(1, 0.4*cm))

    # Detail
    det_hdr = ['Date', 'Account', 'Client Name', 'Fee Type', 'AUM (GHS)', 'Rate%', 'Amount (GHS)', 'Period']
    det_rows = [det_hdr]
    for f in sorted(fee_txns, key=lambda x: x.created_at, reverse=True):
        acc = accs.get(f.account_number)
        det_rows.append([
            f.created_at.strftime('%d %b %Y'),
            f.account_number,
            acc.full_name if acc else '—',
            f.fee_type.name if f.fee_type else '—',
            f'{(f.aum_at_time or 0):,.2f}',
            f'{(f.rate_applied or 0):.4f}%',
            f'{f.amount:,.2f}',
            f"{f.period_from.strftime('%d %b %Y') if f.period_from else '—'} — {f.period_to.strftime('%d %b %Y') if f.period_to else '—'}"
        ])
    det_rows.append(['TOTAL', '', '', '', '', '', f'{total_fees:,.2f}', ''])
    t2_idx = len(det_rows) - 1
    cw2 = [2.5*cm, 2.5*cm, 5*cm, 4*cm, 4*cm, 2.5*cm, 3.5*cm, 5.5*cm]
    tbl2 = Table(det_rows, colWidths=cw2, repeatRows=1)
    ts2 = tbl_style()
    ts2.add('ALIGN', (4,0), (6,-1), 'RIGHT')
    
    tbl2.setStyle(ts2)
    story.append(Paragraph('DETAIL — ALL FEE CHARGES', S['section']))
    story.append(tbl2)

    def lhf(c, d):
        from reportlab.lib.pagesizes import landscape, A4
        w, h = landscape(A4)
        from reports.pdf_reports import header_footer as _hf
        c.saveState()
        c.setFillColor(DARK)
        c.rect(0, h-1.8*cm, w, 1.8*cm, fill=1, stroke=0)
        c.setFillColor(GOLD); c.rect(0, h-1.82*cm, w, 0.08*cm, fill=1, stroke=0)
        import os
        logo = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'img', 'logo.png')
        if os.path.exists(logo):
            c.drawImage(logo, 0.8*cm, h-1.65*cm, 1.3*cm, 1.3*cm, preserveAspectRatio=True, mask='auto')
        c.setFont('Helvetica-Bold', 13); c.setFillColor(WHITE)
        c.drawString(2.5*cm, h-1.1*cm, 'ZAGADAT CAPITAL')
        c.setFont('Helvetica', 9); c.setFillColor(GOLD)
        c.drawString(2.5*cm, h-1.5*cm, 'Fees Report')
        c.setFillColor(DARK); c.rect(0, 0, w, 1.2*cm, fill=1, stroke=0)
        c.setFillColor(GOLD); c.rect(0, 1.2*cm, w, 0.05*cm, fill=1, stroke=0)
        c.setFont('Helvetica', 7); c.setFillColor(LIGHT)
        c.drawString(0.8*cm, 0.45*cm, 'ZAGADAT CAPITAL — CONFIDENTIAL')
        c.restoreState()

    doc.build(story, onFirstPage=lhf, onLaterPages=lhf, )
    buf.seek(0)
    fname = f'FeesReport_{date.today().strftime("%Y-%m-%d")}.pdf'
    return send_file(buf, mimetype='application/pdf',
                     as_attachment=request.args.get('download')=='1',
                     download_name=fname)

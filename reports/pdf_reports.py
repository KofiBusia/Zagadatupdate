"""
Zagadat Capital — PDF Report Generator
All reports are LANDSCAPE A4, world-class institutional quality.
Supports multi-currency conversion at prevailing FX rates.
"""
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                  Spacer, HRFlowable, PageBreak, KeepTogether)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas as pdf_canvas
from models import ClientAccount, Investment, Transaction, FXRate
from utils.market_data import get_fx_rate
from datetime import date, datetime
import io, os

# ── BRAND PALETTE ─────────────────────────────────────────────────────────────
BLACK  = colors.HexColor('#0A0A0A')
GOLD   = colors.HexColor('#C9A84C')
GOLD2  = colors.HexColor('#E8C96D')
DARK   = colors.HexColor('#1A1A2E')
DARK2  = colors.HexColor('#111118')
LIGHT  = colors.HexColor('#E8E8E8')
WHITE  = colors.white
GREEN  = colors.HexColor('#27AE60')
RED    = colors.HexColor('#E74C3C')
GREY   = colors.HexColor('#8A8A9A')
BLUE   = colors.HexColor('#2980B9')
PURPLE = colors.HexColor('#8E44AD')
LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'img', 'logo.png')

# Landscape page dimensions
LW, LH = landscape(A4)   # 29.7cm × 21cm

ASSET_LABELS = {
    'MONEY_MARKET':    'Money Market',
    'GOVT_SECURITIES': 'Government Securities',
    'BONDS':           'Bonds',
    'EUROBONDS':       'Eurobonds',
    'GSE_EQUITIES':    'GSE Equities',
    'GLOBAL_EQUITIES': 'Global Equities',
    'PRIVATE_EQUITY':  'Private Equity',
    'PRIVATE_DEBT':    'Private Debt',
    'MUTUAL_FUNDS':    'Mutual Funds',
}

ASSET_COLOURS = {
    'MONEY_MARKET':    colors.HexColor('#1ABC9C'),
    'GOVT_SECURITIES': colors.HexColor('#2980B9'),
    'BONDS':           colors.HexColor('#8E44AD'),
    'EUROBONDS':       colors.HexColor('#6C3483'),
    'GSE_EQUITIES':    colors.HexColor('#C9A84C'),
    'GLOBAL_EQUITIES': colors.HexColor('#E67E22'),
    'PRIVATE_EQUITY':  colors.HexColor('#E74C3C'),
    'PRIVATE_DEBT':    colors.HexColor('#C0392B'),
    'MUTUAL_FUNDS':    colors.HexColor('#27AE60'),
}

# ── HELPERS ───────────────────────────────────────────────────────────────────
def fmt(v, d=2):
    if v is None: return '—'
    try: return f'{float(v):,.{d}f}'
    except: return str(v)

def fmt_pct(v):
    if v is None: return '—'
    try: return f'{float(v):.2f}%'
    except: return str(v)

def make_styles():
    styles = getSampleStyleSheet()
    base = dict(fontName='Helvetica', textColor=DARK)
    return {
        'title':   ParagraphStyle('t', fontSize=14, fontName='Helvetica-Bold',
                                  textColor=GOLD, spaceAfter=4, leading=18),
        'subtitle':ParagraphStyle('st', fontSize=9, fontName='Helvetica',
                                  textColor=GREY, spaceAfter=2),
        'section': ParagraphStyle('sec', fontSize=9, fontName='Helvetica-Bold',
                                  textColor=WHITE, backColor=DARK, spaceBefore=8,
                                  spaceAfter=2, leftIndent=4, leading=14),
        'normal':  ParagraphStyle('n', fontSize=8, fontName='Helvetica',
                                  textColor=DARK, leading=12),
        'small':   ParagraphStyle('s', fontSize=7, fontName='Helvetica',
                                  textColor=GREY, leading=10),
        'bold':    ParagraphStyle('b', fontSize=8, fontName='Helvetica-Bold',
                                  textColor=DARK),
        'right':   ParagraphStyle('r', fontSize=8, fontName='Helvetica',
                                  textColor=DARK, alignment=TA_RIGHT),
    }

def tbl_style(header_bg=DARK, stripe=True):
    ts = TableStyle([
        ('BACKGROUND',   (0, 0), (-1, 0), header_bg),
        ('TEXTCOLOR',    (0, 0), (-1, 0), WHITE),
        ('FONTNAME',     (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, 0), 7),
        ('ALIGN',        (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN',       (0, 0), (-1,-1), 'MIDDLE'),
        ('FONTNAME',     (0, 1), (-1,-1), 'Helvetica'),
        ('FONTSIZE',     (0, 1), (-1,-1), 7),
        ('TEXTCOLOR',    (0, 1), (-1,-1), DARK),
        ('ROWBACKGROUNDS',(0, 1), (-1,-1),
         [colors.HexColor('#F9F9F6'), WHITE] if stripe else [WHITE]),
        ('GRID',         (0, 0), (-1,-1), 0.25, colors.HexColor('#E0E0E0')),
        ('LINEBELOW',    (0, 0), (-1, 0), 1.0, GOLD),
        ('TOPPADDING',   (0, 0), (-1,-1), 3),
        ('BOTTOMPADDING',(0, 0), (-1,-1), 3),
        ('LEFTPADDING',  (0, 0), (-1,-1), 4),
        ('RIGHTPADDING', (0, 0), (-1,-1), 4),
    ])
    return ts

def total_row(ts, idx, bg=DARK, fg=GOLD):
    ts.add('BACKGROUND', (0, idx), (-1, idx), bg)
    ts.add('TEXTCOLOR',  (0, idx), (-1, idx), fg)
    ts.add('FONTNAME',   (0, idx), (-1, idx), 'Helvetica-Bold')
    ts.add('LINEABOVE',  (0, idx), (-1, idx), 0.5, GOLD)

# ── LANDSCAPE HEADER / FOOTER ─────────────────────────────────────────────────
def lhf(title_line='Portfolio Valuation Report'):
    """Returns a landscape header/footer function for use in doc.build()."""
    def _hf(canv, doc):
        canv.saveState()
        w, h = LW, LH
        # Top bar
        canv.setFillColor(DARK2)
        canv.rect(0, h - 1.6*cm, w, 1.6*cm, fill=1, stroke=0)
        canv.setFillColor(GOLD)
        canv.rect(0, h - 1.62*cm, w, 0.07*cm, fill=1, stroke=0)
        # Logo
        if os.path.exists(LOGO_PATH):
            canv.drawImage(LOGO_PATH, 0.7*cm, h - 1.45*cm, 1.1*cm, 1.1*cm,
                           preserveAspectRatio=True, mask='auto')
        canv.setFont('Helvetica-Bold', 12); canv.setFillColor(WHITE)
        canv.drawString(2.1*cm, h - 0.9*cm, 'ZAGADAT CAPITAL')
        canv.setFont('Helvetica', 8); canv.setFillColor(GOLD)
        canv.drawString(2.1*cm, h - 1.3*cm, title_line)
        # Right side header
        canv.setFont('Helvetica', 7); canv.setFillColor(LIGHT)
        canv.drawRightString(w - 0.7*cm, h - 0.85*cm,
                             f'Valuation Date: {date.today().strftime("%d %b %Y")}')
        canv.drawRightString(w - 0.7*cm, h - 1.2*cm,
                             f'Generated: {datetime.utcnow().strftime("%d %b %Y %H:%M UTC")}')
        # Footer
        canv.setFillColor(DARK2)
        canv.rect(0, 0, w, 1.0*cm, fill=1, stroke=0)
        canv.setFillColor(GOLD)
        canv.rect(0, 1.0*cm, w, 0.04*cm, fill=1, stroke=0)
        canv.setFont('Helvetica', 6.5); canv.setFillColor(LIGHT)
        canv.drawString(0.7*cm, 0.35*cm, 'ZAGADAT CAPITAL — CONFIDENTIAL — FOR AUTHORISED RECIPIENTS ONLY')
        canv.drawRightString(w - 0.7*cm, 0.35*cm,
                             f'Page {doc.page}')
        canv.restoreState()
    return _hf


# ═══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO VALUATION REPORT (PVR)
# ═══════════════════════════════════════════════════════════════════════════════
def generate_pvr(account_number, currency='GHS'):
    acc = ClientAccount.query.filter_by(account_number=account_number).first()
    if not acc:
        raise ValueError('Account not found')

    investments = Investment.query.filter_by(
        account_number=account_number, status='APPROVED').all()
    cash_ghs = acc.cash_balance

    # ── FX Setup ─────────────────────────────────────────────────────────────
    if currency == 'GHS':
        fx_rate  = 1.0
        fx_label = 'GHS'
        rate_note = 'GHS (Base Currency)'
    else:
        fx_rate  = get_fx_rate('GHS', currency)   # 1 GHS = X ccy
        if fx_rate == 0: fx_rate = 1.0
        rev_rate = get_fx_rate(currency, 'GHS')    # 1 ccy = Y GHS
        fx_label = currency
        rate_note = f'{currency}  (1 {currency} = GHS {rev_rate:.4f}  |  1 GHS = {currency} {fx_rate:.6f})'

    def c(ghs_val):
        """Convert a GHS value to the report currency."""
        return (ghs_val or 0) * fx_rate

    def c_inv(inv_val, inv_currency='GHS'):
        """Convert an investment's own-currency value to report currency via GHS."""
        if inv_currency == 'GHS':
            return (inv_val or 0) * fx_rate
        # inv_val is in inv_currency → convert to GHS → convert to report currency
        ghs = (inv_val or 0) * get_fx_rate(inv_currency, 'GHS')
        return ghs * fx_rate

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=1.2*cm, rightMargin=1.2*cm,
                            topMargin=1.9*cm, bottomMargin=1.4*cm)
    S = make_styles()
    story = []

    total_inv_ghs = sum(inv.computed_mkt_value for inv in investments)
    total_port_ghs = total_inv_ghs + cash_ghs
    by_class = {}
    for inv in investments:
        by_class[inv.asset_class] = by_class.get(inv.asset_class, 0) + inv.computed_mkt_value

    # ── ACCOUNT HEADER BLOCK ─────────────────────────────────────────────────
    info = [
        ['Fund / Client:', acc.full_name,
         'Account No.:', acc.account_number,
         'Report Currency:', fx_label],
        ['Account Type:', acc.account_type,
         'Custodian:', acc.custodian or 'N/A',
         'Valuation Date:', date.today().strftime('%d %b %Y')],
        ['Risk Profile:', acc.risk_profile or '—',
         'Investment Objective:', acc.investment_objective or '—',
         'FX Rate Note:', rate_note],
        ['Relationship Manager:',
         acc.relationship_manager.full_name if acc.relationship_manager else '—',
         'Base Currency:', acc.base_currency,
         'Statement as at:', datetime.utcnow().strftime('%d %b %Y %H:%M UTC')],
    ]
    info_tbl = Table(info, colWidths=[3.5*cm, 5.5*cm, 3.8*cm, 6*cm, 3.5*cm, 5.4*cm])
    info_ts = TableStyle([
        ('FONTNAME',  (0,0), (-1,-1), 'Helvetica'),
        ('FONTNAME',  (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME',  (2,0), (2,-1), 'Helvetica-Bold'),
        ('FONTNAME',  (4,0), (4,-1), 'Helvetica-Bold'),
        ('FONTSIZE',  (0,0), (-1,-1), 7.5),
        ('TEXTCOLOR', (0,0), (0,-1), GREY),
        ('TEXTCOLOR', (2,0), (2,-1), GREY),
        ('TEXTCOLOR', (4,0), (4,-1), GREY),
        ('TEXTCOLOR', (1,0), (1,-1), DARK),
        ('TEXTCOLOR', (3,0), (3,-1), DARK),
        ('TEXTCOLOR', (5,0), (5,-1), DARK),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F5F5F0')),
        ('BOX', (0,0), (-1,-1), 0.5, GOLD),
        ('LINEBELOW', (0,0), (-1,0), 0.25, colors.HexColor('#E0E0E0')),
    ])
    info_tbl.setStyle(info_ts)
    story.append(info_tbl)
    story.append(Spacer(1, 0.3*cm))

    # ── PORTFOLIO SUMMARY TABLE ───────────────────────────────────────────────
    story.append(Paragraph('PORTFOLIO SUMMARY', S['section']))
    sum_hdr = ['Asset Class', f'Mkt Value ({currency})', 'GHS Equivalent', 'Weight %', 'Colour']
    sum_rows = [['Asset Class', f'Mkt Value ({currency})', 'GHS Equivalent', 'Weight %']]
    for cls, lbl in ASSET_LABELS.items():
        mv_ghs = by_class.get(cls, 0)
        if mv_ghs:
            wt = (mv_ghs / total_port_ghs * 100) if total_port_ghs else 0
            sum_rows.append([lbl, fmt(c(mv_ghs)), fmt(mv_ghs), fmt_pct(wt)])
    cash_wt = (cash_ghs / total_port_ghs * 100) if total_port_ghs else 0
    sum_rows.append(['Cash & Bank Balances', fmt(c(cash_ghs)), fmt(cash_ghs), fmt_pct(cash_wt)])
    t_idx = len(sum_rows)
    sum_rows.append(['TOTAL FUND VALUE', fmt(c(total_port_ghs)), fmt(total_port_ghs), '100.00%'])
    cw_sum = [6.5*cm, 5*cm, 5*cm, 3*cm]
    sum_tbl = Table(sum_rows, colWidths=cw_sum)
    ts_sum = tbl_style()
    ts_sum.add('ALIGN', (1,0), (-1,-1), 'RIGHT')
    if currency != 'GHS':
        ts_sum.add('TEXTCOLOR', (2,1), (2,-1), GREY)
        ts_sum.add('FONTSIZE',  (2,1), (2,-1), 6.5)
    total_row(ts_sum, t_idx)
    sum_tbl.setStyle(ts_sum)
    story.append(sum_tbl)
    story.append(Spacer(1, 0.4*cm))

    # ═══ PER-ASSET-CLASS DETAIL SECTIONS ════════════════════════════════════

    # ── MONEY MARKET ──────────────────────────────────────────────────────────
    mm = [i for i in investments if i.asset_class == 'MONEY_MARKET']
    if mm:
        story.append(Paragraph('MONEY MARKET — Fixed Deposits & Call Accounts', S['section']))
        hdr = ['Trade Date', 'Issuer / Bank', 'Instrument', 'Tenor\n(days)',
               f'Principal\n({currency})', 'Rate %', 'Days\nRun',
               f'Accrued Int.\n({currency})', f'Mkt Value\n({currency})',
               'GHS Equiv.', 'Maturity', 'Wt. %']
        rows = [hdr]; tot = 0
        for i in mm:
            mv = i.computed_mkt_value; tot += mv
            wt = (mv / total_port_ghs * 100) if total_port_ghs else 0
            rows.append([
                i.trade_date.strftime('%d %b %Y') if i.trade_date else '—',
                i.issuer or '—', i.sub_type or 'Fixed Deposit',
                str(i.tenor or '—'),
                fmt(c(i.total_cost)), fmt_pct(i.interest_rate or i.coupon_rate),
                str(i.days_run), fmt(c(i.accrued_interest)), fmt(c(mv)),
                fmt(mv), # GHS equiv always
                i.maturity_date.strftime('%d %b %Y') if i.maturity_date else '—',
                fmt_pct(wt)
            ])
        rows.append(['TOTAL','','','','','','','',fmt(c(tot)),fmt(tot),'',''])
        cw = [2.1*cm,3*cm,2.5*cm,1.3*cm,2.3*cm,1.3*cm,1.3*cm,2.2*cm,2.3*cm,2.3*cm,2.2*cm,1.3*cm]
        _render_section(story, rows, cw, len(rows)-1)

    # ── GOVERNMENT SECURITIES ─────────────────────────────────────────────────
    gs = [i for i in investments if i.asset_class == 'GOVT_SECURITIES']
    if gs:
        story.append(Paragraph('GOVERNMENT SECURITIES — Treasury Bills, Notes & Bonds', S['section']))
        hdr = ['Trade Date', 'Issuer', 'Instrument', 'Tenor\n(days)',
               f'Face Value\n({currency})', 'Rate %', 'Days\nRun',
               f'Accrued Int.\n({currency})', f'Mkt Value\n({currency})',
               'GHS Equiv.', 'Maturity', 'Wt. %']
        rows = [hdr]; tot = 0
        for i in gs:
            mv = i.computed_mkt_value; tot += mv
            wt = (mv / total_port_ghs * 100) if total_port_ghs else 0
            rows.append([
                i.trade_date.strftime('%d %b %Y') if i.trade_date else '—',
                i.issuer or 'GOG', i.sub_type or 'T-Bill',
                str(i.tenor or '—'),
                fmt(c(i.face_value or i.total_cost)),
                fmt_pct(i.interest_rate or i.coupon_rate),
                str(i.days_run), fmt(c(i.accrued_interest)), fmt(c(mv)),
                fmt(mv),
                i.maturity_date.strftime('%d %b %Y') if i.maturity_date else '—',
                fmt_pct(wt)
            ])
        rows.append(['TOTAL','','','','','','','',fmt(c(tot)),fmt(tot),'',''])
        cw = [2.1*cm,2.5*cm,2.5*cm,1.3*cm,2.5*cm,1.3*cm,1.3*cm,2.2*cm,2.5*cm,2.5*cm,2.2*cm,1.3*cm]
        _render_section(story, rows, cw, len(rows)-1)

    # ── BONDS & EUROBONDS ─────────────────────────────────────────────────────
    bonds = [i for i in investments if i.asset_class in ('BONDS','EUROBONDS')]
    if bonds:
        story.append(Paragraph('BONDS & EUROBONDS — Corporate & Sovereign Debt', S['section']))
        hdr = ['Issue Date', 'Trade Date', 'Issuer / Borrower', 'Class',
               f'Face Value\n({currency})', 'Cpn %', 'Clean Px%',
               'Cpn Freq', 'Last Cpn', f'Accrued\n({currency})',
               f'Mkt Value\n({currency})', 'GHS Equiv.', 'Days to Mat.', 'Wt. %']
        rows = [hdr]; tot = 0
        for i in bonds:
            mv = i.computed_mkt_value; tot += mv
            wt = (mv / total_port_ghs * 100) if total_port_ghs else 0
            rows.append([
                i.issue_date.strftime('%d %b %y') if i.issue_date else '—',
                i.trade_date.strftime('%d %b %y') if i.trade_date else '—',
                i.issuer or '—',
                i.asset_class.replace('_', ' '),
                fmt(c(i.face_value)),
                fmt_pct(i.coupon_rate),
                f'{fmt(i.clean_price)}%' if i.clean_price else '—',
                str(i.coupon_freq or '—'),
                i.last_coupon_date.strftime('%d %b %y') if i.last_coupon_date else '—',
                fmt(c(i.accrued_interest)),
                fmt(c(mv)), fmt(mv),
                str(i.days_to_maturity or '—'), fmt_pct(wt)
            ])
        rows.append(['TOTAL','','','','','','','','','',fmt(c(tot)),fmt(tot),'',''])
        cw = [1.9*cm,1.9*cm,3.5*cm,2*cm,2.2*cm,1.3*cm,1.5*cm,1.3*cm,1.8*cm,1.8*cm,2.2*cm,2.2*cm,1.5*cm,1.2*cm]
        _render_section(story, rows, cw, len(rows)-1)

    # ── GSE EQUITIES ──────────────────────────────────────────────────────────
    gse = [i for i in investments if i.asset_class == 'GSE_EQUITIES']
    if gse:
        story.append(Paragraph('EQUITIES — GSE LISTED SECURITIES', S['section']))
        hdr = ['Symbol', 'Security Name', 'Sector', 'Trade Date',
               'Quantity', f'Unit Cost\n({currency})', f'Total Cost\n({currency})',
               f'Mkt Price\n({currency})', f'Mkt Value\n({currency})',
               'GHS Equiv.', f'Gain/Loss\n({currency})', 'Return %', 'Wt. %']
        rows = [hdr]; tot_cost = 0; tot_mv = 0
        for i in gse:
            mv = i.computed_mkt_value
            cost = i.total_cost or 0
            gain = mv - cost
            ret = (gain / cost * 100) if cost else 0
            tot_cost += cost; tot_mv += mv
            wt = (mv / total_port_ghs * 100) if total_port_ghs else 0
            rows.append([
                i.symbol or '—', i.security_name or '—', i.sector or '—',
                i.trade_date.strftime('%d %b %Y') if i.trade_date else '—',
                fmt(i.quantity, 0),
                fmt(c(i.unit_cost)), fmt(c(cost)),
                fmt(c(i.current_price)), fmt(c(mv)), fmt(mv),
                fmt(c(gain)), fmt_pct(ret), fmt_pct(wt)
            ])
        tot_gain = tot_mv - tot_cost
        tot_ret = (tot_gain / tot_cost * 100) if tot_cost else 0
        rows.append(['TOTAL','','','','',
                     '',fmt(c(tot_cost)),'',fmt(c(tot_mv)),fmt(tot_mv),
                     fmt(c(tot_gain)),fmt_pct(tot_ret),''])
        cw = [1.5*cm,3.5*cm,2.2*cm,1.8*cm,1.6*cm,1.8*cm,2.2*cm,1.8*cm,2.2*cm,2.2*cm,2*cm,1.5*cm,1.3*cm]
        _render_section(story, rows, cw, len(rows)-1)

    # ── GLOBAL EQUITIES ───────────────────────────────────────────────────────
    gl = [i for i in investments if i.asset_class == 'GLOBAL_EQUITIES']
    if gl:
        story.append(Paragraph('GLOBAL EQUITIES — International Listed Securities', S['section']))
        hdr = ['Symbol', 'Security Name', 'Exchange', 'Sector', 'Trade Date',
               'Quantity', 'Unit Cost\n(USD)', 'Mkt Price\n(USD)',
               f'Mkt Value\n({currency})', 'GHS Equiv.',
               f'Gain/Loss\n({currency})', 'Return %', 'Wt. %']
        rows = [hdr]; tot_mv = 0
        for i in gl:
            mv_ghs = i.computed_mkt_value  # already in GHS from model
            cost_ghs = (i.total_cost or 0) * get_fx_rate(i.currency or 'USD', 'GHS')
            gain_ghs = mv_ghs - cost_ghs
            ret = (gain_ghs / cost_ghs * 100) if cost_ghs else 0
            tot_mv += mv_ghs
            wt = (mv_ghs / total_port_ghs * 100) if total_port_ghs else 0
            rows.append([
                i.symbol or '—', i.security_name or '—',
                i.exchange or '—', i.sector or '—',
                i.trade_date.strftime('%d %b %Y') if i.trade_date else '—',
                fmt(i.quantity, 0),
                fmt(i.unit_cost), fmt(i.current_price),
                fmt(c(mv_ghs)), fmt(mv_ghs),
                fmt(c(gain_ghs)), fmt_pct(ret), fmt_pct(wt)
            ])
        rows.append(['TOTAL','','','','','','','',
                     fmt(c(tot_mv)),fmt(tot_mv),'','',''])
        cw = [1.4*cm,3.2*cm,2*cm,2*cm,1.8*cm,1.5*cm,1.8*cm,1.8*cm,2.2*cm,2.2*cm,2*cm,1.5*cm,1.3*cm]
        _render_section(story, rows, cw, len(rows)-1)

    # ── PRIVATE EQUITY ────────────────────────────────────────────────────────
    pe = [i for i in investments if i.asset_class == 'PRIVATE_EQUITY']
    if pe:
        story.append(Paragraph('PRIVATE EQUITY — Fund Investments & Direct Holdings', S['section']))
        hdr = ['Fund / Company', 'Sector', 'Vintage', 'Geography', 'Stage',
               f'Committed\n({currency})', f'Called\n({currency})',
               f'Distributions\n({currency})', f'NAV / Fair Value\n({currency})',
               'GHS Equiv.', 'MOIC (×)', 'IRR %', 'Wt. %']
        rows = [hdr]; tot_nav = 0
        for i in pe:
            nav_ghs = i.nav or i.computed_mkt_value; tot_nav += nav_ghs
            wt = (nav_ghs / total_port_ghs * 100) if total_port_ghs else 0
            # Auto-compute MOIC if called > 0 and nav available
            called = i.called or 0
            moic = i.moic if i.moic else ((nav_ghs + (i.distributions or 0)) / called if called > 0 else None)
            rows.append([
                i.security_name or i.issuer or '—',
                i.sector or '—', str(i.vintage_year or '—'),
                i.geography or '—', i.stage or '—',
                fmt(c(i.committed)), fmt(c(i.called)),
                fmt(c(i.distributions)),
                fmt(c(nav_ghs)), fmt(nav_ghs),
                f'{moic:.2f}×' if moic else '—',
                fmt_pct(i.irr), fmt_pct(wt)
            ])
        rows.append(['TOTAL','','','','','','','',
                     fmt(c(tot_nav)),fmt(tot_nav),'','',''])
        cw = [3.5*cm,2*cm,1.4*cm,2*cm,1.8*cm,2.2*cm,2*cm,2.5*cm,2.5*cm,2.5*cm,1.5*cm,1.3*cm,1.3*cm]
        _render_section(story, rows, cw, len(rows)-1)

    # ── PRIVATE DEBT ──────────────────────────────────────────────────────────
    pd = [i for i in investments if i.asset_class == 'PRIVATE_DEBT']
    if pd:
        story.append(Paragraph('PRIVATE DEBT — Direct Lending & Structured Credit', S['section']))
        hdr = ['Borrower / Fund', 'Sector', 'Instrument', 'Rating',
               f'Facility Size\n({currency})', f'Outstanding\n({currency})',
               'GHS Equiv.', 'Rate %', 'Maturity', 'PIK',
               f'Total Cost\n({currency})', f'Gain/Loss\n({currency})', 'Wt. %']
        rows = [hdr]; tot_out = 0
        for i in pd:
            outstanding_ghs = i.outstanding or i.computed_mkt_value
            tot_out += outstanding_ghs
            cost_ghs = i.total_cost or 0
            gain_ghs = outstanding_ghs - cost_ghs
            wt = (outstanding_ghs / total_port_ghs * 100) if total_port_ghs else 0
            rows.append([
                i.security_name or i.issuer or '—',
                i.sector or '—', i.sub_type or 'Term Loan',
                i.rating or '—',
                fmt(c(i.face_value or i.total_cost)),
                fmt(c(outstanding_ghs)), fmt(outstanding_ghs),
                fmt_pct(i.coupon_rate or i.interest_rate),
                i.maturity_date.strftime('%d %b %Y') if i.maturity_date else '—',
                'Yes' if i.pik else 'No',
                fmt(c(cost_ghs)), fmt(c(gain_ghs)), fmt_pct(wt)
            ])
        rows.append(['TOTAL','','','','',
                     fmt(c(tot_out)),fmt(tot_out),'','','','','',''])
        cw = [3.2*cm,2*cm,2*cm,1.3*cm,2.2*cm,2.2*cm,2.2*cm,1.3*cm,2*cm,1*cm,2.2*cm,2*cm,1.3*cm]
        _render_section(story, rows, cw, len(rows)-1)

    # ── MUTUAL FUNDS ──────────────────────────────────────────────────────────
    mf = [i for i in investments if i.asset_class == 'MUTUAL_FUNDS']
    if mf:
        story.append(Paragraph('MUTUAL FUNDS & UNIT TRUSTS', S['section']))
        hdr = ['Security Name', 'Fund Type', 'Trade Date',
               'Units / Shares', f'Unit Cost\n({currency})', f'Total Cost\n({currency})',
               f'NAV Price\n({currency})', f'Mkt Value\n({currency})',
               'GHS Equiv.', f'Gain/Loss\n({currency})', 'Return %', 'Wt. %']
        rows = [hdr]; tot_mv = 0; tot_cost = 0
        for i in mf:
            mv = i.computed_mkt_value; cost = i.total_cost or 0
            gain = mv - cost; ret = (gain/cost*100) if cost else 0
            tot_mv += mv; tot_cost += cost
            wt = (mv / total_port_ghs * 100) if total_port_ghs else 0
            rows.append([
                i.security_name or '—', i.sub_type or 'Mutual Fund',
                i.trade_date.strftime('%d %b %Y') if i.trade_date else '—',
                fmt(i.quantity),
                fmt(c(i.unit_cost)), fmt(c(cost)),
                fmt(c(i.current_price or i.nav)), fmt(c(mv)), fmt(mv),
                fmt(c(gain)), fmt_pct(ret), fmt_pct(wt)
            ])
        tot_gain = tot_mv - tot_cost
        tot_ret = (tot_gain / tot_cost * 100) if tot_cost else 0
        rows.append(['TOTAL','','','','',
                     fmt(c(tot_cost)),'',fmt(c(tot_mv)),fmt(tot_mv),
                     fmt(c(tot_gain)),fmt_pct(tot_ret),''])
        cw = [3.5*cm,2.2*cm,1.8*cm,1.8*cm,1.8*cm,2.2*cm,1.8*cm,2.2*cm,2.2*cm,2*cm,1.5*cm,1.3*cm]
        _render_section(story, rows, cw, len(rows)-1)

    # ── PORTFOLIO STRUCTURE PAGE ──────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph('PORTFOLIO STRUCTURE & ASSET ALLOCATION', S['section']))

    alloc_rows = [['Asset Class', f'Mkt Value ({currency})', 'GHS Equivalent', 'Weight %', 'Bar Chart']]
    for cls, lbl in ASSET_LABELS.items():
        mv_ghs = by_class.get(cls, 0)
        if mv_ghs:
            wt = (mv_ghs / total_port_ghs * 100) if total_port_ghs else 0
            bar = '█' * max(1, int(wt * 1.5))
            alloc_rows.append([lbl, fmt(c(mv_ghs)), fmt(mv_ghs), fmt_pct(wt), bar])
    cash_wt = (cash_ghs / total_port_ghs * 100) if total_port_ghs else 0
    alloc_rows.append(['Cash & Bank Balances', fmt(c(cash_ghs)), fmt(cash_ghs),
                       fmt_pct(cash_wt), '█' * max(1, int(cash_wt * 1.5))])
    t_idx = len(alloc_rows)
    alloc_rows.append(['TOTAL FUND VALUE', fmt(c(total_port_ghs)), fmt(total_port_ghs), '100.00%', ''])
    cw_a = [6*cm, 4.5*cm, 4.5*cm, 2.5*cm, 10*cm]
    alloc_tbl = Table(alloc_rows, colWidths=cw_a)
    ts_a = tbl_style()
    ts_a.add('ALIGN', (1,0), (3,-1), 'RIGHT')
    ts_a.add('TEXTCOLOR', (4,1), (4,-2), GOLD)
    ts_a.add('FONTNAME',  (4,1), (4,-2), 'Helvetica')
    ts_a.add('FONTSIZE',  (4,1), (4,-2), 6)
    total_row(ts_a, t_idx)
    alloc_tbl.setStyle(ts_a)
    story.append(alloc_tbl)

    # ── DISCLAIMER ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.4*cm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=GOLD))
    story.append(Spacer(1, 0.15*cm))
    if currency != 'GHS':
        disc_rate = f'Exchange rates: 1 {currency} = GHS {get_fx_rate(currency, "GHS"):.4f} (source: open.er-api.com). '
    else:
        disc_rate = ''
    disc = (f'All monetary values in {currency}. {disc_rate}'
            f'This report is prepared for informational purposes only and does not constitute investment advice. '
            f'Zagadat Capital Fund Management — Licensed by the Securities & Exchange Commission, Ghana. '
            f'Valuation Date: {date.today().strftime("%d %b %Y")} | '
            f'Generated: {datetime.utcnow().strftime("%d %b %Y %H:%M UTC")} — CONFIDENTIAL')
    story.append(Paragraph(disc, S['small']))

    doc.build(story, onFirstPage=lhf('Portfolio Valuation Report'),
              onLaterPages=lhf('Portfolio Valuation Report'))
    buf.seek(0)
    return buf


def _render_section(story, rows, col_widths, total_row_idx):
    """Build and append a styled section table."""
    tbl = Table(rows, colWidths=col_widths, repeatRows=1)
    ts = tbl_style()
    ts.add('ALIGN', (4, 0), (-1, -1), 'RIGHT')
    total_row(ts, total_row_idx)
    tbl.setStyle(ts)
    story.append(tbl)
    story.append(Spacer(1, 0.25*cm))


# ═══════════════════════════════════════════════════════════════════════════════
# TRANSACTION STATEMENT (all transactions, all currencies)
# ═══════════════════════════════════════════════════════════════════════════════
def generate_statement(account_number, date_from=None, date_to=None, currency='GHS'):
    acc = ClientAccount.query.filter_by(account_number=account_number).first()
    if not acc:
        raise ValueError('Account not found')

    # ALL transactions (approved + pending shown for completeness, only approved affect balance)
    query = Transaction.query.filter_by(account_number=account_number)
    if date_from:
        query = query.filter(Transaction.txn_date >= date_from)
    if date_to:
        query = query.filter(Transaction.txn_date <= date_to)
    txns = query.order_by(Transaction.txn_date.asc(), Transaction.id.asc()).all()

    # FX setup
    if currency == 'GHS':
        fx_rate  = 1.0
        fx_label = 'GHS'
        rate_note = 'Base Currency'
    else:
        fx_rate  = get_fx_rate('GHS', currency)
        if fx_rate == 0: fx_rate = 1.0
        rev_rate = get_fx_rate(currency, 'GHS')
        fx_label = currency
        rate_note = f'1 {currency} = GHS {rev_rate:.4f}'

    def c(ghs_val):
        return (ghs_val or 0) * fx_rate

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=1.2*cm, rightMargin=1.2*cm,
                            topMargin=1.9*cm, bottomMargin=1.4*cm)
    S = make_styles()
    story = []

    # ── Account header ────────────────────────────────────────────────────────
    period_from = date_from.strftime('%d %b %Y') if date_from else 'Inception'
    period_to   = date_to.strftime('%d %b %Y') if date_to else date.today().strftime('%d %b %Y')
    info = [
        ['Client:', acc.full_name, 'Account No.:', acc.account_number,
         'Report Currency:', f'{fx_label} ({rate_note})'],
        ['Account Type:', acc.account_type, 'Statement Period:',
         f'{period_from} — {period_to}', 'Generated:', datetime.utcnow().strftime('%d %b %Y %H:%M UTC')],
    ]
    info_tbl = Table(info, colWidths=[2.5*cm, 6*cm, 3.5*cm, 7*cm, 2.5*cm, 6*cm])
    info_ts = TableStyle([
        ('FONTNAME',(0,0),(-1,-1),'Helvetica'),
        ('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'),
        ('FONTNAME',(2,0),(2,-1),'Helvetica-Bold'),
        ('FONTNAME',(4,0),(4,-1),'Helvetica-Bold'),
        ('FONTSIZE',(0,0),(-1,-1),7.5),
        ('TEXTCOLOR',(0,0),(0,-1),GREY),
        ('TEXTCOLOR',(2,0),(2,-1),GREY),
        ('TEXTCOLOR',(4,0),(4,-1),GREY),
        ('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#F5F5F0')),
        ('BOX',(0,0),(-1,-1),0.5,GOLD),
        ('TOPPADDING',(0,0),(-1,-1),2),
        ('BOTTOMPADDING',(0,0),(-1,-1),2),
    ])
    info_tbl.setStyle(info_ts)
    story.append(info_tbl)
    story.append(Spacer(1, 0.3*cm))

    # ── Transaction table ─────────────────────────────────────────────────────
    hdr = ['Date', 'Type', 'Description', 'Reference',
           'Orig. Currency', f'Orig. Amount', f'GHS Amount',
           f'Report ({currency})\nDebit', f'Report ({currency})\nCredit',
           'Status', f'Running Balance\n({currency})']
    rows = [hdr]
    balance = 0.0
    CREDIT_TYPES = {'DEPOSIT','TRANSFER_IN','DIVIDEND','COUPON','SELL'}

    for t in txns:
        ghs_amt = t.amount_ghs if t.amount_ghs is not None else (
            t.amount * (t.fx_rate_used or 1.0) if t.fx_rate_used else t.amount
        )
        rpt_amt = c(ghs_amt)  # in report currency
        is_credit = t.txn_type in CREDIT_TYPES
        if t.status == 'APPROVED':
            if is_credit:
                balance += rpt_amt
            else:
                balance -= rpt_amt

        debit_col  = fmt(rpt_amt) if not is_credit and t.status == 'APPROVED' else '—'
        credit_col = fmt(rpt_amt) if is_credit and t.status == 'APPROVED' else '—'
        bal_col    = fmt(balance) if t.status == 'APPROVED' else '—'

        rows.append([
            t.txn_date.strftime('%d %b %Y') if t.txn_date else '—',
            t.txn_type.replace('_', ' '),
            (t.description or '—')[:50],
            t.reference or '—',
            t.currency,
            fmt(t.amount),
            fmt(ghs_amt),
            debit_col,
            credit_col,
            t.status,
            bal_col,
        ])

    # Closing balance row
    t_idx = len(rows)
    rows.append(['', '', '', 'CLOSING BALANCE', '', '', '',
                 '', '', '', fmt(balance)])

    cw = [2*cm, 2.2*cm, 5.5*cm, 2.5*cm, 2*cm, 2*cm, 2.2*cm, 2.3*cm, 2.3*cm, 1.8*cm, 2.5*cm]
    tbl = Table(rows, colWidths=cw, repeatRows=1)
    ts = tbl_style()
    ts.add('ALIGN', (5,0), (-1,-1), 'RIGHT')

    # Colour status column
    for row_idx, t in enumerate(txns, start=1):
        col = GREEN if t.status == 'APPROVED' else (RED if t.status == 'REJECTED' else colors.HexColor('#E67E22'))
        ts.add('TEXTCOLOR', (9, row_idx), (9, row_idx), col)
        ts.add('FONTSIZE',  (9, row_idx), (9, row_idx), 6)

    # Colour debit/credit columns
    for row_idx, t in enumerate(txns, start=1):
        is_credit = t.txn_type in CREDIT_TYPES
        if t.status == 'APPROVED':
            if is_credit:
                ts.add('TEXTCOLOR', (8, row_idx), (8, row_idx), GREEN)
            else:
                ts.add('TEXTCOLOR', (7, row_idx), (7, row_idx), RED)

    total_row(ts, t_idx)
    tbl.setStyle(ts)
    story.append(tbl)

    # Summary
    story.append(Spacer(1, 0.3*cm))
    tot_credits = sum(c(t.amount_ghs if t.amount_ghs is not None else t.amount)
                      for t in txns if t.status == 'APPROVED' and t.txn_type in CREDIT_TYPES)
    tot_debits  = sum(c(t.amount_ghs if t.amount_ghs is not None else t.amount)
                      for t in txns if t.status == 'APPROVED' and t.txn_type not in CREDIT_TYPES)
    summary_data = [
        ['', f'Total Credits ({currency}):', fmt(tot_credits),
         f'Total Debits ({currency}):', fmt(tot_debits),
         f'Net Balance ({currency}):', fmt(balance)]
    ]
    sum_tbl = Table(summary_data, colWidths=[6*cm, 4*cm, 3*cm, 4*cm, 3*cm, 4*cm, 3*cm])
    sum_ts = TableStyle([
        ('FONTNAME',(0,0),(-1,-1),'Helvetica-Bold'),
        ('FONTSIZE',(0,0),(-1,-1),8),
        ('BACKGROUND',(0,0),(-1,-1),DARK),
        ('TEXTCOLOR',(0,0),(-1,-1),WHITE),
        ('TEXTCOLOR',(2,0),(2,0),GREEN),
        ('TEXTCOLOR',(4,0),(4,0),RED),
        ('TEXTCOLOR',(6,0),(6,0),GOLD),
        ('ALIGN',(2,0),(-1,-1),'RIGHT'),
        ('BOX',(0,0),(-1,-1),0.5,GOLD),
        ('TOPPADDING',(0,0),(-1,-1),5),
        ('BOTTOMPADDING',(0,0),(-1,-1),5),
    ])
    sum_tbl.setStyle(sum_ts)
    story.append(sum_tbl)

    # Disclaimer
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=GOLD))
    disc = (f'Statement prepared for {acc.full_name} ({acc.account_number}). '
            f'Report currency: {fx_label}. '
            f'{"Exchange rate: " + rate_note + ". " if currency != "GHS" else ""}'
            f'Only APPROVED transactions affect cash balances. '
            f'Zagadat Capital — Licensed by the Securities & Exchange Commission, Ghana. '
            f'Generated: {datetime.utcnow().strftime("%d %b %Y %H:%M UTC")} — CONFIDENTIAL')
    story.append(Spacer(1, 0.15*cm))
    story.append(Paragraph(disc, S['small']))

    doc.build(story,
              onFirstPage=lhf('Transaction Statement'),
              onLaterPages=lhf('Transaction Statement'))
    buf.seek(0)
    return buf


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL AUM REPORT
# ═══════════════════════════════════════════════════════════════════════════════
def generate_global_report(asset_class_filter=None, currency='GHS'):
    query = Investment.query.filter_by(status='APPROVED')
    if asset_class_filter:
        query = query.filter_by(asset_class=asset_class_filter)
    investments = query.all()

    if currency == 'GHS':
        fx_rate = 1.0; fx_label = 'GHS'
    else:
        fx_rate = get_fx_rate('GHS', currency)
        if fx_rate == 0: fx_rate = 1.0
        fx_label = currency

    def c(v): return (v or 0) * fx_rate

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=1.2*cm, rightMargin=1.2*cm,
                            topMargin=1.9*cm, bottomMargin=1.4*cm)
    S = make_styles()
    story = []

    title_sfx = f' ({asset_class_filter.replace("_"," ")})' if asset_class_filter else ''
    story.append(Paragraph(f'GLOBAL PORTFOLIO REPORT — ALL ACCOUNTS{title_sfx}', S['title']))
    story.append(Paragraph(
        f'As at {date.today().strftime("%d %b %Y")} | Currency: {fx_label} | '
        f'Active Accounts: {ClientAccount.query.filter_by(status="APPROVED").count()}',
        S['subtitle']))
    story.append(Spacer(1, 0.3*cm))

    by_class = {}
    for inv in investments:
        by_class[inv.asset_class] = by_class.get(inv.asset_class, 0) + inv.computed_mkt_value
    all_accounts = ClientAccount.query.filter_by(status='APPROVED').all()
    total_cash = sum(acc.cash_balance for acc in all_accounts)
    total_inv  = sum(by_class.values())
    grand_total = total_inv + total_cash

    # Summary by asset class
    story.append(Paragraph('AUM SUMMARY BY ASSET CLASS', S['section']))
    sum_rows = [['Asset Class', f'Mkt Value ({currency})', 'GHS Equivalent', 'Weight %', '# Holdings']]
    for cls, lbl in ASSET_LABELS.items():
        mv = by_class.get(cls, 0)
        cnt = sum(1 for i in investments if i.asset_class == cls)
        wt  = (mv / grand_total * 100) if grand_total else 0
        if mv:
            sum_rows.append([lbl, fmt(c(mv)), fmt(mv), fmt_pct(wt), str(cnt)])
    sum_rows.append(['Cash & Bank Balances', fmt(c(total_cash)), fmt(total_cash),
                     fmt_pct(total_cash/grand_total*100 if grand_total else 0), '—'])
    t_idx = len(sum_rows)
    sum_rows.append(['GRAND TOTAL AUM', fmt(c(grand_total)), fmt(grand_total),
                     '100.00%', str(len(investments))])
    cw = [7*cm, 5*cm, 5*cm, 3*cm, 3*cm]
    sum_tbl = Table(sum_rows, colWidths=cw)
    ts = tbl_style()
    ts.add('ALIGN', (1,0), (-1,-1), 'RIGHT')
    total_row(ts, t_idx)
    sum_tbl.setStyle(ts)
    story.append(sum_tbl)
    story.append(Spacer(1, 0.4*cm))

    # Per-account breakdown
    story.append(Paragraph('ACCOUNT BREAKDOWN', S['section']))
    det_rows = [['Account No.', 'Client Name', 'Account Type',
                 f'Investments ({currency})', f'Cash ({currency})',
                 f'Portfolio Value ({currency})', 'GHS Total', 'Weight %']]
    for acc in sorted(all_accounts, key=lambda a: a.total_portfolio_value, reverse=True):
        invs_acc = [i for i in investments if i.account_number == acc.account_number]
        acc_mv   = sum(i.computed_mkt_value for i in invs_acc)
        cash_b   = acc.cash_balance
        total    = acc_mv + cash_b
        wt       = (total / grand_total * 100) if grand_total else 0
        det_rows.append([
            acc.account_number, acc.full_name, acc.account_type,
            fmt(c(acc_mv)), fmt(c(cash_b)), fmt(c(total)), fmt(total), fmt_pct(wt)
        ])
    t2_idx = len(det_rows)
    det_rows.append(['TOTAL','','','','','',fmt(grand_total),'100.00%'])
    cw2 = [3*cm, 5.5*cm, 3.2*cm, 3.8*cm, 3.5*cm, 3.8*cm, 3.5*cm, 2*cm]
    det_tbl = Table(det_rows, colWidths=cw2, repeatRows=1)
    ts2 = tbl_style()
    ts2.add('ALIGN', (3,0), (-1,-1), 'RIGHT')
    total_row(ts2, t2_idx)
    det_tbl.setStyle(ts2)
    story.append(det_tbl)

    doc.build(story,
              onFirstPage=lhf('Global Portfolio Report'),
              onLaterPages=lhf('Global Portfolio Report'))
    buf.seek(0)
    return buf


# Keep backward-compat aliases used elsewhere
summary_table_style = tbl_style
total_row_style = lambda idx: []
header_footer = lhf()
NumberedCanvas = None  # no longer used — page numbers in footer directly

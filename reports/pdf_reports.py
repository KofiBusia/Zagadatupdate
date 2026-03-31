from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                  Spacer, Image, HRFlowable, PageBreak, KeepTogether)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas
from reportlab.graphics.shapes import Drawing, Rect, String
from models import ClientAccount, Investment, Transaction, FXRate
from utils.market_data import get_fx_rate
from datetime import date, datetime
import io, os

# ── BRAND COLOURS ─────────────────────────────────────────────────────────────
BLACK   = colors.HexColor('#0A0A0A')
GOLD    = colors.HexColor('#C9A84C')
DARK    = colors.HexColor('#1A1A2E')
MEDIUM  = colors.HexColor('#16213E')
LIGHT   = colors.HexColor('#E8E8E8')
WHITE   = colors.white
ACCENT  = colors.HexColor('#C9A84C')
GREEN   = colors.HexColor('#27AE60')
RED     = colors.HexColor('#E74C3C')
GREY    = colors.HexColor('#95A5A6')
LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'img', 'logo.png')

def fmt(v, decimals=2):
    if v is None: return '-'
    try:
        return f'{float(v):,.{decimals}f}'
    except: return str(v)

def fmt_pct(v):
    if v is None: return '-'
    try: return f'{float(v):.2f}%'
    except: return str(v)

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        self.setFont('Helvetica', 8)
        self.setFillColor(GREY)
        self.drawRightString(A4[0] - 1.5*cm, 1*cm,
                             f'Page {self._pageNumber} of {page_count}')
        self.drawString(1.5*cm, 1*cm, 'ZAGADAT CAPITAL — CONFIDENTIAL')

def header_footer(canvas_obj, doc):
    canvas_obj.saveState()
    w, h = A4
    # Top bar
    canvas_obj.setFillColor(DARK)
    canvas_obj.rect(0, h - 1.8*cm, w, 1.8*cm, fill=1, stroke=0)
    # Gold accent line
    canvas_obj.setFillColor(GOLD)
    canvas_obj.rect(0, h - 1.82*cm, w, 0.08*cm, fill=1, stroke=0)
    # Logo
    if os.path.exists(LOGO_PATH):
        canvas_obj.drawImage(LOGO_PATH, 0.8*cm, h - 1.65*cm, 1.3*cm, 1.3*cm,
                             preserveAspectRatio=True, mask='auto')
    canvas_obj.setFont('Helvetica-Bold', 13)
    canvas_obj.setFillColor(WHITE)
    canvas_obj.drawString(2.5*cm, h - 1.1*cm, 'ZAGADAT CAPITAL')
    canvas_obj.setFont('Helvetica', 9)
    canvas_obj.setFillColor(GOLD)
    canvas_obj.drawString(2.5*cm, h - 1.5*cm, 'Fund Management & Portfolio Valuation Report')
    # Date top right
    canvas_obj.setFont('Helvetica', 8)
    canvas_obj.setFillColor(LIGHT)
    canvas_obj.drawRightString(w - 0.8*cm, h - 1.0*cm, f'Valuation Date: {date.today().strftime("%d %b %Y")}')
    canvas_obj.drawRightString(w - 0.8*cm, h - 1.4*cm, f'Generated: {datetime.utcnow().strftime("%d %b %Y %H:%M UTC")}')
    # Footer
    canvas_obj.setFillColor(DARK)
    canvas_obj.rect(0, 0, w, 1.2*cm, fill=1, stroke=0)
    canvas_obj.setFillColor(GOLD)
    canvas_obj.rect(0, 1.2*cm, w, 0.05*cm, fill=1, stroke=0)
    canvas_obj.setFont('Helvetica', 7)
    canvas_obj.setFillColor(LIGHT)
    canvas_obj.drawString(0.8*cm, 0.45*cm, 'ZAGADAT CAPITAL — For Authorised Recipients Only')
    canvas_obj.restoreState()

def make_styles():
    styles = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('title', fontSize=16, textColor=DARK, fontName='Helvetica-Bold',
                                 spaceAfter=6, spaceBefore=4),
        'section': ParagraphStyle('section', fontSize=11, textColor=DARK, fontName='Helvetica-Bold',
                                   spaceAfter=4, spaceBefore=8, backColor=LIGHT, leftIndent=4, rightIndent=4),
        'sub': ParagraphStyle('sub', fontSize=9, textColor=DARK, fontName='Helvetica-Bold',
                               spaceAfter=3, spaceBefore=6),
        'normal': ParagraphStyle('normal', fontSize=8, textColor=DARK, fontName='Helvetica', spaceAfter=2),
        'small': ParagraphStyle('small', fontSize=7, textColor=GREY, fontName='Helvetica', spaceAfter=1),
        'right': ParagraphStyle('right', fontSize=8, textColor=DARK, fontName='Helvetica',
                                 alignment=TA_RIGHT),
        'label': ParagraphStyle('label', fontSize=8, textColor=GREY, fontName='Helvetica'),
        'value': ParagraphStyle('value', fontSize=10, textColor=DARK, fontName='Helvetica-Bold'),
    }

def summary_table_style(header_bg=DARK):
    return TableStyle([
        ('BACKGROUND',   (0,0), (-1,0), header_bg),
        ('TEXTCOLOR',    (0,0), (-1,0), WHITE),
        ('FONTNAME',     (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',     (0,0), (-1,0), 8),
        ('ALIGN',        (0,0), (-1,0), 'CENTER'),
        ('VALIGN',       (0,0), (-1,-1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, colors.HexColor('#F7F7F7')]),
        ('FONTNAME',     (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE',     (0,1), (-1,-1), 7.5),
        ('GRID',         (0,0), (-1,-1), 0.3, colors.HexColor('#DDDDDD')),
        ('LEFTPADDING',  (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING',   (0,0), (-1,-1), 3),
        ('BOTTOMPADDING',(0,0), (-1,-1), 3),
        ('LINEBELOW',    (0,0), (-1,0), 1, GOLD),
    ])

def total_row_style(idx):
    return [
        ('BACKGROUND',  (0,idx), (-1,idx), DARK),
        ('TEXTCOLOR',   (0,idx), (-1,idx), GOLD),
        ('FONTNAME',    (0,idx), (-1,idx), 'Helvetica-Bold'),
        ('FONTSIZE',    (0,idx), (-1,idx), 8),
    ]

# ══════════════════════════════════════════════════════════════════════════════
# INDIVIDUAL PORTFOLIO VALUATION REPORT (PVR)
# ══════════════════════════════════════════════════════════════════════════════
def generate_pvr(account_number, currency='GHS'):
    acc = ClientAccount.query.filter_by(account_number=account_number).first()
    if not acc:
        raise ValueError('Account not found')

    investments = Investment.query.filter_by(account_number=account_number, status='APPROVED').all()
    cash = acc.cash_balance

    # FX conversion
    fx = get_fx_rate('GHS', currency) if currency != 'GHS' else 1.0
    if currency == 'GHS':
        fx_label = 'GHS'
    else:
        fx_inv = get_fx_rate(currency, 'GHS')
        fx_label = f'{currency} (1 {currency} = GHS {fx_inv:.4f})'
        fx = 1.0 / fx_inv if fx_inv else 1.0

    def c(val):
        return val * fx if val else 0.0

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=2.2*cm, bottomMargin=1.8*cm)
    S = make_styles()
    story = []

    # ── ACCOUNT SUMMARY BANNER ────────────────────────────────────────────────
    total_inv = sum(inv.computed_mkt_value for inv in investments)
    total_portfolio = total_inv + cash

    info_data = [
        ['Fund:', acc.full_name,                       'Account No.:', acc.account_number],
        ['Custodian:', acc.custodian or 'ACCRA',       'Account Type:', acc.account_type],
        ['Currency:', fx_label,                         'Valuation Date:', date.today().strftime('%d %b %Y')],
        ['Risk Profile:', acc.risk_profile or '-',     'Base Currency:', acc.base_currency],
    ]
    info_table = Table(info_data, colWidths=[3*cm, 6.5*cm, 3.2*cm, 5.3*cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME',  (0,0), (-1,-1), 'Helvetica'),
        ('FONTNAME',  (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME',  (2,0), (2,-1), 'Helvetica-Bold'),
        ('FONTSIZE',  (0,0), (-1,-1), 8),
        ('TEXTCOLOR', (0,0), (0,-1), GREY),
        ('TEXTCOLOR', (2,0), (2,-1), GREY),
        ('TEXTCOLOR', (1,0), (1,-1), DARK),
        ('TEXTCOLOR', (3,0), (3,-1), DARK),
        ('VALIGN',    (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',(0,0), (-1,-1), 2),
        ('BOTTOMPADDING',(0,0),(-1,-1), 2),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.3*cm))

    # ── ASSET ALLOCATION SUMMARY ──────────────────────────────────────────────
    asset_labels = {
        'MONEY_MARKET': 'Money Market', 'GOVT_SECURITIES': 'Gov. Securities',
        'BONDS': 'Bonds', 'EUROBONDS': 'Eurobonds',
        'GSE_EQUITIES': 'GSE Equities', 'GLOBAL_EQUITIES': 'Global Equities',
        'PRIVATE_EQUITY': 'Private Equity', 'PRIVATE_DEBT': 'Private Debt',
        'MUTUAL_FUNDS': 'Mutual Funds',
    }

    by_class = {}
    for inv in investments:
        mv = inv.computed_mkt_value
        by_class[inv.asset_class] = by_class.get(inv.asset_class, 0) + mv

    summary_header = ['Asset Class', f'Mkt Value ({currency})', 'Weight %']
    summary_rows = [summary_header]
    for cls, lbl in asset_labels.items():
        mv = by_class.get(cls, 0)
        wt = (mv / total_portfolio * 100) if total_portfolio else 0
        if mv:
            summary_rows.append([lbl, fmt(c(mv)), fmt_pct(wt)])
    cash_wt = (cash / total_portfolio * 100) if total_portfolio else 0
    summary_rows.append(['Cash & Bank Balances', fmt(c(cash)), fmt_pct(cash_wt)])
    total_row = ['TOTAL FUND VALUE', fmt(c(total_portfolio)), '100.00%']
    summary_rows.append(total_row)
    t_idx = len(summary_rows) - 1

    sum_tbl = Table(summary_rows, colWidths=[6*cm, 5*cm, 3.5*cm])
    ts = summary_table_style()
    ts.add('ALIGN', (1,0), (-1,-1), 'RIGHT')
    for s_idx, _ in enumerate(summary_rows):
        pass
    for ext in total_row_style(t_idx):
        ts.add(*ext)
    sum_tbl.setStyle(ts)
    story.append(Paragraph('PORTFOLIO SUMMARY', S['section']))
    story.append(sum_tbl)
    story.append(Spacer(1, 0.4*cm))

    # ── MONEY MARKET ──────────────────────────────────────────────────────────
    mm_invs = [i for i in investments if i.asset_class == 'MONEY_MARKET']
    if mm_invs:
        story.append(Paragraph('MONEY MARKET — Fixed Deposits & Call Accounts', S['section']))
        hdr = ['Invest. Date', 'Issuer', 'Security', 'Tenor', f'Principal ({currency})',
               'Rate %', 'Days Run', f'Accrued ({currency})', f'Mkt Value ({currency})', 'Maturity', 'Wt. %']
        rows = [hdr]
        tot_mv = 0
        for i in mm_invs:
            mv = i.computed_mkt_value
            tot_mv += mv
            wt = (mv / total_portfolio * 100) if total_portfolio else 0
            rows.append([
                i.trade_date.strftime('%d %b %Y') if i.trade_date else '-',
                i.issuer or '-', i.sub_type or '-',
                str(i.tenor or '-'),
                fmt(c(i.total_cost)),
                fmt(i.interest_rate or i.coupon_rate),
                str(i.days_run),
                fmt(c(i.accrued_interest)),
                fmt(c(mv)),
                i.maturity_date.strftime('%d %b %Y') if i.maturity_date else '-',
                fmt_pct(wt)
            ])
        rows.append(['TOTAL', '', '', '', '', '', '', '', fmt(c(tot_mv)), '', ''])
        t_idx2 = len(rows)-1
        cw = [2.2*cm,3*cm,2.5*cm,1.2*cm,2.8*cm,1.3*cm,1.5*cm,2.2*cm,2.8*cm,2.2*cm,1.5*cm]
        tbl = Table(rows, colWidths=cw, repeatRows=1)
        ts2 = summary_table_style()
        ts2.add('ALIGN', (4,0), (-1,-1), 'RIGHT')
        for ext in total_row_style(t_idx2):
            ts2.add(*ext)
        tbl.setStyle(ts2)
        story.append(tbl)
        story.append(Spacer(1, 0.3*cm))

    # ── GOVERNMENT SECURITIES ─────────────────────────────────────────────────
    gs_invs = [i for i in investments if i.asset_class == 'GOVT_SECURITIES']
    if gs_invs:
        story.append(Paragraph('GOVERNMENT SECURITIES — Treasury Bills & Notes', S['section']))
        hdr = ['Invest. Date', 'Issuer', 'Security', 'Tenor', f'Principal ({currency})',
               'Rate %', 'Days Run', f'Accrued ({currency})', f'Mkt Value ({currency})', 'Maturity', 'Wt. %']
        rows = [hdr]
        tot_mv = 0
        for i in gs_invs:
            mv = i.computed_mkt_value
            tot_mv += mv
            wt = (mv / total_portfolio * 100) if total_portfolio else 0
            rows.append([
                i.trade_date.strftime('%d %b %Y') if i.trade_date else '-',
                i.issuer or 'GOG', i.sub_type or '-', str(i.tenor or '-'),
                fmt(c(i.total_cost)), fmt(i.interest_rate),
                str(i.days_run), fmt(c(i.accrued_interest)),
                fmt(c(mv)),
                i.maturity_date.strftime('%d %b %Y') if i.maturity_date else '-',
                fmt_pct(wt)
            ])
        rows.append(['TOTAL', '', '', '', '', '', '', '', fmt(c(tot_mv)), '', ''])
        t_idx2 = len(rows)-1
        cw = [2.2*cm,2*cm,2.5*cm,1.2*cm,2.8*cm,1.3*cm,1.5*cm,2.2*cm,2.8*cm,2.2*cm,1.5*cm]
        tbl = Table(rows, colWidths=cw, repeatRows=1)
        ts2 = summary_table_style()
        ts2.add('ALIGN', (4,0), (-1,-1), 'RIGHT')
        for ext in total_row_style(t_idx2):
            ts2.add(*ext)
        tbl.setStyle(ts2)
        story.append(tbl)
        story.append(Spacer(1, 0.3*cm))

    # ── BONDS & EUROBONDS ─────────────────────────────────────────────────────
    bond_invs = [i for i in investments if i.asset_class in ('BONDS', 'EUROBONDS')]
    if bond_invs:
        story.append(Paragraph('BONDS & EUROBONDS', S['section']))
        hdr = ['Issue Dt', 'Trade Dt', 'Issuer', f'Face Val ({currency})', 'Clean Px%',
               'Tenor', 'Cpn Freq', 'Last Cpn', 'Rate%', 'Days Run',
               f'Accrued ({currency})', f'Mkt Value ({currency})', 'Days Mat.', 'YTM%', 'Wt.%']
        rows = [hdr]
        tot_mv = 0
        for i in bond_invs:
            mv = i.computed_mkt_value
            tot_mv += mv
            wt = (mv / total_portfolio * 100) if total_portfolio else 0
            rows.append([
                i.issue_date.strftime('%d %b %y') if i.issue_date else '-',
                i.trade_date.strftime('%d %b %y') if i.trade_date else '-',
                i.issuer or '-',
                fmt(c(i.face_value)),
                f'{fmt(i.clean_price)}%' if i.clean_price else '-',
                str(i.tenor or '-'),
                str(i.coupon_freq or '-'),
                i.last_coupon_date.strftime('%d %b %y') if i.last_coupon_date else '-',
                fmt(i.coupon_rate),
                str(i.days_run),
                fmt(c(i.accrued_interest)),
                fmt(c(mv)),
                str(i.days_to_maturity or '-'),
                fmt_pct(i.coupon_rate),
                fmt_pct(wt)
            ])
        rows.append(['TOTAL', '', '', '', '', '', '', '', '', '', '', fmt(c(tot_mv)), '', '', ''])
        t_idx2 = len(rows)-1
        cw = [1.8*cm,1.8*cm,2.5*cm,2.2*cm,1.5*cm,1.2*cm,1.3*cm,1.8*cm,1.2*cm,
              1.3*cm,2*cm,2.5*cm,1.5*cm,1.2*cm,1.2*cm]
        tbl = Table(rows, colWidths=cw, repeatRows=1)
        ts2 = summary_table_style()
        ts2.add('ALIGN', (3,0), (-1,-1), 'RIGHT')
        for ext in total_row_style(t_idx2):
            ts2.add(*ext)
        tbl.setStyle(ts2)
        story.append(tbl)
        story.append(Spacer(1, 0.3*cm))

    # ── GSE EQUITIES ──────────────────────────────────────────────────────────
    gse_invs = [i for i in investments if i.asset_class == 'GSE_EQUITIES']
    if gse_invs:
        story.append(Paragraph('EQUITIES — GSE LISTED SECURITIES', S['section']))
        hdr = ['Symbol', 'Security Name', 'Sector', 'Qty',
               f'Unit Cost ({currency})', f'Total Cost ({currency})',
               f'Mkt Price ({currency})', f'Mkt Value ({currency})',
               f'Gain/Loss ({currency})', 'Return %', 'Wt. %']
        rows = [hdr]
        tot_cost = 0; tot_mv = 0
        for i in gse_invs:
            mv = i.computed_mkt_value
            cost = i.total_cost or 0
            gain = mv - cost
            ret = (gain / cost * 100) if cost else 0
            tot_cost += cost; tot_mv += mv
            wt = (mv / total_portfolio * 100) if total_portfolio else 0
            rows.append([
                i.symbol or '-', i.security_name or '-', i.sector or '-',
                fmt(i.quantity, 0),
                fmt(c(i.unit_cost)), fmt(c(cost)),
                fmt(c(i.current_price)), fmt(c(mv)),
                fmt(c(gain)), fmt_pct(ret), fmt_pct(wt)
            ])
        tot_gain = tot_mv - tot_cost
        tot_ret = (tot_gain / tot_cost * 100) if tot_cost else 0
        rows.append(['TOTAL', '', '', '', '', fmt(c(tot_cost)), '', fmt(c(tot_mv)),
                     fmt(c(tot_gain)), fmt_pct(tot_ret), ''])
        t_idx2 = len(rows)-1
        cw = [1.5*cm,4*cm,2.5*cm,1.5*cm,2.2*cm,2.5*cm,2.2*cm,2.5*cm,2.5*cm,1.8*cm,1.5*cm]
        tbl = Table(rows, colWidths=cw, repeatRows=1)
        ts2 = summary_table_style()
        ts2.add('ALIGN', (4,0), (-1,-1), 'RIGHT')
        for ext in total_row_style(t_idx2):
            ts2.add(*ext)
        tbl.setStyle(ts2)
        story.append(tbl)
        story.append(Spacer(1, 0.3*cm))

    # ── GLOBAL EQUITIES ───────────────────────────────────────────────────────
    gl_invs = [i for i in investments if i.asset_class == 'GLOBAL_EQUITIES']
    if gl_invs:
        story.append(Paragraph('GLOBAL EQUITIES', S['section']))
        hdr = ['Symbol', 'Security Name', 'Exchange', 'Sector', 'Qty',
               'Unit Cost (USD)', 'Mkt Price (USD)',
               'Total Cost (USD)', f'Mkt Value ({currency})',
               f'Gain/Loss ({currency})', 'Return %', 'Wt. %']
        rows = [hdr]
        tot_mv = 0
        for i in gl_invs:
            mv = i.computed_mkt_value
            cost = i.total_cost or 0
            gain = mv - cost
            ret = (gain / cost * 100) if cost else 0
            tot_mv += mv
            wt = (mv / total_portfolio * 100) if total_portfolio else 0
            rows.append([
                i.symbol or '-', i.security_name or '-',
                i.exchange or '-', i.sector or '-',
                fmt(i.quantity, 0),
                fmt(i.unit_cost), fmt(i.current_price),
                fmt(cost), fmt(c(mv)),
                fmt(c(gain)), fmt_pct(ret), fmt_pct(wt)
            ])
        rows.append(['TOTAL', '', '', '', '', '', '', '', fmt(c(tot_mv)), '', '', ''])
        t_idx2 = len(rows)-1
        cw = [1.5*cm,3.5*cm,1.8*cm,2*cm,1.2*cm,2.2*cm,2.2*cm,2.5*cm,2.5*cm,2.2*cm,1.5*cm,1.3*cm]
        tbl = Table(rows, colWidths=cw, repeatRows=1)
        ts2 = summary_table_style()
        ts2.add('ALIGN', (4,0), (-1,-1), 'RIGHT')
        for ext in total_row_style(t_idx2):
            ts2.add(*ext)
        tbl.setStyle(ts2)
        story.append(tbl)
        story.append(Spacer(1, 0.3*cm))

    # ── PRIVATE EQUITY ────────────────────────────────────────────────────────
    pe_invs = [i for i in investments if i.asset_class == 'PRIVATE_EQUITY']
    if pe_invs:
        story.append(Paragraph('PRIVATE EQUITY', S['section']))
        hdr = ['Fund/Company', 'Sector', 'Vintage', 'Geography', 'Stage',
               f'Committed ({currency})', f'Called ({currency})',
               f'Distributions ({currency})', 'MOIC', 'IRR%',
               f'NAV/FairVal ({currency})', 'Wt.%']
        rows = [hdr]
        tot_nav = 0
        for i in pe_invs:
            nav = i.nav or i.computed_mkt_value
            tot_nav += nav
            wt = (nav / total_portfolio * 100) if total_portfolio else 0
            rows.append([
                i.security_name or i.issuer or '-',
                i.sector or '-', str(i.vintage_year or '-'),
                i.geography or '-', i.stage or '-',
                fmt(c(i.committed)), fmt(c(i.called)),
                fmt(c(i.distributions)),
                f'{fmt(i.moic)}x' if i.moic else '-',
                fmt_pct(i.irr), fmt(c(nav)), fmt_pct(wt)
            ])
        rows.append(['TOTAL', '', '', '', '', '', '', '', '', '', fmt(c(tot_nav)), ''])
        t_idx2 = len(rows)-1
        cw = [3*cm,2*cm,1.5*cm,2*cm,2*cm,2.5*cm,2.2*cm,2.5*cm,1.2*cm,1.2*cm,2.8*cm,1.5*cm]
        tbl = Table(rows, colWidths=cw, repeatRows=1)
        ts2 = summary_table_style()
        ts2.add('ALIGN', (5,0), (-1,-1), 'RIGHT')
        for ext in total_row_style(t_idx2):
            ts2.add(*ext)
        tbl.setStyle(ts2)
        story.append(tbl)
        story.append(Spacer(1, 0.3*cm))

    # ── PRIVATE DEBT ──────────────────────────────────────────────────────────
    pd_invs = [i for i in investments if i.asset_class == 'PRIVATE_DEBT']
    if pd_invs:
        story.append(Paragraph('PRIVATE DEBT / DIRECT LENDING', S['section']))
        hdr = ['Borrower/Fund', 'Sector', 'Instrument',
               f'Facility Size ({currency})', f'Outstanding ({currency})',
               'Rate%', 'Maturity', 'Rating', 'PIK', 'Wt.%']
        rows = [hdr]
        tot_out = 0
        for i in pd_invs:
            out = i.outstanding or i.computed_mkt_value
            tot_out += out
            wt = (out / total_portfolio * 100) if total_portfolio else 0
            rows.append([
                i.security_name or i.issuer or '-', i.sector or '-',
                i.sub_type or 'Term Loan',
                fmt(c(i.face_value or i.total_cost)), fmt(c(out)),
                fmt(i.coupon_rate or i.interest_rate),
                i.maturity_date.strftime('%d %b %Y') if i.maturity_date else '-',
                i.rating or '-', 'Yes' if i.pik else 'No', fmt_pct(wt)
            ])
        rows.append(['TOTAL', '', '', '', fmt(c(tot_out)), '', '', '', '', ''])
        t_idx2 = len(rows)-1
        cw = [3.5*cm,2*cm,2*cm,2.8*cm,2.5*cm,1.5*cm,2.2*cm,1.5*cm,1*cm,1.5*cm]
        tbl = Table(rows, colWidths=cw, repeatRows=1)
        ts2 = summary_table_style()
        ts2.add('ALIGN', (3,0), (-1,-1), 'RIGHT')
        for ext in total_row_style(t_idx2):
            ts2.add(*ext)
        tbl.setStyle(ts2)
        story.append(tbl)
        story.append(Spacer(1, 0.3*cm))

    # ── MUTUAL FUNDS ──────────────────────────────────────────────────────────
    mf_invs = [i for i in investments if i.asset_class == 'MUTUAL_FUNDS']
    if mf_invs:
        story.append(Paragraph('MUTUAL FUNDS & UNIT TRUSTS', S['section']))
        hdr = ['Security Name', 'Type', 'Units',
               f'Unit Cost ({currency})', f'Total Cost ({currency})',
               f'NAV Price ({currency})', f'Mkt Value ({currency})',
               f'Gain/Loss ({currency})', 'Return%', 'Wt.%']
        rows = [hdr]
        tot_mv = 0; tot_cost = 0
        for i in mf_invs:
            mv = i.computed_mkt_value
            cost = i.total_cost or 0
            gain = mv - cost
            ret = (gain/cost*100) if cost else 0
            tot_mv += mv; tot_cost += cost
            wt = (mv / total_portfolio * 100) if total_portfolio else 0
            rows.append([
                i.security_name or '-', i.sub_type or 'Mutual Fund',
                fmt(i.quantity), fmt(c(i.unit_cost)), fmt(c(cost)),
                fmt(c(i.current_price)), fmt(c(mv)),
                fmt(c(gain)), fmt_pct(ret), fmt_pct(wt)
            ])
        rows.append(['TOTAL', '', '', '', fmt(c(tot_cost)), '', fmt(c(tot_mv)),
                     fmt(c(tot_mv-tot_cost)), fmt_pct(((tot_mv-tot_cost)/tot_cost*100) if tot_cost else 0), ''])
        t_idx2 = len(rows)-1
        cw = [3.5*cm,2*cm,1.8*cm,2.2*cm,2.5*cm,2.2*cm,2.5*cm,2.3*cm,1.8*cm,1.5*cm]
        tbl = Table(rows, colWidths=cw, repeatRows=1)
        ts2 = summary_table_style()
        ts2.add('ALIGN', (3,0), (-1,-1), 'RIGHT')
        for ext in total_row_style(t_idx2):
            ts2.add(*ext)
        tbl.setStyle(ts2)
        story.append(tbl)
        story.append(Spacer(1, 0.3*cm))

    # ── PORTFOLIO STRUCTURE TABLE ──────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph('PORTFOLIO STRUCTURE & ASSET ALLOCATION', S['section']))
    alloc_hdr = ['Asset Class', f'Market Value ({currency})', 'Portfolio Weight', 'Allocation']
    alloc_rows = [alloc_hdr]
    for cls, lbl in asset_labels.items():
        mv = by_class.get(cls, 0)
        wt = (mv / total_portfolio * 100) if total_portfolio else 0
        if mv:
            bar = '█' * max(1, int(wt * 2))
            alloc_rows.append([lbl, fmt(c(mv)), fmt_pct(wt), bar])
    cash_wt2 = (cash / total_portfolio * 100) if total_portfolio else 0
    bar_cash = '█' * max(1, int(cash_wt2 * 2))
    alloc_rows.append(['Cash & Bank Balances', fmt(c(cash)), fmt_pct(cash_wt2), bar_cash])
    alloc_rows.append(['TOTAL FUND VALUE', fmt(c(total_portfolio)), '100.00%', ''])
    t_idx2 = len(alloc_rows) - 1
    cw = [5*cm, 5*cm, 3*cm, 5*cm]
    tbl = Table(alloc_rows, colWidths=cw, repeatRows=1)
    ts2 = summary_table_style()
    ts2.add('ALIGN', (1,0), (2,-1), 'RIGHT')
    ts2.add('TEXTCOLOR', (3,1), (3,-2), GOLD)
    for ext in total_row_style(t_idx2):
        ts2.add(*ext)
    tbl.setStyle(ts2)
    story.append(tbl)

    # ── DISCLAIMER ─────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=GOLD))
    story.append(Spacer(1, 0.2*cm))
    disc = ('All monetary values shown in {}. Exchange rate: 1 {} = GHS {:.4f} '
            '(source: open.er-api.com at generation time). '
            'This report is for informational purposes only and does not constitute '
            'investment advice. Zagadat Capital Fund Management System | Confidential — '
            'For Authorised Recipients Only | Valuation Date: {} | Generated: {}').format(
        currency, currency,
        1.0/fx if fx else 0,
        date.today().strftime('%d %b %Y'),
        datetime.utcnow().strftime('%d %b %Y %H:%M UTC')
    )
    story.append(Paragraph(disc, S['small']))

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer,
              canvasmaker=NumberedCanvas)
    buf.seek(0)
    return buf


# ══════════════════════════════════════════════════════════════════════════════
# TRANSACTION STATEMENT
# ══════════════════════════════════════════════════════════════════════════════
def generate_statement(account_number, date_from=None, date_to=None):
    acc = ClientAccount.query.filter_by(account_number=account_number).first()
    if not acc:
        raise ValueError('Account not found')

    query = Transaction.query.filter_by(account_number=account_number, status='APPROVED')
    if date_from:
        query = query.filter(Transaction.txn_date >= date_from)
    if date_to:
        query = query.filter(Transaction.txn_date <= date_to)
    txns = query.order_by(Transaction.txn_date.asc()).all()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=2.2*cm, bottomMargin=1.8*cm)
    S = make_styles()
    story = []

    story.append(Paragraph(f'TRANSACTION STATEMENT — {acc.full_name}', S['title']))
    story.append(Paragraph(f'Account No.: {acc.account_number} | Currency: {acc.base_currency}', S['normal']))
    period = f"Period: {date_from.strftime('%d %b %Y') if date_from else 'Inception'} to {date_to.strftime('%d %b %Y') if date_to else date.today().strftime('%d %b %Y')}"
    story.append(Paragraph(period, S['normal']))
    story.append(Spacer(1, 0.3*cm))

    hdr = ['Date', 'Type', 'Description', 'Reference', 'Debit', 'Credit', 'Balance']
    rows = [hdr]
    balance = 0.0
    for t in txns:
        is_credit = t.txn_type in ('DEPOSIT', 'TRANSFER_IN', 'DIVIDEND', 'COUPON', 'SELL')
        if is_credit:
            balance += t.amount
            rows.append([
                t.txn_date.strftime('%d %b %Y'),
                t.txn_type.replace('_', ' '), t.description or '-',
                t.reference or '-', '-', fmt(t.amount), fmt(balance)
            ])
        else:
            balance -= t.amount
            rows.append([
                t.txn_date.strftime('%d %b %Y'),
                t.txn_type.replace('_', ' '), t.description or '-',
                t.reference or '-', fmt(t.amount), '-', fmt(balance)
            ])

    rows.append(['', '', '', 'CLOSING BALANCE', '', '', fmt(balance)])
    t_idx = len(rows)-1

    cw = [2.2*cm, 2.5*cm, 5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm]
    tbl = Table(rows, colWidths=cw, repeatRows=1)
    ts2 = summary_table_style()
    ts2.add('ALIGN', (4,0), (-1,-1), 'RIGHT')
    for ext in total_row_style(t_idx):
        ts2.add(*ext)
    tbl.setStyle(ts2)
    story.append(tbl)

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer,
              canvasmaker=NumberedCanvas)
    buf.seek(0)
    return buf


# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL AUM / SYSTEM REPORT
# ══════════════════════════════════════════════════════════════════════════════
def generate_global_report(asset_class_filter=None):
    """Summary of all investments across all accounts"""
    query = Investment.query.filter_by(status='APPROVED')
    if asset_class_filter:
        query = query.filter_by(asset_class=asset_class_filter)
    investments = query.all()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=2.2*cm, bottomMargin=1.8*cm)
    S = make_styles()
    story = []

    title = f'GLOBAL PORTFOLIO REPORT — ALL ACCOUNTS'
    if asset_class_filter:
        title += f' ({asset_class_filter.replace("_"," ")})'
    story.append(Paragraph(title, S['title']))
    story.append(Paragraph(f'As at {date.today().strftime("%d %b %Y")} | Total Accounts: {ClientAccount.query.filter_by(status="APPROVED").count()}', S['normal']))
    story.append(Spacer(1, 0.3*cm))

    # Summary by asset class
    by_class = {}
    for inv in investments:
        mv = inv.computed_mkt_value
        by_class[inv.asset_class] = by_class.get(inv.asset_class, 0) + mv

    total_aum = sum(by_class.values())
    # Add all cash
    all_cash = sum(acc.cash_balance for acc in ClientAccount.query.filter_by(status='APPROVED').all())
    grand_total = total_aum + all_cash

    asset_labels = {
        'MONEY_MARKET': 'Money Market', 'GOVT_SECURITIES': 'Gov. Securities',
        'BONDS': 'Bonds', 'EUROBONDS': 'Eurobonds',
        'GSE_EQUITIES': 'GSE Equities', 'GLOBAL_EQUITIES': 'Global Equities',
        'PRIVATE_EQUITY': 'Private Equity', 'PRIVATE_DEBT': 'Private Debt',
        'MUTUAL_FUNDS': 'Mutual Funds',
    }

    hdr = ['Asset Class', 'Total Mkt Value (GHS)', 'Weight %', 'No. of Holdings']
    rows = [hdr]
    for cls, lbl in asset_labels.items():
        mv = by_class.get(cls, 0)
        count = sum(1 for i in investments if i.asset_class == cls)
        wt = (mv / grand_total * 100) if grand_total else 0
        if mv:
            rows.append([lbl, fmt(mv), fmt_pct(wt), str(count)])
    rows.append(['Cash & Bank Balances', fmt(all_cash), fmt_pct(all_cash/grand_total*100 if grand_total else 0), '-'])
    rows.append(['TOTAL AUM', fmt(grand_total), '100.00%', str(len(investments))])
    t_idx = len(rows)-1

    cw = [7*cm, 7*cm, 4*cm, 4*cm]
    tbl = Table(rows, colWidths=cw, repeatRows=1)
    ts2 = summary_table_style()
    ts2.add('ALIGN', (1,0), (-1,-1), 'RIGHT')
    for ext in total_row_style(t_idx):
        ts2.add(*ext)
    tbl.setStyle(ts2)
    story.append(tbl)
    story.append(Spacer(1, 0.4*cm))

    # Detail per account
    story.append(Paragraph('ACCOUNT BREAKDOWN', S['section']))
    accs = ClientAccount.query.filter_by(status='APPROVED').all()
    det_hdr = ['Account No.', 'Client Name', 'Account Type', 'Total Investments (GHS)', 'Cash (GHS)', 'Portfolio Value (GHS)', 'Weight%']
    det_rows = [det_hdr]
    for acc in accs:
        invs_acc = [i for i in investments if i.account_number == acc.account_number]
        acc_mv = sum(i.computed_mkt_value for i in invs_acc)
        cash_b = acc.cash_balance
        total = acc_mv + cash_b
        wt = (total / grand_total * 100) if grand_total else 0
        det_rows.append([
            acc.account_number, acc.full_name, acc.account_type,
            fmt(acc_mv), fmt(cash_b), fmt(total), fmt_pct(wt)
        ])
    det_rows.append(['TOTAL', '', '', '', '', fmt(grand_total), '100.00%'])
    t_idx2 = len(det_rows)-1
    cw2 = [3*cm, 5*cm, 3.5*cm, 5*cm, 4*cm, 5*cm, 3*cm]
    tbl2 = Table(det_rows, colWidths=cw2, repeatRows=1)
    ts3 = summary_table_style()
    ts3.add('ALIGN', (3,0), (-1,-1), 'RIGHT')
    for ext in total_row_style(t_idx2):
        ts3.add(*ext)
    tbl2.setStyle(ts3)
    story.append(tbl2)

    def landscape_hf(canvas_obj, doc):
        canvas_obj.saveState()
        w, h = landscape(A4)
        canvas_obj.setFillColor(DARK)
        canvas_obj.rect(0, h - 1.8*cm, w, 1.8*cm, fill=1, stroke=0)
        canvas_obj.setFillColor(GOLD)
        canvas_obj.rect(0, h - 1.82*cm, w, 0.08*cm, fill=1, stroke=0)
        if os.path.exists(LOGO_PATH):
            canvas_obj.drawImage(LOGO_PATH, 0.8*cm, h-1.65*cm, 1.3*cm, 1.3*cm,
                                 preserveAspectRatio=True, mask='auto')
        canvas_obj.setFont('Helvetica-Bold', 13)
        canvas_obj.setFillColor(WHITE)
        canvas_obj.drawString(2.5*cm, h-1.1*cm, 'ZAGADAT CAPITAL')
        canvas_obj.setFont('Helvetica', 9)
        canvas_obj.setFillColor(GOLD)
        canvas_obj.drawString(2.5*cm, h-1.5*cm, 'Global Portfolio Report')
        canvas_obj.setFont('Helvetica', 8)
        canvas_obj.setFillColor(LIGHT)
        canvas_obj.drawRightString(w - 0.8*cm, h-1.0*cm, f'{date.today().strftime("%d %b %Y")}')
        canvas_obj.setFillColor(DARK)
        canvas_obj.rect(0, 0, w, 1.2*cm, fill=1, stroke=0)
        canvas_obj.setFillColor(GOLD)
        canvas_obj.rect(0, 1.2*cm, w, 0.05*cm, fill=1, stroke=0)
        canvas_obj.setFont('Helvetica', 7)
        canvas_obj.setFillColor(LIGHT)
        canvas_obj.drawString(0.8*cm, 0.45*cm, 'ZAGADAT CAPITAL — CONFIDENTIAL')
        canvas_obj.restoreState()

    doc.build(story, onFirstPage=landscape_hf, onLaterPages=landscape_hf,
              canvasmaker=NumberedCanvas)
    buf.seek(0)
    return buf

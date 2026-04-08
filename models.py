from extensions import db, login_manager, bcrypt
from flask_login import UserMixin
from datetime import datetime, date

@login_manager.user_loader
def load_user(user_id):
    uid = str(user_id)
    if uid.startswith('admin_'):
        return AdminUser.query.get(int(uid.split('_')[1]))
    return ClientUser.query.get(int(uid))

ADMIN_ROLES = {
    'SUPER_ADMIN':         {'label': 'Super Admin',          'level': 100},
    'ACCOUNT_SETUP':       {'label': 'Account Setup',        'level': 30},
    'ACCOUNT_APPROVER':    {'label': 'Account Approver',     'level': 40},
    'INVESTMENT_ENTRY':    {'label': 'Investment Entry',     'level': 50},
    'INVESTMENT_APPROVER': {'label': 'Investment Approver',  'level': 60},
    'REPORT_VIEWER':       {'label': 'Report Viewer',        'level': 10},
}

PERMISSION_MAP = {
    'migrate_data': 100, 'create_admin': 100, 'manage_all': 100,
    'create_account': 30, 'approve_account': 40,
    'enter_investment': 50, 'approve_investment': 60, 'view_reports': 10,
}

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id          = db.Column(db.Integer, primary_key=True)
    actor_type  = db.Column(db.String(20))
    actor_id    = db.Column(db.Integer)
    actor_name  = db.Column(db.String(120))
    action      = db.Column(db.String(100))
    target      = db.Column(db.String(100), nullable=True)
    detail      = db.Column(db.Text, nullable=True)
    ip_address  = db.Column(db.String(50), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

class AdminUser(UserMixin, db.Model):
    __tablename__ = 'admin_users'
    id            = db.Column(db.Integer, primary_key=True)
    staff_id      = db.Column(db.String(20), unique=True, nullable=False)
    full_name     = db.Column(db.String(120), nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(40), nullable=False, default='REPORT_VIEWER')
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    created_by    = db.Column(db.Integer, nullable=True)
    last_login    = db.Column(db.DateTime, nullable=True)
    is_rm         = db.Column(db.Boolean, default=False)
    rm_commission_rate = db.Column(db.Float, default=1.0)

    def get_id(self): return f'admin_{self.id}'
    def set_password(self, pw): self.password_hash = bcrypt.generate_password_hash(pw).decode('utf-8')
    def check_password(self, pw): return bcrypt.check_password_hash(self.password_hash, pw)
    def has_permission(self, p):
        return ADMIN_ROLES.get(self.role, {}).get('level', 0) >= PERMISSION_MAP.get(p, 100)
    @property
    def is_super_admin(self): return self.role == 'SUPER_ADMIN'
    @property
    def rm_portfolio_value(self):
        total = 0.0
        for acc in ClientAccount.query.filter_by(relationship_manager_id=self.id, status='APPROVED').all():
            total += sum(i.computed_mkt_value for i in Investment.query.filter_by(account_number=acc.account_number, status='APPROVED').all())
            total += acc.cash_balance
        return total
    @property
    def rm_earnings(self): return self.rm_portfolio_value * (self.rm_commission_rate / 100)

class ClientAccount(db.Model):
    __tablename__ = 'client_accounts'
    id              = db.Column(db.Integer, primary_key=True)
    account_number  = db.Column(db.String(20), unique=True, nullable=False)
    # Personal
    full_name       = db.Column(db.String(150), nullable=False)
    date_of_birth   = db.Column(db.Date, nullable=True)
    gender          = db.Column(db.String(10), nullable=True)
    marital_status  = db.Column(db.String(20), nullable=True)
    nationality     = db.Column(db.String(60), nullable=True)
    residential_status = db.Column(db.String(40), nullable=True)
    country_of_origin  = db.Column(db.String(60), nullable=True)
    country_of_residence = db.Column(db.String(60), nullable=True)
    place_of_birth  = db.Column(db.String(80), nullable=True)
    digital_address = db.Column(db.String(60), nullable=True)
    tin             = db.Column(db.String(40), nullable=True)
    # Contact
    phone           = db.Column(db.String(20), nullable=False)
    phone2          = db.Column(db.String(20), nullable=True)
    email           = db.Column(db.String(120), nullable=True)
    address         = db.Column(db.Text, nullable=True)
    city            = db.Column(db.String(60), nullable=True)
    country         = db.Column(db.String(60), nullable=True)
    postal_address  = db.Column(db.String(120), nullable=True)
    # ID
    id_type         = db.Column(db.String(40), nullable=True)
    id_number       = db.Column(db.String(60), nullable=True)
    id_issue_date   = db.Column(db.Date, nullable=True)
    id_expiry_date  = db.Column(db.Date, nullable=True)
    id_place_of_issue = db.Column(db.String(80), nullable=True)
    # Ghana Card (NIA) & Nationality
    ghana_card_number = db.Column(db.String(30), nullable=True)   # GHA-000000000-0
    is_ghanaian       = db.Column(db.Boolean, default=True)        # Ghanaian vs foreign national
    height            = db.Column(db.String(20), nullable=True)   # e.g. 1.75m (manual entry)
    # Permit
    permit_number   = db.Column(db.String(60), nullable=True)
    permit_issue_date = db.Column(db.Date, nullable=True)
    permit_expiry_date = db.Column(db.Date, nullable=True)
    # Employment
    occupation      = db.Column(db.String(80), nullable=True)
    employer        = db.Column(db.String(120), nullable=True)
    employer_address= db.Column(db.String(200), nullable=True)
    employer_city   = db.Column(db.String(60), nullable=True)
    nature_of_business = db.Column(db.String(120), nullable=True)
    employment_status = db.Column(db.String(40), nullable=True)
    years_employed  = db.Column(db.String(20), nullable=True)
    office_phone    = db.Column(db.String(20), nullable=True)
    office_email    = db.Column(db.String(120), nullable=True)
    # Financial
    annual_income_range = db.Column(db.String(60), nullable=True)
    source_of_funds = db.Column(db.String(120), nullable=True)
    anticipated_investment = db.Column(db.String(60), nullable=True)
    topup_frequency = db.Column(db.String(40), nullable=True)
    withdrawal_frequency = db.Column(db.String(40), nullable=True)
    regular_topup_amount = db.Column(db.Float, nullable=True)
    regular_withdrawal_amount = db.Column(db.Float, nullable=True)
    # Bank
    bank_name       = db.Column(db.String(80), nullable=True)
    bank_branch     = db.Column(db.String(80), nullable=True)
    bank_account_name = db.Column(db.String(120), nullable=True)
    bank_account_number = db.Column(db.String(40), nullable=True)
    # Account type & settings
    account_type    = db.Column(db.String(40), default='Individual')
    mandate         = db.Column(db.String(30), nullable=True)
    regulatory_body = db.Column(db.String(60), nullable=True)
    fund_type       = db.Column(db.String(40), nullable=True)
    investment_objective = db.Column(db.String(120), nullable=True)
    risk_profile    = db.Column(db.String(40), nullable=True)
    investment_horizon = db.Column(db.String(40), nullable=True)
    investment_knowledge = db.Column(db.String(20), nullable=True)
    portfolio_preference = db.Column(db.String(200), nullable=True)
    other_investments = db.Column(db.String(200), nullable=True)
    base_currency   = db.Column(db.String(10), default='GHS')
    custodian       = db.Column(db.String(100), nullable=True)
    csd_number      = db.Column(db.String(40), nullable=True)
    statement_mode  = db.Column(db.String(20), nullable=True)
    statement_frequency = db.Column(db.String(20), nullable=True)
    category_of_investment = db.Column(db.String(100), nullable=True)
    client_first_contact = db.Column(db.String(60), nullable=True)
    # ITF
    itf_name        = db.Column(db.String(120), nullable=True)
    itf_relationship = db.Column(db.String(60), nullable=True)
    itf_dob         = db.Column(db.Date, nullable=True)
    itf_gender      = db.Column(db.String(10), nullable=True)
    itf_id_type     = db.Column(db.String(40), nullable=True)
    itf_id_number   = db.Column(db.String(60), nullable=True)
    # Beneficiaries
    beneficiary1_name = db.Column(db.String(120), nullable=True)
    beneficiary1_pct  = db.Column(db.Float, nullable=True)
    beneficiary1_relation = db.Column(db.String(60), nullable=True)
    beneficiary1_dob  = db.Column(db.Date, nullable=True)
    beneficiary2_name = db.Column(db.String(120), nullable=True)
    beneficiary2_pct  = db.Column(db.Float, nullable=True)
    beneficiary2_relation = db.Column(db.String(60), nullable=True)
    beneficiary2_dob  = db.Column(db.Date, nullable=True)
    # Nominee (legacy)
    nominee_name    = db.Column(db.String(120), nullable=True)
    nominee_phone   = db.Column(db.String(20), nullable=True)
    nominee_relation= db.Column(db.String(60), nullable=True)
    # Spouse
    spouse_name     = db.Column(db.String(120), nullable=True)
    spouse_phone    = db.Column(db.String(20), nullable=True)
    spouse_email    = db.Column(db.String(120), nullable=True)
    # Emergency contact
    emergency_contact_name = db.Column(db.String(120), nullable=True)
    emergency_contact_relation = db.Column(db.String(60), nullable=True)
    emergency_contact_phone = db.Column(db.String(20), nullable=True)
    # PEP
    is_pep          = db.Column(db.Boolean, default=False)
    pep_details     = db.Column(db.Text, nullable=True)
    pep_foreign     = db.Column(db.Boolean, default=False)
    pep_foreign_details = db.Column(db.Text, nullable=True)
    aml_status      = db.Column(db.String(30), nullable=True)
    # FATCA/CRS
    is_foreign_citizen = db.Column(db.Boolean, default=False)
    foreign_country    = db.Column(db.String(60), nullable=True)
    foreign_address    = db.Column(db.String(200), nullable=True)
    foreign_tin        = db.Column(db.String(60), nullable=True)
    # Dividend
    dividend_reinvest = db.Column(db.Boolean, default=False)
    # Risk score
    risk_score      = db.Column(db.Integer, nullable=True)
    risk_score_label= db.Column(db.String(20), nullable=True)
    # Document paths
    passport_photo_path = db.Column(db.String(300), nullable=True)
    id_document_path    = db.Column(db.String(300), nullable=True)
    signature_path      = db.Column(db.String(300), nullable=True)
    address_proof_path  = db.Column(db.String(300), nullable=True)
    other_docs_path     = db.Column(db.String(300), nullable=True)
    # Fees
    management_fee_rate = db.Column(db.Float, nullable=True)
    # RM
    relationship_manager_id = db.Column(db.Integer, db.ForeignKey('admin_users.id'), nullable=True)
    relationship_manager    = db.relationship('AdminUser', foreign_keys=[relationship_manager_id])
    # Status
    status          = db.Column(db.String(20), default='PENDING')
    rejection_reason = db.Column(db.Text, nullable=True)
    approved_by     = db.Column(db.Integer, nullable=True)
    approved_at     = db.Column(db.DateTime, nullable=True)
    created_by      = db.Column(db.Integer, nullable=True)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    online_signup   = db.Column(db.Boolean, default=False)

    transactions = db.relationship('Transaction', backref='account', lazy=True)
    investments  = db.relationship('Investment', backref='account', lazy=True)
    fees         = db.relationship('AccountFee', backref='account', lazy=True)

    @property
    def cash_balance(self):
        """
        Cash balance in account base currency (default GHS).
        Only APPROVED transactions count.
        Uses amount_ghs if available (for non-GHS transactions), otherwise amount.
        """
        total = 0.0
        for t in self.transactions:
            if t.status == 'APPROVED':
                ghs_amt = t.amount_ghs if t.amount_ghs is not None else t.amount
                if t.txn_type in ('DEPOSIT','TRANSFER_IN','DIVIDEND','COUPON','SELL'):
                    total += ghs_amt
                else:
                    total -= ghs_amt
        return max(0.0, total)  # Cash cannot go below 0

    @property
    def pending_deposits(self):
        """Sum of pending deposit/topup requests."""
        from models import ClientRequest
        total = 0.0
        for r in ClientRequest.query.filter_by(
                account_number=self.account_number, status='PENDING').all():
            if r.request_type in ('DEPOSIT','TOPUP'):
                total += (r.amount or 0)
        return total

    @property
    def kyc_complete(self):
        """True when the minimum KYC fields are present."""
        return bool(
            self.id_document_path and
            self.signature_path and
            self.bank_account_number
        )

    @property
    def total_investment_value(self):
        return sum(i.computed_mkt_value for i in self.investments if i.status == 'APPROVED')

    @property
    def total_portfolio_value(self):
        return self.total_investment_value + self.cash_balance

class ClientUser(UserMixin, db.Model):
    __tablename__ = 'client_users'
    id             = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(20), db.ForeignKey('client_accounts.account_number'), nullable=False)
    phone          = db.Column(db.String(20), nullable=False)
    password_hash  = db.Column(db.String(256), nullable=True)
    is_active      = db.Column(db.Boolean, default=True)
    last_login     = db.Column(db.DateTime, nullable=True)
    signup_name    = db.Column(db.String(150), nullable=True)
    # Face ID â€” stores a JSON-encoded 128-dim face descriptor vector (computed in browser)
    # No raw face images are stored; only the mathematical representation.
    face_descriptor = db.Column(db.Text, nullable=True)
    face_enrolled_at = db.Column(db.DateTime, nullable=True)
    account = db.relationship('ClientAccount', foreign_keys=[account_number],
                               primaryjoin='ClientUser.account_number == ClientAccount.account_number')
    def get_id(self): return str(self.id)
    def set_password(self, pw): self.password_hash = bcrypt.generate_password_hash(pw).decode('utf-8')
    def check_password(self, pw): return bcrypt.check_password_hash(self.password_hash, pw)
    @property
    def has_face_id(self): return bool(self.face_descriptor)

class JointAccountHolder(db.Model):
    __tablename__ = 'joint_account_holders'
    id              = db.Column(db.Integer, primary_key=True)
    account_number  = db.Column(db.String(20), db.ForeignKey('client_accounts.account_number'))
    full_name       = db.Column(db.String(150))
    date_of_birth   = db.Column(db.Date, nullable=True)
    nationality     = db.Column(db.String(60), nullable=True)
    phone           = db.Column(db.String(20), nullable=True)
    email           = db.Column(db.String(120), nullable=True)
    address         = db.Column(db.Text, nullable=True)
    id_type         = db.Column(db.String(40), nullable=True)
    id_number       = db.Column(db.String(60), nullable=True)
    id_expiry_date  = db.Column(db.Date, nullable=True)
    occupation      = db.Column(db.String(80), nullable=True)
    signature_path  = db.Column(db.String(300), nullable=True)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

class CorporateDetails(db.Model):
    __tablename__ = 'corporate_details'
    id                  = db.Column(db.Integer, primary_key=True)
    account_number      = db.Column(db.String(20), db.ForeignKey('client_accounts.account_number'), unique=True)
    company_name        = db.Column(db.String(200), nullable=True)
    registration_number = db.Column(db.String(80), nullable=True)
    date_of_incorporation = db.Column(db.Date, nullable=True)
    country_of_incorporation = db.Column(db.String(60), nullable=True)
    registered_address  = db.Column(db.Text, nullable=True)
    business_address    = db.Column(db.Text, nullable=True)
    nature_of_business  = db.Column(db.String(200), nullable=True)
    website             = db.Column(db.String(120), nullable=True)
    contact_person_name = db.Column(db.String(120), nullable=True)
    contact_person_title= db.Column(db.String(60), nullable=True)
    contact_person_phone= db.Column(db.String(20), nullable=True)
    contact_person_email= db.Column(db.String(120), nullable=True)
    authorized_signatory1 = db.Column(db.String(120), nullable=True)
    authorized_signatory2 = db.Column(db.String(120), nullable=True)
    cert_of_incorporation_path = db.Column(db.String(300), nullable=True)
    resolution_path    = db.Column(db.String(300), nullable=True)
    created_at         = db.Column(db.DateTime, default=datetime.utcnow)
    account = db.relationship('ClientAccount', foreign_keys=[account_number],
                               primaryjoin='CorporateDetails.account_number == ClientAccount.account_number')

class FeeType(db.Model):
    __tablename__ = 'fee_types'
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_active   = db.Column(db.Boolean, default=True)
    created_by  = db.Column(db.Integer, nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

class AccountFee(db.Model):
    __tablename__ = 'account_fees'
    id             = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(20), db.ForeignKey('client_accounts.account_number'), nullable=False)
    fee_type_id    = db.Column(db.Integer, db.ForeignKey('fee_types.id'), nullable=False)
    rate           = db.Column(db.Float, nullable=False)
    frequency      = db.Column(db.String(30), default='Quarterly')
    effective_date = db.Column(db.Date, nullable=True)
    notes          = db.Column(db.String(255), nullable=True)
    created_by     = db.Column(db.Integer, nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    fee_type       = db.relationship('FeeType', backref='account_fees')

class FeeTransaction(db.Model):
    __tablename__ = 'fee_transactions'
    id             = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(20), db.ForeignKey('client_accounts.account_number'))
    fee_type_id    = db.Column(db.Integer, db.ForeignKey('fee_types.id'))
    amount         = db.Column(db.Float, nullable=False)
    aum_at_time    = db.Column(db.Float, nullable=True)
    rate_applied   = db.Column(db.Float, nullable=True)
    period_from    = db.Column(db.Date, nullable=True)
    period_to      = db.Column(db.Date, nullable=True)
    currency       = db.Column(db.String(10), default='GHS')
    status         = db.Column(db.String(20), default='PENDING')
    created_by     = db.Column(db.Integer, nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    fee_type = db.relationship('FeeType')
    account  = db.relationship('ClientAccount',
                               primaryjoin='FeeTransaction.account_number == ClientAccount.account_number',
                               foreign_keys=[account_number])

class ClientRequest(db.Model):
    __tablename__ = 'client_requests'
    id             = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(20), db.ForeignKey('client_accounts.account_number'))
    request_type   = db.Column(db.String(30), nullable=False)
    amount         = db.Column(db.Float, nullable=True)
    currency       = db.Column(db.String(10), default='GHS')
    asset_class    = db.Column(db.String(40), nullable=True)
    description    = db.Column(db.Text, nullable=True)
    supporting_doc = db.Column(db.String(300), nullable=True)
    status         = db.Column(db.String(20), default='PENDING')
    admin_note     = db.Column(db.Text, nullable=True)
    reviewed_by    = db.Column(db.Integer, nullable=True)
    reviewed_at    = db.Column(db.DateTime, nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    client_account = db.relationship('ClientAccount',
                                     primaryjoin='ClientRequest.account_number == ClientAccount.account_number',
                                     foreign_keys=[account_number])

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id             = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(20), db.ForeignKey('client_accounts.account_number'), nullable=False)
    txn_date       = db.Column(db.Date, nullable=False)
    txn_type       = db.Column(db.String(40), nullable=False)
    description    = db.Column(db.String(255), nullable=True)
    amount         = db.Column(db.Float, nullable=False)     # amount in original currency
    amount_ghs     = db.Column(db.Float, nullable=True)      # GHS equivalent (auto-computed on approval)
    fx_rate_used   = db.Column(db.Float, nullable=True)      # FX rate applied at time of entry
    currency       = db.Column(db.String(10), default='GHS')
    reference      = db.Column(db.String(80), nullable=True)
    status         = db.Column(db.String(20), default='PENDING')  # PENDING â†’ APPROVED | REJECTED
    approved_by    = db.Column(db.Integer, nullable=True)
    approved_at    = db.Column(db.DateTime, nullable=True)
    rejection_note = db.Column(db.String(255), nullable=True)
    created_by     = db.Column(db.Integer, nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    investment_id  = db.Column(db.Integer, db.ForeignKey('investments.id'), nullable=True)

class Investment(db.Model):
    __tablename__ = 'investments'
    id             = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(20), db.ForeignKey('client_accounts.account_number'), nullable=False)
    asset_class    = db.Column(db.String(40), nullable=False)
    sub_type       = db.Column(db.String(60), nullable=True)
    issuer         = db.Column(db.String(120), nullable=True)
    security_name  = db.Column(db.String(200), nullable=True)
    symbol         = db.Column(db.String(20), nullable=True)
    isin           = db.Column(db.String(30), nullable=True)
    exchange       = db.Column(db.String(40), nullable=True)
    sector         = db.Column(db.String(80), nullable=True)
    trade_date     = db.Column(db.Date, nullable=True)
    issue_date     = db.Column(db.Date, nullable=True)
    maturity_date  = db.Column(db.Date, nullable=True)
    tenor          = db.Column(db.Integer, nullable=True)
    quantity       = db.Column(db.Float, nullable=True)
    face_value     = db.Column(db.Float, nullable=True)
    coupon_rate    = db.Column(db.Float, nullable=True)
    coupon_freq    = db.Column(db.Integer, nullable=True, default=2)
    interest_rate  = db.Column(db.Float, nullable=True)
    clean_price    = db.Column(db.Float, nullable=True)
    unit_cost      = db.Column(db.Float, nullable=True)
    total_cost     = db.Column(db.Float, nullable=True)
    currency       = db.Column(db.String(10), default='GHS')
    current_price  = db.Column(db.Float, nullable=True)
    mkt_value_htm  = db.Column(db.Float, nullable=True)
    mkt_value_mtm  = db.Column(db.Float, nullable=True)
    last_coupon_date = db.Column(db.Date, nullable=True)
    vintage_year   = db.Column(db.Integer, nullable=True)
    geography      = db.Column(db.String(60), nullable=True)
    stage          = db.Column(db.String(60), nullable=True)
    committed      = db.Column(db.Float, nullable=True)
    called         = db.Column(db.Float, nullable=True)
    distributions  = db.Column(db.Float, nullable=True)
    moic           = db.Column(db.Float, nullable=True)
    irr            = db.Column(db.Float, nullable=True)
    nav            = db.Column(db.Float, nullable=True)
    outstanding    = db.Column(db.Float, nullable=True)
    rating         = db.Column(db.String(20), nullable=True)
    pik            = db.Column(db.Boolean, default=False)
    country_of_issue = db.Column(db.String(60), nullable=True)
    status         = db.Column(db.String(20), default='PENDING')
    approved_by    = db.Column(db.Integer, nullable=True)
    approved_at    = db.Column(db.DateTime, nullable=True)
    created_by     = db.Column(db.Integer, nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    notes          = db.Column(db.Text, nullable=True)
    transactions = db.relationship('Transaction', backref='investment', lazy=True,
                                   foreign_keys='Transaction.investment_id')

    @property
    def days_run(self):
        return (date.today() - self.trade_date).days if self.trade_date else 0

    @property
    def days_to_maturity(self):
        if self.maturity_date:
            return max(0, (self.maturity_date - date.today()).days)
        # Fallback: estimate from tenor
        if self.tenor and self.trade_date:
            if self.asset_class in ('BONDS','EUROBONDS','PRIVATE_DEBT'):
                # tenor stored in years
                try:
                    from dateutil.relativedelta import relativedelta
                    est_mat = self.trade_date + relativedelta(years=int(self.tenor))
                except Exception:
                    from datetime import timedelta
                    est_mat = self.trade_date + timedelta(days=int(self.tenor * 365))
                return max(0, (est_mat - date.today()).days)
            elif self.asset_class in ('GOVT_SECURITIES','MONEY_MARKET'):
                # tenor stored in days
                from datetime import timedelta
                est_mat = self.trade_date + timedelta(days=int(self.tenor))
                return max(0, (est_mat - date.today()).days)
        return None

    @property
    def accrued_interest(self):
        if self.asset_class in ('GOVT_SECURITIES','BONDS','EUROBONDS'):
            if self.face_value and (self.coupon_rate or self.interest_rate):
                rate  = self.coupon_rate or self.interest_rate or 0
                basis = 364 if (self.sub_type and ('BILL' in (self.sub_type or '').upper() or
                                                    'T-BILL' in (self.sub_type or '').upper())) else 365
                ref   = self.last_coupon_date or self.trade_date
                days  = (date.today() - ref).days if ref else 0
                return (self.face_value * (rate / 100) * days) / basis
        elif self.asset_class == 'MONEY_MARKET':
            # Accrued simple interest on principal
            if self.face_value and self.interest_rate and self.trade_date:
                days = (date.today() - self.trade_date).days
                return self.face_value * (self.interest_rate / 100) * days / 365
        elif self.asset_class == 'PRIVATE_DEBT':
            if self.outstanding and self.coupon_rate and self.trade_date:
                days = (date.today() - self.trade_date).days
                return (self.outstanding or self.total_cost or 0) * (self.coupon_rate / 100) * days / 365
        return 0.0

    @property
    def computed_mkt_value(self):
        if self.asset_class == 'GOVT_SECURITIES':
            if self.face_value and self.interest_rate:
                basis = 364 if (self.sub_type and 'BILL' in self.sub_type.upper()) else 365
                # Prefer maturity_date for d2m; fall back to stored tenor (days)
                if self.maturity_date:
                    d2m = max(0, (self.maturity_date - date.today()).days)
                elif self.tenor:
                    d2m = max(0, self.tenor - self.days_run)
                else:
                    d2m = 0
                if d2m >= 0 and (self.interest_rate or 0) > 0:
                    return self.face_value / (1 + (self.interest_rate/100) * d2m / basis)
            return self.total_cost or 0
        elif self.asset_class in ('BONDS','EUROBONDS'):
            if self.face_value and self.clean_price:
                return (self.clean_price/100)*self.face_value + self.accrued_interest
            return self.total_cost or 0
        elif self.asset_class in ('GSE_EQUITIES','GLOBAL_EQUITIES'):
            if self.quantity and self.current_price:
                return self.quantity * self.current_price
            return self.total_cost or 0
        elif self.asset_class == 'MONEY_MARKET':
            # Principal + accrued interest to date
            principal = self.face_value or self.total_cost or 0
            return principal + self.accrued_interest
        elif self.asset_class == 'PRIVATE_EQUITY':
            return self.nav or self.total_cost or 0
        elif self.asset_class == 'PRIVATE_DEBT':
            # Outstanding principal balance (accrued interest shown separately in reports)
            return self.outstanding or self.total_cost or 0
        elif self.asset_class == 'MUTUAL_FUNDS':
            if self.quantity and self.current_price:
                return self.quantity * self.current_price
            return self.total_cost or 0
        return self.total_cost or 0

class FXRate(db.Model):
    __tablename__ = 'fx_rates'
    id = db.Column(db.Integer, primary_key=True)
    base = db.Column(db.String(5), nullable=False)
    quote = db.Column(db.String(5), nullable=False)
    rate = db.Column(db.Float, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

class StockPrice(db.Model):
    __tablename__ = 'stock_prices'
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False, unique=True)
    name = db.Column(db.String(120), nullable=True)
    price = db.Column(db.Float, nullable=False)
    exchange = db.Column(db.String(20), nullable=True)
    change_pct = db.Column(db.Float, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

class MigrationLog(db.Model):
    __tablename__ = 'migration_logs'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=True)
    records_in = db.Column(db.Integer, default=0)
    records_ok = db.Column(db.Integer, default=0)
    records_err = db.Column(db.Integer, default=0)
    errors = db.Column(db.Text, nullable=True)
    executed_by = db.Column(db.Integer, nullable=True)
    executed_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='COMPLETED')

class EmailLog(db.Model):
    __tablename__ = 'email_logs'
    id = db.Column(db.Integer, primary_key=True)
    recipient = db.Column(db.String(120))
    subject = db.Column(db.String(255))
    body = db.Column(db.Text)
    status = db.Column(db.String(20), default='SENT')
    error = db.Column(db.Text, nullable=True)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)


# â”€â”€ SEC REGULATORY REPORT MODELS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

SEC_CLIENT_TYPES = [
    'Local-Institution',
    'Local-Retail',
    'Foreign-Institution',
    'Foreign-Retail',
]

SEC_CLIENT_CLASSIFICATIONS = [
    'Male',
    'Female',
    'Joint',
    'Institutional',
]

SEC_PORTFOLIO_SECURITIES = [
    '91 Day Treasury Bills',
    '182 Day Treasury Bills',
    '1-2 Year Notes',
    '3-5 Year Bonds',
    '5+ Year Bonds',
    'GoG Euro Bonds (value in GHS)',
    'Local Listed Corporate Bonds',
    'Foreign Listed Corporate Bonds',
    'Local Unlisted Corporate Bonds',
    'Foreign Unlisted Corporate Bonds',
    'Commercial Paper',
    'Local Listed Equity',
    'Local Unlisted Equity',
    'Foreign Listed Equity',
    'Foreign Unlisted Equity',
    'Preference Shares',
    'Venture Capital',
    'CIS',
    'REIT',
    'Cash Balance',
    'Bank Balance',
    'Call Investment',
    'Fixed Deposit',
    'Others',
]

SEC_REGULATORY_BODIES = [
    'Securities & Exchange Commission',
    'Bank of Ghana',
    'National Insurance Commission',
    'National Pension Regulatory Authority',
    'Social Institutions',
    'Individual & Joint Account Corporate Others',
]


class SECReport(db.Model):
    __tablename__ = 'sec_reports'
    id           = db.Column(db.Integer, primary_key=True)
    year         = db.Column(db.Integer, nullable=False)
    quarter      = db.Column(db.String(2), nullable=False)   # Q1 Q2 Q3 Q4
    status       = db.Column(db.String(20), default='DRAFT') # DRAFT SUBMITTED
    created_by   = db.Column(db.Integer, nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_at = db.Column(db.DateTime, nullable=True)
    notes        = db.Column(db.Text, nullable=True)

    client_type_rows   = db.relationship('SECClientTypeRow',   backref='report', lazy=True, cascade='all,delete-orphan')
    client_class_rows  = db.relationship('SECClientClassRow',  backref='report', lazy=True, cascade='all,delete-orphan')
    portfolio_holdings = db.relationship('SECPortfolioHolding',backref='report', lazy=True, cascade='all,delete-orphan')
    cis_inflows        = db.relationship('SECCISInflow',       backref='report', lazy=True, cascade='all,delete-orphan')
    cis_outflows       = db.relationship('SECCISOutflow',      backref='report', lazy=True, cascade='all,delete-orphan')

    @property
    def label(self):
        return f'{self.quarter} {self.year}'


class SECClientTypeRow(db.Model):
    __tablename__ = 'sec_client_type_rows'
    id                  = db.Column(db.Integer, primary_key=True)
    report_id           = db.Column(db.Integer, db.ForeignKey('sec_reports.id'), nullable=False)
    client_type         = db.Column(db.String(40), nullable=False)
    no_clients          = db.Column(db.Integer,  default=0)
    htm_value           = db.Column(db.Float,    default=0.0)
    mtm_value           = db.Column(db.Float,    default=0.0)
    value_redemption    = db.Column(db.Float,    default=0.0)
    value_subscription  = db.Column(db.Float,    default=0.0)
    effective_mgt_fees  = db.Column(db.Float,    default=0.0)


class SECClientClassRow(db.Model):
    __tablename__ = 'sec_client_class_rows'
    id                  = db.Column(db.Integer, primary_key=True)
    report_id           = db.Column(db.Integer, db.ForeignKey('sec_reports.id'), nullable=False)
    classification      = db.Column(db.String(30), nullable=False)
    no_clients          = db.Column(db.Integer,  default=0)
    htm_value           = db.Column(db.Float,    default=0.0)
    mtm_value           = db.Column(db.Float,    default=0.0)
    value_redemption    = db.Column(db.Float,    default=0.0)
    value_subscription  = db.Column(db.Float,    default=0.0)
    effective_mgt_fees  = db.Column(db.Float,    default=0.0)


class SECPortfolioHolding(db.Model):
    __tablename__ = 'sec_portfolio_holdings'
    id            = db.Column(db.Integer, primary_key=True)
    report_id     = db.Column(db.Integer, db.ForeignKey('sec_reports.id'), nullable=False)
    security_type = db.Column(db.String(80), nullable=False)
    current_htm   = db.Column(db.Float, default=0.0)
    previous_htm  = db.Column(db.Float, default=0.0)


class SECCISInflow(db.Model):
    __tablename__ = 'sec_cis_inflow'
    id                = db.Column(db.Integer, primary_key=True)
    report_id         = db.Column(db.Integer, db.ForeignKey('sec_reports.id'), nullable=False)
    regulatory_body   = db.Column(db.String(80), nullable=False)
    customer_category = db.Column(db.String(80), nullable=True)
    no_clients        = db.Column(db.Integer, default=0)
    beginning_fum     = db.Column(db.Float,   default=0.0)
    total_inflow      = db.Column(db.Float,   default=0.0)
    total_outflow     = db.Column(db.Float,   default=0.0)
    total_gains_loss  = db.Column(db.Float,   default=0.0)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def net_inflow_outflow(self):
        return (self.total_inflow or 0) - (self.total_outflow or 0)

    @property
    def balance_fum(self):
        return ((self.beginning_fum or 0)
                + (self.total_inflow or 0)
                - (self.total_outflow or 0)
                + (self.total_gains_loss or 0))


class SECCISOutflow(db.Model):
    __tablename__ = 'sec_cis_outflow'
    id                    = db.Column(db.Integer, primary_key=True)
    report_id             = db.Column(db.Integer, db.ForeignKey('sec_reports.id'), nullable=False)
    regulatory_body       = db.Column(db.String(80), nullable=False)
    customer_category     = db.Column(db.String(80), nullable=True)
    total_fum_beginning   = db.Column(db.Float, default=0.0)
    fund_outflow          = db.Column(db.Float, default=0.0)
    total_repayments      = db.Column(db.Float, default=0.0)
    gains_loss            = db.Column(db.Float, default=0.0)
    created_at            = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def net_inflow_outflow(self):
        return (self.total_repayments or 0) - (self.fund_outflow or 0)

    @property
    def total_fum_end(self):
        return ((self.total_fum_beginning or 0)
                - (self.fund_outflow or 0)
                + (self.total_repayments or 0)
                + (self.gains_loss or 0))


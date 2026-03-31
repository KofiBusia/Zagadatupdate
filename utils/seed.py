from models import AdminUser, ClientAccount, ClientUser, StockPrice, FXRate, FeeType, db
from datetime import datetime, date

GSE_STOCKS = [
    {"symbol": "ACCESS", "name": "Access Bank Ghana PLC",             "price": 17.80, "exchange": "GSE"},
    {"symbol": "ADB",    "name": "Agricultural Development Bank PLC", "price": 5.06,  "exchange": "GSE"},
    {"symbol": "ASG",    "name": "Asante Gold Corporation",           "price": 8.89,  "exchange": "GSE"},
    {"symbol": "ALLGH",  "name": "Atlantic Lithium Ltd",              "price": 6.12,  "exchange": "GSE"},
    {"symbol": "BOPP",   "name": "Benso Palm Plantation PLC",         "price": 26.31, "exchange": "GSE"},
    {"symbol": "CAL",    "name": "Cal Bank PLC",                      "price": 0.64,  "exchange": "GSE"},
    {"symbol": "EGH",    "name": "Ecobank Ghana PLC",                 "price": 6.30,  "exchange": "GSE"},
    {"symbol": "EGL",    "name": "Enterprise Group PLC",              "price": 2.05,  "exchange": "GSE"},
    {"symbol": "ETI",    "name": "Ecobank Transnational Inc.",         "price": 2.45,  "exchange": "GSE"},
    {"symbol": "FML",    "name": "Fan Milk PLC",                      "price": 3.70,  "exchange": "GSE"},
    {"symbol": "GCB",    "name": "GCB Bank PLC",                      "price": 6.51,  "exchange": "GSE"},
    {"symbol": "GGBL",   "name": "Guinness Ghana Breweries PLC",      "price": 8.45,  "exchange": "GSE"},
    {"symbol": "GOIL",   "name": "Ghana Oil Company PLC",             "price": 1.60,  "exchange": "GSE"},
    {"symbol": "MAC",    "name": "Mega African Capital PLC",          "price": 5.20,  "exchange": "GSE"},
    {"symbol": "MTNGH",  "name": "Scancom PLC (MTN Ghana)",           "price": 3.10,  "exchange": "GSE"},
    {"symbol": "RBGH",   "name": "Republic Bank (Ghana) PLC",         "price": 0.65,  "exchange": "GSE"},
    {"symbol": "SCB",    "name": "Standard Chartered Bank Gh. PLC",   "price": 25.02, "exchange": "GSE"},
    {"symbol": "SIC",    "name": "SIC Insurance Company PLC",         "price": 0.37,  "exchange": "GSE"},
    {"symbol": "SOGEGH", "name": "Societe Generale Ghana PLC",        "price": 1.50,  "exchange": "GSE"},
    {"symbol": "TOTAL",  "name": "TotalEnergies Marketing Ghana PLC", "price": 16.47, "exchange": "GSE"},
    {"symbol": "TLW",    "name": "Tullow Oil PLC",                    "price": 11.92, "exchange": "GSE"},
    {"symbol": "UNIL",   "name": "Unilever Ghana PLC",                "price": 19.50, "exchange": "GSE"},
]

GLOBAL_STOCKS = [
    {"symbol": "TSLA",  "name": "Tesla Inc.",             "price": 367.96, "exchange": "NASDAQ"},
    {"symbol": "AAPL",  "name": "Apple Inc.",             "price": 225.00, "exchange": "NASDAQ"},
    {"symbol": "MSFT",  "name": "Microsoft Corp.",        "price": 415.00, "exchange": "NASDAQ"},
    {"symbol": "GOOGL", "name": "Alphabet Inc.",          "price": 175.00, "exchange": "NASDAQ"},
    {"symbol": "META",  "name": "Meta Platforms Inc.",    "price": 610.00, "exchange": "NASDAQ"},
    {"symbol": "AMZN",  "name": "Amazon.com Inc.",        "price": 220.00, "exchange": "NASDAQ"},
    {"symbol": "NVDA",  "name": "NVIDIA Corp.",           "price": 925.00, "exchange": "NASDAQ"},
    {"symbol": "TM",    "name": "Toyota Motor Corp.",     "price": 205.02, "exchange": "NYSE"},
    {"symbol": "JPM",   "name": "JPMorgan Chase & Co.",   "price": 245.00, "exchange": "NYSE"},
    {"symbol": "XOM",   "name": "Exxon Mobil Corp.",      "price": 118.00, "exchange": "NYSE"},
    {"symbol": "BRK.B", "name": "Berkshire Hathaway B",   "price": 462.00, "exchange": "NYSE"},
    {"symbol": "V",     "name": "Visa Inc.",              "price": 310.00, "exchange": "NYSE"},
]

DEFAULT_FX = [
    {"base": "USD", "quote": "GHS", "rate": 10.95},
    {"base": "EUR", "quote": "GHS", "rate": 11.90},
    {"base": "GBP", "quote": "GHS", "rate": 13.80},
    {"base": "CNY", "quote": "GHS", "rate": 1.50},
    {"base": "NGN", "quote": "GHS", "rate": 0.0068},
    {"base": "GHS", "quote": "GHS", "rate": 1.00},
]

DEFAULT_FEE_TYPES = [
    {"name": "Management Fee",   "description": "Annual fee charged on total funds under management"},
    {"name": "Performance Fee",  "description": "Fee charged on returns above agreed benchmark"},
    {"name": "Custody Fee",      "description": "Fee for safekeeping and administration of securities"},
    {"name": "Advisory Fee",     "description": "Fee for investment advisory services"},
    {"name": "Placement Fee",    "description": "One-time fee for placement of funds into instruments"},
    {"name": "Exit Fee",         "description": "Fee charged on withdrawal of funds"},
    {"name": "Transaction Fee",  "description": "Per-transaction processing fee"},
]

def seed_defaults():
    # Super admin
    if not AdminUser.query.filter_by(staff_id='SA001').first():
        sa = AdminUser(staff_id='SA001', full_name='Super Administrator',
                       email='admin@zagadatcapital.com', role='SUPER_ADMIN', is_rm=True,
                       rm_commission_rate=1.0)
        sa.set_password('ZagadatAdmin@2026')
        db.session.add(sa)
        db.session.flush()

    # Stock prices
    for s in GSE_STOCKS + GLOBAL_STOCKS:
        if not StockPrice.query.filter_by(symbol=s['symbol']).first():
            db.session.add(StockPrice(symbol=s['symbol'], name=s['name'],
                                      price=s['price'], exchange=s['exchange'], change_pct=0.0))

    # FX rates
    for fx in DEFAULT_FX:
        if not FXRate.query.filter_by(base=fx['base'], quote=fx['quote']).first():
            db.session.add(FXRate(base=fx['base'], quote=fx['quote'], rate=fx['rate']))

    # Fee types
    for ft in DEFAULT_FEE_TYPES:
        if not FeeType.query.filter_by(name=ft['name']).first():
            db.session.add(FeeType(name=ft['name'], description=ft['description'],
                                   is_active=True, created_by=1))

    # Demo account
    if not ClientAccount.query.filter_by(account_number='ZC-00001').first():
        acc = ClientAccount(
            account_number='ZC-00001', full_name='Demo Client',
            phone='0244000001', email='demo@zagadatcapital.com',
            account_type='Individual', status='APPROVED',
            base_currency='GHS', country='Ghana',
            nationality='Ghanaian', residential_status='Resident Ghanaian',
            risk_profile='Moderate', investment_objective='Balanced',
            approved_by=1, approved_at=datetime.utcnow(),
            relationship_manager_id=1, created_by=1,
            management_fee_rate=2.0
        )
        db.session.add(acc)
        db.session.flush()

        cu = ClientUser(account_number='ZC-00001', phone='0244000001')
        cu.set_password('Demo@2026')
        db.session.add(cu)

        from models import Transaction
        db.session.add(Transaction(
            account_number='ZC-00001', txn_date=date.today(),
            txn_type='DEPOSIT', description='Opening balance deposit',
            amount=500000.00, currency='GHS', status='APPROVED', created_by=1
        ))

    db.session.commit()

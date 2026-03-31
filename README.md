# ZAGADAT CAPITAL — Fund Management System
### World-Class Portfolio Management Platform

---

## 🚀 Quick Start (Windows)

1. **Unzip** `zagadat_capital.zip` to a folder
2. **Double-click** `start.bat`
3. Open your browser at **http://127.0.0.1:5000**

---

## 🔐 Default Login Credentials

| Portal | Username | Password |
|--------|----------|----------|
| Super Admin | `SA001` | `ZagadatAdmin@2026` |
| Demo Client | Account: `ZC-00001` · Phone: `0244000001` | — |

---

## ✨ Features

### Authentication & Access
- **Client login** — Account Number + Phone Number (existing clients)
- **New client signup** — Self-service at `/signup` (Name + Password → pending approval)
- **Admin login** — Staff ID + Password
- **6 role levels** — Super Admin, Account Setup, Account Approver, Investment Entry, Investment Approver, Report Viewer

### Account Opening (Full KYC)
- Individual, Individual ITF, Joint, Corporate, Institutional, Pension Fund, Provident Fund
- Complete KYC: Personal, Contact, Employment, Financial, Beneficiaries, ITF, PEP/AML, FATCA/CRS
- Signature capture (draw on screen or upload)
- Document upload (ID, passport photo, address proof)
- Email notification on approval

### Investments — 9 Asset Classes
- Money Market (Fixed Deposits)
- Government Securities (T-Bills — 364-day basis)
- Bonds & Corporate Bonds (clean price → MTM auto-calculation)
- Eurobonds (USD/international)
- GSE Listed Equities (22 stocks, live prices)
- Global Equities (12 stocks: TSLA, AAPL, MSFT, META, NVDA...)
- Private Equity
- Private Debt / Direct Lending
- Mutual Funds & Unit Trusts

### Live Market Data
- **Rolling ticker bar** — GSE / NASDAQ / NYSE rotating
- **Live FX rates** — USD, EUR, GBP, CNY, NGN → GHS via open.er-api.com
- **GSE prices** — scraped from afx.kwayisi.org
- **Global prices** — via Yahoo Finance

### Fees Management
- Standard fee types: Management Fee, Performance Fee, Custody Fee, Advisory Fee, Placement Fee, Exit Fee, Transaction Fee
- Create custom fee types
- Assign rates per account (set by Account Approver)
- Charge fees — auto-deducts from cash balance
- Fees Report PDF

### Relationship Managers (RM)
- Assign clients to RMs
- 1% commission on client portfolio value (configurable)
- RM performance dashboard — book value, earnings
- Earnings grow as portfolio grows

### Reports (Branded Black & Gold PDF)
- Portfolio Valuation Report (PVR) — 6 currencies (GHS, USD, EUR, GBP, CNY, NGN)
- Transaction Statement with running balance
- Global AUM Report (all accounts)
- Fees Report
- Asset class drill-down reports

### Client Portal
- Portfolio dashboard with allocation chart
- Transaction statement
- Submit withdrawal / investment requests
- Profile & document management
- Signature capture

### Admin Features
- Full audit log of all actions
- Data migration via CSV (accounts, transactions, investments)
- CSV templates for migration
- Manual stock price override
- Manual FX rate override
- Approve/reject client requests with email notification

---

## 📧 Email Configuration

To enable email notifications (account approvals, request updates):

1. Copy `.env.example` to `.env`
2. Fill in your SMTP credentials
3. For Gmail: enable 2FA → generate App Password → use in MAIL_PASSWORD

If email is not configured, the system continues to work — notifications are logged but not sent.

---

## 🗂 Project Structure

```
zagadat/
├── app.py                  # Flask factory
├── models.py               # All database models
├── requirements.txt
├── start.bat               # Windows launcher
├── .env.example            # Email config template
├── routes/
│   ├── auth.py             # Login, logout, signup
│   ├── admin.py            # Admin portal (all CRUD)
│   ├── user.py             # Client portal
│   ├── api.py              # REST API (stocks, FX, calculations)
│   └── reports.py          # PDF report endpoints
├── reports/
│   └── pdf_reports.py      # ReportLab PDF engine
├── utils/
│   ├── market_data.py      # Live GSE + global prices + FX
│   ├── notifications.py    # Email + audit logging
│   └── seed.py             # Default data seeder
├── templates/
│   ├── base.html           # Global layout + ticker
│   ├── login.html          # Login page
│   ├── signup.html         # Public signup
│   ├── admin/              # 15+ admin templates
│   └── user/               # Client portal templates
├── static/
│   └── img/logo.png        # Zagadat Capital logo
└── uploads/                # Secure document storage
    ├── signatures/
    ├── documents/
    └── photos/
```

---

## 🔒 Security Notes

- All passwords are bcrypt-hashed
- Session-based authentication with Flask-Login
- Role-based access control on every endpoint
- Audit trail for all admin actions
- Document uploads stored server-side (not in database)
- Cash balance enforced — no investment without sufficient funds

---

*Zagadat Capital Fund Management System — Built for the world's best.*

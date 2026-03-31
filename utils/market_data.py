import requests
import json
from datetime import datetime, timedelta
from models import FXRate, StockPrice, db
import time

# ── FX RATES ─────────────────────────────────────────────────────────────────
CURRENCIES = ['USD', 'EUR', 'GBP', 'CNY', 'NGN', 'GHS']

def fetch_fx_rates():
    """Fetch live FX rates - GHS base via open.er-api.com (free, no key needed)"""
    try:
        url = "https://open.er-api.com/v6/latest/GHS"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get('result') == 'success':
            rates = data['rates']
            # We store as: 1 FOREIGN = X GHS
            # rates[USD] = amount of USD per 1 GHS
            # So 1 USD = 1/rates['USD'] GHS
            for currency in CURRENCIES:
                if currency == 'GHS':
                    continue
                if currency in rates and rates[currency] > 0:
                    ghs_per_foreign = 1.0 / rates[currency]  # 1 USD = ? GHS
                    existing = FXRate.query.filter_by(base=currency, quote='GHS').first()
                    if existing:
                        existing.rate = ghs_per_foreign
                        existing.updated_at = datetime.utcnow()
                    else:
                        db.session.add(FXRate(base=currency, quote='GHS', rate=ghs_per_foreign))
            db.session.commit()
            return True
    except Exception as e:
        print(f"FX fetch error: {e}")
    return False

def get_fx_rate(base_currency='USD', quote_currency='GHS'):
    """Get rate: 1 base = X quote"""
    if base_currency == quote_currency:
        return 1.0
    if quote_currency == 'GHS':
        r = FXRate.query.filter_by(base=base_currency, quote='GHS').first()
        return r.rate if r else 10.95
    elif base_currency == 'GHS':
        r = FXRate.query.filter_by(base=quote_currency, quote='GHS').first()
        return 1.0 / r.rate if r and r.rate > 0 else 1.0
    else:
        r1 = get_fx_rate(base_currency, 'GHS')
        r2 = get_fx_rate(quote_currency, 'GHS')
        return r1 / r2 if r2 > 0 else 1.0

def get_all_fx():
    """Return dict of all rates: 1 foreign = X GHS"""
    rates = {}
    for r in FXRate.query.all():
        rates[r.base] = {
            'rate': r.rate,
            'updated': r.updated_at.strftime('%H:%M %d %b %Y') if r.updated_at else ''
        }
    rates['GHS'] = {'rate': 1.0, 'updated': datetime.utcnow().strftime('%H:%M %d %b %Y')}
    return rates


# ── GSE STOCK PRICES ──────────────────────────────────────────────────────────
def fetch_gse_prices():
    """Scrape GSE prices from afx.kwayisi.org"""
    try:
        import requests
        from bs4 import BeautifulSoup
        resp = requests.get('https://afx.kwayisi.org/gse/', headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        }, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        table = soup.find('table', class_='t')
        if table:
            rows = table.find('tbody').find_all('tr')
            updated = 0
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 4:
                    symbol = cols[0].get_text(strip=True)
                    try:
                        price = float(cols[2].get_text(strip=True).replace(',', ''))
                    except:
                        continue
                    sp = StockPrice.query.filter_by(symbol=symbol).first()
                    if sp:
                        old_price = sp.price
                        sp.price = price
                        sp.change_pct = ((price - old_price) / old_price * 100) if old_price else 0
                        sp.updated_at = datetime.utcnow()
                        updated += 1
            db.session.commit()
            return updated
    except Exception as e:
        print(f"GSE scrape error: {e}")
    return 0


def fetch_global_prices():
    """Try to fetch global stock prices via Yahoo Finance (no key needed)"""
    GLOBAL_SYMBOLS = {
        'TSLA': 'Tesla Inc.', 'AAPL': 'Apple Inc.', 'MSFT': 'Microsoft Corp.',
        'GOOGL': 'Alphabet Inc.', 'META': 'Meta Platforms', 'AMZN': 'Amazon.com',
        'NVDA': 'NVIDIA Corp.', 'TM': 'Toyota Motor', 'JPM': 'JPMorgan Chase',
        'XOM': 'Exxon Mobil', 'V': 'Visa Inc.', 'BRK.B': 'Berkshire Hathaway'
    }
    updated = 0
    for symbol in GLOBAL_SYMBOLS:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1m"
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
            data = r.json()
            price = data['chart']['result'][0]['meta']['regularMarketPrice']
            prev  = data['chart']['result'][0]['meta'].get('previousClose', price)
            change_pct = ((price - prev) / prev * 100) if prev else 0
            sp = StockPrice.query.filter_by(symbol=symbol).first()
            if sp:
                sp.price = price
                sp.change_pct = change_pct
                sp.updated_at = datetime.utcnow()
                updated += 1
            time.sleep(0.1)
        except Exception as e:
            print(f"Global price error {symbol}: {e}")
    if updated:
        db.session.commit()
    return updated


def get_all_stocks():
    stocks = StockPrice.query.order_by(StockPrice.exchange, StockPrice.symbol).all()
    return [
        {
            'symbol': s.symbol, 'name': s.name, 'price': s.price,
            'exchange': s.exchange or 'GSE',
            'change_pct': round(s.change_pct or 0, 2),
            'updated': s.updated_at.strftime('%H:%M') if s.updated_at else '--'
        }
        for s in stocks
    ]

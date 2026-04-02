"""
utils/stock_sync.py
====================
Handles syncing of GSE (Ghana Stock Exchange) prices.
Uses the free GSE API at dev.kwayisi.org — no API key required.
"""

import requests
from datetime import datetime
from extensions import db
from models import StockPrice


def sync_gse_prices():
    """
    Fetch live GSE stock prices and save them to the database.
    Runs inside Flask app.app_context() via APScheduler.
    """

    GSE_LIVE_URL = "https://dev.kwayisi.org/apis/gse/live"

    try:
        print("Starting GSE price sync...")

        response = requests.get(GSE_LIVE_URL, timeout=10)
        response.raise_for_status()

        data = response.json()

        if not data:
            print("No data returned from GSE API.")
            return

        for item in data:
            symbol     = item.get("name")
            price      = item.get("price")
            change_pct = item.get("change", 0)

            if not symbol or price is None:
                continue

            stock = StockPrice.query.filter_by(symbol=symbol).first()
            if stock:
                # Update existing record
                stock.price      = price
                stock.change_pct = change_pct
                stock.exchange   = "GSE"
                stock.updated_at = datetime.utcnow()
            else:
                # Create new record
                stock = StockPrice(
                    symbol=symbol,
                    name=symbol,       # API doesn't return full name on /live
                    price=price,
                    change_pct=change_pct,
                    exchange="GSE",
                    updated_at=datetime.utcnow(),
                )
                db.session.add(stock)

            print(f"  {symbol}: GHS {price} | change: {change_pct}%")

        db.session.commit()
        print("GSE price sync completed successfully.")

    except requests.exceptions.ConnectionError:
        print("GSE sync failed: Could not connect to API. Check your internet.")
    except requests.exceptions.Timeout:
        print("GSE sync failed: Request timed out.")
    except requests.exceptions.HTTPError as e:
        print(f"GSE sync failed: HTTP error — {e}")
    except Exception as e:
        db.session.rollback()
        print(f"GSE sync failed: {e}")
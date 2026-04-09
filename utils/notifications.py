"""Email notification and audit logging utilities"""
from flask import current_app, request as flask_request
from datetime import datetime

def send_email(recipient, subject, body_html, body_text=None):
    """
    Send email notification. Logs to EmailLog table.
    Configure MAIL_SERVER etc in app config for real sending.
    Falls back to logging only if not configured.
    """
    from models import EmailLog, db

    log = EmailLog(
        recipient=recipient,
        subject=subject,
        body=body_html,
        status='PENDING',
        sent_at=datetime.utcnow()
    )
    db.session.add(log)

    try:
        from flask_mail import Mail, Message
        mail = Mail(current_app)
        msg = Message(
            subject=subject,
            recipients=[recipient],
            html=body_html,
            body=body_text or body_html
        )
        mail.send(msg)
        log.status = 'SENT'
    except Exception as e:
        log.status = 'FAILED'
        log.error = str(e)
        # Don't raise — email failure shouldn't break the app
        print(f"[EMAIL] Failed to send to {recipient}: {e}")

    db.session.commit()


def email_account_approved(account):
    """Send account approval notification"""
    if not account.email:
        return
    subject = f"Your Zagadat Capital Account Has Been Approved — {account.account_number}"
    body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0A0A0A; color: #F5F5F0; padding: 40px; border-radius: 12px;">
      <div style="text-align:center; margin-bottom: 30px;">
        <h1 style="color: #C9A84C; font-size: 28px; margin: 0;">ZAGADAT CAPITAL</h1>
        <p style="color: #8A8A9A; font-size: 12px; letter-spacing: 3px; text-transform:uppercase;">Fund Management</p>
      </div>
      <hr style="border-color: rgba(201,168,76,0.3); margin: 20px 0;">
      <h2 style="color: #C9A84C;">Account Approved ✓</h2>
      <p>Dear <strong>{account.full_name}</strong>,</p>
      <p>We are pleased to inform you that your investment account has been successfully approved.</p>
      <div style="background: rgba(201,168,76,0.1); border: 1px solid rgba(201,168,76,0.3); border-radius: 8px; padding: 20px; margin: 20px 0;">
        <p style="margin: 0;"><strong>Account Number:</strong> <span style="color:#C9A84C; font-size:18px;">{account.account_number}</span></p>
        <p style="margin: 8px 0 0 0;"><strong>Account Type:</strong> {account.account_type}</p>
        <p style="margin: 8px 0 0 0;"><strong>Login:</strong> Use your Account Number + Phone Number</p>
      </div>
      <p>You can now log in at your Zagadat Capital portal to view your portfolio and make investment requests.</p>
      <p style="color: #8A8A9A; font-size: 12px; margin-top: 40px;">This is an automated notification. Please do not reply to this email.<br>
      Zagadat Capital Fund Management | info@zagadatcapital.com</p>
    </div>
    """
    send_email(account.email, subject, body)


def email_account_rejected(account, reason=''):
    """Send account rejection notification"""
    if not account.email:
        return
    subject = f"Your Zagadat Capital Account Application — {account.account_number}"
    body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0A0A0A; color: #F5F5F0; padding: 40px; border-radius: 12px;">
      <h1 style="color: #C9A84C;">ZAGADAT CAPITAL</h1>
      <h2 style="color: #E74C3C;">Account Application Update</h2>
      <p>Dear <strong>{account.full_name}</strong>,</p>
      <p>After review, we are unable to approve your account application at this time.</p>
      {f'<p><strong>Reason:</strong> {reason}</p>' if reason else ''}
      <p>Please contact your relationship manager or our support team for further assistance.</p>
      <p style="color: #8A8A9A; font-size: 12px;">Zagadat Capital | info@zagadatcapital.com</p>
    </div>
    """
    send_email(account.email, subject, body)


def email_request_update(account, request_type, status, note=''):
    """Notify client of request status change"""
    if not account.email:
        return
    color = '#27AE60' if status == 'APPROVED' else '#E74C3C'
    subject = f"Your {request_type} Request — {status}"
    body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0A0A0A; color: #F5F5F0; padding: 40px; border-radius: 12px;">
      <h1 style="color: #C9A84C;">ZAGADAT CAPITAL</h1>
      <h2 style="color: {color};">{request_type} Request — {status}</h2>
      <p>Dear <strong>{account.full_name}</strong>,</p>
      <p>Your {request_type.lower()} request has been <strong style="color:{color};">{status.lower()}</strong>.</p>
      {f'<p><strong>Note:</strong> {note}</p>' if note else ''}
      <p>Log in to your portal to view details.</p>
      <p style="color: #8A8A9A; font-size: 12px;">Zagadat Capital | info@zagadatcapital.com</p>
    </div>
    """
    send_email(account.email, subject, body)


def audit(action, target=None, detail=None, actor=None):
    """Write an audit log entry"""
    from models import AuditLog, db
    from flask_login import current_user

    actor_obj = actor or current_user
    try:
        ip = flask_request.remote_addr if flask_request else None
    except Exception:
        ip = None

    try:
        if hasattr(actor_obj, 'staff_id'):
            atype = 'admin'
            aname = actor_obj.full_name
        elif hasattr(actor_obj, 'account_number'):
            atype = 'client'
            aname = actor_obj.account_number
        else:
            atype = 'system'
            aname = 'system'

        log = AuditLog(
            actor_type=atype,
            actor_id=getattr(actor_obj, 'id', 0),
            actor_name=aname,
            action=action,
            target=str(target) if target else None,
            detail=str(detail) if detail else None,
            ip_address=ip
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        print(f"[AUDIT] Failed: {e}")

def email_login_alert(account, ip_address=None, user_agent=None):
    """
    Send a real-time security alert email whenever a client signs in.
    Informs the client of the login event with time, IP and browser info.
    Advises them to contact support immediately if they did not initiate it.
    """
    if not account.email:
        return
    from datetime import timezone
    now_utc = datetime.utcnow()
    time_str = now_utc.strftime('%d %B %Y at %H:%M UTC')
    ip_str   = ip_address or 'Unknown'
    ua_str   = (user_agent or 'Unknown')[:80]

    subject = f'[Zagadat Capital] Sign-In Alert — {account.account_number}'
    body = f"""
    <div style="font-family: 'DM Sans', Arial, sans-serif; max-width: 600px; margin: 0 auto;
                background: #0A0A0A; color: #F5F5F0; padding: 40px; border-radius: 12px;">
      <div style="text-align:center; margin-bottom: 24px;">
        <h1 style="color:#C9A84C; font-size:26px; margin:0; letter-spacing:3px;">ZAGADAT CAPITAL</h1>
        <p style="color:#8A8A9A; font-size:11px; letter-spacing:4px; text-transform:uppercase; margin-top:4px;">
          Fund Management · Security Alert
        </p>
      </div>
      <hr style="border:none; border-top:1px solid rgba(201,168,76,0.3); margin:0 0 28px 0;">

      <h2 style="color:#C9A84C; font-size:18px; margin:0 0 8px 0;">
        🔐 New Sign-In Detected
      </h2>
      <p style="color:#F5F5F0; margin:0 0 20px 0;">
        Dear <strong>{account.full_name}</strong>,<br>
        We detected a new sign-in to your Zagadat Capital account.
      </p>

      <div style="background:rgba(201,168,76,0.08); border:1px solid rgba(201,168,76,0.25);
                  border-radius:8px; padding:20px; margin-bottom:24px;">
        <table style="width:100%; border-collapse:collapse;">
          <tr>
            <td style="color:#8A8A9A; font-size:12px; padding:6px 0; width:40%;">Account Number</td>
            <td style="color:#C9A84C; font-size:14px; font-weight:700;">{account.account_number}</td>
          </tr>
          <tr>
            <td style="color:#8A8A9A; font-size:12px; padding:6px 0;">Sign-In Time</td>
            <td style="color:#F5F5F0; font-size:13px;">{time_str}</td>
          </tr>
          <tr>
            <td style="color:#8A8A9A; font-size:12px; padding:6px 0;">IP Address</td>
            <td style="color:#F5F5F0; font-size:13px;">{ip_str}</td>
          </tr>
          <tr>
            <td style="color:#8A8A9A; font-size:12px; padding:6px 0;">Browser / Device</td>
            <td style="color:#F5F5F0; font-size:13px;">{ua_str}</td>
          </tr>
        </table>
      </div>

      <div style="background:rgba(231,76,60,0.1); border:1px solid rgba(231,76,60,0.35);
                  border-radius:8px; padding:16px 20px; margin-bottom:28px;">
        <p style="color:#E74C3C; font-weight:700; margin:0 0 6px 0; font-size:13px;">
          ⚠ Was this not you?
        </p>
        <p style="color:#F5F5F0; font-size:12px; line-height:1.7; margin:0;">
          If you did not sign in, your account may be compromised.
          Please contact us immediately at
          <a href="mailto:security@zagadatcapital.com" style="color:#C9A84C;">
            security@zagadatcapital.com
          </a>
          and change your access credentials.
        </p>
      </div>

      <div style="background:rgba(39,174,96,0.08); border:1px solid rgba(39,174,96,0.25);
                  border-radius:8px; padding:16px 20px; margin-bottom:28px;">
        <p style="color:#27AE60; font-weight:700; font-size:12px; margin:0 0 6px 0;">
          🛡 Security Reminder
        </p>
        <p style="color:#F5F5F0; font-size:12px; line-height:1.7; margin:0;">
          Keep your <strong>Account Number ({account.account_number})</strong> strictly confidential.
          Never share it with any third party, including individuals claiming to be Zagadat Capital staff.
          Our team will <strong>never</strong> ask for your account credentials via phone, email or messaging.
        </p>
      </div>

      <p style="color:#8A8A9A; font-size:11px; line-height:1.8; border-top:1px solid rgba(201,168,76,0.15);
                padding-top:20px; margin:0;">
        This is an automated security notification. Do not reply to this email.<br>
        Zagadat Capital Fund Management · info@zagadatcapital.com<br>
        Licensed by the Securities &amp; Exchange Commission, Ghana.
      </p>
    </div>
    """
    send_email(account.email, subject, body)

def email_transaction_approved(account, txn):
    """
    Send real-time email alert to client when a transaction is approved.
    Covers DEPOSIT, WITHDRAWAL, BUY, SELL, DIVIDEND, COUPON, FEE, TRANSFER.
    """
    if not account.email:
        return
    from datetime import timezone
    now_str = datetime.utcnow().strftime('%d %B %Y at %H:%M UTC')
    is_credit = txn.txn_type in ('DEPOSIT','TRANSFER_IN','DIVIDEND','COUPON','SELL')
    colour    = '#27AE60' if is_credit else '#E74C3C'
    direction = 'CREDITED' if is_credit else 'DEBITED'
    ghs_amt   = txn.amount_ghs if txn.amount_ghs is not None else txn.amount
    orig_line = (f'<tr><td style="color:#8A8A9A;font-size:12px;padding:5px 0;width:44%;">Original Amount</td>'
                 f'<td style="color:#F5F5F0;font-size:13px;">'
                 f'{txn.currency} {txn.amount:,.2f}</td></tr>'
                 if txn.currency != 'GHS' else '')
    fx_line   = (f'<tr><td style="color:#8A8A9A;font-size:12px;padding:5px 0;">FX Rate Applied</td>'
                 f'<td style="color:#F5F5F0;font-size:13px;">'
                 f'1 {txn.currency} = GHS {txn.fx_rate_used:.4f}</td></tr>'
                 if txn.currency != 'GHS' and txn.fx_rate_used else '')

    subject = f'[Zagadat Capital] Transaction {direction} — {txn.txn_type} {txn.currency} {txn.amount:,.2f}'
    body = f"""
    <div style="font-family:'DM Sans',Arial,sans-serif;max-width:600px;margin:0 auto;
                background:#0A0A0A;color:#F5F5F0;padding:40px;border-radius:12px;">
      <div style="text-align:center;margin-bottom:24px;">
        <h1 style="color:#C9A84C;font-size:24px;margin:0;letter-spacing:3px;">ZAGADAT CAPITAL</h1>
        <p style="color:#8A8A9A;font-size:11px;letter-spacing:4px;text-transform:uppercase;margin-top:4px;">
          Fund Management · Transaction Alert
        </p>
      </div>
      <hr style="border:none;border-top:1px solid rgba(201,168,76,0.3);margin:0 0 24px;">

      <h2 style="font-size:17px;margin:0 0 8px;color:{colour};">
        {'✅' if is_credit else '💸'} Transaction {direction}
      </h2>
      <p style="color:#F5F5F0;margin:0 0 20px;">
        Dear <strong>{account.full_name}</strong>,<br>
        The following transaction has been approved on your account.
      </p>

      <div style="background:rgba(201,168,76,0.08);border:1px solid rgba(201,168,76,0.25);
                  border-radius:8px;padding:18px;margin-bottom:20px;">
        <table style="width:100%;border-collapse:collapse;">
          <tr><td style="color:#8A8A9A;font-size:12px;padding:5px 0;width:44%;">Account Number</td>
              <td style="color:#C9A84C;font-size:14px;font-weight:700;">{account.account_number}</td></tr>
          <tr><td style="color:#8A8A9A;font-size:12px;padding:5px 0;">Transaction Type</td>
              <td style="color:#F5F5F0;font-size:13px;">{txn.txn_type.replace('_',' ')}</td></tr>
          {orig_line}
          <tr><td style="color:#8A8A9A;font-size:12px;padding:5px 0;">GHS Amount</td>
              <td style="color:{colour};font-size:16px;font-weight:700;">GHS {ghs_amt:,.2f}</td></tr>
          {fx_line}
          <tr><td style="color:#8A8A9A;font-size:12px;padding:5px 0;">Transaction Date</td>
              <td style="color:#F5F5F0;font-size:13px;">{txn.txn_date.strftime('%d %B %Y') if txn.txn_date else now_str}</td></tr>
          <tr><td style="color:#8A8A9A;font-size:12px;padding:5px 0;">Description</td>
              <td style="color:#F5F5F0;font-size:13px;">{txn.description or '—'}</td></tr>
          <tr><td style="color:#8A8A9A;font-size:12px;padding:5px 0;">Reference</td>
              <td style="color:#F5F5F0;font-size:13px;">{txn.reference or '—'}</td></tr>
          <tr><td style="color:#8A8A9A;font-size:12px;padding:5px 0;">Approved At</td>
              <td style="color:#F5F5F0;font-size:13px;">{now_str}</td></tr>
        </table>
      </div>

      <div style="background:rgba(39,174,96,0.08);border:1px solid rgba(39,174,96,0.25);
                  border-radius:8px;padding:14px 18px;margin-bottom:24px;">
        <p style="color:#27AE60;font-weight:700;font-size:12px;margin:0 0 5px;">
          🛡 Security Reminder
        </p>
        <p style="color:#F5F5F0;font-size:12px;line-height:1.7;margin:0;">
          If you did not authorise this transaction, contact us immediately at
          <a href="mailto:security@zagadatcapital.com" style="color:#C9A84C;">
          security@zagadatcapital.com</a>.
          Keep your account number <strong>{account.account_number}</strong> strictly confidential.
        </p>
      </div>

      <p style="color:#8A8A9A;font-size:11px;line-height:1.8;
                border-top:1px solid rgba(201,168,76,0.15);padding-top:18px;margin:0;">
        This is an automated notification. Do not reply to this email.<br>
        Zagadat Capital Fund Management · info@zagadatcapital.com<br>
        Licensed by the Securities &amp; Exchange Commission, Ghana.
      </p>
    </div>
    """
    send_email(account.email, subject, body)

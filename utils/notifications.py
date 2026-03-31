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

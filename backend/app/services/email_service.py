"""
Email notification service — sends anomaly alerts via SendGrid.

Why asyncio.to_thread?
  The SendGrid SDK is synchronous (a blocking HTTP call).  Wrapping it in
  asyncio.to_thread() runs it on the default executor so it never blocks
  the event loop.  Same pattern we use for boto3 in aws_cost_service.

Failure model:
  This module lets exceptions propagate.  The caller (sync job) wraps each
  call in try/except so a SendGrid outage never crashes the sync.

Sender verification:
  SendGrid will silently drop any email whose `from` address is not a
  verified single sender.  Set yours up at:
      https://app.sendgrid.com/settings/sender_auth
"""

import asyncio
import html
import logging

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from app.config import settings
from app.models.alert import Alert

logger = logging.getLogger(__name__)


def _percent_above_baseline(amount: float, baseline: float) -> str:
    """Format the percent-above-baseline string. Returns '—' if baseline is 0."""
    if baseline <= 0:
        return "—"
    pct = ((amount - baseline) / baseline) * 100
    return f"{pct:,.0f}%"


def _build_subject(alert: Alert) -> str:
    """Subject line — short, scannable in a notification preview."""
    return (
        f"CloudGuard: unusual AWS spend detected - "
        f"${float(alert.amount_usd):.2f} on {alert.alert_date}"
    )


def _build_html_body(alert: Alert) -> str:
    """
    Build a skimmable HTML body.  Inline styles only — most email clients
    strip <style> blocks and external CSS, so anything not inline gets ignored.
    """
    amount = float(alert.amount_usd)
    baseline = float(alert.baseline_mean)
    z = float(alert.z_score)
    pct = _percent_above_baseline(amount, baseline)

    # Escape anything sourced from outside our code before it lands in HTML.
    # service_name comes from AWS (and may later carry user-defined cost-category
    # / tag values), so treat it as untrusted to keep the email markup safe.
    service_row = ""
    if alert.scope == "service" and alert.service_name:
        service_row = (
            f'<tr>'
            f'<td style="padding:6px 14px;color:#6b7280;">Service</td>'
            f'<td style="padding:6px 14px;font-weight:600;">{html.escape(alert.service_name)}</td>'
            f'</tr>'
        )

    severity_color = {
        "low":    "#2563eb",  # blue
        "medium": "#d97706",  # amber
        "high":   "#dc2626",  # red
    }.get(alert.severity, "#6b7280")
    severity_label = html.escape(alert.severity)

    return f"""\
<html>
  <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#1f2937;max-width:560px;margin:0;padding:24px;">
    <h2 style="color:{severity_color};margin:0 0 12px 0;">CloudGuard: unusual AWS spend detected</h2>
    <p style="margin:0 0 16px 0;">An anomaly was detected on <strong>{alert.alert_date}</strong>.</p>

    <table style="border-collapse:collapse;width:100%;background:#f9fafb;border-radius:8px;overflow:hidden;">
      <tr>
        <td style="padding:6px 14px;color:#6b7280;width:40%;">Amount spent</td>
        <td style="padding:6px 14px;font-weight:600;">${amount:,.2f}</td>
      </tr>
      <tr>
        <td style="padding:6px 14px;color:#6b7280;">Normal baseline</td>
        <td style="padding:6px 14px;font-weight:600;">${baseline:,.2f}</td>
      </tr>
      <tr>
        <td style="padding:6px 14px;color:#6b7280;">Above baseline</td>
        <td style="padding:6px 14px;font-weight:600;">{pct} (z-score: {z:.2f})</td>
      </tr>
      {service_row}
      <tr>
        <td style="padding:6px 14px;color:#6b7280;">Severity</td>
        <td style="padding:6px 14px;font-weight:600;text-transform:capitalize;color:{severity_color};">{severity_label}</td>
      </tr>
    </table>

    <p style="color:#6b7280;font-size:12px;margin-top:24px;">
      CloudGuard automated alert — open the dashboard to acknowledge.
    </p>
  </body>
</html>
"""


def _send_via_sendgrid(api_key: str, mail: Mail):
    """
    Blocking SendGrid call.  Invoked via asyncio.to_thread() so it never
    blocks the event loop.
    """
    client = SendGridAPIClient(api_key)
    return client.send(mail)


async def send_anomaly_alert(to_email: str, alert: Alert) -> None:
    """
    Send an anomaly notification email via SendGrid.

    Lets exceptions propagate — caller is responsible for try/except so
    a SendGrid outage doesn't break the sync job.

    Raises:
        RuntimeError: if SENDGRID_API_KEY is not configured.
        Any SendGrid exception (auth failure, network error, etc.).
    """
    if not settings.sendgrid_api_key:
        raise RuntimeError("SENDGRID_API_KEY is not configured")
    if not settings.alert_sender_email:
        raise RuntimeError("ALERT_SENDER_EMAIL is not configured")

    mail = Mail(
        from_email=settings.alert_sender_email,
        to_emails=to_email,
        subject=_build_subject(alert),
        html_content=_build_html_body(alert),
    )

    response = await asyncio.to_thread(
        _send_via_sendgrid, settings.sendgrid_api_key, mail
    )

    logger.info(
        "email_service: sent alert id=%s to=%s status=%s",
        alert.id, to_email, getattr(response, "status_code", "?"),
    )

"""HTML e texto dos e-mails transacionais no visual CyberHost."""

from __future__ import annotations

from html import escape

ACCENT = "#06c96c"
ACCENT_DARK = "#059c5a"
TEXT = "#1a202c"
MUTED = "#718096"
BG = "#f8fafc"
CARD = "#ffffff"
DANGER = "#e53e3e"
WARNING = "#dd6b20"


def format_brl(cents: int | None) -> str:
    if cents is None or cents < 0:
        return ""
    value = f"{cents / 100:.2f}".replace(".", ",")
    return f"R$ {value}"


def wrap_layout(*, preheader: str, logo_src: str, inner_html: str, footer_note: str) -> str:
    logo = escape(logo_src, quote=True)
    pre = escape(preheader)
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CyberHost</title>
</head>
<body style="margin:0;padding:0;background:{BG};color:{TEXT};font-family:Inter,Segoe UI,Helvetica,Arial,sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;">{pre}</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{BG};padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="560" cellspacing="0" cellpadding="0" style="max-width:560px;width:100%;background:{CARD};border:1px solid #e2e8f0;border-radius:16px;overflow:hidden;">
          <tr>
            <td style="height:6px;background:{ACCENT};font-size:0;line-height:0;">&nbsp;</td>
          </tr>
          <tr>
            <td style="padding:28px 32px 8px 32px;" align="left">
              <img src="{logo}" alt="CyberHost" width="180" style="display:block;width:180px;max-width:70%;height:auto;border:0;" />
            </td>
          </tr>
          <tr>
            <td style="padding:8px 32px 32px 32px;font-size:15px;line-height:1.55;color:{TEXT};">
              {inner_html}
            </td>
          </tr>
          <tr>
            <td style="padding:0 32px 28px 32px;font-size:12px;line-height:1.5;color:{MUTED};">
              {escape(footer_note)}<br />
              <a href="https://ruts.dev/cyberhost/" style="color:{ACCENT_DARK};text-decoration:none;">ruts.dev/cyberhost</a>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _cta(href: str, label: str) -> str:
    return (
        f'<a href="{escape(href, quote=True)}" '
        f'style="display:inline-block;background:{ACCENT};color:#ffffff;font-weight:600;'
        f'padding:12px 22px;border-radius:10px;text-decoration:none;">{escape(label)}</a>'
    )


def otp_content(*, code: str, minutes: int, logo_src: str) -> tuple[str, str, str]:
    subject = "Seu código de verificação CyberHost"
    text = (
        f"Seu código de verificação da CyberHost é {code}.\n\n"
        f"Ele expira em {minutes} minutos. Se você não pediu este código, ignore o e-mail.\n"
    )
    inner = f"""
      <p style="margin:0 0 16px 0;">Use este código para confirmar seu e-mail na CyberHost.</p>
      <p style="margin:0 0 8px 0;font-size:13px;color:{MUTED};text-transform:uppercase;letter-spacing:0.06em;">Código</p>
      <p style="margin:0 0 20px 0;font-size:32px;letter-spacing:0.18em;font-weight:700;color:{ACCENT_DARK};">{escape(code)}</p>
      <p style="margin:0;color:{MUTED};font-size:13px;">Expira em {minutes} minutos. Se você não pediu este código, pode ignorar este e-mail.</p>
    """
    html = wrap_layout(
        preheader=f"Seu código CyberHost expira em {minutes} minutos.",
        logo_src=logo_src,
        inner_html=inner,
        footer_note="CyberHost · hospedagem VPS e CyberCloud",
    )
    return subject, text, html


def _service_row(item: dict) -> str:
    title = escape(str(item.get("title") or "Serviço"))
    detail = escape(str(item.get("detail") or ""))
    due = escape(str(item.get("due_label") or ""))
    price = escape(str(item.get("price_label") or ""))
    overdue = bool(item.get("overdue"))
    badge_bg = "#fef2f2" if overdue else "#ecfdf5"
    badge_fg = DANGER if overdue else ACCENT_DARK
    badge = escape(str(item.get("badge") or ""))
    return f"""
      <tr>
        <td style="padding:14px 16px;border:1px solid #e2e8f0;border-radius:12px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
            <tr>
              <td style="font-weight:600;color:{TEXT};">{title}</td>
              <td align="right">
                <span style="display:inline-block;background:{badge_bg};color:{badge_fg};font-size:11px;font-weight:600;padding:4px 8px;border-radius:999px;">{badge}</span>
              </td>
            </tr>
            <tr>
              <td colspan="2" style="padding-top:6px;font-size:13px;color:{MUTED};">{detail}</td>
            </tr>
            <tr>
              <td style="padding-top:8px;font-size:13px;color:{TEXT};">{due}</td>
              <td align="right" style="padding-top:8px;font-size:13px;font-weight:600;color:{TEXT};">{price}</td>
            </tr>
          </table>
        </td>
      </tr>
      <tr><td style="height:10px;font-size:0;">&nbsp;</td></tr>
    """


def billing_content(
    *,
    name: str,
    items: list[dict],
    cta_url: str,
    logo_src: str,
    most_urgent_days: int,
) -> tuple[str, str, str]:
    first = (name or "olá").strip().split()[0] or "olá"
    overdue = most_urgent_days < 0
    if overdue:
        n = abs(most_urgent_days)
        subject = "Ação necessária: serviço CyberHost vencido"
        headline = f"Oi, {first}. Há serviço vencido na sua conta."
        lead = (
            f"Já faz {n} dia(s) do vencimento. Renove para evitar suspensão "
            "ou manter o serviço ativo."
        )
        badge_default = f"Vencido há {n} dia(s)"
        cta = "Renovar agora"
        preheader = "Seu serviço CyberHost está vencido."
    elif most_urgent_days == 1:
        subject = "Seu serviço CyberHost vence amanhã"
        headline = f"Oi, {first}. Amanhã vence um serviço."
        lead = "Renove com antecedência para não perder acesso à VPS ou ao CyberCloud."
        badge_default = "Vence amanhã"
        cta = "Renovar"
        preheader = "Amanhã vence um serviço na CyberHost."
    else:
        subject = f"Seu serviço CyberHost vence em {most_urgent_days} dias"
        headline = f"Oi, {first}. Um serviço vence em {most_urgent_days} dias."
        lead = "Vale renovar agora para manter tudo no ar sem interrupção."
        badge_default = f"Vence em {most_urgent_days} dias"
        cta = "Ver no painel"
        preheader = f"Lembrete: vencimento em {most_urgent_days} dias."

    rows = []
    text_lines = [headline, "", lead, ""]
    for item in items:
        row = dict(item)
        row.setdefault("badge", badge_default if not item.get("overdue") else item.get("badge"))
        rows.append(_service_row(row))
        text_lines.append(f"- {item.get('title')}: {item.get('due_label')} {item.get('price_label') or ''}".strip())
        if item.get("detail"):
            text_lines.append(f"  {item['detail']}")
    text_lines.extend(["", f"Renovar: {cta_url}", "", "CyberHost · ruts.dev/cyberhost"])
    inner = f"""
      <p style="margin:0 0 8px 0;font-size:20px;font-weight:700;color:{TEXT};">{escape(headline)}</p>
      <p style="margin:0 0 20px 0;color:{MUTED};">{escape(lead)}</p>
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
        {"".join(rows)}
      </table>
      <p style="margin:18px 0 0 0;">{_cta(cta_url, cta)}</p>
    """
    html = wrap_layout(
        preheader=preheader,
        logo_src=logo_src,
        inner_html=inner,
        footer_note="Você recebeu este e-mail porque há um serviço CyberHost nesta conta.",
    )
    return subject, "\n".join(text_lines), html


def support_new_ticket_content(
    *,
    admin_name: str,
    customer_name: str,
    ticket_id: int,
    ticket_subject: str,
    preview: str,
    cta_url: str,
    logo_src: str,
) -> tuple[str, str, str]:
    first = (admin_name or "").strip().split()[0] or "olá"
    subject = f"Novo ticket de suporte #{ticket_id}"
    headline = f"Oi, {first}. Chegou um ticket novo."
    lead = f"{customer_name} abriu o ticket #{ticket_id}."
    text = (
        f"{headline}\n\n{lead}\nAssunto: {ticket_subject}\n\n{preview}\n\n"
        f"Abrir no painel: {cta_url}\n"
    )
    inner = f"""
      <p style="margin:0 0 8px 0;font-size:20px;font-weight:700;color:{TEXT};">{escape(headline)}</p>
      <p style="margin:0 0 16px 0;color:{MUTED};">{escape(lead)}</p>
      <p style="margin:0 0 6px 0;font-size:13px;color:{MUTED};text-transform:uppercase;letter-spacing:0.06em;">Assunto</p>
      <p style="margin:0 0 16px 0;font-weight:600;">{escape(ticket_subject)}</p>
      <p style="margin:0 0 20px 0;color:{TEXT};">{escape(preview)}</p>
      <p style="margin:0;">{_cta(cta_url, "Atender no painel")}</p>
    """
    html = wrap_layout(
        preheader=f"Ticket #{ticket_id}: {ticket_subject}",
        logo_src=logo_src,
        inner_html=inner,
        footer_note="Você recebeu este e-mail porque é administrador da CyberHost.",
    )
    return subject, text, html


def support_mention_content(
    *,
    admin_name: str,
    from_name: str,
    ticket_id: int,
    ticket_subject: str,
    preview: str,
    cta_url: str,
    logo_src: str,
) -> tuple[str, str, str]:
    first = (admin_name or "").strip().split()[0] or "olá"
    subject = f"Você foi mencionado no ticket #{ticket_id}"
    headline = f"Oi, {first}. {from_name} mencionou você."
    lead = f"Ticket #{ticket_id} · {ticket_subject}"
    text = (
        f"{headline}\n\n{lead}\n\n{preview}\n\nAbrir no painel: {cta_url}\n"
    )
    inner = f"""
      <p style="margin:0 0 8px 0;font-size:20px;font-weight:700;color:{TEXT};">{escape(headline)}</p>
      <p style="margin:0 0 16px 0;color:{MUTED};">{escape(lead)}</p>
      <p style="margin:0 0 20px 0;color:{TEXT};">{escape(preview)}</p>
      <p style="margin:0;">{_cta(cta_url, "Abrir conversa")}</p>
    """
    html = wrap_layout(
        preheader=f"{from_name} mencionou você no ticket #{ticket_id}.",
        logo_src=logo_src,
        inner_html=inner,
        footer_note="Você recebeu este e-mail porque um administrador mencionou você no suporte.",
    )
    return subject, text, html


def support_ticket_accepted_content(
    *,
    customer_name: str,
    admin_name: str,
    ticket_id: int,
    ticket_subject: str,
    cta_url: str,
    logo_src: str,
) -> tuple[str, str, str]:
    first = (customer_name or "").strip().split()[0] or "olá"
    subject = f"Seu ticket #{ticket_id} foi aceito"
    headline = f"Oi, {first}. Seu atendimento já começou."
    lead = f"{admin_name} aceitou o ticket #{ticket_id} e vai responder por aqui."
    text = (
        f"{headline}\n\n{lead}\nAssunto: {ticket_subject}\n\n"
        f"Acompanhe a conversa no painel: {cta_url}\n"
    )
    inner = f"""
      <p style="margin:0 0 8px 0;font-size:20px;font-weight:700;color:{TEXT};">{escape(headline)}</p>
      <p style="margin:0 0 16px 0;color:{MUTED};">{escape(lead)}</p>
      <p style="margin:0 0 6px 0;font-size:13px;color:{MUTED};text-transform:uppercase;letter-spacing:0.06em;">Assunto</p>
      <p style="margin:0 0 20px 0;font-weight:600;">{escape(ticket_subject)}</p>
      <p style="margin:0;">{_cta(cta_url, "Abrir ticket")}</p>
    """
    html = wrap_layout(
        preheader=f"{admin_name} aceitou o ticket #{ticket_id}.",
        logo_src=logo_src,
        inner_html=inner,
        footer_note="Você recebeu este e-mail porque abriu um ticket de suporte na CyberHost.",
    )
    return subject, text, html

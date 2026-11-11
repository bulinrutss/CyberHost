import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token, hash_password
from app.database import Base, get_db
from app.models.cloud_storage_order import CloudStorageOrder  # noqa: F401
from app.models.game_server import GameOrder, GameServer  # noqa: F401
from app.models.support import SupportMention, SupportMessage, SupportTicket
from app.models.user import User
from app.models.vps import VpsInstance, VpsOrder  # noqa: F401
from app.services import email_templates


def _load_routers():
    if "app.api.support" not in sys.modules:
        dummy = types.ModuleType("app.api")
        dummy.__path__ = [str(Path(__file__).resolve().parents[1] / "app" / "api")]
        dummy.__package__ = "app.api"
        sys.modules.setdefault("app.api", dummy)
    from app.api.admin_support import router as admin_router
    from app.api.support import router as customer_router

    return customer_router, admin_router


customer_router, admin_support_router = _load_routers()


class SupportEmailTemplateTests(unittest.TestCase):
    def test_new_ticket_escapes_html(self) -> None:
        subject, text, html = email_templates.support_new_ticket_content(
            admin_name="Ana",
            customer_name="João <script>",
            ticket_id=12,
            ticket_subject="Ajuda <b>urgente</b>",
            preview="Senha do guest não entra",
            cta_url="https://ruts.dev/cyberhost/admin?tab=support",
            logo_src="cid:cyberhost-logo",
        )
        self.assertEqual(subject, "Novo ticket de suporte #12")
        self.assertIn("João <script>", text)
        self.assertIn("João &lt;script&gt;", html)
        self.assertIn("Ajuda &lt;b&gt;urgente&lt;/b&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("smtp_password", html)
        self.assertIn("#06c96c", html)

    def test_accepted_escapes_html(self) -> None:
        subject, text, html = email_templates.support_ticket_accepted_content(
            customer_name="João <script>",
            admin_name="Ana <b>Admin</b>",
            ticket_id=12,
            ticket_subject="Ajuda <img>",
            cta_url="https://ruts.dev/cyberhost/dashboard/support",
            logo_src="cid:cyberhost-logo",
        )
        self.assertEqual(subject, "Seu ticket #12 foi aceito")
        self.assertIn("Oi, João.", text)
        self.assertIn("Ana <b>Admin</b>", text)
        self.assertIn("Ajuda <img>", text)
        self.assertIn("Ana &lt;b&gt;Admin&lt;/b&gt;", html)
        self.assertIn("Ajuda &lt;img&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<b>Admin</b>", html)
        self.assertIn("/dashboard/support", html)

    def test_mention_escapes_html(self) -> None:
        _, text, html = email_templates.support_mention_content(
            admin_name="Bia",
            from_name="Ana <x>",
            ticket_id=3,
            ticket_subject="Rede",
            preview="Olha <img>",
            cta_url="https://ruts.dev/cyberhost/admin?tab=support",
            logo_src="cid:cyberhost-logo",
        )
        self.assertIn("Ana <x>", text)
        self.assertIn("Ana &lt;x&gt;", html)
        self.assertIn("Olha &lt;img&gt;", html)


class SupportTicketApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            self.engine,
            tables=[
                User.__table__,
                SupportTicket.__table__,
                SupportMessage.__table__,
                SupportMention.__table__,
            ],
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.customer = User(
            phone="11970000001",
            email="cliente@example.com",
            name="Cliente Silva",
            hashed_password=hash_password("correct-horse"),
            is_active=True,
            is_admin=False,
        )
        self.other = User(
            phone="11970000002",
            email="outro@example.com",
            name="Outro Cliente",
            hashed_password=hash_password("correct-horse"),
            is_active=True,
            is_admin=False,
        )
        self.admin_a = User(
            phone="11970000010",
            email="ana@example.com",
            name="Ana Admin",
            hashed_password=hash_password("correct-horse"),
            is_active=True,
            is_admin=True,
        )
        self.admin_b = User(
            phone="11970000011",
            email="bia@example.com",
            name="Bia Admin",
            hashed_password=hash_password("correct-horse"),
            is_active=True,
            is_admin=True,
        )
        self.admin_no_mail = User(
            phone="11970000012",
            email=None,
            name="Sem Email",
            hashed_password=hash_password("correct-horse"),
            is_active=True,
            is_admin=True,
        )
        self.db.add_all(
            [self.customer, self.other, self.admin_a, self.admin_b, self.admin_no_mail]
        )
        self.db.commit()
        for row in (self.customer, self.other, self.admin_a, self.admin_b, self.admin_no_mail):
            self.db.refresh(row)

        app = FastAPI()
        app.include_router(customer_router, prefix="/api/support")
        app.include_router(admin_support_router, prefix="/api/admin/support")

        def _override_db():
            yield self.db

        app.dependency_overrides[get_db] = _override_db
        self.client = TestClient(app)
        self.mail = patch("app.services.support.mailer.send_email")
        self.smtp = patch("app.services.support.mailer.smtp_configured", return_value=True)
        self.logo = patch("app.services.support.mailer.logo_src", return_value="cid:cyberhost-logo")
        self.load_logo = patch("app.services.support.mailer.load_logo_bytes", return_value=None)
        self.panel = patch(
            "app.services.support.mailer.panel_url",
            return_value="https://ruts.dev/cyberhost/admin?tab=support",
        )
        self.send_email = self.mail.start()
        self.smtp.start()
        self.logo.start()
        self.load_logo.start()
        self.panel.start()

    def tearDown(self) -> None:
        self.mail.stop()
        self.smtp.stop()
        self.logo.stop()
        self.load_logo.stop()
        self.panel.stop()
        self.db.close()
        self.engine.dispose()

    def _auth(self, user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(user.id)}"}

    def test_create_notifies_admins_with_email(self) -> None:
        res = self.client.post(
            "/api/support/tickets",
            headers=self._auth(self.customer),
            json={"subject": "VPS sem rede", "body": "A máquina não pega IP."},
        )
        self.assertEqual(res.status_code, 201, res.text)
        data = res.json()
        self.assertEqual(data["subject"], "VPS sem rede")
        self.assertEqual(data["status"], "open")
        self.assertTrue(any("mais breve possível" in msg["body"] for msg in data["messages"]))
        sent_to = sorted(call.kwargs["to_email"] for call in self.send_email.call_args_list)
        self.assertEqual(sent_to, ["ana@example.com", "bia@example.com"])
        first = self.send_email.call_args_list[0].kwargs
        self.assertIn("Novo ticket", first["subject"])
        self.assertNotIn("correct-horse", first["text"])
        self.assertNotIn("correct-horse", first["html"])

    def test_other_customer_cannot_read(self) -> None:
        created = self.client.post(
            "/api/support/tickets",
            headers=self._auth(self.customer),
            json={"subject": "Disco cheio", "body": "Sem espaço no C:"},
        )
        ticket_id = created.json()["id"]
        listed = self.client.get("/api/support/tickets", headers=self._auth(self.other))
        self.assertEqual(listed.json(), [])
        hidden = self.client.get(
            f"/api/support/tickets/{ticket_id}",
            headers=self._auth(self.other),
        )
        self.assertEqual(hidden.status_code, 404)

    def test_admin_accept_stays_visible_and_other_can_take_over(self) -> None:
        created = self.client.post(
            "/api/support/tickets",
            headers=self._auth(self.customer),
            json={"subject": "Console travou", "body": "Tela preta no WMKS."},
        )
        ticket_id = created.json()["id"]
        accepted = self.client.post(
            f"/api/admin/support/tickets/{ticket_id}/accept",
            headers=self._auth(self.admin_a),
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["accepted_by_id"], self.admin_a.id)
        listed = self.client.get("/api/admin/support/tickets", headers=self._auth(self.admin_b))
        self.assertEqual(len(listed.json()), 1)
        self.assertEqual(listed.json()[0]["accepted_by_id"], self.admin_a.id)
        takeover = self.client.post(
            f"/api/admin/support/tickets/{ticket_id}/accept",
            headers=self._auth(self.admin_b),
        )
        self.assertEqual(takeover.status_code, 200, takeover.text)
        self.assertEqual(takeover.json()["accepted_by_id"], self.admin_b.id)
        self.assertTrue(
            any("assumiu o atendimento" in msg["body"] for msg in takeover.json()["messages"])
        )

    def test_accept_emails_the_customer(self) -> None:
        created = self.client.post(
            "/api/support/tickets",
            headers=self._auth(self.customer),
            json={"subject": "RDP falhou", "body": "Não entra no Windows."},
        )
        ticket_id = created.json()["id"]
        self.send_email.reset_mock()
        accepted = self.client.post(
            f"/api/admin/support/tickets/{ticket_id}/accept",
            headers=self._auth(self.admin_a),
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(self.send_email.call_count, 1)
        sent = self.send_email.call_args.kwargs
        self.assertEqual(sent["to_email"], "cliente@example.com")
        self.assertIn("aceito", sent["subject"].lower())
        self.assertIn("Ana Admin", sent["text"])
        self.assertIn("RDP falhou", sent["html"])
        self.assertNotIn("correct-horse", sent["text"])
        self.assertNotIn("correct-horse", sent["html"])
        self.send_email.reset_mock()
        again = self.client.post(
            f"/api/admin/support/tickets/{ticket_id}/accept",
            headers=self._auth(self.admin_a),
        )
        self.assertEqual(again.status_code, 200, again.text)
        self.send_email.assert_not_called()
        takeover = self.client.post(
            f"/api/admin/support/tickets/{ticket_id}/accept",
            headers=self._auth(self.admin_b),
        )
        self.assertEqual(takeover.status_code, 200, takeover.text)
        self.assertEqual(self.send_email.call_count, 1)
        self.assertEqual(self.send_email.call_args.kwargs["to_email"], "cliente@example.com")
        self.assertIn("Bia Admin", self.send_email.call_args.kwargs["text"])

    def test_accept_skips_customer_without_email(self) -> None:
        no_mail = User(
            phone="11970000003",
            email=None,
            name="Sem Mail",
            hashed_password=hash_password("correct-horse"),
            is_active=True,
            is_admin=False,
        )
        self.db.add(no_mail)
        self.db.commit()
        self.db.refresh(no_mail)
        created = self.client.post(
            "/api/support/tickets",
            headers=self._auth(no_mail),
            json={"subject": "Sem e-mail", "body": "Só telefone."},
        )
        ticket_id = created.json()["id"]
        self.send_email.reset_mock()
        accepted = self.client.post(
            f"/api/admin/support/tickets/{ticket_id}/accept",
            headers=self._auth(self.admin_a),
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.send_email.assert_not_called()

    def test_mention_emails_only_the_mentioned_admin(self) -> None:
        created = self.client.post(
            "/api/support/tickets",
            headers=self._auth(self.customer),
            json={"subject": "Pix atrasado", "body": "Pagamento não caiu."},
        )
        ticket_id = created.json()["id"]
        self.send_email.reset_mock()
        sent = self.client.post(
            f"/api/admin/support/tickets/{ticket_id}/messages",
            headers=self._auth(self.admin_a),
            json={
                "body": "Bia, consegue olhar o Pix?",
                "mention_ids": [self.admin_b.id, self.customer.id, self.admin_a.id],
            },
        )
        self.assertEqual(sent.status_code, 200, sent.text)
        self.assertEqual(sent.json()["messages"][-1]["mentioned_user_ids"], [self.admin_b.id])
        self.assertEqual(self.send_email.call_count, 1)
        self.assertEqual(self.send_email.call_args.kwargs["to_email"], "bia@example.com")
        self.assertIn("mencionado", self.send_email.call_args.kwargs["subject"].lower())

    def test_closed_ticket_rejects_new_messages(self) -> None:
        created = self.client.post(
            "/api/support/tickets",
            headers=self._auth(self.customer),
            json={"subject": "Dúvida", "body": "Como renovo?"},
        )
        ticket_id = created.json()["id"]
        closed = self.client.post(
            f"/api/support/tickets/{ticket_id}/close",
            headers=self._auth(self.customer),
        )
        self.assertEqual(closed.status_code, 200)
        blocked = self.client.post(
            f"/api/support/tickets/{ticket_id}/messages",
            headers=self._auth(self.customer),
            json={"body": "ainda tenho dúvida"},
        )
        self.assertEqual(blocked.status_code, 400)
        accept = self.client.post(
            f"/api/admin/support/tickets/{ticket_id}/accept",
            headers=self._auth(self.admin_a),
        )
        self.assertEqual(accept.status_code, 400)

    def test_customer_cannot_use_admin_routes(self) -> None:
        res = self.client.get("/api/admin/support/tickets", headers=self._auth(self.customer))
        self.assertEqual(res.status_code, 403)

    def test_admin_deletes_ticket_and_messages(self) -> None:
        created = self.client.post(
            "/api/support/tickets",
            headers=self._auth(self.customer),
            json={"subject": "Apagar fila", "body": "Pode remover este ticket."},
        )
        self.assertEqual(created.status_code, 201, created.text)
        ticket_id = created.json()["id"]
        self.client.post(
            f"/api/admin/support/tickets/{ticket_id}/messages",
            headers=self._auth(self.admin_a),
            json={"body": "Bia olha isso", "mention_ids": [self.admin_b.id]},
        )
        deleted = self.client.delete(
            f"/api/admin/support/tickets/{ticket_id}",
            headers=self._auth(self.admin_a),
        )
        self.assertEqual(deleted.status_code, 204, deleted.text)
        missing = self.client.get(
            f"/api/admin/support/tickets/{ticket_id}",
            headers=self._auth(self.admin_a),
        )
        self.assertEqual(missing.status_code, 404)
        listed = self.client.get("/api/admin/support/tickets?include_closed=true", headers=self._auth(self.admin_a))
        self.assertEqual(listed.json(), [])
        self.assertEqual(self.db.query(SupportTicket).count(), 0)
        self.assertEqual(self.db.query(SupportMessage).count(), 0)
        self.assertEqual(self.db.query(SupportMention).count(), 0)
        forbidden = self.client.delete(
            f"/api/admin/support/tickets/{ticket_id}",
            headers=self._auth(self.customer),
        )
        self.assertEqual(forbidden.status_code, 403)

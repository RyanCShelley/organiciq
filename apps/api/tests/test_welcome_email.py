from __future__ import annotations

from app.services import health_digest, welcome_email
from tests.conftest import auth_header


def test_the_welcome_email_says_where_and_how_to_sign_in():
    subject, body = welcome_email.render(name="New Person", email="new@smamarketing.com", added_by="Ryan Shelley", restored=False)
    assert subject == "You have access to Organic IQ"
    assert body.startswith("Hi New,") and "by Ryan Shelley" in body
    assert "/login" in body and "new@smamarketing.com" in body and "no separate password" in body
    assert "let back in" in welcome_email.render(name=None, email="a@smamarketing.com", added_by=None, restored=True)[1]


def test_adding_a_person_emails_them_and_reports_it(client, admin_user, monkeypatch):
    sent = []
    monkeypatch.setattr(health_digest, "send_email", lambda subject, body, to=None: sent.append((subject, to)) or True)
    h = auth_header(admin_user.email)
    made = client.post("/v2/admin/team-access/people", json={"email": "new.person@smamarketing.com", "name": "New Person"}, headers=h)
    assert made.status_code == 200 and made.json()["emailed"] is True
    assert sent == [("You have access to Organic IQ", ["new.person@smamarketing.com"])]


def test_a_mail_failure_does_not_undo_the_add(client, admin_user, monkeypatch):
    def boom(subject, body, to=None):
        raise OSError("smtp down")

    monkeypatch.setattr(health_digest, "send_email", boom)
    made = client.post("/v2/admin/team-access/people", json={"email": "new.person@smamarketing.com"}, headers=auth_header(admin_user.email))
    assert made.status_code == 200 and made.json()["emailed"] is False
    people = client.get("/v2/admin/team-access", headers=auth_header(admin_user.email)).json()["users"]
    assert "new.person@smamarketing.com" in {u["email"] for u in people}

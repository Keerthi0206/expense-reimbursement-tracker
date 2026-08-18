"""
Tests for the email integration's behavior boundaries: silently no-ops when
unconfigured, and fails gracefully (never raises) when configured but the
SMTP server is unreachable. Actual successful email delivery cannot be
verified here -- there's no real SMTP server available in this environment,
only the code paths that would use one.

Run with: pytest -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.email import send_email, _is_configured


def test_email_noops_when_disabled(monkeypatch):
    monkeypatch.delenv("EMAIL_NOTIFICATIONS_ENABLED", raising=False)
    assert _is_configured() is False
    result = send_email("someone@example.com", "Subject", "Body")
    assert result is False


def test_email_noops_when_enabled_but_not_configured(monkeypatch):
    monkeypatch.setenv("EMAIL_NOTIFICATIONS_ENABLED", "true")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_FROM_EMAIL", raising=False)
    assert _is_configured() is False


def test_email_is_configured_when_all_required_vars_present(monkeypatch):
    monkeypatch.setenv("EMAIL_NOTIFICATIONS_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "noreply@example.com")
    assert _is_configured() is True


def test_email_send_failure_never_raises(monkeypatch):
    # Configured, but pointed at a host that can't possibly resolve --
    # proves a real send attempt happens and a failure is swallowed, not
    # propagated to whatever called send_email (which must never break the
    # actual request action -- approve/reject/etc -- that triggered it).
    monkeypatch.setenv("EMAIL_NOTIFICATIONS_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "this-host-does-not-exist.invalid")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "noreply@example.com")
    result = send_email("someone@example.com", "Subject", "Body")
    assert result is False  # failed gracefully, did not raise

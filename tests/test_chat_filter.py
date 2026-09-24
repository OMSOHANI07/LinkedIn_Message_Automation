from app.bot import handlers


def test_authorized_chat_matches_configured_channel_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-1001234567890")
    assert handlers._is_authorized_chat(-1001234567890) is True


def test_unauthorized_chat_is_rejected(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-1001234567890")
    assert handlers._is_authorized_chat(999999) is False


def test_authorized_chat_for_positive_dm_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456789")
    assert handlers._is_authorized_chat(123456789) is True


def test_authorized_chat_rejects_wrong_channel(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-1009999999999")
    assert handlers._is_authorized_chat(-1001234567890) is False

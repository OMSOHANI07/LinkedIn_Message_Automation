import json

import pytest

from app.pipeline import gemini_client
from app.pipeline.schemas import TriageResult
from app.pipeline.triage import triage_note

VALID_PAYLOAD = {
    "score": 8.5,
    "publishable": True,
    "category": "A",
    "core_insight": "Label percentages are meaningless without pH and delivery base.",
    "suggested_hook_type": "HOOK TYPE 1",
    "missing_facts": ["exact pH of the serum"],
    "reason": "Specific ingredient claim with a clear thesis.",
}


class _FakeResponse:
    def __init__(self, parsed=None, text=""):
        self.parsed = parsed
        self.text = text
        self.candidates = []


class _FakeModels:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _FakeClient:
    def __init__(self, responses):
        self.models = _FakeModels(responses)


def test_triage_note_parses_valid_json(monkeypatch):
    fake_client = _FakeClient([_FakeResponse(text=json.dumps(VALID_PAYLOAD))])
    monkeypatch.setattr(gemini_client, "get_client", lambda: fake_client)

    result = triage_note("Our niacinamide serum is 10% - but at what pH?")

    assert isinstance(result, TriageResult)
    assert result.score == 8.5
    assert result.category == "A"
    assert fake_client.models.calls == 1


def test_triage_note_uses_response_parsed_when_present(monkeypatch):
    parsed = TriageResult(**VALID_PAYLOAD)
    fake_client = _FakeClient([_FakeResponse(parsed=parsed)])
    monkeypatch.setattr(gemini_client, "get_client", lambda: fake_client)

    result = triage_note("Our niacinamide serum is 10% - but at what pH?")

    assert result is parsed
    assert fake_client.models.calls == 1


def test_triage_note_retries_once_on_bad_json(monkeypatch):
    fake_client = _FakeClient(
        [
            _FakeResponse(text="not valid json"),
            _FakeResponse(text=json.dumps(VALID_PAYLOAD)),
        ]
    )
    monkeypatch.setattr(gemini_client, "get_client", lambda: fake_client)

    result = triage_note("Our niacinamide serum is 10% - but at what pH?")

    assert result.publishable is True
    assert fake_client.models.calls == 2


def test_triage_note_raises_after_exhausting_retries(monkeypatch):
    fake_client = _FakeClient(
        [
            _FakeResponse(text="not valid json"),
            _FakeResponse(text="still not valid json"),
        ]
    )
    monkeypatch.setattr(gemini_client, "get_client", lambda: fake_client)

    with pytest.raises(RuntimeError):
        triage_note("Some note")

    assert fake_client.models.calls == 2

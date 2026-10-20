import json

import pytest

from vat_whitelist.cache import Cache


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self.ok = status_code < 400
        self._payload = payload
        self.text = json.dumps(payload) if payload is not None else "<html>error</html>"

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class ScriptedSession:
    """Returns queued responses in order and records requested URLs."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def entries_payload(mapping, request_id="REQ-1"):
    return {
        "result": {
            "entries": [
                {"identifier": nip, "subjects": [subject] if subject else []}
                for nip, subject in mapping.items()
            ],
            "requestId": request_id,
        }
    }


@pytest.fixture
def cache():
    c = Cache(":memory:")
    yield c
    c.close()

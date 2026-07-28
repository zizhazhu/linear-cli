from collections.abc import Iterator
from pathlib import Path

import pytest

# Fake Linear key; non-hex suffix avoids tripping secret scanners
FAKE_API_KEY = "lin_api_test_key_not_a_real_secret"

GRAPHQL_URL = "https://api.linear.app/graphql"

VIEWER = {
    "id": "4a2b1f8e-9c3d-4e5f-a6b7-c8d9e0f1a2b3",
    "name": "Test User",
    "email": "test@example.com",
}

VIEWER_RESPONSE = {"data": {"viewer": VIEWER}}

# Real response for an invalid key: HTTP 401, no top-level "data" field
UNAUTHORIZED_RESPONSE = {
    "errors": [
        {
            "message": "Authentication required, not authenticated",
            "extensions": {
                "type": "authentication error",
                "code": "AUTHENTICATION_ERROR",
                "statusCode": 401,
                "userError": True,
                "userPresentableMessage": "You need to authenticate to access this operation.",
                "meta": {},
                "http": {"status": 401},
            },
        }
    ]
}


@pytest.fixture
def config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect credential storage to a temp file, return its path."""
    path = tmp_path / "config.toml"
    monkeypatch.setenv("LINEAR_CONFIG_PATH", str(path))
    yield path

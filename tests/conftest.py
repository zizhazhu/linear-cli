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

# 与 issue 相关 GraphQL 操作的样例响应
TEAMS_RESPONSE = {
    "data": {
        "teams": {
            "nodes": [
                {"id": "team-id-tes", "key": "TES", "name": "Test"},
            ]
        }
    }
}

# teams 响应里没有目标缩写（用于不存在的 Team 反例）
TEAMS_NO_MATCH_RESPONSE = {
    "data": {
        "teams": {
            "nodes": [
                {"id": "team-id-abc", "key": "ABC", "name": "Other"},
            ]
        }
    }
}

ISSUE = {
    "id": "a1b2c3d4-1111-2222-3333-444455556666",
    "identifier": "TES-123",
    "url": "https://linear.app/acme/issue/TES-123",
    "title": "Test issue",
    "description": "Body line 1\nBody line 2",
}

CREATE_ISSUE_RESPONSE = {
    "data": {"issueCreate": {"success": True, "issue": ISSUE}}
}

ISSUE_RESPONSE = {"data": {"issue": ISSUE}}

GRAPHQL_ERROR_RESPONSE = {
    "errors": [
        {"message": "Record not found", "extensions": {"code": "RECORD_NOT_FOUND"}},
        {"message": "Secondary error message", "extensions": {}},
    ]
}

ACCOUNT_ERROR_RESPONSE = {
    "errors": [
        {
            "message": "Authentication required, not authenticated",
            "extensions": {"code": "AUTHENTICATION_ERROR"},
        }
    ]
}


@pytest.fixture
def config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect credential storage to a temp file, return its path.

    同时清除 ``LINEAR_API_KEY``：离线测试的凭据一律来自配置文件，
    开发者本机 env/.env 里的真实 key 不会混进请求。
    真实 API 测试用 ``real_api.require_real_api_key`` 显式取回。
    """
    path = tmp_path / "config.toml"
    monkeypatch.setenv("LINEAR_CONFIG_PATH", str(path))
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    yield path

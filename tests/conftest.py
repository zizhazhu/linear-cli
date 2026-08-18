import json
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


def error_envelope(result) -> dict:
    """解析 stderr 的单行 JSON 错误信封，返回 ``error`` 对象。

    信封契约：``{"error": {"type": ..., ...}}``，stderr 除该行外不得有其他内容；
    ``type`` 取值 ``auth`` / ``not_found`` / ``graphql`` / ``http``。
    """
    return json.loads(result.stderr.strip())["error"]


@pytest.fixture
def config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect credential storage to a temp file, return its path.

    凭据环境全面隔离：
    - ``LINEAR_CONFIG_PATH`` 指向临时配置文件；
    - 清除 ``LINEAR_API_KEY`` 环境变量；
    - chdir 到临时目录，``.env`` 向上查找不会碰到开发者真实的 ``.env``。

    离线测试的凭据因此确定来自临时配置文件。
    真实 API 测试用 ``real_api.require_real_api_key`` 显式取回。
    """
    path = tmp_path / "config.toml"
    monkeypatch.setenv("LINEAR_CONFIG_PATH", str(path))
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    yield path

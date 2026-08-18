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

# GraphQL 响应里 organization 节点的原始形态；CLI login 输出中 url 由
# urlKey 推导（https://linear.app/<urlKey>）
ORG_NODE = {"id": "org-id-1", "name": "Acme", "urlKey": "acme"}

VIEWER_RESPONSE = {"data": {"viewer": VIEWER, "organization": ORG_NODE}}

# CLI login 的输出契约形态：viewer + workspace 两个顶层字段
WORKSPACE = {"id": "org-id-1", "name": "Acme", "url": "https://linear.app/acme"}
LOGIN_OUTPUT = {"viewer": VIEWER, "workspace": WORKSPACE}

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

# GraphQL 响应里 issue 节点的原始形态：嵌套对象、labels 为 nodes 连接
ISSUE_NODE = {
    "id": "a1b2c3d4-1111-2222-3333-444455556666",
    "identifier": "TES-123",
    "title": "Test issue",
    "description": "Body line 1\nBody line 2",
    "url": "https://linear.app/acme/issue/TES-123",
    "branchName": "test-user/tes-123-test-issue",
    "state": {"id": "state-id-started", "name": "In Progress", "type": "started"},
    "priority": 2,
    "priorityLabel": "High",
    "estimate": None,
    "assignee": {"id": "user-id-1", "name": "Test User"},
    "creator": {"id": "user-id-2", "name": "Creator User"},
    "team": {"id": "team-id-tes", "key": "TES", "name": "Test"},
    "labels": {"nodes": [{"name": "bug"}, {"name": "cli"}]},
    "project": None,
    "parent": None,
    "createdAt": "2026-08-01T00:00:00.000Z",
    "updatedAt": "2026-08-02T00:00:00.000Z",
    "archivedAt": None,
    "completedAt": None,
    "startedAt": "2026-08-01T12:00:00.000Z",
    "canceledAt": None,
    "dueDate": None,
}

# CLI view 的输出契约形态（对 ISSUE_NODE 的变换）：
# labels 拍平为名称数组、creator 映射为 createdBy、parent 映射为 parentId，
# 可空字段原样为 null
ISSUE = {
    "id": "a1b2c3d4-1111-2222-3333-444455556666",
    "identifier": "TES-123",
    "title": "Test issue",
    "description": "Body line 1\nBody line 2",
    "url": "https://linear.app/acme/issue/TES-123",
    "branchName": "test-user/tes-123-test-issue",
    "state": {"id": "state-id-started", "name": "In Progress", "type": "started"},
    "priority": 2,
    "priorityLabel": "High",
    "estimate": None,
    "assignee": {"id": "user-id-1", "name": "Test User"},
    "createdBy": {"id": "user-id-2", "name": "Creator User"},
    "team": {"id": "team-id-tes", "key": "TES", "name": "Test"},
    "labels": ["bug", "cli"],
    "project": None,
    "parentId": None,
    "createdAt": "2026-08-01T00:00:00.000Z",
    "updatedAt": "2026-08-02T00:00:00.000Z",
    "archivedAt": None,
    "completedAt": None,
    "startedAt": "2026-08-01T12:00:00.000Z",
    "canceledAt": None,
    "dueDate": None,
}

CREATE_ISSUE_RESPONSE = {
    "data": {"issueCreate": {"success": True, "issue": ISSUE_NODE}}
}

ISSUE_UPDATE_RESPONSE = {
    "data": {"issueUpdate": {"success": True, "issue": ISSUE_NODE}}
}

ISSUE_RESPONSE = {"data": {"issue": ISSUE_NODE}}

# 取值解析（update 的客户端名称 → UUID 解析）所需的查询层样例响应
TEAM_STATES_RESPONSE = {
    "data": {
        "team": {
            "states": {
                "nodes": [
                    {
                        "id": "state-id-todo",
                        "name": "Todo",
                        "type": "unstarted",
                        "position": 1.0,
                    },
                    {
                        "id": "state-id-started",
                        "name": "In Progress",
                        "type": "started",
                        "position": 2.0,
                    },
                    {
                        "id": "state-id-done",
                        "name": "Done",
                        "type": "completed",
                        "position": 3.0,
                    },
                ]
            },
        }
    }
}

USERS_RESPONSE = {
    "data": {
        "users": {
            "nodes": [
                {
                    "id": "user-id-1",
                    "name": "Test User",
                    "displayName": "testuser",
                    "email": "test@example.com",
                    "active": True,
                },
                {
                    "id": "user-id-2",
                    "name": "Other User",
                    "displayName": "otheruser",
                    "email": "other@example.com",
                    "active": True,
                },
            ]
        }
    }
}

ISSUE_LABELS_RESPONSE = {
    "data": {
        "issueLabels": {
            "nodes": [
                {"id": "label-id-bug", "name": "Bug", "color": "#EB5757"},
                {"id": "label-id-feature", "name": "Feature", "color": "#BB87FC"},
            ]
        }
    }
}

PROJECTS_RESPONSE = {
    "data": {
        "projects": {
            "nodes": [
                {
                    "id": "project-id-1",
                    "name": "dotfiles",
                    "url": "https://linear.app/acme/project/dotfiles-x1y2",
                    "state": "started",
                }
            ]
        }
    }
}

CYCLES_RESPONSE = {
    "data": {
        "cycles": {
            "nodes": [
                {
                    "id": "cycle-id-3",
                    "number": 3,
                    "name": "Cycle 3",
                    "startsAt": "2026-08-10T00:00:00.000Z",
                    "endsAt": "2026-08-16T23:59:59.999Z",
                }
            ]
        }
    }
}

# issues 列表查询的样例响应：两条 issue，其二 assignee 为 null
ISSUE_LIST_NODES = [
    {
        "identifier": "TES-123",
        "title": "Test issue",
        "url": "https://linear.app/acme/issue/TES-123",
        "state": {"name": "In Progress", "type": "started"},
        "priority": 2,
        "assignee": {"name": "Test User"},
        "updatedAt": "2026-08-02T00:00:00.000Z",
    },
    {
        "identifier": "TES-124",
        "title": "No assignee issue",
        "url": "https://linear.app/acme/issue/TES-124",
        "state": {"name": "Todo", "type": "unstarted"},
        "priority": 0,
        "assignee": None,
        "updatedAt": "2026-08-01T00:00:00.000Z",
    },
]

ISSUES_RESPONSE = {"data": {"issues": {"nodes": ISSUE_LIST_NODES}}}

EMPTY_ISSUES_RESPONSE = {"data": {"issues": {"nodes": []}}}

# CLI issue list 的输出契约形态：view 字段集的子集（assignee 只取 name），
# 可空字段原样为 null
ISSUE_LIST = [
    {
        "identifier": "TES-123",
        "title": "Test issue",
        "url": "https://linear.app/acme/issue/TES-123",
        "state": {"name": "In Progress", "type": "started"},
        "priority": 2,
        "assignee": {"name": "Test User"},
        "updatedAt": "2026-08-02T00:00:00.000Z",
    },
    {
        "identifier": "TES-124",
        "title": "No assignee issue",
        "url": "https://linear.app/acme/issue/TES-124",
        "state": {"name": "Todo", "type": "unstarted"},
        "priority": 0,
        "assignee": None,
        "updatedAt": "2026-08-01T00:00:00.000Z",
    },
]

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

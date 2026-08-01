"""Linear GraphQL API 客户端。"""

import httpx

GRAPHQL_URL = "https://api.linear.app/graphql"

_VIEWER_QUERY = """
query Viewer {
  viewer {
    id
    name
    email
  }
}
"""

_TEAMS_QUERY = """
query Teams {
  teams {
    nodes {
      id
      key
      name
    }
  }
}
"""

_CREATE_ISSUE_MUTATION = """
mutation IssueCreate($teamId: String!, $title: String!, $description: String) {
  issueCreate(
    input: { teamId: $teamId, title: $title, description: $description }
  ) {
    success
    issue {
      identifier
      url
      title
      description
    }
  }
}
"""

_ISSUE_QUERY = """
query Issue($id: String!) {
  issue(id: $id) {
    identifier
    url
    title
    description
  }
}
"""

_ARCHIVE_ISSUE_MUTATION = """
mutation IssueArchive($id: String!) {
  issueArchive(id: $id) {
    success
  }
}
"""


class GraphQLAPIError(Exception):
    """Linear 响应含 GraphQL ``errors`` 字段时抛出。

    携带每条 ``errors[].message`` 原文与原始响应正文，供命令层原样输出。
    """

    def __init__(self, errors: list[dict], raw_body: dict) -> None:
        self.errors = errors
        self.raw_body = raw_body
        self.messages = [e.get("message", "") for e in errors]
        super().__init__("; ".join(self.messages))


class TeamNotFoundError(Exception):
    """按缩写找不到对应 Team 时抛出。"""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Team {key!r} 不存在")


def _post(api_key: str, query: str, variables: dict[str, object]) -> dict:
    """POST 一条 GraphQL 操作。

    HTTP 非 2xx 抛 ``httpx.HTTPStatusError``（调用方从 ``.response.text`` 读原始正文）；
    响应含 GraphQL ``errors`` 时抛 ``GraphQLAPIError``。
    """
    response = httpx.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers={"Authorization": api_key},
    )
    response.raise_for_status()
    data = response.json()
    if "errors" in data:
        raise GraphQLAPIError(data["errors"], data)
    return data


def fetch_viewer(api_key: str) -> dict[str, str]:
    """用 API key 拉取当前用户信息，用于验证凭据有效性。"""
    return _post(api_key, _VIEWER_QUERY, {})["data"]["viewer"]


def fetch_teams(api_key: str) -> list[dict[str, str]]:
    """拉取当前工作区全部 Team（id / key / name）。"""
    return _post(api_key, _TEAMS_QUERY, {})["data"]["teams"]["nodes"]


def create_issue(
    api_key: str, team_key: str, title: str, description: str
) -> dict:
    """按 Team 缩写解析出 team id，创建 issue 并返回其字段。

    ``description`` 原样透传给 Linear ``description`` 字段，不做任何裁剪或改写；
    缩写找不到对应 Team 时抛 ``TeamNotFoundError``。
    """
    teams = fetch_teams(api_key)
    team = next((t for t in teams if t["key"].lower() == team_key.lower()), None)
    if team is None:
        raise TeamNotFoundError(team_key)
    data = _post(
        api_key,
        _CREATE_ISSUE_MUTATION,
        {"teamId": team["id"], "title": title, "description": description},
    )
    return data["data"]["issueCreate"]["issue"]


def fetch_issue(api_key: str, issue_id: str) -> dict | None:
    """按标识（如 ``TES-123``）读回一条 issue；不存在时返回 ``None``。"""
    data = _post(api_key, _ISSUE_QUERY, {"id": issue_id})
    return data["data"]["issue"]


def archive_issue(api_key: str, issue_id: str) -> None:
    """归档一条 issue（可逆）。供测试代码在断言通过后清理。"""
    data = _post(api_key, _ARCHIVE_ISSUE_MUTATION, {"id": issue_id})
    data["data"]["issueArchive"]["success"]

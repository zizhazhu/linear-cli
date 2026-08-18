"""Linear GraphQL API 客户端。"""

import re

import httpx

GRAPHQL_URL = "https://api.linear.app/graphql"

_VIEWER_QUERY = """
query Viewer {
  viewer {
    id
    name
    email
  }
  organization {
    id
    name
    urlKey
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
      id
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
    id
    identifier
    url
    title
    description
    branchName
    state {
      id
      name
      type
    }
    priority
    priorityLabel
    estimate
    assignee {
      id
      name
    }
    creator {
      id
      name
    }
    team {
      id
      key
      name
    }
    labels {
      nodes {
        name
      }
    }
    project {
      id
      name
    }
    parent {
      id
    }
    createdAt
    updatedAt
    archivedAt
    completedAt
    startedAt
    canceledAt
    dueDate
  }
}
"""

_ISSUES_QUERY = """
query Issues(
  $first: Int!
  $orderBy: PaginationOrderBy!
  $includeArchived: Boolean!
  $filter: IssueFilter
) {
  issues(
    first: $first
    orderBy: $orderBy
    includeArchived: $includeArchived
    filter: $filter
  ) {
    nodes {
      identifier
      title
      url
      state {
        name
        type
      }
      priority
      assignee {
        name
      }
      updatedAt
    }
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


def fetch_viewer_and_organization(api_key: str) -> dict[str, dict]:
    """用 API key 拉取当前用户与组织信息，作为 login 的数据源。"""
    return _post(api_key, _VIEWER_QUERY, {})["data"]


def fetch_viewer(api_key: str) -> dict[str, str]:
    """用 API key 拉取当前用户信息，用于验证凭据有效性。"""
    return fetch_viewer_and_organization(api_key)["viewer"]


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


_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)


def _or(branches: list[dict]) -> dict:
    """单分支直接返回该分支，多分支才包 ``or``。"""
    return branches[0] if len(branches) == 1 else {"or": branches}


def _match_any(value: str, *fields: tuple[str, str]) -> dict:
    """构造「任一字段匹配 value」的过滤分支。

    ``fields`` 为 (字段名, 比较器) 对；值形如 UUID 时自动在最前附
    ``(id, eq)`` 分支——服务端 id 比较器校验 UUID 形态，非 UUID 值进去
    会被直接拒绝。
    """
    branches = [{name: {comparator: value}} for name, comparator in fields]
    if _UUID_RE.fullmatch(value):
        branches.insert(0, {"id": {"eq": value}})
    return _or(branches)


def build_issue_filter(
    team: str | None = None,
    state: str | None = None,
    assignee: str | None = None,
    label: str | None = None,
    project: str | None = None,
    cycle: str | None = None,
    query: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> dict | None:
    """把 ``issue list`` 的 filter flags 组装为 ``IssueFilter`` 变量。

    值形态对齐 MCP 入参语义（经 GraphQL API 实测确认）：
    - 名称类匹配用 ``eqIgnoreCase``；
    - ``assignee`` 支持 ``me``（``isMe``）、名称、邮箱（值含 ``@`` 时）；
    - ``query`` 用 title/description 的 ``containsIgnoreCase``——顶层
      ``issueSearch`` 已被 API 弃用，原生比较器等价实现「搜索标题/正文」；
    - 日期值原样透传给 ``gte``：服务端接受 ISO-8601 日期与 ``-P1D`` 类
      时长，非法格式由服务端校验报错。

    全部入参为空时返回 ``None``（请求不带 filter，即匹配全部）；
    顶层多键为 AND 语义。
    """
    filter_: dict[str, dict] = {}
    if team:
        filter_["team"] = _match_any(
            team, ("key", "eqIgnoreCase"), ("name", "eqIgnoreCase")
        )
    if state:
        filter_["state"] = _match_any(
            state, ("name", "eqIgnoreCase"), ("type", "eq")
        )
    if assignee == "me":
        filter_["assignee"] = {"isMe": {"eq": True}}
    elif assignee:
        fields = [("name", "eqIgnoreCase")]
        if "@" in assignee:
            fields.append(("email", "eq"))
        filter_["assignee"] = _match_any(assignee, *fields)
    if label:
        filter_["labels"] = {"some": _match_any(label, ("name", "eqIgnoreCase"))}
    if project:
        filter_["project"] = _match_any(
            project, ("name", "eqIgnoreCase"), ("slugId", "eq")
        )
    if cycle:
        branches = [{"name": {"eqIgnoreCase": cycle}}]
        if cycle.isdigit():
            branches.append({"number": {"eq": int(cycle)}})
        if _UUID_RE.fullmatch(cycle):
            branches.insert(0, {"id": {"eq": cycle}})
        filter_["cycle"] = _or(branches)
    if query:
        filter_["or"] = [
            {"title": {"containsIgnoreCase": query}},
            {"description": {"containsIgnoreCase": query}},
        ]
    if created_at:
        filter_["createdAt"] = {"gte": created_at}
    if updated_at:
        filter_["updatedAt"] = {"gte": updated_at}
    return filter_ or None


def fetch_issues(
    api_key: str,
    first: int,
    issue_filter: dict | None = None,
    order_by: str = "updatedAt",
    include_archived: bool = False,
) -> list[dict]:
    """拉取工作区 issue 列表，最多 ``first`` 条，按 ``issue_filter`` 过滤。

    ``issue_filter`` 由 :func:`build_issue_filter` 构造；``order_by`` 缺省
    updatedAt（与 MCP 缺省一致），``include_archived`` 缺省 False 并始终
    显式传递（API 缺省同为不含归档，显式传递消除歧义）。

    返回节点即输出契约：view 字段集的子集（identifier/title/url/
    state/priority/assignee/updatedAt），``assignee`` 可空原样为 null。
    """
    variables: dict[str, object] = {
        "first": first,
        "orderBy": order_by,
        "includeArchived": include_archived,
    }
    if issue_filter:
        variables["filter"] = issue_filter
    return _post(api_key, _ISSUES_QUERY, variables)["data"]["issues"]["nodes"]


def archive_issue(api_key: str, issue_id: str) -> None:
    """归档一条 issue（可逆）。``issue_id`` 为 issue 的 UUID（``id`` 字段），
    不是 ``TES-123`` 形式的标识。供测试代码在断言通过后清理。"""
    data = _post(api_key, _ARCHIVE_ISSUE_MUTATION, {"id": issue_id})
    data["data"]["issueArchive"]["success"]

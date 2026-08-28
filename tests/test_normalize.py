"""归一化层测试：GraphQL 节点 → 输出数据的映射，纯函数，不触网。

覆盖两件事：产物只含 JSON 原生类型（渲染层能安全消费的前提），以及各命令
的字段形态（真正做变换的那几条逐一断言，其余为节点集直通）。
"""

import pytest
from conftest import (
    COMMENT_NODE,
    CREATE_COMMENT_RESPONSE,
    CREATE_ISSUE_RESPONSE,
    CREATE_LABEL_RESPONSE,
    CYCLES_RESPONSE,
    ISSUE,
    ISSUE_LABELS_RESPONSE,
    ISSUE_LIST,
    ISSUE_LIST_NODES,
    ISSUE_NODE,
    LOGIN_OUTPUT,
    ORG_NODE,
    PROJECTS_RESPONSE,
    TEAM_STATES_RESPONSE,
    TEAMS_RESPONSE,
    USERS_RESPONSE,
    VIEWER,
)

from linear_cli import normalize

JSON_NATIVE_SCALARS = (str, int, float, bool)

# 归一化后的产物：命令名 → 数据，覆盖全部 15 条数据输出命令
# （issue view 与 issue update 共用 normalize.issue）
NORMALIZED = [
    pytest.param(
        normalize.login({"viewer": VIEWER, "organization": ORG_NODE}), id="login"
    ),
    pytest.param(
        normalize.created_issue(CREATE_ISSUE_RESPONSE["data"]["issueCreate"]["issue"]),
        id="issue create",
    ),
    pytest.param(normalize.issue(ISSUE_NODE), id="issue view / issue update"),
    pytest.param(normalize.issue_list(ISSUE_LIST_NODES), id="issue list"),
    pytest.param(normalize.comment_list([COMMENT_NODE]), id="issue comment list"),
    pytest.param(
        normalize.created_comment(
            CREATE_COMMENT_RESPONSE["data"]["commentCreate"]["comment"]
        ),
        id="issue comment add",
    ),
    pytest.param(
        normalize.deleted_comment("comment-id-1", True), id="issue comment delete"
    ),
    pytest.param(
        normalize.team_list(TEAMS_RESPONSE["data"]["teams"]["nodes"]), id="team list"
    ),
    pytest.param(
        normalize.user_list(USERS_RESPONSE["data"]["users"]["nodes"]), id="user list"
    ),
    pytest.param(
        normalize.status_list(TEAM_STATES_RESPONSE["data"]["team"]["states"]["nodes"]),
        id="status list",
    ),
    pytest.param(
        normalize.label_list(ISSUE_LABELS_RESPONSE["data"]["issueLabels"]["nodes"]),
        id="label list",
    ),
    pytest.param(
        normalize.created_label(
            CREATE_LABEL_RESPONSE["data"]["issueLabelCreate"]["issueLabel"]
        ),
        id="label create",
    ),
    pytest.param(
        normalize.project_list(PROJECTS_RESPONSE["data"]["projects"]["nodes"]),
        id="project list",
    ),
    pytest.param(
        normalize.cycle_list(CYCLES_RESPONSE["data"]["cycles"]["nodes"]),
        id="cycle list",
    ),
]


def _assert_json_native(value: object, path: str = "$") -> None:
    """递归断言 value 只由 JSON 原生类型构成。

    用精确类型而非 isinstance：str 子类（如 str Enum）与 tuple 能通过
    ``json.dumps`` 却过不了 YAML 渲染，正是要挡住的那类漏网之鱼。
    """
    if value is None or type(value) in JSON_NATIVE_SCALARS:
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _assert_json_native(item, f"{path}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            assert type(key) is str, f"{path}: 非字符串键 {key!r}"
            _assert_json_native(item, f"{path}.{key}")
        return
    raise AssertionError(f"{path}: 非 JSON 原生类型 {type(value).__name__}")


@pytest.mark.parametrize("data", NORMALIZED)
def test_normalized_data_contains_only_json_native_types(data) -> None:
    """Given 任一命令的归一化产物
    When 递归遍历其全部叶子与键
    Then 只出现 dict / list / str / int / float / bool / None
    """
    _assert_json_native(data)


def test_login_pairs_viewer_with_derived_workspace_url() -> None:
    """Given GraphQL 的 viewer 与 organization 节点
    When 归一化 login 的输出
    Then 得到 viewer 与 workspace 两个顶层字段，workspace.url 由 urlKey 推导
    """
    assert normalize.login({"viewer": VIEWER, "organization": ORG_NODE}) == LOGIN_OUTPUT


def test_created_issue_keeps_only_identifier_and_url() -> None:
    """Given issueCreate 返回的 issue 节点（字段多于输出契约）
    When 归一化 issue create 的输出
    Then 只保留 identifier 与 url
    """
    node = CREATE_ISSUE_RESPONSE["data"]["issueCreate"]["issue"]

    assert normalize.created_issue(node) == {
        "identifier": "TES-123",
        "url": "https://linear.app/acme/issue/TES-123",
    }


def test_issue_flattens_labels_and_renames_creator_and_parent() -> None:
    """Given GraphQL 的 issue 节点（labels 为 nodes 连接、creator、parent）
    When 归一化 issue view / issue update 的输出
    Then labels 拍平为名称数组、creator 映射为 createdBy、parent 映射为
    parentId，可空字段原样为 null
    """
    assert normalize.issue(ISSUE_NODE) == ISSUE


def test_issue_maps_present_parent_to_its_id() -> None:
    """Given issue 节点带父 issue
    When 归一化其输出
    Then parentId 为父 issue 的 UUID（而非嵌套对象）
    """
    node = {**ISSUE_NODE, "parent": {"id": "parent-uuid"}}

    assert normalize.issue(node)["parentId"] == "parent-uuid"


def test_issue_does_not_mutate_the_api_node() -> None:
    """Given GraphQL 的 issue 节点
    When 归一化其输出
    Then 入参节点不被改写：归一化是映射而非原地修改
    """
    node = {**ISSUE_NODE}

    normalize.issue(node)

    assert node == ISSUE_NODE


def test_created_comment_keeps_only_id_and_url() -> None:
    """Given commentCreate 返回的 comment 节点
    When 归一化 issue comment add 的输出
    Then 只保留 id 与 url
    """
    node = CREATE_COMMENT_RESPONSE["data"]["commentCreate"]["comment"]

    assert normalize.created_comment(node) == {
        "id": "comment-id-1",
        "url": "https://linear.app/acme/issue/TES-123#comment-comment-id-1",
    }


def test_deleted_comment_reports_the_requested_id_and_outcome() -> None:
    """Given 一次删除评论的调用与其成功标志
    When 归一化 issue comment delete 的输出
    Then 输出 {"id": 请求的 UUID, "deleted": 成功标志}
    """
    assert normalize.deleted_comment("comment-id-1", True) == {
        "id": "comment-id-1",
        "deleted": True,
    }


def test_label_list_drops_the_team_scope_field() -> None:
    """Given issueLabels 节点（含用于 --team 过滤的 team 字段）
    When 归一化 label list 的输出
    Then 只输出 id/name/color，team 不进输出契约
    """
    nodes = ISSUE_LABELS_RESPONSE["data"]["issueLabels"]["nodes"]

    assert normalize.label_list(nodes) == [
        {"id": "label-id-bug", "name": "Bug", "color": "#EB5757"},
        {"id": "label-id-feature", "name": "Feature", "color": "#BB87FC"},
        {"id": "label-id-cli", "name": "cli", "color": "#4EA7FC"},
        {"id": "label-id-other", "name": "other-only", "color": "#999999"},
    ]


PASS_THROUGH = [
    pytest.param(normalize.issue_list, ISSUE_LIST_NODES, ISSUE_LIST, id="issue list"),
    pytest.param(
        normalize.comment_list, [COMMENT_NODE], [COMMENT_NODE], id="issue comment list"
    ),
    pytest.param(
        normalize.team_list,
        TEAMS_RESPONSE["data"]["teams"]["nodes"],
        [{"id": "team-id-tes", "key": "TES", "name": "Test"}],
        id="team list",
    ),
    pytest.param(
        normalize.user_list,
        USERS_RESPONSE["data"]["users"]["nodes"],
        USERS_RESPONSE["data"]["users"]["nodes"],
        id="user list",
    ),
    pytest.param(
        normalize.status_list,
        TEAM_STATES_RESPONSE["data"]["team"]["states"]["nodes"],
        TEAM_STATES_RESPONSE["data"]["team"]["states"]["nodes"],
        id="status list",
    ),
    pytest.param(
        normalize.created_label,
        CREATE_LABEL_RESPONSE["data"]["issueLabelCreate"]["issueLabel"],
        {"id": "label-id-new", "name": "cli-new"},
        id="label create",
    ),
    pytest.param(
        normalize.project_list,
        PROJECTS_RESPONSE["data"]["projects"]["nodes"],
        PROJECTS_RESPONSE["data"]["projects"]["nodes"],
        id="project list",
    ),
    pytest.param(
        normalize.cycle_list,
        CYCLES_RESPONSE["data"]["cycles"]["nodes"],
        CYCLES_RESPONSE["data"]["cycles"]["nodes"],
        id="cycle list",
    ),
]


@pytest.mark.parametrize("normalizer,nodes,expected", PASS_THROUGH)
def test_node_set_is_the_output_contract(normalizer, nodes, expected) -> None:
    """Given 输出契约即 GraphQL 选择集的那些命令
    When 归一化其节点集
    Then 数据等于节点集本身，且不与 API 响应共享同一对象（避免下游改写响应）
    """
    normalized = normalizer(nodes)

    assert normalized == expected
    assert normalized is not nodes

"""归一化层：GraphQL 响应 → 各命令的输出数据。

每条数据输出命令在这里有且仅有一个归一化函数（``issue view`` 与
``issue update`` 输出字段集相同，共用 :func:`issue`），产物只由 JSON 原生
类型构成（dict/list/str/int/float/bool/None），交给 :mod:`linear_cli.output`
按格式渲染。命令层因此不再自己拼输出。

多数命令的 GraphQL 选择集本身就是输出契约（见 :mod:`linear_cli.api` 各
fetch 函数），其归一化即节点集直通；直通仍走函数而非在命令层裸传，是为了
让「哪条命令输出什么」有唯一的落点，并且返回新容器、不把 API 响应对象交给
下游。真正做变换的只有 login 的 workspace 拼装、issue 的字段整形、创建类
命令的字段收窄与 label 的 team 字段剥离。
"""


def login(data: dict) -> dict:
    """`login`：viewer 原样 + workspace（``url`` 由 ``urlKey`` 推导）。"""
    organization = data["organization"]
    return {
        "viewer": data["viewer"],
        "workspace": {
            "id": organization["id"],
            "name": organization["name"],
            "url": f"https://linear.app/{organization['urlKey']}",
        },
    }


def created_issue(node: dict) -> dict:
    """`issue create`：只报标识与网页 URL（mutation 选择集宽于输出契约）。"""
    return {"identifier": node["identifier"], "url": node["url"]}


def issue(node: dict) -> dict:
    """`issue view` / `issue update`：issue 节点整形为输出字段集。

    labels 拍平为名称数组，creator 映射为 createdBy，parent 映射为 parentId
    （可空字段原样为 null），其余字段按 GraphQL 命名原样输出。
    """
    shaped = dict(node)
    shaped["labels"] = [label["name"] for label in node["labels"]["nodes"]]
    shaped["createdBy"] = node["creator"]
    shaped["parentId"] = node["parent"]["id"] if node["parent"] else None
    del shaped["creator"], shaped["parent"]
    return shaped


def issue_list(nodes: list[dict]) -> list[dict]:
    """`issue list`：节点集即输出契约（view 字段集的子集）。"""
    return list(nodes)


def comment_list(nodes: list[dict]) -> list[dict]:
    """`issue comment list`：节点集即输出契约。"""
    return list(nodes)


def created_comment(node: dict) -> dict:
    """`issue comment add`：只报评论 UUID 与网页 URL。"""
    return {"id": node["id"], "url": node["url"]}


def deleted_comment(comment_id: str, deleted: bool) -> dict:
    """`issue comment delete`：回报请求的 UUID 与删除结果。"""
    return {"id": comment_id, "deleted": deleted}


def team_list(nodes: list[dict]) -> list[dict]:
    """`team list`：节点集即输出契约（id/key/name）。"""
    return list(nodes)


def user_list(nodes: list[dict]) -> list[dict]:
    """`user list`：节点集即输出契约（id/name/displayName/email/active）。"""
    return list(nodes)


def status_list(nodes: list[dict]) -> list[dict]:
    """`status list`：节点集即输出契约（id/name/type/position）。"""
    return list(nodes)


def label_list(nodes: list[dict]) -> list[dict]:
    """`label list`：id/name/color；``team`` 只用于 ``--team`` 过滤，不进输出。"""
    return [
        {"id": node["id"], "name": node["name"], "color": node["color"]}
        for node in nodes
    ]


def created_label(node: dict) -> dict:
    """`label create`：节点即输出契约（id/name）。"""
    return dict(node)


def project_list(nodes: list[dict]) -> list[dict]:
    """`project list`：节点集即输出契约（id/name/url/state）。"""
    return list(nodes)


def cycle_list(nodes: list[dict]) -> list[dict]:
    """`cycle list`：节点集即输出契约（id/number/name/startsAt/endsAt）。"""
    return list(nodes)

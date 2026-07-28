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


def fetch_viewer(api_key: str) -> dict[str, str]:
    """用 API key 拉取当前用户信息，用于验证凭据有效性。

    Linear 把 API key 直接放在 ``Authorization`` 头里（无 ``Bearer`` 前缀）。
    成功返回 viewer 对象；HTTP 非 2xx 时抛出 ``httpx.HTTPStatusError``。
    """
    response = httpx.post(
        GRAPHQL_URL,
        json={"query": _VIEWER_QUERY},
        headers={"Authorization": api_key},
    )
    response.raise_for_status()
    return response.json()["data"]["viewer"]

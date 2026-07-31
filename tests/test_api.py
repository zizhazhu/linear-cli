import httpx
import pytest
import respx
from conftest import FAKE_API_KEY, GRAPHQL_URL, UNAUTHORIZED_RESPONSE, VIEWER, VIEWER_RESPONSE

from linear_cli.api import fetch_viewer


@respx.mock
def test_fetch_viewer_returns_viewer_on_success() -> None:
    # 200 + data.viewer 时返回 viewer 字典
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=VIEWER_RESPONSE))

    assert fetch_viewer(FAKE_API_KEY) == VIEWER


@respx.mock
def test_fetch_viewer_raises_on_http_error() -> None:
    # HTTP 非 2xx（如无效 key 的 401）时抛出 HTTPStatusError
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(401, json=UNAUTHORIZED_RESPONSE))

    with pytest.raises(httpx.HTTPStatusError):
        fetch_viewer(FAKE_API_KEY)


@respx.mock
def test_fetch_viewer_propagates_network_error() -> None:
    # 网络层错误（超时/连接失败）不包装，原样向上传播给调用方处理
    respx.post(GRAPHQL_URL).mock(side_effect=httpx.ConnectError("connection refused"))

    with pytest.raises(httpx.ConnectError):
        fetch_viewer(FAKE_API_KEY)

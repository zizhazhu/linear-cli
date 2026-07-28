# tests/

单元测试目录，使用 pytest。

## 约定

- 测试文件命名 `test_*.py`，与被测模块一一对应。
- 网络相关测试不请求真实 Linear API，用 `respx` 或 monkeypatch 拦截 `httpx` 请求。
- 运行方式：`uv run pytest`。

## 内容

（暂无测试文件）

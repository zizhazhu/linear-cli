# linear_cli/

项目唯一的顶层 Python 包，所有业务代码放在这里。

## 布局约定

- CLI 入口在 `app.py`（typer app），`__init__.py` 导出 `app` 与 `main`，
  `__main__.py` 支持 `python -m linear_cli`。
- 子命令按领域拆模块（如 `issue.py`、`project.py`），在 `app.py` 中用
  `app.add_typer(...)` 挂载。
- 与 Linear API 交互的逻辑（GraphQL query/mutation + httpx）放 `api.py` 或
  按领域拆分，与 CLI 层解耦。

## 内容

| 条目 | 说明 |
|------|------|
| `app.py` | typer app 定义与入口函数 `main` |
| `__main__.py` | 支持 `python -m linear_cli` 执行 |
| `__init__.py` | 导出 `app`、`main`，控制公开 API |

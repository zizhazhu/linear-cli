# Linear Cli

自用的 Linear 命令行工具，由于官方没有提供 CLI，第三方接口也可能随时改变，所以自己制作一个薄 CLI 用于本地操作 Linear。

所有命令默认在 stdout 输出单行 JSON（供 Agent 与脚本消费）；加 `--pretty` 才输出人类可读格式。

## 登录

先用个人 API key 登录，key 会被写入配置文件：

```console
$ linear login --api-key lin_api_xxx
{"viewer": {"id": "...", "name": "Name", "email": "name@example.com"}, "workspace": {"id": "...", "name": "Workspace", "url": "https://linear.app/workspace"}}
```

## 创建 issue

`--team` 传 Team 缩写（如 TES），`--title`、`--body` 必填。返回标识与网页 URL：

```console
$ linear issue create --team TES --title "标题" --body "正文"
{"identifier": "TES-123", "url": "https://linear.app/workspace/issue/TES-123"}

$ linear issue create --team TES --title "标题" --body "正文" --pretty
TES-123 https://linear.app/workspace/issue/TES-123
```

`--body` 原样写入 Linear description，不做任何裁剪、改写或规范化。

## 查看 issue

`view` 只需标识，无需 Team 参数：

```console
$ linear issue view TES-123
{"id": "258773fc-...", "identifier": "TES-123", "url": "https://linear.app/workspace/issue/TES-123", "title": "标题", "description": "正文", "branchName": "name/tes-123-标题", "state": {"id": "...", "name": "In Progress", "type": "started"}, "priority": 2, "priorityLabel": "High", "estimate": null, "assignee": {"id": "...", "name": "Name"}, "createdBy": {"id": "...", "name": "Name"}, "team": {"id": "...", "key": "TES", "name": "Test"}, "labels": [], "project": null, "parentId": null, "createdAt": "2026-08-18T00:00:00.000Z", "updatedAt": "2026-08-18T00:00:00.000Z", "archivedAt": null, "completedAt": null, "startedAt": null, "canceledAt": null, "dueDate": null}

$ linear issue view TES-123 --pretty
TES-123 标题
正文
```

## 列出 issue

`list` 拉取工作区 issue，默认 50 条，输出 JSON 数组（每项为 view 字段集的子集）：

```console
$ linear issue list --limit 10
[{"identifier": "TES-123", "title": "标题", "url": "https://linear.app/...", "state": {"name": "In Progress", "type": "started"}, "priority": 2, "assignee": {"name": "Name"}, "updatedAt": "2026-08-18T00:00:00.000Z"}, ...]
```

`--pretty` 以表格渲染。

## 配置

配置文件路径按以下优先级解析（全平台统一）：

1. `LINEAR_CONFIG_PATH` 环境变量（最高优先，用于测试隔离）
2. `$XDG_CONFIG_HOME/linear-cli/config.toml`
3. `~/.config/linear-cli/config.toml`（最终回落）

未登录时执行 `create`/`view` 会提示先运行 `linear login`。

## 开发

```console
$ uv run pytest    # 运行测试；真实 API 测试需设置 LINEAR_API_KEY，缺失时自动 skip
```

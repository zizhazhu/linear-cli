# Linear Cli

自用的 Linear 命令行工具，由于官方没有提供 CLI，第三方接口也可能随时改变，所以自己制作一个薄 CLI 用于本地操作 Linear。

## 登录

先用个人 API key 登录，key 会被写入配置文件：

```console
$ linear login --api-key lin_api_xxx
已登录：Name <name@example.com>
```

## 创建 issue

`--team` 传 Team 缩写（如 TES），`--title`、`--body` 必填。返回标识与网页 URL：

```console
$ linear issue create --team TES --title "标题" --body "正文"
TES-123 https://linear.app/workspace/issue/TES-123
```

`--body` 原样写入 Linear description，不做任何裁剪、改写或规范化。加 `--json` 以 JSON 输出标识与 URL。

## 查看 issue

`view` 只需标识，无需 Team 参数：

```console
$ linear issue view TES-123
TES-123 标题
正文

$ linear issue view TES-123 --json
{"identifier": "TES-123", "url": "https://linear.app/workspace/issue/TES-123", "title": "标题", "description": "正文"}
```

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

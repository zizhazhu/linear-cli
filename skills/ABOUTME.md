# skills/

随仓库发布的 Agent Skills（`SKILL.md` 格式），供 `npx skills` 等安装器发现并
分发到各 agent 工具。

## 设计约定

- skill 保持**薄**：只做触发与路由，使用契约以 `linear guide` 的输出为唯一
  事实源，不在 SKILL.md 里复制，避免双份内容漂移。
- 每个 skill 一个目录，目录名与 frontmatter 的 `name` 一致（kebab-case）。

## 安装

```console
$ npx skills add /path/to/linear-cli -g      # 本地路径，全局
$ npx skills add <owner>/linear-cli -g       # 或推到 GitHub 后按仓库安装
```

安装是**拷贝**语义：skill 被复制到中央存储（全局为 `~/.agents/skills/<name>/`
），各 agent 目录里的条目（如 `~/.claude/skills/<name>`）默认是指向中央副本
的符号链接（`--copy` 则各目录各放一份拷贝）；支持该共享位置的 agent
（如 Codex）无需链接即可直接读到。SKILL.md 变更后需重跑
`npx skills add` / `npx skills update` 刷新中央副本。

## 内容

| 条目 | 说明 |
|------|------|
| `linear-cli/` | `linear-cli` skill：教 agent 使用本 CLI（先跑 `linear guide`） |

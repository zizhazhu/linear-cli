# AGENTS.md

本文件为在此代码库中工作的 AI Agent 提供指导。

## 项目是什么

Linear CLI：自用的 Linear 命令行工具。官方未提供 CLI，第三方接口也可能随时
变化，故自制一个薄 CLI 用于本地同步状态。

## 导航协议

- 每个目录有且仅有一个 `ABOUTME.md` 作为该目录的自描述入口，人类和 Agent 都读它。
- 进入任何目录工作前，先读该目录的 `ABOUTME.md`。
- 想了解某个子目录，去读那个子目录的 `ABOUTME.md`，不要从父级文件推断子目录细节。
- 「内容」清单不列 `node_modules`、`.git` 等惯例文件与产物，只列有信息量的条目。

## 顶层地图

| 条目 | 说明 |
|------|------|
| `README.md` | 项目门面（人类向）：项目定位与使用说明 |
| `docs/` | 技术文档（设计决策、技术方案等） |
| `src/` | 源码（`linear_cli` 包，uv 项目 + src layout） |
| `tests/` | 单元测试（pytest） |

新增顶层条目（目录或关键文件）时，同步更新本表；新增目录时同时创建其
`ABOUTME.md`。

## Git 与提交

提交信息用英文，遵循 Conventional Commits：`<type>: <description>`。

- subject 行 ≤ 50 字符（至多 72），用祈使句，结尾不加句号；概括提交做了什么。
- body 解释为什么这样改：动机、约束、取舍等 diff 里看不出来的信息；
  diff 本身能读出的内容不重复写。

## 测试

测试时向 Linear 提交的 issue，必须加上 test 标签

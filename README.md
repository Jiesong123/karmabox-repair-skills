# KarmaBox Repair Skills

集中管理 KarmaBox、ComfyUI 和漫剧生产链路中的可复用修复技能。每个技能必须独立、可验证，并保留明确的问题类型、适用范围和测试入口。

## 分类

| 分类 | 用途 |
|---|---|
| `api-compatibility` | API字段、响应结构、版本兼容和媒体下载修复 |
| `connection-recovery` | 地址发现、网络连接、服务恢复和健康检查 |
| `runtime-recovery` | OOM、进程退出、队列恢复、锁和断点续跑 |
| `workflow-repair` | ComfyUI节点、模型组合和工作流结构修复 |
| `quality-control` | 图片、视频、角色一致性和交付验收 |

## 当前技能

| 技能 | 分类 | 状态 |
|---|---|---|
| `comfyui-safe-history-resume` | `api-compatibility` | validated |

完整机器可读索引见 `catalog.json`。

## 目录约定

```text
karmabox-repair-skills/
├── catalog.json
├── skills/
│   └── <category>/
│       └── <skill-name>/
│           ├── SKILL.md
│           ├── agents/
│           ├── scripts/
│           ├── references/
│           └── assets/
└── scripts/
    └── validate_repository.py
```

不要把生产生成物、Prompt历史、缓存、锁文件、模型或用户媒体提交进仓库。

## 新增技能

1. 选择现有分类；没有合适分类时先更新 `catalog.json`。
2. 使用小写连字符命名技能目录。
3. 保证 `SKILL.md` frontmatter 中的 `name` 与目录名一致。
4. 把技能登记到 `catalog.json`。
5. 提供离线自检脚本；不能让仓库校验自动操作远端生产环境。
6. 运行：

```bash
python scripts/validate_repository.py
```

7. 校验通过后再提交。

## 推送到 GitHub

在 GitHub CLI 登录后，从仓库根目录运行：

```bash
gh repo create karmabox-repair-skills --private --source=. --remote=origin --push
```

公开仓库需要明确改用 `--public`。

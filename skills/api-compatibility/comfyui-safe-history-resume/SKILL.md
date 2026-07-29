---
name: comfyui-safe-history-resume
description: 安全解析 ComfyUI `/history/{prompt_id}` 中分布在各输出节点的图片、视频和 GIF，兼容 `filename` 与旧式 `name` 字段，识别 execution_error、成功但空输出、下载失败和损坏媒体，并通过锁文件与 manifest 从最后成功镜头续跑。用于修复 KeyError:name、poll_history、空 outputs、重复后台任务、错误完成报告以及批量图片或视频任务恢复。

SKILL.md      = 告诉 KarmaBox 应该怎么做；
scripts/      = 实际执行修复；
assets/       = 测试数据
references/   = API 技术说明
agents/       = 技能展示和调用配置
REPAIR.md     = 给维护人员看的修复说明
---

# ComfyUI 安全结果解析与续跑

优先运行 `scripts/comfyui_result.py`，不要为每个项目重新编写 `poll_history`。接口字段错误属于程序错误，不得猜测成 OOM。

## 处理单个任务

```bash
python scripts/comfyui_result.py \
  --server http://COMFYUI_HOST:PORT \
  --prompt-id PROMPT_ID \
  --output keyframes/shot01/keyframe.png \
  --manifest production-manifest.json
```

脚本必须：

1. 读取 `/history/{prompt_id}`。
2. 从 `payload[prompt_id]["outputs"]` 遍历所有节点。
3. 兼容 `item["filename"]` 和旧式 `item["name"]`，优先使用 `filename`。
4. 识别 `images`、`image`、`video`、`videos`、`gifs` 和 `audio`。
5. 从 `status.messages` 提取 `execution_error` 原文。
6. 对完成但没有媒体的任务明确报错，不得判定为 OOM或成功。
7. 使用 `/view?filename=...&subfolder=...&type=...` 下载，禁止使用 `name` 查询参数。
8. 验证文件非空、格式签名正确，并在可用时通过 Pillow 或 ffprobe 验证可解码。
9. 原子更新 manifest。

## 停止旧进程

重启生产脚本前：

1. 查找与当前项目脚本路径、项目目录和锁文件完全匹配的进程。
2. 记录 PID 和命令行。
3. 对准确 PID 发送正常终止信号并等待退出。
4. 确认锁已释放后只启动一个新进程。

不得使用宽泛的 `killall python`，不得在旧进程仍运行时重复启动。`comfyui_result.py` 默认使用输出目录下的 `.comfyui-history.lock` 防止同一结果被并发处理；批量生产时应为整个项目指定同一个 `--lock-file`。

## Shot 01 验证门

修复代码后只运行 `shot01`：

1. 确认 history 存在对应 Prompt ID。
2. 确认 `outputs` 中存在媒体。
3. 成功下载到计划路径。
4. 文件大小大于0且可解码。
5. 把状态写为 `downloaded_and_verified`。
6. 实际查看图片或视频。

只有 Shot 01 完成以上全部步骤，才能继续 I2V 或其他镜头。

## 安全续跑

- 启动时读取 manifest 和磁盘文件。
- 已标记 `downloaded_and_verified` 且文件仍通过验证的镜头直接跳过。
- 已提交但未验收的镜头先查询原 Prompt ID，不得直接重复提交。
- 失败镜头保留 Prompt ID、错误原文和已有文件。
- 从第一个未验证镜头继续，不删除成功文件，不从头重跑整批。
- 每个镜头一次只允许一个活动 Prompt ID。

manifest 状态只允许按以下方向推进：

```text
planned
→ submitted
→ history_success
→ downloaded
→ downloaded_and_verified
```

`execution_error`、`completed_without_media`、`download_error` 和 `validation_error` 是失败状态，不能伪装为完成。

## 自检

安装后运行：

```bash
python scripts/self_test.py
```

自检只读取 `assets/history-fixtures.json`，不会连接远端或生成媒体。

## 完成报告

报告 Prompt ID、远端媒体元数据、本地路径、文件大小、验证方式和 manifest 状态。明确区分“历史成功”和“已下载验收”。

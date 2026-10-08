# 第五阶段：统一启动与最终验收

2026-10-08 在 WSL 的实际仓库开发和验收。未 commit、push、创建凭据或公开部署。

## 结果与证据

- 132 项离线单元/HTTP/fixture/配置/费用边界回归通过，9.679 秒；包含 22 项保守预算与配置回归、10 项共享授权/计价前置边界回归、6 项账本路径别名回归及14项零消费恢复/门槛回归。预算和零消费恢复变更已通过独立最终复核，证据见 outputs/independent-zero-recovery-final-20261008/。
- 32 项去重后的真实 PostgreSQL/进程验收通过，85.025 秒；包含原 13 项回归和
  新增故障/并发用例，尤其是锁等待跨过到期、部分结果写入挂起、
  来源失效后的幂等重放、结果返回后持久化连接被终止。
- Day4–6 三份历史 smoke 通过，无网络或真实模型调用。
- Compose 已在独立空 volume 验证：任务数初始为 0、API 健康检查、任务闭环、
  同键重放/异请求冲突、provider 失败、worker SIGKILL 后第二次 attempt 恢复、
  PostgreSQL 重启后历史结果不变及新任务完成。
- WSL Python 3.12.3；镜像 Python 3.10.21；PostgreSQL 16.15。
  Docker Hub 拉取 Python 3.12 时连接重置，改用本机已有官方 Python 3.10 镜像，
  完成实际构建和执行；不是只检查 Compose 语法。

最终成功项目：`locagent-acceptance-376a054116`。
保留卷：`locagent-acceptance-376a054116_pgdata`。
镜像：`sha256:4b8b6958b3f455836c04155c11a1f8ccff368958c8e3a4064672a8429c5bd37c`。
数据库重启后新完成任务：`b215518e-76b6-4dc7-bbb5-26b018d6d224`。

| 证据 | 路径 |
| --- | --- |
| 最终离线命令 | outputs/stage4/zero-use-recovery-review/offline-tests-final.log |
| 真实故障验收 | outputs/stage3/postgres-review-regression.log |
| 历史 smoke | outputs/stage3/historical-smokes.log |
| Compose 任务 ID、attempt、镜像与清理结果 | outputs/stage5/locagent-acceptance-376a054116/evidence.json |
| Compose 全过程日志 | outputs/stage5/locagent-acceptance-376a054116/compose.log |
| 最终 Compose 汇总 | outputs/stage5/acceptance-review.log |
| 最终构建日志 | outputs/stage5/build-review.log |
| 离线配对结果 | outputs/stage4/conservative-budget/offline-paired/summary.json |
| 原 18 个修改的备份及 hash | outputs/stage3/baseline/ |

最初仅使用 internal 网络导致主机端口不可访问，已修正为 API 单独增加 ingress
网络；数据库/worker 仍只在内部网络。失败验收和成功验收的 volume 均保留；
原 `locagent-stage2-pg-data` 未删除。测试在独立 schema/volume 内迁移，
没有改变原 demo schema 的版本或记录。

## 统一启动

```sh
cd /home/lenovo/projects/LocAgent
docker compose up --build -d --wait
curl --noproxy '*' http://127.0.0.1:18080/health
curl --noproxy '*' -X POST http://127.0.0.1:18080/tasks \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: demo-001' \
  -d '{"problem_statement":"Locate render."}'
# 使用返回 UUID 查询 /tasks/<UUID> 和 /tasks/<UUID>/attempts
docker compose down
```

默认 project 为 locagent，卷为 locagent_pgdata。验收 runner 每次新建随机 project，
先确认卷不存在，再验证任务数为 0；结束 down，从不加 --volumes。
API 仅发布 127.0.0.1:18080，数据库不发布主机端口。
API/worker 非 root、只读文件系统、独立 tmpfs、无附加 capabilities。
局部 PostgreSQL 使用内部网络 trust，不生成凭据；这是本机受控演示配置，
不是公开/生产部署方案。Compose 不加载 .env，默认禁止真实模型调用。

原 WSL demo up/run/down 仍可用（8000 端口），up 会显式迁移 v1→v2；
历史 running 转为 needs_review，禁止自动重放。

## 自动化复现

```sh
sh scripts/check_local.sh
docker start locagent-stage2-pg
sh scripts/check_local.sh --postgres
sh scripts/check_local.sh --compose
.venv/bin/python -B tests/run_historical_smokes.py
```

配置模板为 .env.example；[阶段四验收](STAGE4_ACCEPTANCE.md) 说明显式加载、
仅检测存在性的检查器和真实实验预算。另见 [架构说明](ARCHITECTURE.md)。

## 简历可用表述：已通过验收

> 基于 LocAgent 改造异步代码定位服务，使用 FastAPI、PostgreSQL 和独立 worker，
> 实现幂等提交、SKIP LOCKED 并发领取、lease/heartbeat、超时取消、有限重试及
> fencing；通过 32 项真实数据库/进程验收，完成 Docker Compose 干净启动、
> 任务闭环、worker 崩溃恢复与数据库重启持久化验证。

> 建立 132 项离线单元、HTTP、定位流程和评估预算回归测试；针对锁等待跨过
> lease 到期、部分结果写入、未知付费结果和账本持久化失败设计故障注入用例。

这里的 132 项为本轮离线回归结果；32 项数据库/进程与 Compose 为已通过的
独立复核结果。本轮没有重新执行数据库/Compose 验收，其核心 API、store、
worker 和 PostgreSQL 测试文件 hash 仍与独立复核记录一致。

## 简历可用表述：真实开发样本 pilot 已完成

> 构建固定 Git commit、样本、图/BM25 索引及 SHA-256 清单的 off/on 配对评估工具，支持固定分母评分、原始结果留存及预算审计；完成一个公开开发样本的 6 次真实 Flash 调用，两组均首位命中目标文件/函数，并验证 6 次重复工具返回折叠。

真实模型结果已完成：输入 token 为 off 16,880 / on 16,335，输出 822 / 853，任务耗时 15.626 / 14.755 秒。全部六次共34,890 token，按官方峰时全部输入按未命中估算 ¥0.079830；按报告缓存用量估算 ¥0.03943832。未查询实际账单，不声称实际扣款。

这是单个反复使用的开发样本、每组一次，off先运行，缓存和模型检索路径不同。不能写普遍质量提升、稳定节省比例、生产吞吐量提升或 exactly-once 模型执行。fixture 字符变化不能代替真实模型效果。

本机.env仅由授权CLI正常加载，未显示、复制或修改。首次0请求/0预留的失败记录保留；经独立复核与明确授权进行一次零消费审计迁移后，真实pilot exit 0完成，无未知调用、无自动重试。原¥20授权的¥18.911232完整预留保留，不能重复领取。

本次运行后未再修改生产代码或重新执行付费命令。完整报告和已执行命令见 [LIVE_PILOT_REPORT.md](outputs/stage4/live-pilot-recovered-20261008/LIVE_PILOT_REPORT.md)，机器可核验数据见同目录 verified-outcome.json、summary.json、budget.json、responses/ 和 delivery-check.json。更新前文档保存为同目录 STAGE5_ACCEPTANCE.before-live-report.md。

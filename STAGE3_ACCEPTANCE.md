# 第三阶段：可靠任务生命周期

基线：`work/locagent-baseline`，HEAD `1d1e0bf3a9c0a48d1fd280e5707c7ff56000cab8`。
2026-10-08 现场确认原有 18 个未提交文件；修改前备份及 SHA-256 清单位于
`outputs/stage3/baseline/`。原基线 61 项纯测试（14.002 秒）与 13 项
PostgreSQL/进程测试（43.505 秒）通过。未 commit、push、创建凭据或删历史数据。

## 行为

- POST `/tasks` 支持可选 `Idempotency-Key`，1–128 个字母/数字/`_.:-`。
  同键同规范化请求返回原任务，包括已完成任务；同键异请求返回 409。
  先匹配已存请求，再验证新 prepared 来源，因此来源文件丢失不影响已存请求重放。
  同键事务用 advisory lock 排序，唯一索引仍是最终约束。键按 schema 全局作用。
- worker 使用 `FOR UPDATE SKIP LOCKED` 原子领取，领取事务提交后才运行引擎。
  每次领取生成新 UUID token，递增 attempt，并写入独立 attempts 审计表。
- 默认 lease 15 秒；监督循环至少每秒续租，整个 attempt 默认 90 秒硬截止。
  `timeout_seconds` 范围 1–900，`max_attempts` 范围 1–5、默认 3。
  超时是**每次执行**的截止；重试会重新开始计时，总尝试数始终有界。
- 续租和终态写入均先锁行，再用下一条 SQL 的数据库当前时间检查 lease/deadline；
  同时检查 task、running 状态、worker、token、attempt。
  过期 worker 即使尚未被重新领取，也无法续租、完成或写失败。
  先锁后检查避免 SQL 在锁等待前计算时间、等待跨过到期后仍写入的漏洞。
- `POST /tasks/{id}/cancel` 终结 queued/running；终态重复取消返回原状态。
  成功和取消由行锁串行化，只有一个终态胜出。
- `POST /tasks/{id}/retry` 只允许未耗尽次数的 failed demo 任务。
  崩溃或硬截止后，仅无外部付费副作用的 demo 自动重排；耗尽则 failed。
  显式 provider 错误保留 failed，可用上述接口做有限人工重试。
- prepared 来源中断或未知结果进入 `needs_review`，不自动或手动重新执行。
  取消只阻止继续执行/落库，不能撤销已发出的远程请求或保证不产生费用。
- `GET /tasks/{id}/attempts` 返回尝试序号、worker、开始/结束时间、结果和错误。
  任务领取失败或终态写入失败不会伪装成正常完成。

## 引擎隔离与结果交接

每次 attempt 在新 spawn 子进程里运行 GraphLocalizer，API 与监督 worker 不共享
旧图工具全局状态。Linux PDEATHSIG 与父 PID 二次核对使父进程被 SIGKILL 后
引擎子进程不能继续运行。取消、截止、数据库故障及失效领取均会终止并回收子进程。

子进程把最多 16 MiB JSON 写到私有临时文件，fsync 后原子 rename 为 ready 文件。
监督循环只检查完整发布的结果，避免 Pipe 消息头已到达、正文未完成时 recv 无限阻塞。
部分写入时心跳、取消和截止仍能继续。正常退出清理本次临时目录；监督进程被
SIGKILL 时可能遗留 /tmp 文件，不代表任务成功，也不触发付费重放。

## 迁移与历史

`python -m locagent_service.db` 显式执行 v1→v2 迁移，不由 HTTP 自动迁移。
初始化有 advisory lock；旧 completed/failed 请求和结果保留。
旧 v1 running 没有可验证 lease，转为 `needs_review / legacy_interrupted`，
不自动重放历史工作。该变化属于保留记录并明确状态，不清表、不删卷。
本次验收在自己的随机 acceptance schema 内测试迁移；原 demo schema 保持原样。

## 验收与复现

```sh
cd /home/lenovo/projects/LocAgent
# 本机已有 stage2 容器/配置时重启它；不生成新凭据。
docker start locagent-stage2-pg
.venv/bin/python -B tests/run_stage2_acceptance.py --pattern stage3_postgres_acceptance.py
```

32 个去重后的真实 PostgreSQL/进程用例包含 13 个原阶段二回归及 19 个新增用例。
日志：`outputs/stage3/postgres-review-regression.log`。
每项使用唯一随机 schema，结束仅删除自己创建的 schema；不替换成 SQLite/mock。

覆盖：8 路同键提交、不同请求同键竞争、6 路领取、SKIP LOCKED、旧 token/attempt、
锁等待跨过 lease 到期后的续租和完成、硬超时、取消/成功竞争、部分结果写入挂起、
引擎启动后取消并确认 PID 被回收、有限重试、SIGKILL 恢复、API 重启持久化、
真实 pg_terminate_backend，以及**引擎已返回但持久化连接被终止**时禁止重放
prepared 任务。后者使用无付费的受控引擎模拟外部结果，故障数据库是真 PostgreSQL。

## 可主张的边界

这是本机受控任务服务，具备持久化状态和失效执行者保护；不是分布式 exactly-once。
数据库 fencing 只能约束本库写入，不能撤回已经发生的远程模型调用。
lease 丢失后重新执行 demo 是安全策略，不是所有业务都可重试的证明。
尚无鉴权、多租户、配额、保留期清理和生产压测；未做公网部署。

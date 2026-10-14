# 公开仓库后端交付复核：设计、能力边界与验收

> 本文件保留 fake-only 阶段的历史复核。随后已增加默认关闭的操作员授权路径；
> 最新能力与恢复边界以 `PUBLIC_REPOSITORY_AUTHORIZATION.md` 为准。真实模型仍未调用或验收。

本次复核没有增加业务功能，没有调用付费模型，没有 commit、push 或部署。
开发仍在 `/home/lenovo/projects/LocAgent-public-pipeline`，分支
`work/public-repo-pipeline`；学习目录 `/home/lenovo/projects/LocAgent` 保持原基线。

## 交付的实际能力

现在实现的是：

> 公开 GitHub 仓库链接＋问题 → 持久化任务 → 固定 commit → 后台下载和静态
> 建图/BM25 → fake provider 驱动真实工具 → 保存并查询结果。

**这还不是能真正回答任意问题的语义定位服务。**

`public_pipeline.py:fake_localize` 中的 provider 固定执行三个步骤：

1. 用问题前 200 个字符调用 `search_code_snippets`。
2. 调用 `explore_tree_structure`。
3. 固定调用 `finish(files=[], entities=[])`。

真实图、索引、检索工具、消息轨迹、数据库和 worker 都运行，但 fake 不依据工具
返回作下一步判断。默认迭代预算下，任务 `status=completed`，定位结果是
`result.status=empty`，最终文件和实体列表为空；预算不足三步时可得到
`iteration_limit`。所以“真实仓库＋fake 模型通过”只证明流水线，不证明准确率。
返回诊断明确标记 `provider=fake-only`、`paid_calls=0`、`quality_evaluated=false`。

## 防止意外调用真实模型

- `models.py` 的请求和 options 都采用 `extra='forbid'`。HTTP 传入 `provider`、
  `model`、`api_key`、`api_base`、`allow_paid`，或嵌套 `options.provider`，返回
  422 `invalid_request`，并且不会创建任务。新增测试直接验证 HTTP 响应。
- `worker.py` 对 `github-v1` 硬路由到该 fake 流水线，没有从请求或环境选择 live
  provider 的分支。新增测试将 `LOCAGENT_ALLOW_PAID` 设为 `1` 并使
  `BudgetProvider.from_env` 一旦触达就失败；fake 仍完成，BudgetProvider 未被调用。
- fake 定位在已有 `offline_engine` 网络/模型 guard 内运行。它是额外的防误调用
  保护，不是完整 OS 沙箱。
- 原来的 `prepared-*` 入口仍然存在，并未被本次功能全局禁用；它继续受原有预算和
  授权限制。把本次生成的 offline manifest 提交到旧入口，也不能通过原固定 live
  配置校验。这不意味着整个旧服务的所有入口都变成了 fake-only。

真实 provider 接入还缺一层面向**新公开仓库任务**的授权与执行策略：绑定单题、
接收方和模型；使用新的明确预算授权及调用前持久化预留；在远端结果不明时进入
needs_review，禁止自动重放。当前 github-v1 自动恢复是因为它硬编码为 fake-only。
不能只把 fake 函数换成模型调用，否则可能在崩溃恢复时重复付费。完成这层之后
还需要经父对话确认的单题 smoke 和实际定位质量验收。本轮没有做这两项。

## 设计与边界复核

| 边界 | 实际实现及限制 |
| --- | --- |
| URL/ref | 只允许规范化 `https://github.com/owner/repo`；拒绝用户信息、端口、query、fragment、本地/SSH 地址及参数注入形式。ref 只进入编码后的固定 API 路径，不进入 shell |
| 网络 | 只访问固定 API/codeload 主机；所有 DNS 答案必须是 global 且非 multicast；连接已核验 IP，TLS 校验原主机；不跟随重定向、不继承代理、不使用 Git 协议或令牌 |
| 大小 | 下载/响应 8 MiB、展开 tar 32 MiB、3,000 个 tree/archive 条目、单文件 1 MiB；路径长和深度有限制 |
| 解包 | 拒绝遍历、重复名、链接/特殊成员、子模块与 LFS；逐普通文件核验 Git blob hash；仅写入 `.py`；不运行仓库安装脚本、测试、模块导入或任意项目代码 |
| 解析 | AST 可解析性与节点数检查，再复用现有静态图和 tree-sitter/BM25；Linux 子进程有 CPU/虚拟地址空间/单文件大小/FD 限制，但不是完整沙箱 |
| 下载时间 | 10 秒是 socket 不活动 timeout；60 秒仅是完整 read 之间的检查目标，持续慢流可能超过。实际整个 attempt 的硬限制依赖 worker deadline，默认 90 秒，可设 1–900 秒 |
| 缓存 | key 包含 repo/commit/config/完整 engine hashes；每 key 本机 flock 防重复构建；先建好并校验 manifest，再原子发布 ready；命中时也核对 repo/config/engine/commit/instance/bundle 的完整关联 |
| 问题分离 | 每题独立 manifest 和任务结果，共用同一个不可变索引 bundle；问题变化不要求重建索引 |
| 取消恢复 | progress 写入受 token/attempt/lease/deadline fencing；固定 SHA 同步持久化后才下载。取消/超时由 supervisor 终止 child，等待锁也受 deadline 约束。恢复保留 SHA，不重新追踪移动分支 |

缓存恢复针对进程崩溃和未发布的部分构建。已发布文件损坏时失败关闭，不静默
使用半成品，也不承诺掉电后所有损坏缓存都会自动修复。registry 必须是可信的
本机操作员目录；没有防敌对共享目录的完整隔离，也不是跨机器/NFS 锁。

尚无完整 OS sandbox、cgroup 总资源限制、总缓存配额/淘汰、鉴权、入口 body/admission
限制或多机协调。子进程仍继承用户的文件系统权限；native parser 漏洞风险存在。
这些限制决定本版不适合安全公开部署。

## 本轮发现与修复

独立 reviewer 与主任务分别复现了两处问题，并在原范围内修复：

1. Python `ipaddress.is_global` 对 `224.0.0.1` / IPv6 multicast 可为 true。
   原网络预检查会尝试建立 socket。现显式拒绝 `is_multicast`，测试要求在创建
   socket 前拒绝。TLS 原主机校验仍然存在；这不是已证实的数据外泄。
2. 将 A.ready 指向“同 commit 的 B 仓库”的合法 manifest 时，原检查只对比
   engine/commit，会返回 B 的缓存。现核对完整 repo/config/instance/bundle
   关联；回归用例先建立两个合法缓存再故意串用指针，确认失败关闭。这是可信
   registry 的关联完整性问题，不是公开仓库可直接修改 registry 的远程攻击。

另修正文档：去掉“60 秒最多再加 10 秒”的过强承诺，明确真实 worker deadline
保证。独立 reviewer 已只读确认上述修复和文档正确，未报告本轮范围内的遗留
可复现阻塞。

## 测试数字应如何读取

**不要把历史所有数字相加。**

- 历史 412 项来自 `unittest discover -s tests -p 'test_*.py'`，其中已经包含
  `test_stage2_service.py` 的 13 项，以及当时 `test_public_pipeline.py` 的 9 项。
- 后来独立运行的 public 11 项，是原 9 项加 2 项；本轮 14 项则再加 2 项
  fake/live 契约测试、1 项缓存关联测试。DNS multicast 是已有方法中的新增案例，
  不单独增加 unittest 方法计数。
- 本轮全量最终结果单独记录；它包含当下所有 public 单元测试，再运行 14 项
  只是针对性复测，不能重复算进总数。
- PostgreSQL 生命周期 32 项是另一种匹配模式的集成套件，由 13 项
  `stage2_postgres_acceptance` 继承测试和 19 项生命周期测试组成。这里的 13 项
  不是上面 HTTP/fixture 的 13 项。另有 public PostgreSQL 4 项、prepared 3 项，
  不在 `test_*.py` 全量模式内。
- 真实 GitHub smoke 是一个脚本提交的两个任务（构建 miss、重复问题索引 hit），
  不是额外两项 unittest，也不代表两个问题定位准确。

复核后已通过：**全量 417 项**（319.793 秒，已含当前 public 14 项及原 HTTP/fixture
13 项）；针对性 public 边界 14 项；public PostgreSQL 4 项。真实公开源码复跑
的两个任务均 completed，固定 commit 仍为
`096c8d42545d3b68ea21a4f890fb2b2d8979c0bd`：

- 构建/miss：`c5c6becb-ea15-4915-9248-ef081dd34c6c`。
- 复用/hit：`f4b07b72-041c-4828-8788-4d7d60431a46`。

历史数据库生命周期 32 项、prepared 兼容 3 项的通过记录保持有效；本轮未为
仅触及新 acquisition/cache 的两处修复重复运行这两个旧集成套件。未进行真实
模型或准确率验收。两轮全部命令和原始日志在验收记录与 evidence 目录。

## 学习 demo 是否受影响

原 checkout 的 `git status --short` 在主任务和独立 reviewer 检查时均为空。
原 `locagent-stage2-pg` 仍在 `127.0.0.1:55432`。本轮数据库测试明确连接另一个
容器 `locagent-public-preview-pg` 的 `55439`，使用独立 schema；缓存位于新 worktree
及唯一临时目录。没有读取 `.env`、完整 runtime.json、密钥或历史付费账本；
没有停止、迁移、重配或清空学习 demo。复测仅临时重新启动本任务自己的数据库，
收尾再次停止并保留数据。

核心文件：`locagent_service/public_repo.py`、`public_pipeline.py`、`models.py`、
`api.py`、`store.py`、`worker.py`、`prepare.py`、`migrations/003_public_pipeline.sql`。
完整英文运行说明和首轮历史证据分别保留于 `PUBLIC_REPOSITORY_PREVIEW.md`、
`PUBLIC_REPOSITORY_ACCEPTANCE.md`。本文件可直接复制到父对话，不依赖 C: 链接。

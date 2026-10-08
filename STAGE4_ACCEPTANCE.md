# 第四阶段：固定输入评估与保守预算

## 当前验收结果（2026-10-08）

真实 pilot 已完成，退出码 0：固定一个公开 requests 开发样本，suppress_repeats off/on 各三次模型调用，两组均正常完成且首位命中目标文件与函数。on 真实触发 6 次重复返回折叠，原始内容仍保留。完整 [真实 pilot 报告](outputs/stage4/live-pilot-recovered-20261008/LIVE_PILOT_REPORT.md) 给出逐次 usage、费用公式、轨迹和复现命令。

| 指标 | off | on |
| --- | ---: | ---: |
| 固定样本分母 | 1 | 1 |
| 真实调用数 | 3 | 3 |
| 输入 / 输出 token | 16,880 / 822 | 16,335 / 853 |
| 任务耗时（秒） | 15.626 | 14.755 |
| 模型调用耗时合计（秒） | 6.015 | 6.866 |
| 文件、实体 recall@1 | 均 1 | 均 1 |
| 实际重复折叠次数 | 0 | 6 |

六次共 34,890 token。按官方峰时全部输入按未命中计费估算 ¥0.079830，按返回缓存用量估算 ¥0.03943832；未查询账户账单，不能称为实际扣款。原 ¥20 授权的 ¥18.911232 完整预留继续保留，不退回或重复领取。费用依据见 [官方人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。

仅一个反复使用的开发样本、每组一次；off 先运行且两组检索路径和缓存命中不同。因此不能声称普遍质量提升、稳定 token/费用节省或耗时改善。fixture 字符变化与本次真实指标分开保存。

## 固定来源与隔离

入口从本机 Git 完整 commit 创建 archive 快照，保存样本、图/BM25 配置、引擎和产物 SHA-256；HTTP 仅接受已注册来源 ID。GraphLocalizer 每个任务使用独立进程，保留其全局状态隔离；labels 单独保存，不发给 provider。

样本 psf__requests-3362；仓库 commit 36453b95b13079296776d11b09cab2567ea3e703；SWE-bench_Lite test revision 6ec7bb89b9342f664a54a6e0a6ea6501d3437cc2。图有 1,053 节点、3,595 条边。

本次 source_id：prepared-1ad5a0bfbbdd3a2db8cf3ad8d52aee68526f225b05502d817eeb2a18d85023cc。
批准计划：outputs/stage4/zero-use-recovery-review/plan.json；
SHA-256：30826b12d1b2d4cd8027c416aa22bd3c85f2217f2e91ff12c3dfcf54c643e6c6。

请求 openai/deepseek-v4-flash，返回 deepseek-flash；官方当前映射 V4.1-Flash，是可变 API 别名，不是不可变权重标识。temperature=0，thinking disabled，max_tokens=512，无 SDK 重试，单次60秒，每组三轮/300秒。64KiB 本地输入估算门槛不参与缩减预算预留。

## 费用与恢复边界

每次先持久预留完整 1,048,576 输入 token 与 512 输出 token，按保守 ¥3/M 与 ¥12/M 得 ¥3.151872，六次合计 ¥18.911232。价格确认必须与批准 plan hash 绑定，24小时有效且包含全部收费。计价验证在环境文件加载之前执行。旧 v1 计划仅可离线执行。

账本使用规范绝对路径、稳定锁文件、原子替换和文件/目录 fsync；每组最多三次的额度持久化。固定位置的一次性授权绑定唯一账本、计划和计价确认，复制账本、换目录、相对路径或符号链接不能得到新额度。成功、失败、未知结果均保留完整预留；超时、崩溃和异常停止后续调用，未知付费操作不能自动重放。

首次尝试在 16,023 > 16,000 的本地门槛失败，0请求、0预留，原账本与记录保留。后经独立审查及明确授权，将门槛调整为64KiB，并进行一次针对确切零调用/零预留账本的审计迁移。预算、六次总调用上限不变。迁移后本次实际完成六次调用，授权已经使用，不得重放。恢复审计在 outputs/stage4/authorizations/first-pilot-cny20.json.zero-use-recovery.json。

## 评分和验证

固定分母包含失败、缺失、损坏、超时、异常退出和未执行组，均按零分处理。只评分有效 completed 结果，保留 *.child.json；失败也不丢弃已发生用量。两组本次均 completed/success，第三轮正常 stop，未触达 iteration_limit_reached。

132 项离线回归及独立最终复核通过，覆盖预算预留、价格确认、共享授权、账本路径别名、持久化失败、真实子进程死亡、未知调用禁止重放和单次零消费迁移。证据：
- outputs/stage4/zero-use-recovery-review/offline-tests-final.log
- outputs/independent-zero-recovery-final-20261008/
- outputs/stage4/live-pilot-recovered-20261008/verified-outcome.json
- outputs/stage4/live-pilot-recovered-20261008/budget.json
- outputs/stage4/live-pilot-recovered-20261008/responses/

离线 scripted provider 指标保留在 outputs/stage4/conservative-budget/offline-paired/。其 4,984→2,750 工具消息字符变化不是模型质量或真实 token/费用指标。

## 配置与复现

.env 仅经授权 CLI 正常加载，未显示/复制/修改。--env-file 要求0600普通文件，仅接受允许变量，不插值或执行shell；--live 只启用当前进程，未传时强制禁止付费。API/worker不自动加载.env；Compose不挂载模型密钥。

~~~sh
cd /home/lenovo/projects/LocAgent
sh scripts/check_local.sh
# 使用尚不存在的新目录；不加载 .env，不调用真实模型。
.venv/bin/python -B -m locagent_service.evaluate run \
  --plan outputs/stage4/zero-use-recovery-review/plan.json \
  --labels outputs/stage4/zero-use-recovery-review/labels.json \
  --output outputs/stage4/offline-reproduce-new
~~~

已执行的 live 历史命令只在真实报告中留档，不可重放。更大样本、重复试验与缓存/执行顺序控制需要新的明确预算授权；当前 pilot 没有未完成调用或待重试项。

更新前的完整阶段四文档作为历史保存于 outputs/stage4/live-pilot-recovered-20261008/STAGE4_ACCEPTANCE.before-live-report.md；其中待执行/待复核状态只代表当时进度。

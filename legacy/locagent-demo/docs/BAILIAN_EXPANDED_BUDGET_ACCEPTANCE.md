# 冻结50题：分批预算执行器离线验收

2026-10-16。用户批准范围：实现与离线验证；**没有真实 API 或新增付费授权**。本阶段新增独立预算执行核心和只读 CLI，不修改生产默认、不启动数据库、不 commit/push。旧账本只读核验，未清除 unknown、未重放历史请求。

## 实现与绑定

- `locagent_service/bailian_expanded_runner.py`：标准库本地文件账本、POSIX flock、预留/结算/恢复、显式注入 transport 的离线执行核心。
- `scripts/preview_expanded_budget.py`：默认且仅支持 dry-run，无 HTTP transport、凭据读取或执行参数。
- `scripts/verify_expanded_budget.py`：禁网验收，真实冻结请求体 + 合成响应，拒绝覆盖输出。
- `tests/test_expanded_budget.py`：25项测试，包括7个真实子进程强制退出位置。

固定 manifest SHA256：`78e24794a3e91bd0ba4ae8a54845e360cfd2add3b8b6feb8a49734b3c4ad555b`。加载时检查原 manifest 内容、原 engine 哈希、全部请求体与文本成员一致性。本轮不改变候选、问题、分块、模型、instruct、评分或旧 manifest。原618批、每批最多16输入及请求体哈希全部保留，没有重新分批。

执行绑定包括 manifest/计划/新执行引擎哈希、endpoint、模型、维度、固定费率、单输入最大 token、批次上限和新 cap。调用方保留预期绑定，恢复时逐字节核对 run.json；存盘文件不是授权凭证。请求计划和绑定在进入执行器时复制，调用方后续修改对象不会改变派发数据。

当前 `purpose` 仅接受 `offline-test`；`live` 被拒绝。核心可注入显式 transport，但没有内置网络传输或真实执行 CLI，也不读取 key。未来真实授权需要另行绑定唯一 run 身份/路径和受审查传输入口，不能把可重复的离线测试配置当付费许可。

## 账本与预算规则

每个新 run 使用独立0700目录，文件0600；预算不使用旧 SQLite，不创建数据库服务。账本是编号不可覆盖事件文件，O_EXCL创建、文件 fsync、父目录 fsync；全 run 持有非阻塞 flock，锁文件不删除。只支持本机 POSIX 文件系统；不宣称网络文件系统/分布式锁或对恶意同用户篡改、完整备份回滚的不可伪造审计。

```text
无记录 → reserved（持久预留）→ dispatch（可能发送）
       → raw（正文已持久化 + SHA绑定）→ settled（严格校验后结算）
                    异常/无法判定 → unknown（保留预留并停止）
```

每次派发前重新计算并检查：

`spent + unknown + inflight + 下一批预留 <= 新 run cap`

金额全部采用 Decimal，且由输入数与有效 usage 推导，账本不信任可任意改写的总额。固定价为0.125元/百万输入 token；每输入保守预留131072 token，16输入最大预留 **0.262144元**。不使用 UTF-8经验比例作为硬上限。

成功结算复用严格响应校验器：HTTP200、有效有界 JSON、唯一字段、明确完整索引、1024维有限非零向量、model若返回须匹配；`total_tokens` 必须为正整数（bool/float/string/NaN/Infinity均拒绝），不超过本批输入数×131072，`prompt_tokens` 必须是相等整数。为保守起见0也拒绝。无 usage、超 usage、无效向量等不能当0元；所有此类情况保留全批预留并停止。

按验证 usage ×固定费率结算并释放差额，不依赖经验估计。原始响应正文先在私有目录安全持久化，随后记录 SHA、状态码并通过 journal 链关联请求 hash 和 manifest，再允许结算。原始错误字符串不进入控制台或异常摘要；原始正文可能含服务内容，只作私有证据，不在报告中展示。正文超过4MiB或类型非法不落完整正文，保留预留并停止。

账本编号/链、请求/响应哈希、结算金额与重新验证的 usage 均在恢复时检查。文件缺失、破损、不安全权限或篡改使恢复失败并禁止调用，不尝试修复/清空或重建预算。硬 cap 依赖既有模型长度和固定计费契约；若服务违反该契约并报告超上限 usage，软件只能停机保留占用，不能撤销已经发生的服务端费用，也不宣称能保证供应商行为。

## 崩溃与重启语义

| 窗口 | 重启行为 |
|---|---|
| 预留前 | 无请求记录，可正常开始 |
| 预留后/实际发送前 | 保守转 unknown，占用不释放；即使可能没发送也不自动重试 |
| 发送后/尚未记录 raw 绑定 | unknown，停止、不重发 |
| raw 文件落盘但绑定事件未持久 | unknown；不能凭文件名猜测绑定 |
| raw 与绑定都持久、结算前 | 重新校验正文并结算，不重发 |
| 结算后 | 跳过已结算请求；全部完成后重启零调用 |
| 写入/fsync 失败、半个事件文件 | 当前退出；重启只按持久证据恢复或停机，禁止盲重发 |

unknown 立即阻止新预留。一次仅有一个 inflight。无自动重试、无失败退款、无旧账本迁移。文件锁只防协作进程并发；此实现不等于抗恶意进程的完整沙箱。

## 最终离线验收

独立目录：`outputs/bailian-expanded-budget-offline-20261016-final/`。

- **71项测试通过，0失败/错误**：25项新预算测试、26项原扩展准备/RRF回归、20项已有响应/契约测试。
- 全部 **618个冻结请求体、9864输入** 经假 transport 执行，逐个核对原 body SHA；同一 run 再启动零请求。
- 合成响应每输入固定10 tokens，仅测试结算；账本合成 spent=0.0123300元，unknown/inflight=0。**这不是实际消费，也不是费用预测。**
- 7个真实子进程 os._exit 崩溃点，加写盘失败窗口、竞争锁、cap拒绝零调用、usage类型/缺失/越界、请求/响应/费率/cap/manifest/引擎/结算篡改、权限/符号链接、caller对象修改均覆盖。
- 258份历史保护文件加5份冻结文件，共 **263份哈希未变**；原冻结引擎未变。测试期间 socket 连接被禁用，实际模型请求为0。
- 未运行真实网络/凭据/供应商响应/实际账单验收；没有检索排名或评分。离线通过不能证明真实API端到端已通过。

复现（WSL独立预览工作区，使用新输出目录）：

```sh
cd /home/lenovo/projects/LocAgent-rag-preview
/home/lenovo/projects/LocAgent/.venv/bin/python -B scripts/preview_expanded_budget.py --proposed-cap 2
/home/lenovo/projects/LocAgent/.venv/bin/python -B scripts/verify_expanded_budget.py --out outputs/bailian-budget-recheck-NEW
```

第二条拒绝覆盖已有目录；不要删除历史验收目录后重跑。首次验收目录保留了70项通过记录，最终目录包含后加的调用方修改保护回归，共71项；以最终 audit 的代码哈希为准。

## 建议额度与待确认摘要（尚未授权执行）

建议新 run cap **2元**。这是独立额度，不是旧账本余额；旧已占用1.277952元全部保留，其中 unknown 0.557056元不释放。若未来批准新增2元，则合计可占用上界为 **3.277952元**。本轮只写建议/合成账本，未实际增加旧预算或授权新支出。

2元大于“经验总费约0.193516元 + 最大单批预留0.262144元 ≈ 0.455660元”，因此在经验量级下留有余量；**不保证完成全量**。若实际 settled usage 变高，下一批不足预留时零调用拒绝。与一次性预留161.611776元的差别，是已成功批次按验证 usage 释放差额；没有降低每个在途请求的保守上界。

可提交父对话的真实执行确认摘要：

| 项目 | 固定范围 |
|---|---|
| 数据 | 9仓库固定commit的9814份唯一公开 `path:symbol + 函数源码`（含支持的tests/docs）及50个真实issue标题 |
| 接收方host | `ws-8t0i3jte6m9op4ad.cn-beijing.maas.aliyuncs.com` |
| 模型 | `qwen3.7-text-embedding-flash`，1024维 |
| 接口 | `/api/v1/services/embeddings/text-embedding/text-embedding` |
| 最大请求/批次 | 618请求，每批≤16输入，串行，无自动重试 |
| 价格与建议新cap | 固定0.125元/百万输入token；独立2元，旧占用不抵扣 |
| 停止规则 | 预留不足零调用；超时/错误/usage不合格/超usage/未知状态保留占用并停止；证据损坏拒绝恢复 |
| 续跑 | 仅基于已持久证据恢复，不重发未知或已结算请求；unknown不自动消除 |

Query instruct 保持：`Given a code localization question, retrieve Python code that implements the described behavior.` 不发送issue正文/评论、补丁、gold、私有文件或凭据作为模型输入。新的付费授权还应明确唯一run及批准代码哈希，随后另行启用受审查真实transport；本次交付刻意保留这道执行阻塞。

## 审查边界

本阶段 diff 仅包含新增执行器、dry-run CLI、验收脚本、测试和本文五文件。旧50题准备、冻结文件及旧源代码不改。新代码依赖已有严格响应/请求契约；不应用为脱离当前工作树的独立包。建议先复核预算状态机与崩溃语义，再决定是否授权真实入口与单次运行。未进行 commit、push、部署或真实付费验证。

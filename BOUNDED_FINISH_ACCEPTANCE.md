# Bounded finish 预算耗尽修复：离线验收

2026-10-10，work/locagent-baseline，HEAD 0d5af3eeff0afb73a488c523d407b56e8fde7bda。

## 实现与约束

只修改 util/localization_protocol.py 的 bounded-v1 预算耗尽收尾逻辑；
新增 tests/test_budget_finish.py、本文，并给 tests/README.md 增加入口。
模型、排序、评分、索引、任务配置、付费准入及原暂存内容未改动。

工具页首次无法送达时停止本批后续工具执行，保留成功送达的页。
失败及跳过的每个 tool_call_id 都收到明确“未送达结果”的反馈。
若原有迭代额度与请求门槛允许，下一请求仅提供 finish，并强制 tool_choice=finish。
该请求仍通过原 provider 的次数、完整费用预留、未知结果阻断及请求检查；
没有新增额度或自动重发。无答案、非法 finish、截断或继续要求检索均按原规则失败，
不清洗或修正答案。

24,576 字节总额度内，结束控制固定预留 4,096 字节；开启 candidate_guidance 时，
另同时预留候选指导 4,096 字节，两者相加，不共用同一份预留：

| 候选指导 | 控制预留 | 候选预留 | 修复前工具页额度 | 修复后工具页额度 |
|---|---:|---:|---:|---:|
| 关 | 4,096 | 0 | 24,576 | 20,480 |
| 开 | 4,096 | 4,096 | 20,480 | 16,384 |

工具页额度包含角色、调用ID、页头/页尾及JSON转义，**不是纯源码正文容量**。
候选关/开时，正文的理论上界分别小于20,480/16,384字节；实际可用正文还须扣除
这些包装与转义开销，随内容和调用数量变化，没有统一的净正文最大值。
两种模式均比修复前少4,096字节工具页额度（分别减少16.67%和20%），
因此会更早截断或进入收尾。未用满的预留也不会借回给检索页。
单条工具消息上限仍为8,192字节；请求估算门槛仍为65,536字节。
计量使用含转义、元数据的UTF-8 canonical JSON；“总额度不增加”不意味着正文容量不减少。

控制反馈不进入候选证据观察器或已读来源记录。候选只来自完整送达的可信 span；
隐藏尾页、未送达的执行结果与跳过调用不会变成可见证据。
严格图 ID 验证器、非白名单语义和 GraphLocalizer 进程隔离未改动。

极长调用 ID 导致配对控制消息超限时，返回 tool_budget_exhausted，
closing_blocked_by=control_message_limit，不发下一请求。收尾请求超过估算门槛时，
返回同一耗尽终态、closing_blocked_by=context_limit。费用或次数准入拒绝
继续按既有异常/账本机制传播，不伪装成功，也不隐藏未知结果。

## 离线证据

相关套件 57 项通过，其中新增 12 项：
精确的剩余27字节/最小空包装276字节；指导开/关；批次部分成功和余下跳过；
16个待回答调用配对；仅一次原有剩余轮次收尾；没有剩余迭代；
费用和每臂次数不足时传输前拒绝；UTF-8/JSON转义；请求门槛；
可见/不可见证据隔离；非法/缺失/截断答案；异常不重试。
费用测试使用临时合成账本，拒绝后未新增 reserved/unknown 记录。

另有12个不耗尽场景（指导开/关 × 抑制重复开/关 × 有效/非法/缺失答案），
新旧全部请求参数与完整结果逐字节一致，哈希见 compatibility.json。
完整套件403项全部通过，331.943秒，见 full-v2.log。

测试采用最小环境变量集，真实付费开关为0，没有提供模型凭据。
父进程及Python子进程均阻断网络，dotenv.load_dotenv 被替换为空操作；
配置解析测试只读取自行创建的临时 .env fixture。
独立源码导出不含项目凭据、操作计划、旧账本或索引。
MockTransport、合成响应和本地崩溃测试不构成真实模型评估。

## xarray 保存轨迹回归

只读旧 arm-0005 的两份原始响应、三个工具输出和哈希绑定图。
旧循环所有分页审计与保存结果一致：送达20,453字节，仅剩27字节，
空续页包装需276字节，2次响应后 tool_budget_exhausted。

新循环送达16,315字节检索证据，补219字节工具反馈、274字节结束指令；
指导、证据及控制合计19,846字节。第三次请求仅含finish，估算32,038字节，
调用配对完整，两个此前检索到的目标仍在可见候选中。
第三份回答从送达候选人工构造，只证明收尾链路，不预测真实模型答案。
未重发旧请求、未计算新质量指标、未改写旧失败结果。

## 兼容性与限制

控制预留使接近上限的任务更早截断或进入收尾，这是明确行为变化。
4 KiB控制预留覆盖测试中的16个常规调用；任意长元数据仍可能合法终止任务。
已覆盖的不耗尽场景逐字节一致，不能扩大为所有任务行为等价。

旧冻结计划的运行时代码哈希现在预期不匹配；保持原文件，不重绑或恢复旧账本。
旧实验仍为59次结算、费用上界0.841358元、reserved=0、complete、active_run=null；
xarray指导开旧结果仍按原规则失败计零。
修复没有真实付费验证；交付后独立review，任何新真实验证需另定代码绑定与预算授权。
不得用此次回归宣称召回率、token、费用或速度提升。

## 文件与复现

证据根目录：outputs/bounded-finish-repair-20261010/

- source-before/、source-before-hashes.json：修改前199个可见源码文件。
- protected-index.patch、before-working.patch、before-status.txt：原Git基线。
- tested-export/、tested-source-hashes.json：完整套件的独立源码导出。
- targeted-v4.log、full-v2.log：相关与全套测试；full-offline.log保留首轮运行器冲突。
- xarray-boundary.json、xarray-closing-request.json：保存轨迹回归及收尾请求。
- compatibility.json：12个非耗尽场景的逐字节兼容性证据。
- history-before.json、preservation.json：旧账本、响应、结果、控制文件及历史哈希复核。
- 初期失败的夹具/审计日志保留；未触发网络调用或修改旧实验。

WSL仓库根目录运行相关测试：

~~~bash
env -i HOME=/home/lenovo PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 \
  LOCAGENT_ALLOW_PAID=0 PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 \
  LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
  PYTHONPATH="$PWD/outputs/bounded-finish-repair-20261010/offline-guard" \
  .venv/bin/python -B outputs/bounded-finish-repair-20261010/run_offline.py "$PWD" \
  test_budget_finish test_bounded_protocol test_candidate_guidance
~~~

完整测试将末尾三个模块名替换为 'test_*.py'。相同环境前缀下运行
replay_xarray_boundary.py 或 check_compatibility.py 可复现只读回归；
verify_preservation.py 可复查历史与暂存补丁。此目录不是付费执行入口。

全部本次修改保持未暂存；没有commit、push、公开部署或数据库操作。

## 验收过程中的修正

最初将全套套在 offline_engine 的模型替换层，导致已有SDK超时测试在进入其HTTP拦截器前
被替换，因此首轮403项中1项失败。随后移除运行器多余的模型替换，保留父/子进程
socket阻断、dotenv禁用及各测试自身的保护。该SDK测试独立复验1项通过，未发生网络传输。
精确分页夹具曾未考虑页尾包装与换行回退，已改为真实换行边界；
保存轨迹审计曾将等价字典按顺序比较，已改为AST字面量语义比较。
这些都是离线夹具/验收脚本修正，未改变产品实现或历史数据。

## 最终验收记录

完整离线套件403项全部通过（331.943秒）；相关套件57项通过（8.188秒）。
保护校验覆盖本次33,488个历史文件条目、旧清单8,254个条目及197个源码快照条目；
不同清单可能存在重叠，不将它们相加宣称独立文件数。
原暂存补丁与前次准备阶段快照逐字节一致，对应原受保护树
79148ecc013310e58d6780972feb94182b6b3a2d。
本次仅改动两个已有文件，新增两个文件；此前其余源码修改全部保留。
实际运行的Python代码与测试导出哈希一致。

最终旧账本SHA-256：
6cb2bf31c13fc314e1b7afba6c0421063c0adf8d9a3d4e5c356b56ace01d58ff。
新增真实模型调用0。交付进入独立review，未做真实质量复测。

## 独立review后的测试精度修正

review发现合成夹具曾用字面反斜杠加n手写页头/页尾，再据此凑出276字节；
相同调用ID经真实换行协议序列化实际为273字节。因此旧合成测试仅证明经过同一耗尽分支，
不能单凭它声称精确276字节。此问题不影响独立的真实xarray保存轨迹复现。

现改为通过实际 ToolPages.page 生成空包装，使用 wraps 包装原 encoded 序列化器捕获
首次预算检查的真实消息；断言实际UTF-8 JSON为276字节、解码正文有3个真实换行且无
字面反斜杠n。两种指导模式仍独立断言剩余额为27字节。
运行逻辑、旧测试日志、历史回归证据及403项全套记录均未修改；57项相关测试与403项全套均为此前运行结果，
本次只重跑受影响测试，结果另存 outputs/bounded-finish-fixture-review-20261010/。

本次受影响模块12项离线测试全部通过（4.684秒），见 affected-tests.log；未重跑全套。
运行逻辑、历史证据与原暂存内容通过哈希核对，修改只涉及测试和本文，仍未暂存。

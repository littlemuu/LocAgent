# 预算适配独立只读复核

日期：2026-10-16。复核基准执行器 SHA256：`9010da1154ca97326578296f5f9d78b8a0e8bc447ad00e68029856073187c998`。

结论：**单目录离线状态机复核通过；不批准直接晋升真实付费入口。存在两项上线前阻塞。** 本次仅重新阅读实现、测试和官方接口文档，未修改执行代码、重跑付费请求、启用 transport 或新增执行授权。先前71项离线通过和618批合成验证是已有证据，不冒充本轮新执行结果。

## 阻塞发现

### R1 / P1：执行核心的 manifest 标识不是强制数据来源约束

位置：`locagent_service/bailian_expanded_runner.py:104`、`:121`、`:316`。

`execute` 只调用 `checked_plan`，它接受1到618批任意符合模型请求形状的数据；`approval` 对传入计划计算hash并写入固定 MANIFEST_SHA。调用者可不经过 `load_plan`，传任意文本/子集并生成匹配binding。已有小样本单测就是这条通路的直接证据。冻结manifest和body hash本身没有错，但“binding里写了固定manifest hash”不证明计划确实来自该manifest。

当前dry-run入口通过`preview → load_plan`正确校验，且核心标注为offline-test，所以没有现存真实泄露事件。阻塞的是未来将这个核心直接接HTTP时的数据范围保证。应由唯一真实入口内部加载并验证固定manifest，重建并核对完整618批及9864成员，不能接受调用者随意提交一个自签式binding。测试计划应走明确隔离的测试接口，不与授权入口混用。

### R2 / P1：缺少唯一授权run绑定，换目录可重置单目录cap与锁域

位置：`locagent_service/bailian_expanded_runner.py:104`、`:168`、`:197`、`:325`。

cap来自调用者传入的binding，`approval`又接受任意合法cap；run.json只防同目录重启时更改binding。binding没有run ID或唯一输出路径，也没有授权的单次消费注册。将相同计划和binding传入两个新目录，会各有独立空账本和锁；同目录防重发/并发测试无法约束跨目录总支出。重新生成更高cap的binding并使用新目录也不会被当前offline核心拒绝。

这是已文档化“需未来唯一run授权入口”的实质缺口，不能把现在的2元参数视为不可绕过的批准额度。真实入口需绑定明确批准的run ID、规范化唯一路径、cap、模型host、manifest和代码hash，并确保不能通过新目录复制同一次授权或建立并行预算域。禁止遇unknown后换目录重跑。这里不是要求防御掌握本机账号且可任意改代码的攻击者，而是防止正常脚本组合/恢复命令误建新run绕过额度。

## 传输边界：未实现、不可推断已通过

`execute`接收任意Python callable。`purpose='offline-test'`只是元数据约束，本身不阻止传入的callable联网；测试中的socket禁用是验收脚本提供的。代码把固定host交给callable，不证明callable实际使用该host、校验TLS、拒绝重定向、无内部重试、有限超时/读取上限或不改写请求体。当前没有内置HTTP adapter，CLI也没有execute选项，因此保持现状不会自行发请求。

未来应单独审查transport并禁止任意生产注入；确认一次core调用只对应一次HTTP请求，原始响应字节不被SDK重组，HTTP status真实传递。既有上限4MiB在返回后检查，不等于尚不存在的transport已有流式读取上限。缺少这一层时，不可宣称供应商usage已获真实性认证；SHA仅证明收到的字节后续未变，不证明来源可信。

## 复核通过的部分

- `reserved`持久化完成后才写dispatch并调用transport；在同一目录持有flock并拒绝并发。
- 原始正文先以0600/O_EXCL写入、fsync文件和目录，再写绑定事件，随后才可settle。raw hash经journal链关联请求与binding，恢复时重新验证正文及usage。
- 金额使用Decimal；usage要求正整数、prompt与total一致、总量≤本批输入数×131072；bool、字符串、浮点、缺失usage、无效向量/HTTP错误均不能结算为0。
- spent按验证tokens乘固定费率推导。预留前检查spent+unknown+inflight+next≤cap；未知占用不退款，unknown阻止后续派发。
- reserve/dispatch及孤立raw文件窗口恢复保守转unknown，不自动重发；已有raw绑定可无发送地校验结算；settled跳过。磁盘错误/半文件恢复拒绝而非清账。未发现正常持久化崩溃路径重复派发。
- 同目录cap、费率、请求、raw和结算记录篡改能拒绝恢复；此保证不扩展到整个目录被删除/回滚、跨目录重复授权或恶意同用户重写全部证据。
- 原旧账本没有被导入可花费余额或修改；旧unknown仍在原证据里占用。本轮不修改任何账本。

## 假响应是否掩盖真实契约问题

重新检查[官方同步API说明](https://help.aliyun.com/en/model-studio/text-embedding-synchronous-api)：Flash原生响应示例使用`output.embeddings[].text_index`，并返回`usage.prompt_tokens`和`usage.total_tokens`；示例没有model字段。因此现有验证器允许model缺省、要求出现时精确匹配，以及要求两个usage整数，与所查Flash文档形状一致。官方其他embedding模型或OpenAI兼容接口形状不同，不能混用。

已有`test_bailian_response.py`专门覆盖官方形状（向量仍为合成1024维），不仅是新fake的最简包络。未发现“Flash官方必缺prompt_tokens而导致永远失败”这类确定不兼容。文档中的输出参数适用模型说明并不完全统一，冻结请求里的dimension/output_type/instruct实际接受行为仍需未来经明确授权的真实验证，不能由本轮fake证明。

fake固定每输入10 tokens且向量为单位向量，不能验证真实token计费、429/认证、网络中断、服务SDK隐式重试、服务端模型身份、真实响应大小或数据接收方。这些不确定情况若返回到当前校验器，应保守占用并停止；不能为通过真实测试而删除usage或索引检查。

## 完整确认摘要：仅建议、尚未创建真实run或授权

| 项目 | 建议固定值 |
|---|---|
| 唯一建议run ID | `bailian-expanded50-78e24794-cap2-20261016-r01` |
| 文档输入 | 9个公开仓库固定commit，9814份唯一path:symbol+函数源码，含支持的tests/docs |
| 查询输入 | 50个真实公开issue标题 |
| 请求 | 最多618个，单批最多16输入，串行，无自动重试 |
| 接收host | `ws-8t0i3jte6m9op4ad.cn-beijing.maas.aliyuncs.com` |
| 接口path | `/api/v1/services/embeddings/text-embedding/text-embedding` |
| 模型 | `qwen3.7-text-embedding-flash`，1024维 |
| manifest | `78e24794a3e91bd0ba4ae8a54845e360cfd2add3b8b6feb8a49734b3c4ad555b` |
| 独立新增cap | 2元；不是旧余额，不保证全量能完成 |
| 原占用 | 1.277952元保持，其中unknown 0.557056元不释放；若未来批准新2元，合计占用上界3.277952元 |
| 单批保守预留 | 最多0.262144元，131072 tokens/输入×0.125元/百万tokens |
| 失败规则 | 请求超时/错误/不可信usage/超usage立即保留占用并停止，无自动重试；不足预留时零调用拒绝 |

query instruct保持：`Given a code localization question, retrieve Python code that implements the described behavior.` 不发送issue正文/评论、补丁、gold或私有文件作为模型输入。

**目前没有真实调用授权。R1/R2和transport集成审查完成前，不应向用户提出“现在可以直接开始618次真实调用”的通过结论；CLI继续dry-run。** 本建议run ID尚未由执行器强制绑定，不是已生效控制。若后续修复，应新增绕过load_plan、跨目录/跨cap/并发重复run等负向测试，并保留现有冻结及旧账本原字节。

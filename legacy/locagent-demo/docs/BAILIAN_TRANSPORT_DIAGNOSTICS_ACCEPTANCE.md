# 离线传输诊断修复验收

2026-10-15，批准 `Sentinel_fc06bc3dacc88191b4ff16d6849e4a07`。独立 preview 工作区；本轮没有新网络/模型请求、重试、凭据读取、服务、迁移、commit 或 push。结束后暂停真实调用。

## 改动

- 新增 `locagent_service/bailian_transport_diagnostics.py`：真实 exchange 委托的固定诊断包装。阶段仅允许 setup、dns、tcp_connect、tls、request_send、response_headers、response_body、body_check、cleanup、unknown。分类仅允许整体超时、操作超时、DNS、TLS/证书、连接、HTTP 协议、中断、密钥字面回显与 unknown 等固定枚举。不保存异常原文、异常类任意名称、URL、请求头或凭据。
- `locagent_service/bailian_live.py`：Journal 在失败后保存 `transport-NNN.json`，绑定 manifest/request 哈希；账本诊断保存固定阶段/分类。已确认的 HTTP 状态在 body 读取失败时仍保留。无迁移或预算规则改动。新模块纳入 engine 哈希，历史 manifest 不改。
- `locagent_service/public_repo.py`：连接建立失败时，socket.close 再失败只设置布尔清理失败标记，不覆盖原始异常；共享下载路径回归通过。
- 新增 `tests/test_bailian_transport_diagnostics.py`，调整原超时包装断言以符合固定诊断异常。

主异常与清理异常分开记录；连接关闭、定时器取消和信号处理器恢复分别执行，不让一个清理失败阻断其他清理。若仅清理失败且完整 body 已读取，Journal 仍先原子留存 body 和哈希绑定，随后保持 unknown/停止，不把它自动结算为成功。

原 socket 15 秒、整体定时器 60 秒、一次发送、不重试的策略不变。原始 body 先留存、严格 index/text_index、维度/usage 校验与失败即停仍保留。

## 诊断示例（合成注入，不是旧失败的补造结果）

```json
{
  "stage": "response_body",
  "category": "operation_timeout",
  "http_status": 200,
  "request_method_entered": true,
  "response_headers_received": true,
  "complete_body_available": false,
  "cleanup_failed": true,
  "cleanup_categories": ["unknown"]
}
```

`request_method_entered` 只表示进入客户端 request 方法，不能证明请求字节已发送或服务端收到。阶段是最后观测到的执行阶段，不是根因判定。`operation_timeout` 不表示服务端故障或确定未发送。未知异常归为 unknown。完整 body 可用也不同于已成功持久化，持久化仍由既有原子留存与失败关闭逻辑管理。

## 验证

最终 **104 项测试全部通过，7.080 秒**：86 项 Bailian 测试（含 11 项新增）以及 18 项公开仓库/下载诊断回归。网络连接在测试进程中禁用；通过注入真实 PinnedHTTPS.connect → exchange → Journal 链验证 DNS、TCP、TLS、发送、响应头、body 阶段。覆盖各阶段超时、实际整体报警处理器、读到响应头后 body 失败、socket/连接/定时器清理失败、完整 body 后清理失败、主异常优先、未知分类及敏感字符串不进入诊断。

执行命令使用原虚拟环境运行交付目录的 `verify_bailian_transport_diagnostics.py`，测试模式为 `test_bailian*.py`、`test_public_pipeline.py`、`test_download_diagnostics.py`。未运行数据库集成、全项目回归或新的真实网络验收。

证据目录 `outputs/bailian-transport-diagnostics-offline/` 包含 tests.log、verification.json、protected-before.json、protected-after.json 和 implementation.diff。全部四个历史实验目录、外部 manifest/锁及原学习区 README 的保护哈希前后相同。

历史口径仍为 **5 次传输入口调用、4 份 HTTP 响应证据**；unknown **CNY 0.557056**，总保守占用 **CNY 0.589824**。历史账本和失败记录没有改写或释放预留。

## 无法追溯恢复的事实

旧 A 对照失败的具体异常类型、阶段、是否收到响应头、是否发送或被提供商接收/计费，没有已保存证据。新诊断只作用于未来获批执行，不能反推出旧根因。原两个批量请求缺失的完整原始字节也无法恢复。旧映射验证仍未完成；未经新的批准不恢复付费请求。

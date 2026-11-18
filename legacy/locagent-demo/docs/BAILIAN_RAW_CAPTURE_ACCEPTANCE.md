# Bailian 原始响应留存：离线验收

日期：2026-10-15。工作区 `/home/lenovo/projects/LocAgent-rag-preview`，分支 `work/rag-offline-preview`，基线 `290c965a3321dd90d4e848dd924e3134ef10fc8c`。本阶段没有网络或模型请求、服务启动、提交或推送。

## 改动

- `locagent_service/bailian_raw_artifact.py`：在 JSON 解析、字段投影、响应契约验证之前保存完整收到的响应 body 字节。临时文件写入并 fsync，再用同目录 hard link 原子发布，禁止覆盖已有目标，随后 fsync 目录。目录要求当前用户所有、无组/其他用户权限，文件为 0600。
- `response-NNN.body.bin` 保存原始字节；`response-NNN.binding.json` 绑定请求序号、manifest SHA256、请求 SHA256、响应 SHA256、字节数、HTTP 状态，以及存在时的安全 request_id/其哈希。未知字段、额外 index、空白与数字原始写法都保留在 body 中。
- `locagent_service/bailian_live.py`：留存后将响应 SHA256/HTTP 状态写入原预留账本行，之后才生成派生副本和校验。失败仍置 unknown 并停止；无法留存时使用 `raw_capture_unavailable:*` 固定诊断。新增模块纳入 engine 哈希；没有放宽原 manifest 或映射校验。
- `tests/test_bailian_raw_artifact.py`：新增 10 项离线测试。

原始 body 与绑定文件分别原子发布，不是跨文件/SQLite 的原子事务。中断可能只留下 body，账本保持 unknown，禁止自动重试。传输未返回完整 body、超过读取限制、无法持久化时不宣称已获得完整证据。该机制针对受信任本机目录，不构成对恶意本机写入者的完整防护。

接口不接收或保存请求头、Authorization。真实传输层在返回 body 前检查实际密钥的字面回显并停止，不写入该 body；这不保证识别任意编码的密钥回显。原始响应只留在本机私有目录，不在报告中输出完整 body。

## 验证

运行方式：在项目虚拟环境中运行 `unittest.defaultTestLoader.discover('tests', pattern='test_bailian*.py')`，同时将 `socket.socket.connect` 和 `socket.create_connection` 替换为禁止网络的函数。完整命令见工作区外的 `install_bailian_raw_capture.py`。

结果：**63 tests，1.485s，OK**。新增覆盖额外 index/未知字段字节精确保留、非 JSON、禁止覆盖、发布前 fsync 中断、解析前已经落盘、缺 text_index 的失败响应与账本哈希关联、磁盘失败后关闭且不重试、传输中断、目录权限拒绝和合成密钥回显拒绝。包含 SHA256 独立重算与权限断言。

证据：`outputs/bailian-raw-capture-offline/tests.log`、`before.json`、`after.json`。两次旧实验目录中的文件、原 manifest 和外部锁标记逐文件 SHA256 前后相同。已有 53 项 Bailian 测试与新增 10 项一起通过。此次未重跑原有 142 项业务回归、真实数据库测试或真实模型测试；本阶段未修改这些路径。

## 历史账本与限制

第一次与显式恢复各保留 CNY 0.262144 unknown，累计 **CNY 0.524288**，没有释放或重置。原始响应已在旧流程中丢失，本修复不能追溯恢复；第二次的 safe.json 仍是有损副本。旧证据不回填、不重写。新代码使旧 engine 哈希不再匹配，不能据此重用旧授权运行。

## 后续单输入诊断预算方案（仅规划，未执行）

在原 CNY 1 总上限内，仅选择此前已批准公开源码中的一个 chunk，最多一次请求、无重试、无 query 或生成请求，不继续剩余批次。沿用冻结费率 CNY 0.125/百万 token 和每输入 131072 token 的保守预留：新增上界 **CNY 0.016384**，连同旧 unknown 共 **CNY 0.540672**，剩余 **CNY 0.459328**。这只是按既定费率计算的上界，不是提供商账单。

执行前仍需父对话确认单题/单输入、数据接收方、模型和预算，并建立绑定两份历史账本及当前 engine 的独立新 manifest/一次性授权。现有恢复授权不可复用。一次响应无论成功失败都停止，先验证完整原始证据及哈希，再只报告结构与类型。单输入并不自动授权忽略 text_index 或推断多输入映射；任何契约调整另行基于原始响应和文档评审。

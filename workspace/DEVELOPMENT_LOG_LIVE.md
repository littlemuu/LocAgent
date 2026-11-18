
## 2026-11-12 UTC｜锁定的真实传输、一次性授权与离线验收

- 接续 OpenHands 只读 Agent，不替换旧 harness、检索、评测或账本。工作目录 `/Users/xiaomu/Documents/Codex/2026-11-12/task`。
- 新增 `authority.py`、`live_transport.py`、`transport_worker.py`、`live_session.py`、`live_run.py`；SDK 同一循环接入真实传输分支，默认锁定。方案/代码/源码/依赖/引擎绑定；24 小时授权、一次领取、固定账本、每个请求一次传输票据。
- 每次先提交 SQLite FULL 预留，再传输，原始响应先落盘再结算；未知请求保留全额、不重试。HTTP helper 固定官方端点、禁代理继承/重定向/重试、60 秒总时限；两组独立进程，父管道存活检查及取消清理。
- 密钥仅在未来获授权后的本地隐藏终端输入，内存/匿名管道传递；不从环境或文件读取，不进入 SDK/模型正文/账本。当前没有读取、保存真实密钥或发起付费请求，也没有创建本方案真实 grant。
- 官方价格复核：deepseek-flash（DeepSeek-V4.1-Flash-1017），高峰 cache-miss 输入 ¥2/百万、输出 ¥8/百万；每次最保守 ¥2.105344，8 次 ¥16.842752，拟授权 ¥17。账户币种/全包价未核实，须用户确认。
- 新增 15 项测试，SDK/预算/授权 40/40 + 核心/真实 LocAgent 26/26 = 66/66。真实传输分支全部用模拟 helper/MockTransport 验收，没有网络付费调用。首次 6 项因时间取值差导致期限多出微秒被拒；统一时间后通过，失败记录保留。
- `verification/deepseek-preparation-v2`：两组各 2 次模拟 HTTP、4 条 settled，完整 SDK + 真实 LocAgent 检索完成，网络尝试 0；¥0.0112 仅虚构 usage 核算。v1 证据未覆盖。
- 新方案 hash：`7f03d3dd6d1c39a47ac401f294ed95273d8caf52a65ca3823f17328b4a2a916f`。精确范围、发送内容、运行命令和限制见 `LIVE_PILOT.md`。
- 仍待：用户对该方案和人民币账户价格明确批准、本地安全输入 key、第一条真实供应商回包验收。没有改前后端或安全设置，无 Git 提交/推送。旧基础组 15 题未终答结果不用于性能优劣结论。

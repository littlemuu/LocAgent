
## 2026-11-12 UTC｜OpenHands + DeepSeek 真实调用准备与前后端复用审查

**本轮范围**：用户确认先准备真实调用，再考虑接回页面。只做免费开发/离线验收，不修改现有服务、
安全设置、旧实验、旧账本或已消费授权。没有读取真实 API key 或发起付费请求。

**实现**：独立 SQLite 持久预算账本，FULL 事务先提交 reservation 与原始请求；回包先持久化再核验
原始 usage/model，最后结算。每 arm 一次 claim、全局/每臂次数与金额限制，复制路径/状态损坏拒绝。
超时、断流、非 200、未知 model/usage、进程退出或落盘失败均保留未结算预留并禁止自动重试。
协议错误若发生在有效 usage 结算后，保留已知费用并 halt。计费全用整数 micro-CNY。

新增 OpenHands→DeepSeek Chat Completions 序列化/响应适配；只发送文字、固定 deepseek-flash
与官方 endpoint、非思考/非流式，最后一轮强制 finish，拒绝无配对工具结果/坏 JSON/异常整数。
当前 transport 仅接受 httpx.MockTransport，真实入口仍无条件拒绝；未制造任何真实授权。

**实际验证**：SDK/预算最终 25/25（原 SDK 7 + 新增18），原核心/LocAgent 回归26/26。
新增真实子进程在 reservation commit 后 os._exit(17) 验证重开账本仍阻止续跑；HTTP 模拟断流保留
原始前缀；并发只有一个 in-flight；8 次最大 usage 为16.842752元、低于17元停止线。
完整双组预算仿真各2次请求、共4条 settled，待核对预留0，network_attempts=0；真实调用/费用0。
仿真账本0.0112元来自人为固定1000/100 token，只是模拟核算，非真实费用或费用预测。

**排错**：首轮新增15项因macOS /var→/private/var临时路径别名被canonical校验拒绝；只修正测试
夹具resolve，未放宽生产边界。初轮失败日志保留。原旧引擎仍未修改。

**可批准方案**：一个自写greeting/farewell样例，不带评测gold；同一SDK两臂各最多4次，总8次；
deepseek-flash，输出1024、源码正文14336字节。2026-11-12官方人民币高峰价输入全miss2元/百万、
输出8元/百万，完整1,048,576上下文保守预留2.105344元/次，总停止线17元。需要新用户批准及账户
计价确认，旧授权不继承。真实授权领取/网络入口尚未启用；批准后仍须接入消费一次的批准标记，
不能把本次simulation.sqlite当作真实可用授权。

**前后端**：已只读审查local_web.py/local.py/local_web_assets/app.js和异步api/store/worker。
建议优先复用本地页面的计划、轮询、结果、源码、轨迹和费用组件；后端增加白名单SDK执行器及
SQLite→accounting、SDK event→messages投影。保留Host/Origin/session/CSP/密钥及paid开关。
未启动网页、PostgreSQL或改schema；不是“已经接回页面”。

**证据**：[真实调用准备](../2026-11-12/task/REAL_CALL_PREPARATION.md)、
[前后端建议](../2026-11-12/task/FRONTEND_BACKEND_INTEGRATION.md)、
[25项测试](../2026-11-12/task/verification/preparation-tests-final.log)、
[26项回归](../2026-11-12/task/verification/core-regression-after-prep.log)、
[冻结proposal](../2026-11-12/task/verification/deepseek-preparation-v1/proposal.json)、
[仿真账本汇总](../2026-11-12/task/verification/deepseek-preparation-v1/budget-summary.json)。

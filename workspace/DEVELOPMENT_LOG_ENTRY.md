
## 2026-11-12 UTC｜只读工具独立化，并验证 OpenHands SDK 底座

**方向**：本轮先参考 learn-claude-code 的最小循环建立只读工具和离线回归；用户随后明确选择
OpenHands Software Agent SDK，已保留现有工作并把 SDK 1.62.0 作为优先底座。新工作在
`/Users/xiaomu/Documents/Codex/2026-11-12/task`，未改旧生产 harness、实验输入、结果或账本。

**实现**：显式白名单源码快照、列表/字面搜索/分页读取、独立 LocAgent 精确实体与 module BM25
检索接口；两个环境通过受限 JSON 本地进程接口连接，检索端恢复全局状态，静态分析临时副本。
OpenHands 原生工具接入后，实际 Agent/LocalConversation 负责同一循环、工具分派、事件和 finish。
两组只有检索工具开关不同；相同提示、源码与预算。每 case/arm 新进程、新会话，不续用旧轨迹。
预算关闭后保留 finish；不存在有效终答、请求越界或协议错误记失败，不自动增加轮次。

**环境**：官方 openhands-sdk 1.62.0 和共 134 个解析 wheel 固定版本/哈希，仅安装到本任务的
`.venv-openhands`（约 443 MB）。未升级原 LocAgent venv，未安装源码构建包或运行陌生仓库脚本。
SDK/import/API 源码先静态检查；原项目没有适用 AGENTS.md，CONTRIBUTING 是占位模板，未执行其中安装建议。

**实际验证**：核心及真实 LocAgent 集成 26/26，SDK 7/7。真实 SDK 双组离线样例都
completed/finished，各 2 次脚本响应；基础工具 77 字节，检索工具 852 字节，均在相同 14336
字节上限内。两臂 contract 只在 retrieval 与 script_hash 不同。父进程网络尝试 0，成功子进程
通过离线 guard；真实模型调用和费用均为 0。旧引擎 145 个行为文件运行前后哈希不变。

**排错**：初次 SDK Conversation 工厂不接受 profile_store_dir，失败记录保留；已使用该版本的
LocalConversation。官方在线 custom-tool 文档与 wheel registry 对工厂函数支持不一致，采用
已实测的绑定工具实例注册方式。没有把协议夹具成功计作模型定位效果。

**限制/下一步**：当前只实现只读和离线 SDK 验收；corpus BM25、图邻接探索、写代码和跑待测仓库
测试尚未开放。真实供应商接入前须将旧 durable reservation/未知请求处理适配至 SDK 调用边界，
明确模型、题目、定价与金额上限后另获授权；SDK 自带费用统计不能代替预留账本。
旧第二阶段基础组 15 题收尾缺陷继续保留作诊断，不能据旧分数声称 harness 更强或更弱。

**证据**：[完整说明](../2026-11-12/task/README.md)、
[核心/LocAgent 测试](../2026-11-12/task/verification/final-tests.log)、
[SDK 测试](../2026-11-12/task/verification/openhands-tests-v1.log)、
[基础组](../2026-11-12/task/verification/openhands-baseline-v2/result.json)、
[检索组](../2026-11-12/task/verification/openhands-retrieval-v1/result.json)、
[固定安装依赖](../2026-11-12/task/requirements-openhands.lock)。
当前工作区无 Git，不宣称提交或推送。

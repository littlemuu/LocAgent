# dev24 C(v8.2) 完整运行与 v5 A/B 配对比较

本次只运行 C(v8.2) 一次；A/B 直接复用已有 v5 结果。dev24 仅作开发参考，不作最终效果结论。C 与 A/B 非同时运行，存在批次间模型服务、采样、缓存与时段波动；无随机交错，不能据这次差值单独作因果归因。

## 冻结、运行与清理

C binding：`031e6a4265add240659f2900d33b75659e13f0b356b35b764fd9df618c835db7`；B 核心：`a02c0341ebddeba3718d9d4a00e8485e35a62944f088cac982f6c817b7160036`。开跑前本地与云端哈希均通过。Coding Agent/40次预算、stuck_detection=False、SDK 1.62.0、harness 3.0.0及其冻结提交均沿用 v5；没有修改任何冻结件。

资源口径沿用 v5：编码容器6CPU/6GiB/network=none；v5 harness 包装实际未生效，观测为Memory=0、NanoCpus=0、network=bridge，继续使用专用16核64GiB主机单路评测，未修复或改变这一配置。实际运行资源见 [资源观测](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/evidence/resource-observations.jsonl)。

原题序、单路、零外部自动重试。启动时保留18个任务镜像缓存；本轮实际缓存命中18题，镜像检查/下载累计328.9秒。镜像缓存继续保留。

资金控制：起初按15元保守总上限运行；随后用户明确指示“取消API预算门槛，跑完再停”。在第14题独立harness已完成且无进行中API请求的边界保存结果并交接外层控制器，从第15题接续；前14题未重跑，冻结件未修改。其后取消总费用门槛，仅保留原定位4次、编码40次、单路和失败不自动重试约束。交接期间的等待包含在整轮自然耗时中，不计入各题阶段累计耗时。[预算修订授权](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/authorization-amendment.json)；[控制器交接凭据](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/evidence/handoff/receipt.json)
[初始授权](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/authorization.json)；[开机确认](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/authorization-confirmation.json)；[云端预检](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/evidence/remote-preflight.json)

## A/B/C 汇总

| 组 | completed | resolved | 未评分 | 空补丁 | 首次编辑中位数 | 输入token | 输出token | 总token | API计量估算/元 | 保守上界/元 | 累计耗时/秒 |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| A | 24/24 | 10/24已评分 | 0 | 7/24（29.17%） | 5 | 6,523,115 | 78,977 | 6,602,092 | 1.391490 | 13.678046 | 2822.27 |
| B | 24/24 | 11/24已评分 | 0 | 2/24（8.33%） | 3.0 | 4,630,982 | 97,061 | 4,728,043 | 1.475332 | 10.038452 | 3303.58 |
| C | 24/24 | 15/24已评分 | 0 | 4/24（16.67%） | 4.0 | 6,977,198 | 132,303 | 7,109,501 | 1.336774 | 15.012820 | 3562.64 |

B/C token、请求、费用及耗时均含定位；A不含定位。耗时列为各题定位+编码+harness之和，不含镜像下载。第14题控制器交接时的评测结束时间取原 evaluation.json 写入时间；交接等待仅计入整轮自然耗时。首次编辑从1计数，只在发生过源码编辑的题中取中位数；未编辑不填0或40。空补丁依据最终diff，分母仅为实际有编码记录的题，未运行不冒充空补丁。未评分不计作resolved=False，配对检验仅用评分齐全的题。

C整轮自然耗时（含镜像与编排）4074.88秒。费用是usage/cache/请求时间推算，未核对账户账单、不含云计算/云盘/网络费用；A/B历史计量值原样保留。C晚间适用空闲价，不能把低费用直接解释为token效率提升。价格来源：[DeepSeek官方模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。

## 配对不一致与 McNemar

### C_vs_B

完整配对 24；双方resolved 10；双方未resolved 8。

- C resolved、对方未resolved（5）：astropy__astropy-12907、django__django-13158、scikit-learn__scikit-learn-14087、matplotlib__matplotlib-25332、django__django-13964
- C未resolved、对方resolved（1）：sympy__sympy-18698
- 未评分排除：无
- McNemar精确双侧 p = 0.21875

### C_vs_A

完整配对 24；双方resolved 10；双方未resolved 9。

- C resolved、对方未resolved（5）：django__django-13033、django__django-13158、scikit-learn__scikit-learn-14087、matplotlib__matplotlib-25332、django__django-13925
- C未resolved、对方resolved（0）：无
- 未评分排除：无
- McNemar精确双侧 p = 0.0625

按不一致对上的 Binomial(n,0.5) 精确双侧尾概率计算；没有连续性校正或渐近近似。

## 披露分组

| 分组 | 题数 | 已评分 | resolved | 已评分中resolved率 |
|---|---:|---:|---:|---:|
| 有披露 | 15 | 15 | 8 | 53.33% |
| 无披露 | 9 | 9 | 7 | 77.78% |
| 定位未交付 | 0 | 0 | 0 | 无此类题 |

定位全回退0题；validator_error 0；残留规则条数：{'R1': 15, 'R2': 0, 'R3': 0, 'R4': 5}。分组是观察性描述，题目难度与证据缺口可能共同影响结果。

## 重点题逐题 A/B/C

| 题目 | A resolved | B resolved | C resolved | C首次编辑 | C编码请求 | C披露 |
|---|---|---|---|---:|---:|---:|
| astropy__astropy-12907 | 是 | 否 | 是 | 10 | 17 | 0 |
| django__django-13964 | 是 | 否 | 是 | 4 | 40 | 0 |
| django__django-13033 | 否 | 是 | 是 | 7 | 19 | 0 |
| sympy__sympy-18698 | 否 | 是 | 否 | 未编辑 | 40 | 1 |
| django__django-13925 | 否 | 是 | 是 | 3 | 7 | 3 |

- astropy__astropy-12907：把 _cstack 右下块的填充常数 1 改为实际 right 矩阵，保留嵌套模型的可分离结构，原 harness 判定 resolved。
- django__django-13964：把未同步的外键值判断从仅 None 扩展到 field.empty_values，并将缓存删除改为容错 pop；原 harness 判定 resolved。
- django__django-13033：将外键 attname 与查询路径最后一段 pieces[-1] 比较，修正带关联前缀的排序判断；原 harness 判定 resolved。
- sympy__sympy-18698：C 已把差异追到 _symbolic_factor_list，但随后反复运行同一探针并用满40次，未编辑，原评分未resolved。
- django__django-13925：在 _check_default_pk 中排除关联主键，避免对多表继承产生的关系主键误报警告，原 harness 判定 resolved。

## read_file 报错

C总计8次；B历史总计5次，原日志也存在此问题。

| 题目 | C次数 | C类型 | B次数 | B类型 |
|---|---:|---|---:|---|
| sphinx-doc__sphinx-11445 | 2 | ValueError | 1 | ValueError |
| psf__requests-2317 | 2 | ValueError | 1 | ValueError |
| pytest-dev__pytest-7490 | 0 | 无 | 1 | ValueError |
| astropy__astropy-12907 | 1 | ValueError | 0 | 无 |
| django__django-13158 | 0 | 无 | 1 | ValueError |
| scikit-learn__scikit-learn-14087 | 1 | ValueError | 0 | 无 |
| sphinx-doc__sphinx-8721 | 1 | ValueError | 0 | 无 |
| astropy__astropy-14365 | 1 | ValueError | 0 | 无 |
| django__django-13925 | 0 | 无 | 1 | ValueError |

[B/C逐条错误与请求参数](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/read-file-errors-BC.json)

## C未resolved题的离线轨迹判断

只审阅已评分且未resolved的C题。判断来自原定位包、编码工具轨迹、最终补丁与原harness日志；不重新调用模型/运行代码。使用40次本身不等于循环；重复同一无进展操作才据轨迹标记。沿用错误假设只记录具体诊断与后续操作的对应，不宣称证明因果效应；证据不足明确写不确定或未见明确证据。

| 题目 | 沿用定位错误假设 | 用满40次 | 循环 | 依据 |
|---|---|---|---|---|
| [sympy__sympy-21379](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/failure-audit/sympy__sympy-21379/trace.md) | 未见明确证据 | 是 | 是 | 编码器用复现追到 sinh._eval_is_real → Mod.eval → gcd，多项式抛错位置也更正为 _parallel_poly_from_expr；未见坚持定位包中 _parallel_dict_from_expr 的错误归属。不能据未修复反推受错误诊断影响。 请求1及7–39共34次重复同一复现，仅改变 tail/head/sed 输出窗口；39次工具调用无源代码编辑，第40次结束为空补丁。 |
| [astropy__astropy-14182](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/failure-audit/astropy__astropy-14182/trace.md) | 是（轨迹对应） | 是 | 是 | 定位建议把边框索引改为 position_line；编码补丁照此取 self.header.position_line=0，harness 显示首尾实际变成列名而非等号边框，test_write_normal 与 test_rst_with_header_rows 均失败。能确认采纳了同一错误具体方案，不能据此独立证明因果影响大小。 第4/5次编辑后不再改源码；请求11–35原样重复同一写表命令25次，36–39又重复另一命令4次，直到40次结束。 |
| [pylint-dev__pylint-7080](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/failure-audit/pylint-dev__pylint-7080/trace.md) | 未见明确证据 | 是 | 是 | 定位猜测 Windows 分隔符/二次过滤缺口；编码器随后读取 expand_modules 并在终答确认过滤链已存在，未实施分隔符修正。最终只加了未接入调用点的 helper，递归当前目录的目标测试仍失败，不能据此判定采纳了定位错误假设。 请求 12–39 连续 28 次执行完全相同的替换脚本，old 与 new 相同且均未产生源码变化；最终补丁仅保留请求 9 的 helper。 |
| [sphinx-doc__sphinx-11445](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/failure-audit/sphinx-doc__sphinx-11445/trace.md) | 不确定 | 是 | 是 | 编码器沿用“prolog 前置影响标题识别”的调查方向，并将定位写的 parse 调用点修正为 decorate；但未复现、未修改代码，现有轨迹不能确定该根因假设是错的，不能将沿用方向直接计为沿用错误假设。 请求 21–39 连续 19 次执行同一 bof 搜索命令，无源码编辑；终答亦承认重复相同输出，最终为空补丁。 |
| [pydata__xarray-4094](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/failure-audit/pydata__xarray-4094/trace.md) | 未见明确证据 | 是 | 是 | 沿用了残留标量 y 坐标及 drop_vars 的定位方向，但请求 5 的实际输出支持该窄事实：drop 前有 y=(a,)，drop 后只剩 x。失败的直接轨迹是始终未落地修改，不能把已获得支持的诊断计为错误假设。 请求 27–39 连续 13 次相同 edit_file 操作，old=new，源码变化为空；此前反复执行无效替换并追加重复打印。最终空补丁，终答承认未真正修改。 |
| [psf__requests-2317](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/failure-audit/psf__requests-2317/trace.md) | 未见明确证据 | 否 | 否 | 沿用了 bytes 方法归一化方向，但 C 自行把 to_native_string 扩展到 PreparedRequest.prepare_method，且放在 None 检查之前，原 harness 的 test_basic_building 因 None.decode 报错；定位并未建议这一扩展。另存在证书及旧测试兼容性干扰，保持原评分。 共 12 次请求；读取、修改、复现及逐步缩小测试范围有推进，未出现前述无进展重复循环。 |
| [sympy__sympy-18698](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/failure-audit/sympy__sympy-18698/trace.md) | 未见明确证据 | 是 | 是 | 定位猜测低层 dmp/dup 分组决定异常；编码器通过比较模块 sqf_list 与 Poly.sqf_list，明确确认低层算法正常，转而定位 _symbolic_factor_list 按 Mul 参数拆分的差异，未沿用低层归因。最终仍未编辑。 请求 16–39 重复同一 _symbolic_factor_list 核心探针 24 次（少数附带查看其他代码），全程源码变化为空，40 次后交付空补丁。 |
| [sphinx-doc__sphinx-8595](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/failure-audit/sphinx-doc__sphinx-8595/trace.md) | 未见明确证据 | 否 | 否 | 按定位区分 None 与空 __all__ 并修改代码；原 harness 日志显示 C 新建 empty_all.py 与评测测试补丁同名，git apply 报 already exists，后续测试文件不存在、pytest exit 4。因此原评分仍为未resolved，但日志不足以判定定位诊断错误。 共14次请求；有源码及测试编辑，重复测试用于改变输出窗口/定位失败，后续继续排查，不属于用满40次的无进展循环。 |
| [sphinx-doc__sphinx-8721](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/failure-audit/sphinx-doc__sphinx-8721/trace.md) | 未见明确证据 | 否 | 否 | 编码器读取完整 viewcode.py 后沿用“在 collect_pages 再检查 epub 开关”的方向；原测试总览为4 passed/1 failed，唯一列出的失败是 test_viewcode，但原 harness report 将目标与其他测试记失败，存在输出/评分口径差异。保留原resolved=False，不据此判定定位根因错误。 共10次请求，读取、改源码、加测试、对照基础版本及筛选测试均有推进，没有40次耗尽或重复无效操作。 |

[离线判断结构化明细](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/failure-judgments.json)

## 逐题记录及边界

[C逐题CSV](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/C-per-task.csv)；[A/B/C逐题JSON](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/ABC-per-task.json)；[完整汇总及配对JSON](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/summary.json)。

requests-2317保持原harness评分，证书错误单独列在[环境观察文件](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/environment-observations.json)；不补跑、不重评、不修改证书。C还引入 method=None 转换的额外回归，不能将全部失败归因于证书。
sphinx-8595存在测试补丁同名文件冲突；sphinx-8721原测试总览与harness逐项评分不一致。均保留原resolved=False，详见[额外评测观察](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/additional-harness-observations.json)。未触碰holdout50。A/B未重跑；没有额外重复C。
云端临时API密钥已删除，运行/全部容器均为0，24个任务镜像缓存保留。控制台已核验“已关机”“关机不计费模式”，公网IPv4为“-”，计费栏为“按量计费-部分停止计费”。
[清理和关机状态](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/final-cloud-audit.json)；[关机凭据](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/shutdown-receipt.json)；[云端最终哈希与缓存核验](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/final-remote-verification.json)；[结果一致性检查](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-c-v82-20261117/delivery/result-validation.json)。

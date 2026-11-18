# sympy__sympy-21379

原结果：回退；实际源码计量 14325/14336，余 11 字节；请求 4 次。

[原回答原文（原始provider内容精确提取）](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/sympy__sympy-21379/raw-answer.txt)；[原始诊断审计](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/sympy__sympy-21379/locator/diagnostic-audit.json)；[原始provider响应](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/sympy__sympy-21379/locator-wire/response-4.json)

[C全部实际工具输出](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/sympy__sympy-21379/tool-output.txt)

C完整行账本：sympy/core/basic.py:761-942; sympy/core/basic.py:949-952; sympy/core/basic.py:955-955; sympy/core/basic.py:1026-1041; sympy/core/basic.py:1061-1064; sympy/core/function.py:2108-2108; sympy/core/function.py:2196-2211; sympy/core/function.py:2432-2432; sympy/polys/polytools.py:4360-4420

注意：文件已读范围不自动等于该实体已读范围。未知函数终点不补猜。

## 01-01 R4_citation_not_delivered:polytools.py:4399

**误判：范围/用途**。该引用出现在最小验证的待观察 traceback 落点，不是已读事实断言；其完整路径 sympy/polys/polytools.py:4399 本来也已读。全文扫描和不识别用途导致回退。

原回答片段：
```text
L26：最小验证：`python -c "from sympy import *; x,y,z=symbols('x y z',real=True); e=exp(sinh(Piecewise((x,y>x),(y,True))/z)); import traceback; traceback.print_exc() if False else print(e.subs({1:1.0}))"`（配合 `SYMPY_USE_CACHE=no` 与开启缓存各跑一次，观察 traceback 是否落在 polytools.py:4399）。
```

校验器匹配依据：
```json
{
  "regex": "(?P<path>[\\w./-]+\\.py):(?P<start>\\d+)(?:[-–](?P<end>\\d+))?",
  "citation": "polytools.py:4399",
  "path": "polytools.py",
  "start": 4399,
  "end": 4399
}
```

校验器按字面路径记账：无；按唯一后缀候选对应：sympy/polys/polytools.py:4360-4420；另有实际搜索行：4399

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 4,
    "path": "sympy/polys/polytools.py",
    "requested": {
      "cursor": null,
      "end_line": 4420,
      "path": "sympy/polys/polytools.py",
      "start_line": 4360
    },
    "delivered_metadata": {
      "end_column": 0,
      "end_line": 4420,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 4360,
      "total_lines": 7229
    },
    "cumulative_source_bytes": 10296
  }
]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 1,
    "path": "sympy/polys/polytools.py",
    "line": 4399,
    "text": "            raise PolynomialError(\"Piecewise generators do not make sense\")"
  }
]
```

## 01-02 R1_body_incomplete_unmarked:sympy/polys/polytools.py:_parallel_dict_from_expr

**边界：实体身份+标注格式**。原回答另写“未读 _parallel_dict_from_expr 函数头”，但未带路径；所写 polytools.py 限定名又可能指导入别名/错误模块。不能凭此确定该完整 ID 的正文边界，也不把纠正定位身份当成纯校验误判修复。

原回答片段：
```text
entities 候选：sympy/polys/polytools.py:_parallel_dict_from_expr
L14：- 待验证假设：异常来自 `sympy/polys/polytools.py:_parallel_dict_from_expr` 的 gens 检查，即某条路径把含 `Piecewise` 的表达式送进 Poly 构造（如 `expand`/`as_poly`/`cancel` 类调用），而非 `subs` 本身直接抛错。
```

校验器匹配依据：
```json
{
  "entity": "sympy/polys/polytools.py:_parallel_dict_from_expr",
  "structured_candidate": true,
  "exact_unread_same_line": false,
  "entity_complete": false,
  "condition": "complete_entity=False 且没有同一行完整ID+字面“未读完”；False具体AST span未持久化"
}
```

校验器按字面路径记账：sympy/polys/polytools.py:4360-4420；完整实体边界未留存，不把整文件范围当函数覆盖；另有实际搜索行：4399

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 4,
    "path": "sympy/polys/polytools.py",
    "requested": {
      "cursor": null,
      "end_line": 4420,
      "path": "sympy/polys/polytools.py",
      "start_line": 4360
    },
    "delivered_metadata": {
      "end_column": 0,
      "end_line": 4420,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 4360,
      "total_lines": 7229
    },
    "cumulative_source_bytes": 10296
  }
]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 1,
    "path": "sympy/polys/polytools.py",
    "line": 4399,
    "text": "            raise PolynomialError(\"Piecewise generators do not make sense\")"
  }
]
```

原答中的未读/未核验相关上下文：
```text
L19: 未核验点
L20: - `sympy/core/basic.py:Basic._subs` 未读完（仅 1026-1041、1061-1064 已读，docstring 与 1042-1060 缺失）。
L21: - `sympy/core/basic.py:Basic.subs` 未读完：分页 cursor `rf1_e05b5bdfccaa95ed8bb81f49ce43fd2d1157d871d8faa36deca72123911aa8ed` 未续读（943-948 缺失）。
L22: - `sympy/core/function.py:Subs` 未读完（仅 2196-2211 已读）。
L23: - 未读 `_parallel_dict_from_expr` 函数头与 `expand`/`sinh`/`exp` 的 `_eval_subs`，调用链未穷尽。
```

函数长度："未知"

预算归因：题级预算确实耗尽（余11字节），但此实体存在模块/别名问题且未请求该完整定义；不能把这条R1直接归因于字节截断。

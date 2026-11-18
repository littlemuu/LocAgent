# psf__requests-2317

原结果：回退；实际源码计量 10171/14336，余 4165 字节；请求 4 次。

[原回答原文（原始provider内容精确提取）](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/psf__requests-2317/raw-answer.txt)；[原始诊断审计](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/psf__requests-2317/locator/diagnostic-audit.json)；[原始provider响应](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/psf__requests-2317/locator-wire/response-39.json)

[C全部实际工具输出](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/psf__requests-2317/tool-output.txt)

C完整行账本：requests/sessions.py:340-470

注意：文件已读范围不自动等于该实体已读范围。未知函数终点不补猜。

## 10-01 R4_citation_not_delivered:requests/compat.py:96

**误判：搜索证据遗漏**。96行 builtin_str=str 确已在搜索结果中交付，原文明确“搜索命中（未读正文）”；没有声称已确认分支条件。

原回答片段：
```text
L7：- 搜索命中（未读正文）：requests/compat.py:96 与 :111 均定义 `builtin_str = str`；requests/models.py:443/469/474 用 `builtin_str` 处理 Content-Length；requests/utils.py:663 用 `isinstance(string, builtin_str)` 判断。
```

校验器匹配依据：
```json
{
  "regex": "(?P<path>[\\w./-]+\\.py):(?P<start>\\d+)(?:[-–](?P<end>\\d+))?",
  "citation": "requests/compat.py:96",
  "path": "requests/compat.py",
  "start": 96,
  "end": 96
}
```

校验器按字面路径记账：无；另有实际搜索行：96

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 4,
    "path": "requests/compat.py",
    "requested": {
      "cursor": null,
      "end_line": 125,
      "path": "requests/compat.py",
      "start_line": 80
    },
    "delivered_metadata": {
      "error": "tool_error",
      "error_type": "ValueError"
    },
    "cumulative_source_bytes": 7460
  },
  {
    "tool_index": 5,
    "path": "requests/compat.py",
    "requested": {
      "cursor": null,
      "end_line": 120,
      "path": "requests/compat.py",
      "start_line": 85
    },
    "delivered_metadata": {
      "error": "tool_error",
      "error_type": "ValueError"
    },
    "cumulative_source_bytes": 7508
  }
]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 1,
    "path": "requests/compat.py",
    "line": 96,
    "text": "    builtin_str = str"
  }
]
```

## 10-02 R4_citation_not_delivered:requests/models.py:443

**误判：搜索证据遗漏**。443/469/474行 builtin_str 处理Content-Length均由搜索交付，原文限制为搜索命中。

原回答片段：
```text
L7：- 搜索命中（未读正文）：requests/compat.py:96 与 :111 均定义 `builtin_str = str`；requests/models.py:443/469/474 用 `builtin_str` 处理 Content-Length；requests/utils.py:663 用 `isinstance(string, builtin_str)` 判断。
```

校验器匹配依据：
```json
{
  "regex": "(?P<path>[\\w./-]+\\.py):(?P<start>\\d+)(?:[-–](?P<end>\\d+))?",
  "citation": "requests/models.py:443",
  "path": "requests/models.py",
  "start": 443,
  "end": 443
}
```

校验器按字面路径记账：无；另有实际搜索行：443

C read_file 请求和实际返回：
```json
[]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 1,
    "path": "requests/models.py",
    "line": 443,
    "text": "                self.headers['Content-Length'] = builtin_str(length)"
  }
]
```

## 10-03 R4_citation_not_delivered:requests/utils.py:663

**误判：搜索证据遗漏**。663行 isinstance(string,builtin_str) 判断由搜索交付，陈述只复述这段代码。

原回答片段：
```text
L7：- 搜索命中（未读正文）：requests/compat.py:96 与 :111 均定义 `builtin_str = str`；requests/models.py:443/469/474 用 `builtin_str` 处理 Content-Length；requests/utils.py:663 用 `isinstance(string, builtin_str)` 判断。
```

校验器匹配依据：
```json
{
  "regex": "(?P<path>[\\w./-]+\\.py):(?P<start>\\d+)(?:[-–](?P<end>\\d+))?",
  "citation": "requests/utils.py:663",
  "path": "requests/utils.py",
  "start": 663,
  "end": 663
}
```

校验器按字面路径记账：无；另有实际搜索行：663

C read_file 请求和实际返回：
```json
[]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 1,
    "path": "requests/utils.py",
    "line": 663,
    "text": "    if isinstance(string, builtin_str):"
  }
]
```

## 10-04 R1_body_incomplete_unmarked:requests/compat.py:builtin_str

**误判：实体类型+标注格式**。builtin_str 是条件分支里的 str 别名赋值，不是此文件的 AST 函数/类定义；完整函数体检查永远无法命中。原回答还明确写该定义未读完、未确认分支。应单独检查预测实体类型，不能报告“函数未读且未标”。

原回答片段：
```text
entities 候选：requests/compat.py:builtin_str
L10：- 待验证假设：在 Python 3 下 `requests/compat.py:builtin_str` 绑定为 `str`，因此 `str(b'GET')` 得到 `"b'GET'"`，与用户观察一致；Python 2 下 `str` 对 bytes 是恒等，故 2.6 不复现。
```

校验器匹配依据：
```json
{
  "entity": "requests/compat.py:builtin_str",
  "structured_candidate": true,
  "exact_unread_same_line": false,
  "entity_complete": false,
  "condition": "complete_entity=False 且没有同一行完整ID+字面“未读完”；False具体AST span未持久化"
}
```

校验器按字面路径记账：无；完整实体边界未留存，不把整文件范围当函数覆盖；另有实际搜索行：96,111

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 4,
    "path": "requests/compat.py",
    "requested": {
      "cursor": null,
      "end_line": 125,
      "path": "requests/compat.py",
      "start_line": 80
    },
    "delivered_metadata": {
      "error": "tool_error",
      "error_type": "ValueError"
    },
    "cumulative_source_bytes": 7460
  },
  {
    "tool_index": 5,
    "path": "requests/compat.py",
    "requested": {
      "cursor": null,
      "end_line": 120,
      "path": "requests/compat.py",
      "start_line": 85
    },
    "delivered_metadata": {
      "error": "tool_error",
      "error_type": "ValueError"
    },
    "cumulative_source_bytes": 7508
  }
]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 1,
    "path": "requests/compat.py",
    "line": 96,
    "text": "    builtin_str = str"
  },
  {
    "tool_index": 1,
    "path": "requests/compat.py",
    "line": 111,
    "text": "    builtin_str = str"
  }
]
```

原答中的未读/未核验相关上下文：
```text
L7: - 搜索命中（未读正文）：requests/compat.py:96 与 :111 均定义 `builtin_str = str`；requests/models.py:443/469/474 用 `builtin_str` 处理 Content-Length；requests/utils.py:663 用 `isinstance(string, builtin_str)` 判断。
L14: 未核验点
L15: - requests/compat.py 的 `builtin_str` 定义函数体未读完（两次读取均报错），仅凭搜索命中行，未确认 py2/py3 分支条件。
L16: - requests/models.py 的 `Request`/`PreparedRequest.prepare` 完整函数体未读，method 后续如何进入 urllib3 请求行未核验。
L17: - requests/utils.py 未读，`safe_encode_list` 是否存在于本仓库未确认。
```

函数长度："不适用：builtin_str为别名赋值"

预算归因：未耗尽14,336总字节；不能将缺口归于总字节上限。可能有4096单页截断、未续读、cursor错误、请求次数结束、所选范围不足或实体身份问题，见原工具记录。

## 10-05 R1_body_incomplete_unmarked:requests/sessions.py:Session.prepare_request

**真违规：函数头缺失**。C仅从340行开始读 prepare_request 的中间部分，未收到定义头；候选中列出该方法，推断还讨论其行为，却没有该函数未读完的说明。

原回答片段：
```text
entities 候选：requests/sessions.py:Session.prepare_request
L5：- requests/sessions.py:363-365：`prepare_request` 中再次调用 `request.method.upper()` 传给 `PreparedRequest.prepare`。
L11：- 待验证假设：`requests/sessions.py:Session.request` 缺少对 bytes 型 method 的显式解码（如 `method.decode('ascii')`），是该方法路径上的可疑点；`Session.prepare_request` 只做 `upper()`，不会修复该问题。
```

校验器匹配依据：
```json
{
  "entity": "requests/sessions.py:Session.prepare_request",
  "structured_candidate": true,
  "exact_unread_same_line": false,
  "entity_complete": false,
  "condition": "complete_entity=False 且没有同一行完整ID+字面“未读完”；False具体AST span未持久化"
}
```

校验器按字面路径记账：requests/sessions.py:340-470；完整实体边界未留存，不把整文件范围当函数覆盖；另有实际搜索行：16,428

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 3,
    "path": "requests/sessions.py",
    "requested": {
      "cursor": null,
      "end_line": 470,
      "path": "requests/sessions.py",
      "start_line": 400
    },
    "delivered_metadata": {
      "end_column": 0,
      "end_line": 470,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 400,
      "total_lines": 671
    },
    "cumulative_source_bytes": 7412
  },
  {
    "tool_index": 6,
    "path": "requests/sessions.py",
    "requested": {
      "cursor": null,
      "end_line": 400,
      "path": "requests/sessions.py",
      "start_line": 340
    },
    "delivered_metadata": {
      "end_column": 78,
      "end_line": 400,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 340,
      "total_lines": 671
    },
    "cumulative_source_bytes": 10171
  }
]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 1,
    "path": "requests/sessions.py",
    "line": 16,
    "text": "from .compat import cookielib, OrderedDict, urljoin, urlparse, builtin_str"
  },
  {
    "tool_index": 1,
    "path": "requests/sessions.py",
    "line": 428,
    "text": "        method = builtin_str(method)"
  }
]
```

原答中的未读/未核验相关上下文：
```text
L7: - 搜索命中（未读正文）：requests/compat.py:96 与 :111 均定义 `builtin_str = str`；requests/models.py:443/469/474 用 `builtin_str` 处理 Content-Length；requests/utils.py:663 用 `isinstance(string, builtin_str)` 判断。
L14: 未核验点
L15: - requests/compat.py 的 `builtin_str` 定义函数体未读完（两次读取均报错），仅凭搜索命中行，未确认 py2/py3 分支条件。
L16: - requests/models.py 的 `Request`/`PreparedRequest.prepare` 完整函数体未读，method 后续如何进入 urllib3 请求行未核验。
L17: - requests/utils.py 未读，`safe_encode_list` 是否存在于本仓库未确认。
```

函数长度："未知"

预算归因：未耗尽14,336总字节；不能将缺口归于总字节上限。可能有4096单页截断、未续读、cursor错误、请求次数结束、所选范围不足或实体身份问题，见原工具记录。

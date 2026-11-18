# django__django-13925

原结果：回退；实际源码计量 11290/14336，余 3046 字节；请求 4 次。

[原回答原文（原始provider内容精确提取）](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/django__django-13925/raw-answer.txt)；[原始诊断审计](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/django__django-13925/locator/diagnostic-audit.json)；[原始provider响应](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/django__django-13925/locator-wire/response-94.json)

[C全部实际工具输出](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/django__django-13925/tool-output.txt)

C完整行账本：django/db/models/base.py:1240-1330; django/db/models/options.py:200-250

注意：文件已读范围不自动等于该实体已读范围。未知函数终点不补猜。

## 24-01 R4_citation_not_delivered:django/apps/config.py:64-70

**真违规：事实连续引用有缺口**。事实段把64-70写为已读依据；C仅搜索收到64、69、70，未收到65-68，没有在此说明仅搜索，且同时概括两个属性行为。

原回答片段：
```text
L5：- django/apps/config.py:64-70：`default_auto_field` 属性与 `_is_default_auto_field_overridden` 仅比较类属性是否被覆盖。
```

校验器匹配依据：
```json
{
  "regex": "(?P<path>[\\w./-]+\\.py):(?P<start>\\d+)(?:[-–](?P<end>\\d+))?",
  "citation": "django/apps/config.py:64-70",
  "path": "django/apps/config.py",
  "start": 64,
  "end": 70
}
```

校验器按字面路径记账：无；另有实际搜索行：64,69,70

C read_file 请求和实际返回：
```json
[]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 2,
    "path": "django/apps/config.py",
    "line": 64,
    "text": "    def default_auto_field(self):"
  },
  {
    "tool_index": 2,
    "path": "django/apps/config.py",
    "line": 69,
    "text": "    def _is_default_auto_field_overridden(self):"
  },
  {
    "tool_index": 2,
    "path": "django/apps/config.py",
    "line": 70,
    "text": "        return self.__class__.default_auto_field is not AppConfig.default_auto_field"
  }
]
```

## 24-02 R4_citation_not_delivered:tests/check_framework/test_model_checks.py:389-412

**真违规：事实连续引用有缺口**。事实段引用389-412并断言测试覆盖两条路径，C只收到稀疏搜索命中（389/394/399/412等），没有完整测试体，未标“搜索命中”。

原回答片段：
```text
L6：- tests/check_framework/test_model_checks.py:389-412：测试覆盖了 app 级 default_auto_field 与 setting 两种抑制路径。
```

校验器匹配依据：
```json
{
  "regex": "(?P<path>[\\w./-]+\\.py):(?P<start>\\d+)(?:[-–](?P<end>\\d+))?",
  "citation": "tests/check_framework/test_model_checks.py:389-412",
  "path": "tests/check_framework/test_model_checks.py",
  "start": 389,
  "end": 412
}
```

校验器按字面路径记账：无；另有实际搜索行：394,389,399,412

C read_file 请求和实际返回：
```json
[]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 1,
    "path": "tests/check_framework/test_model_checks.py",
    "line": 394,
    "text": "                id='models.W042',"
  },
  {
    "tool_index": 2,
    "path": "tests/check_framework/test_model_checks.py",
    "line": 389,
    "text": "                    \"CheckDefaultPKConfig.default_auto_field attribute to \""
  },
  {
    "tool_index": 2,
    "path": "tests/check_framework/test_model_checks.py",
    "line": 399,
    "text": "    def test_default_auto_field_setting(self):"
  },
  {
    "tool_index": 2,
    "path": "tests/check_framework/test_model_checks.py",
    "line": 412,
    "text": "    def test_app_default_auto_field(self, apps):"
  }
]
```

## 24-03 R4_citation_not_delivered:base.py:364

**误判：受限搜索陈述**。该推断明确“搜索仅命中…manager.auto_created”“无法确认”pk来源；364行manager赋值确由C搜索交付，不是编造已读根因证据。

原回答片段：
```text
L10：- 待验证假设：`_meta.pk.auto_created` 的赋值来源未在本次证据中出现（搜索仅命中 base.py:364、options.py:439 的 manager.auto_created），因此无法确认继承场景下该标志的实际取值路径。
```

校验器匹配依据：
```json
{
  "regex": "(?P<path>[\\w./-]+\\.py):(?P<start>\\d+)(?:[-–](?P<end>\\d+))?",
  "citation": "base.py:364",
  "path": "base.py",
  "start": 364,
  "end": 364
}
```

校验器按字面路径记账：无；按唯一后缀候选对应：django/db/models/base.py:1240-1330；另有实际搜索行：364

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 3,
    "path": "django/db/models/base.py",
    "requested": {
      "cursor": null,
      "end_line": 1330,
      "path": "django/db/models/base.py",
      "start_line": 1280
    },
    "delivered_metadata": {
      "end_column": 30,
      "end_line": 1330,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 1280,
      "total_lines": 2139
    },
    "cumulative_source_bytes": 6648
  },
  {
    "tool_index": 5,
    "path": "django/db/models/base.py",
    "requested": {
      "cursor": null,
      "end_line": 1280,
      "path": "django/db/models/base.py",
      "start_line": 1240
    },
    "delivered_metadata": {
      "end_column": 49,
      "end_line": 1280,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 1240,
      "total_lines": 2139
    },
    "cumulative_source_bytes": 11049
  }
]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 6,
    "path": "django/db/models/base.py",
    "line": 364,
    "text": "            manager.auto_created = True"
  }
]
```

## 24-04 R4_citation_not_delivered:options.py:439

**误判：受限搜索陈述**。同上，options.py:439的manager赋值确已搜索交付，且用于说明证据不足。

原回答片段：
```text
L10：- 待验证假设：`_meta.pk.auto_created` 的赋值来源未在本次证据中出现（搜索仅命中 base.py:364、options.py:439 的 manager.auto_created），因此无法确认继承场景下该标志的实际取值路径。
```

校验器匹配依据：
```json
{
  "regex": "(?P<path>[\\w./-]+\\.py):(?P<start>\\d+)(?:[-–](?P<end>\\d+))?",
  "citation": "options.py:439",
  "path": "options.py",
  "start": 439,
  "end": 439
}
```

校验器按字面路径记账：无；按唯一后缀候选对应：django/db/models/options.py:200-250；另有实际搜索行：439

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 4,
    "path": "django/db/models/options.py",
    "requested": {
      "cursor": null,
      "end_line": 250,
      "path": "django/db/models/options.py",
      "start_line": 200
    },
    "delivered_metadata": {
      "end_column": 23,
      "end_line": 250,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 200,
      "total_lines": 895
    },
    "cumulative_source_bytes": 9036
  }
]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 6,
    "path": "django/db/models/options.py",
    "line": 439,
    "text": "        manager.auto_created = True"
  }
]
```

## 24-05 R1_body_incomplete_unmarked:django/apps/config.py:AppConfig._is_default_auto_field_overridden

**边界：搜索片段/装饰器口径**。C搜索已见69行定义和70行return，却没有完整函数/装饰器span；R1可能反映未读装饰器或仅拒绝搜索证据。当前日志不能独立证明完整实体覆盖，保守归边界。

原回答片段：
```text
entities 候选：django/apps/config.py:AppConfig._is_default_auto_field_overridden
L2：- django/db/models/base.py:1298-1320：`_check_default_pk` 的触发条件只有三项：`cls._meta.pk.auto_created` 为真、`settings.is_overridden('DEFAULT_AUTO_FIELD')` 为假、`cls._meta.app_config._is_default_auto_field_overridden` 为假；三者同时成立才返回 models.W042。
L5：- django/apps/config.py:64-70：`default_auto_field` 属性与 `_is_default_auto_field_overridden` 仅比较类属性是否被覆盖。
```

校验器匹配依据：
```json
{
  "entity": "django/apps/config.py:AppConfig._is_default_auto_field_overridden",
  "structured_candidate": true,
  "exact_unread_same_line": false,
  "entity_complete": false,
  "condition": "complete_entity=False 且没有同一行完整ID+字面“未读完”；False具体AST span未持久化"
}
```

校验器按字面路径记账：无；完整实体边界未留存，不把整文件范围当函数覆盖；另有实际搜索行：64,69,70

C read_file 请求和实际返回：
```json
[]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 2,
    "path": "django/apps/config.py",
    "line": 64,
    "text": "    def default_auto_field(self):"
  },
  {
    "tool_index": 2,
    "path": "django/apps/config.py",
    "line": 69,
    "text": "    def _is_default_auto_field_overridden(self):"
  },
  {
    "tool_index": 2,
    "path": "django/apps/config.py",
    "line": 70,
    "text": "        return self.__class__.default_auto_field is not AppConfig.default_auto_field"
  }
]
```

原答中的未读/未核验相关上下文：
```text
L12: 未核验点
L13: - 未读完：`Model._meta` 构建与 pk 自动创建逻辑（options.py 中 pk 相关方法、base.py 中字段继承处理）未读。
L14: - 未核验：`Options._get_default_pk_class` 的调用点（未读）。
```

函数长度："未知"

预算归因：未耗尽14,336总字节；不能将缺口归于总字节上限。可能有4096单页截断、未续读、cursor错误、请求次数结束、所选范围不足或实体身份问题，见原工具记录。

---
title: "{{title}} - 摘要"
type: summary
tags: []
source: []
created: "{{created_date}}"
updated: "{{updated_date}}"
status: draft
original_doc: ""
doc_type: ""  # paper / article / report
key_points: []
confidence: medium
---

# {{title}} - 摘要

## 文档信息

- **原文**：[[{{original_doc}}]]
- **类型**：{{doc_type}}
- **摘要日期**：{{created_date}}

## 核心结论

[3-5 条核心结论，每条带 Source ID]

1. 结论1 [Source: {{original_doc}}]
2. 结论2 [Source: {{original_doc}}]
3. 结论3 [Source: {{original_doc}}]

## 关键要点

{{#each key_points}}
### {{this.title}}
{{this.content}}
[Source: ../{{../original_doc}}]

{{/each}}

## 技术细节摘要

[关键方法、参数、数据]
[Source: {{original_doc}}]

## 适用场景

- 场景1：[描述]
- 场景2：[描述]

## 局限性

[原文提到的局限性]
[Source: {{original_doc}}]

## 相关链接

- 完整文档：[[{{original_doc}}]]
- 提取的实体：{{#each extracted_entities}}[[wiki/entities/{{this}}|{{this}}]] {{/each}}
- 涉及的概念：{{#each related_concepts}}[[wiki/concepts/{{this}}|{{this}}]] {{/each}}

---

_审核状态：{{status}} | 最后更新：{{updated_date}}_

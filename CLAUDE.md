# CLAUDE.md - LLM 行为规范

> 本文档定义了 LLM Agent 在 LLM-Wiki 知识编译系统中的行为准则。
> 
> **角色定位**：你是知识库的"编译器"，不是通用聊天机器人。
> **核心任务**：将原始文档转化为结构化、可追溯、可复用的 Wiki 知识。

---

## 一、角色定义

### 1.1 Agent-G（生成者）

**你的职责**：
1. 读取原始文档（raw/papers/markdown/）
2. 生成/更新 wiki 页面（Entity/Concept/Paper/Summary）
3. 确保信息完整、准确、可追溯

**你禁止做的事**：
- ❌ 过度摘要（将 80KB 压缩到 2KB）
- ❌ 生成无法溯源的信息
- ❌ 修改 raw/ 目录的任何文件
- ❌ 删除已有的 Conflict 标记

### 1.2 Agent-R（审核者）

**你的职责**：
1. 按评分标准审核 Agent-G 生成的页面
2. 给出具体、可执行的修改建议
3. 确保综合分 ≥7.5 才能通过

**你禁止做的事**：
- ❌ 模糊评价（如"质量一般"）
- ❌ 忽略任何维度的检查
- ❌ 对明显问题放水通过

---

## 二、核心原则

### 2.1 完整性原则

**要求**：原始文档的核心信息必须完整保留，禁止过度摘要。

**正确做法**：
```markdown
## 方法
论文提出 MFIT 多保真度热建模框架：
- L0 层：解析热阻公式，ns 级估算
- L1 层：RC 热网络，O(n) 复杂度  
- L2 层：FVM 有限体积法，局部热点精确仿真
- 自适应切换：热梯度阈值触发
[Source: 241009188.md]
```

**错误做法**（过度摘要）：
```markdown
## 方法
论文提出多保真度热建模框架，通过不同精度的模型平衡效率与准确性。
```

### 2.2 可追溯原则

**要求**：每条事实陈述后必须标注 Source ID。

**格式**：
```markdown
MFIT 支持设计早期阶段的快速热评估 [Source: 241009188.md#概述]。
精度损失 <5% [Source: 241009188.md#实验验证]。
```

**检查清单**：
- [ ] 每条事实后都有 `[Source: filename.md]`
- [ ] 引用格式统一（方括号 + Source: + 文件名）
- [ ] 无无法溯源的"补充说明"

### 2.3 冲突标记原则

**要求**：发现与已有页面的矛盾时，必须显式标记。

**格式**：
```markdown
MFIT 的计算速度提升 100-500 倍 [Source: 241009188.md]。

[Conflict: wiki/concepts/FVM_simulation.md 声称典型提升为 10-50 倍，
来源：某综述论文。需要核实哪个数据更准确。]
```

**禁止**：
- ❌ 发现冲突但不标记
- ❌ 直接覆盖已有信息而不说明
- ❌ 删除已有的 Conflict 标记

### 2.4 Append-only 原则

**要求**：
- index.md 和 log.md 采用追加模式，不删除历史记录
- Conflict 标记只能追加说明，不能删除
- 页面更新时，旧版本保留在 Git 历史中

---

## 三、页面类型规范

### 3.1 Entity（实体页）

**命名**：`Entity_[名称].md` 或 `entities/[ID].md`

**用途**：记录具体的人/项目/技术/论文

**必填 Frontmatter**：
```yaml
title: "实体名称"
type: entity
tags: []
source: []
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
status: draft  # draft/generated/reviewed/stable
confidence: medium  # low/medium/high
entity_type: ""  # person/project/technology/paper/organization
center_idea: ""
key_terms: []
related_fields: []
```

**正文结构**：
1. 概述（一句话定义）
2. 关键信息（类型、领域、置信度）
3. 详细描述（背景、核心内容）
4. 关键数据/参数（表格形式）
5. 相关链接

### 3.2 Concept（概念页）

**命名**：`Concept_[主题].md` 或 `concepts/[主题].md`

**用途**：记录抽象主题，可横向对比

**必填 Frontmatter**：
```yaml
title: "概念名称"
type: concept
tags: []
source: []
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
status: draft
definition: ""
related_concepts: []
related_entities: []
```

**正文结构**：
1. 定义
2. 核心要点（3-5 条）
3. 原理/机制
4. 应用场景
5. 横向对比（表格）
6. 演进历史
7. 相关链接

### 3.3 Paper（论文页）

**命名**：`papers/[arXivID]_论文.md`

**用途**：单篇论文的完整结构化（非摘要）

**必填 Frontmatter**：
```yaml
title: "论文标题"
type: paper
tags: []
source: [[raw/papers/markdown/xxxx.md]]
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
status: draft
arxiv_id: ""
authors: []
venue: ""
publish_date: ""
keywords: []
confidence: medium
llm_enhanced: False
center_idea: ""
```

**正文结构**：
1. 基本信息（表格）
2. 核心观点
3. 摘要（完整版）
4. 问题定义
5. 方法（详细，保留技术细节）
6. 实验验证（含关键结果表格）
7. 结论与展望
8. 提取的实体
9. 涉及的概念
10. 相关论文

### 3.4 Summary（摘要页）

**命名**：`summaries/[标题]_摘要.md`

**用途**：单篇文档的结构化摘要

**必填 Frontmatter**：
```yaml
title: "标题 - 摘要"
type: summary
tags: []
source: []
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
status: draft
original_doc: ""
doc_type: ""  # paper/article/report
key_points: []
confidence: medium
```

### 3.5 Synthesis（综合页）

**命名**：`syntheses/[主题]_综合.md`

**用途**：多源综合分析，查询结果沉淀

**必填 Frontmatter**：
```yaml
title: "主题 - 综合分析"
type: synthesis
tags: []
source: []
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
status: draft
synthesis_date: "YYYY-MM-DD"
source_docs: []
query_origin: ""
confidence: medium
```

---

## 四、工作流程

### 4.1 Agent-G 工作流程

```
开始
  │
  ▼
读取原始文档
  │
  ▼
分析文档结构
  │
  ├─ 提取实体 → 生成/更新 Entity 页
  ├─ 提取概念 → 生成/更新 Concept 页
  ├─ 整理论文 → 生成 Paper 页
  └─ 生成摘要 → 生成 Summary 页
  │
  ▼
检查与已有页面的冲突
  │
  ├─ 发现冲突 → 添加 [Conflict: ...] 标记
  └─ 无冲突 → 继续
  │
  ▼
标注所有 Source ID
  │
  ▼
输出完整 wiki 页面
  │
  ▼
结束
```

### 4.2 Agent-R 工作流程

```
开始
  │
  ▼
读取 Agent-G 生成的页面
  │
  ▼
按 5 维度评分
  │
  ├─ 完整性（25%）：信息保留率
  ├─ 准确性（25%）：Source ID 比例
  ├─ 规范性（20%）：Frontmatter/命名
  ├─ 可发现性（15%）：index/交叉引用
  └─ 冲突处理（15%）：Conflict 标记
  │
  ▼
计算综合分
  │
  ├─ ≥7.5 → 通过，状态改为 reviewed
  └─ <7.5 → 打回，附具体修改建议
  │
  ▼
输出评分报告
  │
  ▼
结束
```

---

## 五、评分标准速查

| 维度 | 权重 | 10 分标准 | 7 分标准 | 4 分标准 |
|------|------|-----------|----------|----------|
| 完整性 | 25% | 核心信息 ≥95% | 80-95% | <80% |
| 准确性 | 25% | Source ID ≥95% | 80-95% | <80% |
| 规范性 | 20% | 完全符合 | 轻微问题 | 严重问题 |
| 可发现性 | 15% | index 已更新 | 部分更新 | 未更新 |
| 冲突处理 | 15% | 冲突正确标记 | - | 冲突未标记 |

**通过阈值**：综合分 ≥ 7.5

---

## 六、禁止事项清单

### 6.1 Agent-G 禁止事项

- ❌ 修改 raw/ 目录的任何文件
- ❌ 过度摘要（将长文压缩到原长的 10% 以下）
- ❌ 生成无法溯源的信息
- ❌ 省略关键段落（问题定义、方法、实验、结论）
- ❌ 删除已有的 Conflict 标记
- ❌ 使用模糊的 Source ID（如 [Source: 多篇文献]）

### 6.2 Agent-R 禁止事项

- ❌ 给出模糊评价（如"质量一般"）
- ❌ 忽略任何维度的检查
- ❌ 对明显问题放水通过
- ❌ 不给出具体修改建议就打回

---

## 七、输出格式规范

### 7.1 Wiki 页面格式

```markdown
---
title: "页面标题"
type: entity/concept/paper/summary/synthesis
tags: []
source: []
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
status: draft
# ... 类型特定字段
---

# 页面标题

## 章节1
内容 [Source: filename.md]

## 章节2
内容 [Source: filename.md]

[Conflict: 如有冲突，在此标记]

---
_审核状态：{status} | 最后更新：{updated}_
```

### 7.2 评分报告格式

```markdown
# 审核报告

## 基本信息
- **页面**: wiki/...
- **审核时间**: YYYY-MM-DD HH:MM
- **审核者**: Agent-R

## 评分详情
| 维度 | 得分 | 权重 | 加权分 | 说明 |
|------|------|------|--------|------|
| ... | ... | ... | ... | ... |
| **综合分** | - | - | **X.XX** | - |

## 结论
✅ 通过 / ❌ 打回重写

## 建议
1. ...
2. ...
```

### 7.3 Log 条目格式

```markdown
## [YYYY-MM-DD] Ingest | 文档标题
- **原始文档**: raw/papers/markdown/xxxx.md
- **生成页面**:
  - wiki/papers/xxxx_论文.md
  - wiki/entities/xxxx.md
  - wiki/concepts/xxxx.md
- **冲突标记**: 无 / 详见 xxx.md
- **审核结果**: 通过 (8.5/10) / 打回
- **后续建议**: ...
```

---

## 八、示例

### 8.1 高质量 Entity 页示例

见：`wiki/entities/241009188.md`

### 8.2 高质量 Concept 页示例

见：`wiki/concepts/3Dintegration.md`

### 8.3 高质量 Paper 页示例

目标格式：保留原始文档 80%+ 内容，每条陈述带 Source ID

---

## 九、更新记录

| 日期 | 版本 | 更新内容 |
|------|------|----------|
| 2026-04-22 | v3.0 | 初始版本，基于 Phase 0.1 经验 + 方案.md 架构 |

---

**记住**：你的目标是构建一个可持续演进、高质量、可追溯的知识库。每一次生成都应该让知识库变得更好，而不是更混乱。

# V2 Iteration 2 设计文档：综述生成 + 对比分析

> **日期**: 2026-05-04
> **版本**: V2 Iteration 2
> **ACP 角色**: 架构师

---

## 一、需求确认

| 功能 | 触发方式 | 审核要求 |
|------|----------|----------|
| 综述生成 | 独立综述页面，输入关键词/概念名 | 新建 review_survey.py 审核模块 |
| 对比分析 | 支持论文对比 + 概念对比两种模式 | 新建 review_compare.py 审核模块 |

---

## 二、架构设计

### 2.1 模块划分

```
scripts/
├── survey.py          # Agent_S: 综述生成（新增）
├── compare.py         # Agent_C: 对比分析（新增）
├── review_survey.py   # Agent_RS: 综述审核（新增）
├── review_compare.py  # Agent_RC: 对比审核（新增）
├── agent_g.py         # Agent_G: 论文生成（已有，不修改）
├── review.py          # Agent_R: 论文审核（已有，不修改）
├── batch.py           # 批量编排（已有，需扩展支持 survey/compare）

api/routers/
├── synthesis.py       # 综述/对比 API 端点（新增）

web/src/pages/
├── SurveyPage.tsx     # 综述页面（新增）
├── ComparePage.tsx    # 对比页面（新增）
```

### 2.2 数据流

#### 综述生成数据流

```
用户输入关键词
  │
  ▼
ChromaDB 语义检索 (top_k=20)
  │
  ▼
收集关联 Paper 页面内容
  │
  ▼
收集关联 Entity/Concept 页面内容
  │
  ▼
构建综述 Prompt (含所有提取内容)
  │
  ▼
call_llm 生成结构化综述
  │
  ▼
review_survey 审核 (5维度, 阈值7.5)
  │
  ├─ 通过 → 写入 wiki/syntheses/{主题}_综述.md
  └─ 不通过 → 自动修复 (最多3轮) → 重新审核
  │
  ▼
更新 ChromaDB 索引
```

#### 对比分析数据流

```
用户选择对比对象 (论文ID列表 或 概念关键词)
  │
  ▼
读取各方案 Paper 页面
  │
  ▼
提取实验数据/指标/局限性
  │
  ▼
构建对比 Prompt
  │
  ▼
call_llm 生成对比矩阵 + 场景建议
  │
  ▼
review_compare 审核 (5维度, 阈值7.5)
  │
  ├─ 通过 → 写入 wiki/syntheses/{主题}_对比.md
  └─ 不通过 → 自动修复 (最多3轮) → 重新审核
  │
  ▼
更新 ChromaDB 索引
```

### 2.3 API 设计

| 端点 | 方法 | 说明 | 参数 |
|------|------|------|------|
| `/api/synthesis/survey` | POST | 生成综述 | `{keyword, max_papers?}` |
| `/api/synthesis/compare` | POST | 生成对比 | `{mode: "papers"\|"concepts", items: [...]}` |
| `/api/synthesis/list` | GET | 列出所有综述/对比 | `?page=&page_size=&type=survey\|compare` |
| `/api/synthesis/{id}` | GET | 获取详情 | - |

所有生成操作为异步任务，返回 `{task_id}`，通过轮询获取结果。

### 2.4 综述输出模板

```markdown
---
title: "{主题} - 综述"
type: synthesis
tags: [survey, {主题关键词}]
source: [{关联论文ID列表}]
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
status: reviewed
synthesis_date: "YYYY-MM-DD"
source_docs: [{原始文档列表}]
query_origin: "{用户输入的关键词}"
confidence: high
---

# {主题} - 综述分析

## 时间线
{该方向的演进历史，标注关键论文和时间节点}

## 关键突破
{里程碑论文及其贡献，含数据支撑}

## 当前 SOTA
{目前最先进的方法和结果}

## 开放问题
{尚未解决的挑战}

## 相关实体
{该方向的关键人物、机构、技术}

## 参考文献
{带 Source ID 的引用列表}
```

### 2.5 对比输出模板

```markdown
---
title: "{主题} - 对比分析"
type: synthesis
tags: [comparison, {主题关键词}]
source: [{关联论文ID列表}]
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
status: reviewed
synthesis_date: "YYYY-MM-DD"
source_docs: [{原始文档列表}]
query_origin: "compare:{对比对象}"
confidence: high
---

# {主题} - 对比分析

## 对比矩阵
| 维度 | 方案A | 方案B | ... |
|------|-------|-------|-----|
| 准确性 | ... | ... | ... |
| 速度 | ... | ... | ... |
| ... | ... | ... | ... |

## 方案详述
### 方案A: {名称}
{原理简述、独特优势、已知局限性}

### 方案B: {名称}
{原理简述、独特优势、已知局限性}

## 场景化建议
- "场景A（需要X）→ 选 Y"
- "场景B（需要Z）→ 选 W"

## Source 溯源
{每条数据的出处}
```

### 2.6 审核标准

#### 综述审核 (review_survey.py)

| 维度 | 权重 | 检查项 |
|------|------|--------|
| 完整性 | 30% | 时间线+突破+SOTA+开放问题 4节齐全，内容≥3000字 |
| 准确性 | 30% | Source ID 覆盖率≥80%，事实可溯源 |
| 结构 | 20% | Frontmatter 规范，synthesis 模板格式 |
| 可发现性 | 10% | 关联概念/实体有链接 |
| 冲突标注 | 10% | 矛盾结论已标记 [Conflict:...] |

#### 对比审核 (review_compare.py)

| 维度 | 权重 | 检查项 |
|------|------|--------|
| 完整性 | 30% | 对比矩阵+详述+场景建议 3节齐全 |
| 准确性 | 30% | 矩阵数据有出处，评分有依据 |
| 结构 | 20% | Frontmatter 规范，表格格式正确 |
| 可发现性 | 10% | 关联论文有链接 |
| 矛盾标注 | 10% | 矛轂数据已标记 |

---

## 三、技术实现要点

### 3.1 关键词检索策略

```python
# survey.py 核心逻辑
def collect_papers(keyword: str, max_papers: int = 20) -> list:
    """从 ChromaDB 语义检索 + VaultIndex 关键词匹配"""
    # 1. ChromaDB 语义检索
    semantic_results = search_engine.search(keyword, top_k=max_papers * 2)
    
    # 2. VaultIndex 关键词匹配（补充语义检索遗漏）
    keyword_results = vault_index.search_by_keyword(keyword)
    
    # 3. 合并去重
    all_papers = deduplicate(semantic_results + keyword_results)
    
    # 4. 按相关度排序，取 top_k
    return all_papers[:max_papers]
```

### 3.2 Prompt 设计原则

- System Prompt 明确角色和输出格式
- User Prompt 包含所有关联论文的核心内容
- 要求 LLM 先分析后生成
- 强制 Source ID 标注

### 3.3 异步任务模式

复用 V1.1 已有的 `background_tasks` 机制：

```python
@router.post("/survey")
async def create_survey(request: SurveyRequest, user=Depends(require_role("core"))):
    task_id = f"survey_{int(time.time())}"
    background_tasks[task_id] = {"status": "running", "progress": 0}
    # 启动后台任务
    ...
    return {"task_id": task_id, "status": "running"}
```

---

## 四、前端设计

### SurveyPage.tsx

- 输入区：关键词输入框 + 最大论文数滑块
- 结果区：Markdown 渲染 + Source 高亮
- 历史区：已生成综述列表

### ComparePage.tsx

- 模式切换：论文对比 / 概念对比
- 论文对比：选择 2+ 篇论文（下拉搜索）
- 概念对比：输入 2+ 个概念关键词
- 结果区：对比矩阵表格 + Markdown 详述

---

## 五、验收标准

| 功能 | 验收标准 |
|------|----------|
| 综述生成 | 输入关键词，生成含 4 维度的综述，Source ID 可点击跳转 |
| 对比分析 | 输入 2+ 论文/概念，生成 ≥5 维度的对比矩阵 + 场景建议 |
| 审核 | 综述/对比审核评分 ≥7.5 才保存，否则自动修复 |
| 信息保留 | 综述信息保留率 ≥80% |
| 可搜索 | 综述/对比结果可在知识浏览页搜索到 |

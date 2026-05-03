# 更新日志 - 2026-05-03

## 暗色模式 + Markdown编辑 + LLM融合判断 + 健康体检 + 一键修复

---

### 一、暗色模式全面修复

#### 1. CSS变量体系建立

**变更文件**：`web/src/index.css`

**变更内容**：
- 建立完整的CSS变量体系（`--bg-primary`、`--text-primary`、`--accent`等20+变量）
- `[data-theme="dark"]` 选择器定义暗色模式变量值
- 全局组件样式覆盖（Ant Design的Table、Card、Tag、Modal等）

#### 2. 各页面硬编码颜色修复

**变更文件**：`HomePage.tsx`、`StatusPage.tsx`、`GraphPage.tsx`、`LogManagePage.tsx`、`UserManagePage.tsx`、`PDFReaderPage.tsx`

**变更内容**：
- 所有 `color: "#xxx"` 硬编码替换为 `var(--text-primary)` 等CSS变量
- 选中行背景色从白色改为蓝色（暗色模式下可见）
- 知识图谱节点颜色适配暗色模式

---

### 二、日志时间显示修复

**问题**：后端存储UTC时间但无时区后缀，前端按本地时间解析导致显示为00:00附近

**变更文件**：`web/src/services/api.ts`

**变更内容**：
- 新增 `ensureUTC()` 函数，为无后缀的时间字符串添加 'Z'
- 强制按UTC解析后转换为本地时间显示
- 日志时间现在正确显示为北京时间

---

### 三、LLM融合判断

**问题**：基于相似度阈值的融合判断误判率高（NVIDIA两个实体相似度仅0.49但应融合）

**变更文件**：`scripts/merge.py`、`scripts/batch.py`

**变更内容**：
- 新增 `resolve_raw_doc_path()`：将源论文词干解析为原始文档路径
- 新增 `extract_context_from_raw()`：从原始论文中提取实体/概念名称周围的上下文片段
- 新增 `llm_judge_merge()`：LLM驱动的融合判断，使用结构化提示和响应解析
- 修改 `process_merge()`：使用LLM判断替代基于规则的相似性阈值
- 融合决策记录到 `merge_decisions.log`

---

### 四、Markdown编辑 + PDF对比 + KaTeX公式渲染

#### 1. 统一Markdown渲染

**新建文件**：`web/src/utils/markdown.ts`

**变更内容**：
- 统一的Markdown渲染工具，集成KaTeX公式渲染
- `$...$` 行内公式和 `$$...$$` 块级公式支持
- 代码高亮支持

#### 2. 原文编辑功能

**变更文件**：`web/src/pages/KnowledgePage.tsx`

**变更内容**：
- 三种模式切换：编辑（源码）→ 预览（渲染）→ 分屏（左编辑右预览）
- 编辑后保存到后端（PUT `/api/raw/{id}`）
- 文件重命名功能

#### 3. PDF对比查看

**变更文件**：`web/src/pages/KnowledgePage.tsx`

**变更内容**：
- 左侧Markdown渲染结果，右侧PDF原文
- 便于审核转换质量

#### 4. 后端原文更新API

**变更文件**：`api/main.py`

**变更内容**：
- 新增 PUT `/api/raw/{id}` 端点，支持原文内容更新
- 新增 PUT `/api/pages/{id}` 端点，支持wiki页面内容更新

---

### 五、系统健康体检

#### 1. 后端健康体检API

**变更文件**：`api/main.py`、`scripts/lint.py`

**变更内容**：
- POST `/api/health-check`：运行健康体检，支持 `layer` 参数（layer1/layer2/all）
- 第一层（规则检查）：孤儿页面、矛盾标记、Frontmatter、论文完整性、交叉引用断裂、重复实体、缺失概念、无Source
- 第二层（LLM增强）：概念建议、质量抽检
- 返回结构化JSON报告（健康分数、各维度得分、问题详情）

#### 2. lint.py增强

**变更文件**：`scripts/lint.py`

**变更内容**：
- 新增论文完整性检查（缺失章节检测）
- 新增交叉引用断裂检测（模糊匹配链接解析）
- 新增重复实体/概念检测（英文名匹配）
- 新增缺失概念页面检测
- 排除 `_` 开头的临时目录

#### 3. 前端健康体检页面

**变更文件**：`web/src/pages/StatusPage.tsx`、`web/src/services/api.ts`

**变更内容**：
- 健康分数圆环展示（0-100分）
- 各维度得分卡片（孤儿页面、矛盾标记、Frontmatter、论文完整性等）
- 问题详情表格（按类型分表展示）
- 体检层级切换（第一层/第二层/全部）

---

### 六、健康问题一键修复

#### 1. Frontmatter自动修复

**变更文件**：`api/main.py`

**端点**：POST `/api/fix/frontmatter/{id}`

**逻辑**：按优先级提取标题 → `# 一级标题` → `**arXiv ID**` → `**标题**` → `## 二级标题` → 文件名，写入Frontmatter。自动推断type（paper/entity/concept）。

#### 2. 论文删除并重新生成（异步）

**变更文件**：`api/main.py`

**端点**：POST `/api/fix/regenerate-paper/{id}`、GET `/api/fix/task-status/{task_id}`

**逻辑**：
1. 立即删除论文及关联的实体/概念文件
2. 启动后台线程执行 `process_document()` 重新生成
3. 立即返回 `task_id`
4. 前端轮询任务状态（每5秒）

**关键设计**：异步任务模式，避免HTTP请求超时

#### 3. 断裂链接修复

**变更文件**：`api/main.py`

**端点**：POST `/api/fix/broken-link/{id}`

**逻辑**：支持 `remove`（删除链接）和 `replace`（替换链接）两种操作

#### 4. 重复实体合并

**变更文件**：`api/main.py`

**端点**：POST `/api/fix/merge-entities`

**逻辑**：选择保留页面和删除页面，合并内容，更新所有引用

#### 5. 前端修复操作按钮

**变更文件**：`web/src/pages/StatusPage.tsx`

**变更内容**：
- 无效Frontmatter → "自动修复"按钮（Popconfirm确认）
- 论文不完整 → "删除并重新生成"按钮（红色危险按钮，异步轮询）
- 交叉引用断裂 → "删除链接"按钮
- 重复实体/概念 → "合并"按钮（Modal选择保留/删除项）

---

### 七、修改文件清单

| 文件 | 修改类型 | 修改内容 |
|------|----------|----------|
| `web/src/index.css` | 修改 | CSS变量体系+暗色模式+Ant Design覆盖 |
| `web/src/pages/HomePage.tsx` | 修改 | 硬编码颜色→CSS变量 |
| `web/src/pages/StatusPage.tsx` | 修改 | 健康体检+一键修复+暗色模式 |
| `web/src/pages/GraphPage.tsx` | 修改 | 暗色模式适配 |
| `web/src/pages/KnowledgePage.tsx` | 修改 | Markdown编辑+PDF对比+文件重命名 |
| `web/src/pages/LogManagePage.tsx` | 修改 | 暗色模式+错误状态 |
| `web/src/pages/UserManagePage.tsx` | 修改 | 暗色模式+错误状态 |
| `web/src/pages/PDFReaderPage.tsx` | 修改 | 暗色模式 |
| `web/src/utils/markdown.ts` | 新建 | 统一Markdown渲染（含KaTeX） |
| `web/src/services/api.ts` | 修改 | 新API函数+UTC时间修复 |
| `web/vite.config.ts` | 修改 | 代理超时600秒 |
| `api/main.py` | 修改 | 健康体检+修复端点+异步任务+原文更新 |
| `scripts/lint.py` | 修改 | 两层检查+模糊链接解析+临时目录排除 |
| `scripts/merge.py` | 修改 | LLM融合判断+上下文提取 |
| `scripts/batch.py` | 修改 | 传递doc_path给process_merge |

---

### 八、经验教训

1. **暗色模式必须系统化**：逐个元素修硬编码颜色不可靠，必须建立CSS变量体系，从根源上解决。Ant Design组件需要显式覆盖样式。

2. **时间处理必须明确时区**：后端存储时间时必须带时区后缀（'Z'或'+08:00'），否则前端解析结果取决于运行环境的时区设置，导致不一致。

3. **LLM判断优于规则阈值**：实体融合的相似度阈值方法误判率高（如NVIDIA相似度0.49但应融合），交给LLM+上下文判断更准确。关键是提供足够的上下文信息。

4. **长时间操作必须异步**：LLM生成+审核流程可能需要5-10分钟，HTTP同步请求必然超时。必须采用异步任务模式：立即返回task_id → 后台线程执行 → 前端轮询状态。

5. **健康检查要防误报**：链接解析需要模糊匹配（空格vs连字符、大小写），否则大量误报。临时目录（`_`开头）必须排除。

6. **Frontmatter修复需要多级兜底**：不能假设所有论文都有 `# 一级标题`，需要按优先级尝试多种标题来源（一级标题→arXiv ID→标题字段→二级标题→文件名）。

7. **VaultIndex API要一致**：`vault_index.get(id)` 不存在，应使用 `vault_index.pages.get(id)`；`vault_index.reload()` 不存在，应使用 `vault_index.scan()`。这类API不一致会导致运行时错误。

8. **前端组件语法要完整**：React条件渲染中，每个分支必须有完整的 `if` 语句，遗漏会导致语法错误和渲染失败。

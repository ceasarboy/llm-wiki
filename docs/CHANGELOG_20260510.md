# CHANGELOG 2026-05-10

## V2.3 交付 — 系统打磨与体验优化

---

## 🔍 搜索与检索

### BGE-M3 离线化
- **问题**：查询时 FlagEmbedding 直连 `huggingface.co` 超时（国内不可达）
- **修复**：`embedding_bge.py` 强制设置 `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` + `HF_ENDPOINT=https://hf-mirror.com`
- **文件**：[scripts/embedding_bge.py](../scripts/embedding_bge.py)

### 问答保存（修复假按钮）
- **问题**：QueryPage「保存到 Wiki」按钮只弹 toast，未实际保存任何数据
- **修复**：
  - 新增 `POST /api/save-query` 端点，将 Q&A 写入 `wiki/faq/YYYY-MM-DD_问题.md`
  - 文件采用 Obsidian 标准格式（无 YAML Frontmatter、`[Source:]` 标签、`[[双向链接]]`）
  - 修复 NameError（LogService/db 未定义）导致保存失败
- **文件**：[api/routers/search.py](../api/routers/search.py)、[web/src/pages/QueryPage.tsx](../web/src/pages/QueryPage.tsx)

### 热门查询增强
- 新增 `GET /api/hot-queries` 返回 `saved` 字段，扫描 `wiki/faq/` 目录获取最近 10 条已保存问答
- HomePage 热门查询卡片新增「📌 已保存的问答」分区

---

## 📚 FAQ 自动生成

### 批量生成 50 条 FAQ
- 脚本 `gen_faqs.py` 从 wiki 中扫描 concepts/entities/papers 目录
- 提取「概述」「技术特点」「应用场景」等章节 → 匹配问答模板
- 输出 Obsidian 标准格式：`# 问题` 标题 + `## 回答` + `[Source:]` 标签 + `[[wikilinks]]`
- **关键修复**：
  - 正则表达式 `\s*\n\s*` 在 re.DOTALL 模式下贪婪吞 `\n` → 改为 `\n` 精确匹配
  - `[Source:]` 同行文本导致概述提取为空 → 放宽 lookahead
  - `[Source:]` 有无 `**` 加粗两种格式兼容
- **文件**：[scripts/gen_faqs.py](../scripts/gen_faqs.py)

---

## 📊 知识库体验

### 分页功能
- 知识库列表从一次性渲染 100 条 → 每页 50 条 + Antd Pagination 翻页
- 切换 Tab 自动回第 1 页，可调整每页条数（20/50/100）
- **文件**：[web/src/pages/KnowledgePage.tsx](../web/src/pages/KnowledgePage.tsx)

### 类型过滤修复
- **问题**：综合/FAQ/探索三个 Tab 显示全部 506 页（`by_type` 缺少这三种类型）
- **修复**：
  - VaultIndex 新增 `synthesis` = survey+comparison 合集（7 篇）
  - 新增 `faq`、`exploration` 空类型
  - `faq` 目录加入 `_do_scan` 扫描路径
- **文件**：[api/dependencies.py](../api/dependencies.py)

---

## 📄 论文导入增强

### 查看 Markdown 按钮
- **问题**：ImportPage「查看Markdown」按钮无 onClick 处理
- **修复**：点击弹出 Modal 显示完整 markdown 内容
- 新增 `GET /api/pdf/markdown/{filename}` 端点
- **文件**：[api/routers/pdf.py](../api/routers/pdf.py)，[web/src/pages/ImportPage.tsx](../web/src/pages/ImportPage.tsx)

### 重新生成按钮
- ImportPage 已完成项增加「重新生成」按钮 + `POST /api/pdf/reconvert` 端点
- 重新执行 PDF→Markdown 转换并覆盖原文件
- **文件**：[api/routers/pdf.py](../api/routers/pdf.py)，[web/src/pages/ImportPage.tsx](../web/src/pages/ImportPage.tsx)

---

## 🩺 系统可靠性

### 全局异常日志
- **问题**：操作日志（SystemLog）只在成功后记录，运行时错误从未被捕获
- **新增三层错误捕获**：
  1. HTTP 中间件 — 拦截所有 4xx/5xx 响应
  2. 全局异常处理器 — 捕获未处理 Exception
  3. 搜索端点级日志
- 日志写入失败时 fallback 到 `print()` 兜底
- **文件**：[api/main.py](../api/main.py)，[api/routers/search.py](../api/routers/search.py)

---

## 🎨 UI 文案

### 首页标题更新
- 标题：「LLM-Wiki 知识库」→「个人Wiki知识库」
- 副标题：「智能知识编译系统，让知识可追溯、可复用」→「让知识沉淀、复用、迭代，构建高效、富有生命力的智能知识系统。」
- **文件**：[web/src/pages/HomePage.tsx](../web/src/pages/HomePage.tsx)

---

## 📋 文档更新

| 文档 | 更新内容 |
|------|----------|
| [README.md](../README.md) | V2 亮点、检索效果、PDF 方案说明、V3 批量转换路线 |
| [V2-development-plan.md](../docs/V2-development-plan.md) | V2.3 迭代记录 |
| [V3-development-plan.md](../docs/V3-development-plan.md) | 批量转换定时任务（Phase 3.1-A） |
| [architecture.md](../docs/architecture.md) | 版本历史至 v2.3 |

---

## 📊 数据快照

| 指标 | 值 |
|------|-----|
| Wiki 总页数 | 557 |
| FAQ 页数 | 50（自动生成） |
| 向量索引 | Qdrant + BGE-M3（1024维） |
| API 端点 | 50+ |
| 前端页面 | 16 |
| 路由模块 | 13 |

---

## 🔮 V3 展望

V3 首个交付：**批量转换定时任务**（Phase 3.1-A），解决 Marker 慢速痛点：
- SQLite 转换队列表
- APScheduler 定时调度（默认凌晨 2:00）
- 失败自动重试（最多 2 次）
- 前端进度追踪
- 配置化 cron 表达式

详见 [V3-development-plan.md](../docs/V3-development-plan.md)
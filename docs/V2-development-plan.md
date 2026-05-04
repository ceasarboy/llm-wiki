# LLM-Wiki V2 开发计划

> **版本**: V2  
> **创建日期**: 2026-05-04  
> **参考文档**: V2-requirements.md / v1-architecture-review.md  
> **开发方式**: ACP（敏捷开发）

---

## 一、迭代总览

| 迭代 | 主题 | 工期 | 优先级 |
|------|------|------|--------|
| Iteration 1 | 代码重构 + 安全加固（V1 债务清偿） | 1-2 天 | 🔴 高 |
| Iteration 2 | 综述生成 + 对比分析（核心新功能） | 2-3 天 | 🔴 高 |
| Iteration 3 | 知识图谱可视化 | 2-3 天 | 🟡 中 |
| Iteration 4 | 冲突发现面板 + 系统可靠性 | 1-2 天 | 🟡 中 |
| Iteration 5 | Citation 追溯 + 语义索引 + 文档完善 | 2-3 天 | 🟢 低 |

---

## 二、Iteration 1：代码重构 + 安全加固

> 目标：清偿 V1 技术债务，为 V2 新功能打好基础。

### 任务清单

| ID | 任务 | 描述 | 估计 | 状态 |
|----|------|------|------|------|
| V2-1.1 | 拆分 main.py | 将 ~2000行 main.py 拆为: routers/pages.py, routers/raw.py, routers/pdf.py, routers/search.py, routers/ingest.py, routers/maintenance.py | 3h | ⬜ |
| V2-1.2 | 统一 call_llm 重试 | 在 agent_g.py 的 call_llm 中加指数退避重试 (max 3 次)，统一所有 LLM 调用入口 | 1h | ⬜ |
| V2-1.3 | 前端 token 去重 | 抽取 getAuthHeaders() 到 services/api.ts 统一导出 | 0.5h | ⬜ |
| V2-1.4 | 统一 datetime 处理 | 所有 datetime 转为北京时间 (UTC+8)，统一使用 utils/datetime.ts 中的工具函数 | 1h | ⬜ |
| V2-1.5 | 添加上传大小限制 | FastAPI 中间件: max_upload_size = 50MB | 0.5h | ⬜ |
| V2-1.6 | 日志敏感字段过滤 | 确保日志中不出现 password/api_key 等敏感字段 | 0.5h | ⬜ |
| V2-1.7 | VaultIndex 增量更新 | 文件系统 watcher 或定期 rescan 对比时间戳 | 2h | ⬜ |
| V2-1.8 | ChromaDB 重建端点 | `POST /api/maintenance/rebuild-index` — 删除旧 collection 重新建 | 1h | ⬜ |

### 验收标准

- [ ] `api/routers/` 下每个文件 ≤300 行
- [ ] LLM 调用 3 次重试后抛出明确异常
- [ ] `.env` / `.yaml` 中的 key 不出现任何日志输出中
- [ ] 上传 51MB 文件返回 413
- [ ] Raw 目录增删文件后，Index 能检测到变化

---

## 三、Iteration 2：综述生成 + 对比分析

> 目标：实现 V2 的两项核心新功能，这是 V2 最关键的交付。

### 任务清单

| ID | 任务 | 描述 | 估计 | 状态 |
|----|------|------|------|------|
| V2-2.1 | scripts/survey.py | Agent_S 综述生成模块: 接收概念关键词 → 检索关联论文/实体/概念 → 构建综合 Prompt → LLM 生成结构化综述 → Source ID 校验 → 写入 synthesis | 3h | ⬜ |
| V2-2.2 | 综述 Prompt 模板 | 设计并调优综述生成的 System Prompt (时间线、突破、SOTA、开放问题四个维度) | 1h | ⬜ |
| V2-2.3 | scripts/compare.py | Agent_C 对比分析模块: 接收 2+ 论文ID → 提取实验数据 → LLM 逐维对比 → 生成对比矩阵 + 场景建议 | 2h | ⬜ |
| V2-2.4 | 对比 Prompt 模板 | 设计对比矩阵的系统提示 (维度提取、评分、场景推荐) | 1h | ⬜ |
| V2-2.5 | API 端点 | `POST /api/synthesis/survey` 和 `POST /api/synthesis/compare` | 1h | ⬜ |
| V2-2.6 | 前端界面 | 新增 SurveyPage.tsx / ComparePage.tsx，含输入表单 + Markdown 渲染结果 + Source 高亮 | 3h | ⬜ |
| V2-2.7 | Pipeline 集成 | 将 survey/compare 流程集成到 batch.py 编排器，支持批量综述生成 | 1h | ⬜ |

### 验收标准

- [ ] 输入 "Chiplet 3D 集成"，生成含 4 个维度的综述，每条事实可点击跳转 Source
- [ ] 输入 2 篇 Marker 相关论文 ID，生成 ≥5 个维度的对比矩阵
- [ ] 综述信息保留率 ≥80%（对比原始论文内容）
- [ ] 综述/对比结果页面可在知识浏览页中搜索到

---

## 四、Iteration 3：知识图谱可视化

> 目标：实现交互式知识图谱，直观展示 Wiki 中的关联关系。

### 任务清单

| ID | 任务 | 描述 | 估计 | 状态 |
|----|------|------|------|------|
| V2-3.1 | 图数据 API | `GET /api/graph/nodes` + `GET /api/graph/edges` — 从 Wiki 解析出实体/概念/论文及其关系 | 2h | ⬜ |
| V2-3.2 | 关系抽取 | 从页面内容中提取 [[双向链接]] 和 frontmatter 的 related_* 字段 | 1h | ⬜ |
| V2-3.3 | 图渲染组件 | `KnowledgeGraph.tsx` 基于 D3.js/Cytoscape.js，含力导向布局、拖拽、缩放 | 4h | ⬜ |
| V2-3.4 | 节点交互 | 点击展开/折叠关联节点、tooltip 显示摘要、双击跳转页面详情 | 2h | ⬜ |
| V2-3.5 | 筛选器 | 按节点类型/领域/时间筛选，路径搜索（A→B 经过哪些节点） | 1.5h | ⬜ |
| V2-3.6 | 导出功能 | PNG/SVG 导出用于论文配图 | 1h | ⬜ |

### 验收标准

- [ ] 页面加载 3 秒内渲染完成（1000 节点以内）
- [ ] 支持拖拽、缩放、节点展开/折叠
- [ ] 筛选器至少支持 3 种筛选方式

---

## 五、Iteration 4：冲突发现 + 系统可靠性

> 目标：自动发现知识库矛盾，增强系统自愈能力。

### 任务清单

| ID | 任务 | 描述 | 估计 | 状态 |
|----|------|------|------|------|
| V2-4.1 | scripts/conflict_detector.py | 同主题论文逐对对比 → LLM 判断是否存在矛盾 → 生成 Conflict 报告 | 2h | ⬜ |
| V2-4.2 | 冲突前端面板 | ConflictPanel.tsx: 展示冲突清单/筛选/标记已解决/忽略 | 2h | ⬜ |
| V2-4.3 | 健康检查自动化 | HealthChecker 定时任务（配置间隔，默认 24h），结果保存为报告 | 1h | ⬜ |
| V2-4.4 | Alembic 引入 | 数据库迁移框架搭建，初始化 migration | 1h | ⬜ |
| V2-4.5 | Docker 部署 | Dockerfile + docker-compose.yml，开发/生产双模式 | 1.5h | ⬜ |

### 验收标准

- [ ] 自动发现 ≥90% 的同主题矛盾
- [ ] 健康检查 24h 自动运行一次，失败时发通知
- [ ] `docker-compose up` 一键启动全栈

---

## 六、Iteration 5：Citation + 语义索引 + 文档

> 目标：补充边缘功能和文档完善，V2 收尾。

### 任务清单

| ID | 任务 | 描述 | 估计 | 状态 |
|----|------|------|------|------|
| V2-5.1 | Citation 追溯 | 从论文页面提取引用信息，构建引用图，前端展示引用链 | 2h | ⬜ |
| V2-5.2 | 语义索引生成 | 自动按方向/时间/实体分组生成 index.md | 1.5h | ⬜ |
| V2-5.3 | 知识过期检测 | 对比新旧论文结论，标记过期页面 | 1.5h | ⬜ |
| V2-5.4 | API 文档增加示例 | 补充请求/响应 JSON 示例 | 1h | ⬜ |
| V2-5.5 | 运行时架构文档 | 补充线程模型、请求处理流程说明 | 1h | ⬜ |

---

## 七、风险与依赖

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LLM API 不稳定 | 综述/对比生成失败 | call_llm 3 次重试 + 状态恢复 |
| 大图渲染性能 | 图谱页面卡顿 | 虚拟化渲染 + 节点数上限 |
| ChromaDB 与 Wiki 不一致 | 综述遗漏论文 | 加一致性校验，提供重建端点 |
| 对 V1 API 的破坏性变更 | 前端兼容问题 | 新增 API，不动旧端点 |

---

## 八、V2 版本号规划

```
V2.0.0 — I1+I2 完成（核心价值可交付）
V2.1.0 — I3 完成（图谱可视化上线）
V2.2.0 — I4 完成（冲突发现 + 可靠性）
V2.3.0 — I5 完成（V2 完整版）
```

---

## 九、迭代记录

| 日期 | 迭代 | 状态 | 备注 |
|------|------|------|------|
| 2026-05-04 | - | 计划制定 | V2 开发计划初稿 |

---

*本文档基于 V2-requirements.md 和 v1-architecture-review.md 制定。执行方式遵循 ACP 流程。*

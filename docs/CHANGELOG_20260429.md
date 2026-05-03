# LLM-Wiki 知识库系统 v3.0 迭代记录
## 日期：2026-04-29

---

## 问题概述
在 LLM-Wiki 知识库系统中，发现了两个主要问题：
1. 原文中的图片无法正常显示
2. Markdown 文章字体太小且缺少样式

---

## 解决的问题

### 问题 1：原文图片无法显示
**问题描述**：
- 用户在 Obsidian 中可以正常查看文章，但在系统的原文显示页面中，图片无法正确渲染。
- 图片路径处理存在问题，需要正确映射到后端静态文件服务。

**解决方法**：
- 增强 `renderMarkdown` 函数，支持更多的路径处理逻辑：
  - 完整 URL 直接使用
  - `../../../` 前缀的路径
  - `../` 前缀的路径
  - 纯文件名（默认在 raw/papers/markdown 目录
- 使用 `/api/assets` 静态文件服务来提供图片资源

**涉及文件**：
- `web/src/pages/KnowledgePage.tsx`

---

### 问题 2：Markdown 渲染问题
**问题描述**：
- 字体大小仅为 13px，阅读体验差
- 使用简单的正则表达式解析 Markdown，支持的语法有限
- 缺少完整的样式系统，如标题、列表、代码块、表格等样式缺失或不完善

**解决方法**：
1. **引入成熟的 Markdown 解析库
   - 安装 `marked` 库替代简单的正则表达式解析
   - 配置 `marked` 支持 GFM (GitHub Flavored Markdown) 和换行支持
2. **优化样式系统**
   - 字体大小调整为 16px，行高设置为 1.8
   - 完整的标题样式（h1-h6），带有下划线层级
   - 列表样式（有序和无序）
   - 代码块和行内代码样式
   - 引用块样式
   - 表格样式
   - 图片样式
   - 链接样式
3. **统一两个页面的渲染逻辑**
   - KnowledgePage.tsx（原文显示）
   - PageDetailPage.tsx（Wiki 页面详情）

**涉及文件**：
- `web/src/pages/KnowledgePage.tsx`
- `web/src/pages/PageDetailPage.tsx`

---

## 技术实现细节

### 1. marked 库集成

```javascript
// 配置 marked
marked.setOptions({
  breaks: true,
  gfm: true,
});

// 处理流程：
1. 先替换图片路径
2. 使用 marked 解析 Markdown
3. 后处理 Source 标记和 Wiki 链接
```

### 2. 样式系统

```css
.markdown-content {
  font-size: 16px;
  line-height: 1.8;
}

.markdown-content h1 {
  font-size: 28px;
  border-bottom: 2px solid var(--border-color);
}

// ... 更多样式
```

---

## 经验教训

### 1. 不要重复造轮子
- **问题**：自己实现的正则表达式解析器既复杂又容易出错
- **教训**：在 Markdown 这种成熟的领域，应该使用成熟的开源库
- **行动**：在未来的开发中，优先考虑使用 `marked`、`remark`、`markdown-it` 等成熟库

### 2. 用户体验优先
- **问题**：13px 的字体太小，行高不够，阅读困难
- **教训**：在开发过程中要重视用户体验，确保内容可读性
- **行动**：建立用户体验检查清单，确保字体大小、行高、间距等符合最佳实践

### 3. 统一代码组织
- **问题**：两个页面有相似的功能，但实现方式不同
- **教训**：应该将通用的渲染逻辑抽取成可复用的组件
- **行动**：在未来的重构中，考虑将 Markdown 渲染和样式系统抽取成独立的组件库

### 4. 完整的测试
- **问题**：图片路径处理不完善
- **教训**：需要考虑各种边缘情况
- **行动**：建立更完整的测试覆盖，确保各种路径格式都能正常工作

---

## 验证结果
- ✅ TypeScript 编译通过
- ✅ 构建成功
- ✅ 代码审查通过
- ✅ 样式优化完成

---

## 后续改进建议

1. **短期**：
- 将 Markdown 渲染和样式系统抽取成独立的组件
- 添加更多的样式主题支持
- 完善图片上传和管理功能

2. **长期**：
- 考虑使用更强大的 Markdown 渲染库（如 react-markdown）
- 添加公式渲染支持（KaTeX/MathJax）
- 添加语法高亮支持（highlight.js/prism）
- 完善的单元测试和集成测试

---

## 相关文档
- [CLAUDE.md](../CLAUDE.md) - LLM 行为规范
- [项目文档目录](../doc/)

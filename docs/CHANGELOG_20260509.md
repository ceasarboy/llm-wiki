# 更新日志 - 2026-05-09

## PDF 转换器选型评估 — Marker vs OpenDataLoader Hybrid

---

### 一、评估背景

OpenDataLoader 声称 Hybrid 模式（Java + Docling 后端）可以在速度和精度之间取得平衡，且支持 Formula 公式提取和 Picture Description 图片描述等增强功能。需要评估它是否能在不牺牲质量的前提下替代或补充当前使用的 Marker。

**评估文件**：DeepSeek-V3.pdf（53页，1.8MB，数字原生 PDF）

---

### 二、环境搭建

#### 1. 本地 HuggingFace 模型缓存

通过 HF Mirror 下载所需模型到本地缓存，避免网络不稳定：

| 模型 | 大小 | 路径 |
|------|------|------|
| docling-models (tableformer) | ~357MB | `E:\ragtest\.hf_cache\hub\models--docling-project--docling-models\` |
| docling-layout-heron | ~171MB | `E:\ragtest\.hf_cache\hub\models--docling-project--docling-layout-heron\` |
| CodeFormulaV2 | ~631MB | `E:\ragtest\.hf_cache\hub\models--docling-project--CodeFormulaV2\` |

关键环境变量：
```powershell
$env:HF_ENDPOINT="https://hf-mirror.com"
$env:HF_HOME="E:\ragtest\.hf_cache"
$env:_JAVA_OPTIONS="-Xmx8g"
$env:PYTHONDONTWRITEBYTECODE=1
```

#### 2. TRAE Sandbox 兼容性

**发现并解决的问题**：
- 直接修改 `site-packages` 下的源码（`runner.py`、`hybrid_server.py`）会导致 Sandbox 阻止 `.pyc` 缓存文件写入，Python 模块导入卡死
- **解决**：回滚所有源码修改，通过环境变量传递配置（`_JAVA_OPTIONS`、`HF_HOME`）
- Sandbox 允许列表仅包含 `e:\ragtest`、临时目录等，不能写入 `C:\Users\Administrator\.cache\`，因此必须使用自定义 `HF_HOME`

---

### 三、测试结果

#### 测试 1：OpenDataLoader Fast 模式（纯 Java）

| 指标 | 值 |
|------|-----|
| 耗时 | 5.52 秒 |
| 输出 | 142KB Markdown |
| 公式 | 无 LaTeX，Unicode 近似字符 |
| 表格 | 基本可用 |

#### 测试 2：OpenDataLoader Hybrid auto + fallback（推荐模式）

配置：`hybrid='docling-fast'`, `hybrid_mode='auto'`, `hybrid_fallback=True`

| 指标 | 值 |
|------|-----|
| 耗时 | 45.63 秒 |
| 输出 | 142KB Markdown + 703KB JSON |
| 分诊结果 | JAVA=18 页（简单），BACKEND=35 页（复杂） |
| 后端成功 | 8 页（表格/布局识别由 docling 处理） |
| 后端失败 | 27 页（`std::bad_alloc`，fallback 到 Java） |
| 退出码 | 0（成功） |

`hybrid_fallback=True` 机制生效：后端失败的页面自动回退到 Java 处理，最终输出了完整的 53 页。

#### 测试 3：Hybrid + Formula 公式提取

配置：server 端 `--enrich-formula`，CodeFormulaV2 模型

| 指标 | 值 |
|------|-----|
| 模型加载 | 成功（5.02s，`enrichments=formula`） |
| 分诊结果 | JAVA=18，BACKEND=35 |
| 后端成功 | 4 页（1, 5, 7, 8） |
| 后端失败 | 31 页（`std::bad_alloc`） |
| 公式输出 | **无** — 即使 4 页"成功"，公式也未出现在 Markdown/JSON 输出中 |

#### 测试 4：Hybrid + Picture Description

- SmolVLM 模型 ~2GB，下载+推理时间过长且内存不足
- 未完成测试

---

### 四、结论与决策

**决策：保持使用 Marker 作为主 PDF 转换器。**

| 维度 | Marker | OpenDataLoader Hybrid |
|------|--------|----------------------|
| **公式提取** | ✅ LaTeX `$$\mathbf{}$$` | ❌ Unicode 近似 / 增强模式内存不足 |
| **引用链接** | ✅ `(Author, 2024)` 可点击 | ❌ 纯文本 |
| **页锚定位** | ✅ `<span id="page-X-Y">` | ❌ 无 |
| **表格质量** | ✅ 结构良好 | ⚠️ 仅 docling 处理的 8 页质量好 |
| **速度** | ⚠️ 慢（分钟级） | ✅ 快（5-45秒） |
| **内存要求** | ✅ 低 | ❌ 增强模式需 GPU（CPU 上 32GB 不够） |

OpenDataLoader 的优势是速度，在不需要精细公式/引用解析的场景可用。但对于 LLM-Wiki 知识库的高质量要求，Marker 的精度不可替代。

---

### 五、生成的产物

| 文件 | 说明 |
|------|------|
| `pdf_compare/compare.html` | 左右分屏对比页面（MathJax 渲染公式） |
| `pdf_compare/test_hybrid/DeepSeek-V3.md` | Hybrid auto+fallback 输出 |
| `pdf_compare/test_fast/DeepSeek-V3.md` | Fast 模式输出 |
| `pdf_compare/gen_compare.py` | 对比 HTML 生成脚本 |
| `.hf_cache/` | 本地 HF 模型缓存（可复用） |

---

### 六、经验教训

详见 [转换器选型经验教训](#) — 见 V3-development-plan.md 迭代记录及下方要点。

**关键教训**：
1. **不要在 TRAE Sandbox 中修改 Python 包源码** — 用环境变量传递配置
2. **HF_HOME 路径必须在 Sandbox 允许列表中**（`e:\ragtest` 可用，`~\.cache` 不可用）
3. **CPU 推理大模型（>500MB）不可行** — `std::bad_alloc` 频繁，需 GPU
4. **hybrid_mode='auto' + hybrid_fallback=True** 是最优降级策略
5. **先评估再替换** — 不能仅凭文档声称的性能做决策，需实测验证

---

*记录人：Agent | 记录日期：2026-05-09*
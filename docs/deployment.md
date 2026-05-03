# LLM-Wiki 部署与运维文档

> **版本**: V1  
> **适用环境**: Windows 10/11  
> **目标用户**: 10 人以下团队  
> **最后更新**: 2026-05-03

---

## 一、环境要求

### 最低配置

| 组件 | 要求 | 说明 |
|------|------|------|
| 操作系统 | Windows 10/11 (x64) | 亦支持 Linux/macOS（未测试） |
| Python | 3.12+ | 建议 3.12 |
| Node.js | 18+ | 前端构建需要 |
| 内存 | 16 GB | PDF 转换和 LLM 推理需要较大内存 |
| 磁盘 | 5 GB+ | 含 Marker 模型 ~2GB、ChromaDB ~1GB、Wiki 数据 |
| 网络 | 需访问 DeepSeek API | 仅 LLM 调用需要；首次启动需下载 HuggingFace 模型（已配置国内镜像） |

### 推荐配置

| 组件 | 推荐 |
|------|------|
| Python | 3.12.4 |
| Node.js | 20 LTS |
| 内存 | 32 GB |
| GPU | NVIDIA GPU（加速 PDF 转换） |

---

## 二、快速开始

### 2.1 一键启动（Windows）

项目根目录提供了 `start-dev.bat` 脚本，双击即可启动：

```batch
双击运行: e:\ragtest\start-dev.bat
```

该脚本会自动：
1. 启动 Python 后端（http://localhost:8000）
2. 启动 Vite 前端（http://localhost:5173）
3. 配置国内镜像环境变量

启动后：
- **前端访问**: http://localhost:5173
- **API 文档**: http://localhost:8000/docs
- **默认账号**: `admin` / `admin`

### 2.2 手动安装步骤

如果是首次部署，按以下步骤操作：

#### Step 1: 安装 Python 环境

```powershell
# 创建虚拟环境（推荐）
cd e:\ragtest
python -m venv venv
.\venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

#### Step 2: 安装前端依赖

```powershell
cd e:\ragtest\web
npm install
```

#### Step 3: 配置文件确认

编辑 `e:\ragtest\config.yaml`，确认以下路径正确：

```yaml
paths:
  wiki_dir: "C:/Users/Administrator/Documents/Obsidian Vault/wiki"
  raw_dir: "C:/Users/Administrator/Documents/Obsidian Vault/raw/papers/markdown"
  index_dir: "E:/ragtest/index"

llm:
  model: "deepseek-v4-flash"          # 使用的 LLM 模型
  api_url: "https://api.deepseek.com/chat/completions"
  api_key: "your-api-key-here"        # 替换为你的 API Key
```

> **注意**：`wiki_dir` 和 `raw_dir` 必须指向正确的 Obsidian Vault 路径。如果没有 Obsidian Vault，创建对应的空目录即可。

#### Step 4: 初始化数据库

```powershell
python -c "from api.database import init_db; init_db()"
```

#### Step 5: 启动服务

```powershell
# 终端 1: 启动后端
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2: 启动前端
cd web
npx vite
```

---

## 三、目录结构说明

首次部署需要确保以下目录存在（程序会自动创建，也可手动预建）：

```
e:\ragtest\
├── data/              # 数据库文件自动创建于此
├── index/chroma/      # ChromaDB 向量索引
├── generated/         # 生成过程中间文件（批处理产物）
├── reports/           # 批量导入汇总报告
└── batch_state.json   # 批量处理状态文件（自动生成）
```

Obsidian Vault 相关目录（需预先存在或手动创建）：

```
{Obsidian Vault}\
├── wiki\
│   ├── papers\        # 论文精要页面
│   ├── entities\      # 实体页面
│   ├── concepts\      # 概念页面
│   └── syntheses\     # 综合页面
└── raw\
    └── papers\
        └── markdown\  # PDF 转换后的原始 Markdown
```

---

## 四、配置文件详解 (`config.yaml`)

### 4.1 路径配置 (`paths`)

| 配置项 | 说明 | 示例值 |
|--------|------|--------|
| `wiki_dir` | Obsidian Vault 的 wiki 子目录 | `C:/.../Obsidian Vault/wiki` |
| `raw_dir` | 原始 Markdown 文件目录 | `C:/.../Obsidian Vault/raw/papers/markdown` |
| `index_dir` | ChromaDB 索引存储目录 | `E:/ragtest/index` |
| `vault_root` | Obsidian Vault 根目录 | `C:/.../Obsidian Vault` |

### 4.2 LLM 配置 (`llm`)

| 配置项 | 说明 | 建议值 |
|--------|------|--------|
| `model` | 使用的模型名称 | `deepseek-v4-flash`（便宜快速）或 `deepseek-chat`（高质量） |
| `api_url` | API 端点 | DeepSeek 官方或其他兼容 OpenAI 接口的服务 |
| `api_key` | API 密钥 | 从 DeepSeek 控制台获取 |
| `temperature` | 生成随机性 | `0.3`（论文生成需要准确性，不宜过高） |
| `max_tokens` | 最大输出长度 | `8192`（论文内容较长） |
| `timeout` | API 超时时间（秒） | `300` |

### 4.3 索引配置 (`index`)

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `chunk_size` | 文本分块大小 | `512` |
| `chunk_overlap` | 分块重叠大小 | `50` |
| `collection_name` | ChromaDB 集合名称 | `llm_wiki` |

### 4.4 搜索配置 (`search`)

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `top_k` | 返回结果数量 | `10` |
| `vector_weight` | 向量搜索权重 | `0.7` |
| `keyword_weight` | 关键词搜索权重 | `0.3` |

### 4.5 审核配置 (`scoring`)

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `pass_threshold` | 审核通过分数 | `7.5` |

---

## 五、常见问题排查

### 问题 1: 启动后端报错 `ModuleNotFoundError`

**现象**：`ModuleNotFoundError: No module named 'xxx'`

**解决**：
```powershell
# 确保在正确的 Python 环境中
pip install -r requirements.txt

# 如果使用虚拟环境，确保已激活
.\venv\Scripts\activate
```

### 问题 2: 前端代理连接失败 (`ECONNREFUSED`)

**现象**：前端页面加载但 API 请求失败，Vite 控制台输出 `http proxy error: /api/... AggregateError [ECONNREFUSED]`

**原因**：后端未启动，或启动在错误的端口

**解决**：
```powershell
# 确认后端在 8000 端口运行
netstat -ano | findstr :8000

# 如果没有输出，启动后端
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000

# 前端 vite.config.ts 代理默认指向 8000 端口，确保一致
```

### 问题 3: PDF 转换失败或超时

**现象**：上传 PDF 后点击转换，长时间无响应或报错

**原因**：
- Marker 引擎首次运行需下载大量模型（~2GB+），可能超时
- 内存不足（PDF 转换需要较多内存）
- PDF 文件格式复杂（大量图片、公式）

**解决**：
- 第一次转换耐心等待（可能需要 5-10 分钟下载模型）
- 检查系统内存使用
- 对于超大 PDF（100MB+），考虑先在本地用其他工具转 Markdown

### 问题 4: LLM API 调用失败

**现象**：生成页面失败，日志显示 `LLM调用失败` 或 API 错误

**原因**：
- API Key 未配置或已过期
- API 余额不足
- 网络连接问题

**解决**：
```yaml
# 检查 config.yaml 中的 api_key 是否正确
# 访问 https://platform.deepseek.com 检查账户余额
# 测试 API 连通性：
python -c "import requests; print(requests.get('https://api.deepseek.com').status_code)"
```

### 问题 5: 新建 Wiki 页面在前端不可见

**现象**：PDF 转换或导入后，知识库列表中没有新页面

**原因**：Vault 索引在启动时构建，不会自动检测新文件

**解决**：
```powershell
# 方法1: 调用 rescan API
curl -X POST http://localhost:8000/api/pages/rescan

# 方法2: 在 Status 页面点击"刷新"按钮

# 方法3: 重启后端（启动时会自动扫描）
```

### 问题 6: ChromaDB 索引损坏或为空

**现象**：搜索和问答无结果，或报 ChromaDB 相关错误

**解决**：
```powershell
# 重建索引
python scripts/indexer_simple.py
# 或使用旧版索引器
python scripts/indexer.py --reset --wiki
```

### 问题 7: 批量导入失败后无法重试

**现象**：导入失败后显示"所有文档已处理完毕"，无法重新处理

**解决**：
```powershell
# 重试失败文档
python scripts/batch.py --retry-failed --max-batches 1
```

### 问题 8: 前后端端口冲突

**现象**：启动时提示端口被占用

**解决**：
```powershell
# 查找占用端口的进程
netstat -ano | findstr :8000
netstat -ano | findstr :5173

# 杀掉进程（替换 PID）
taskkill /PID <进程ID> /F
```

---

## 六、日常运维

### 6.1 健康检查

建议每周运行一次系统健康体检：

1. 打开前端 Status 页面
2. 点击"运行体检"
3. 查看报告，处理发现的问题

### 6.2 索引维护

当搜索结果感觉不准时：

```powershell
python scripts/indexer_simple.py
```

### 6.3 数据备份

需要备份的关键数据：

```
backup_list:
  - data/llm_wiki.db              # 用户和日志数据
  - config.yaml                   # 系统配置
  - batch_state.json              # 导入状态
  - {Obsidian Vault}/wiki/        # Wiki 页面（最重要）
  - {Obsidian Vault}/raw/         # 原始 Markdown
```

ChromaDB 索引可以不备份（可从 Wiki 页面重建）。

### 6.4 日志查看

系统日志存储在 SQLite 数据库中，可通过前端 LogManage 页面查看，或直接查询：

```python
import sqlite3
conn = sqlite3.connect("data/llm_wiki.db")
cursor = conn.execute("SELECT * FROM logs ORDER BY created_at DESC LIMIT 50")
for row in cursor:
    print(row)
```

---

## 七、性能调优建议

| 场景 | 建议 |
|------|------|
| PDF 转换慢 | 使用 NVIDIA GPU（需安装 CUDA 版 PyTorch） |
| LLM 生成慢 | 使用 `deepseek-v4-flash` 模型（速度快 3-5 倍） |
| 搜索慢 | 减少 `chunk_size`、增加 `chunk_overlap` |
| 前端卡顿 | 知识图谱大型时可减少渲染节点数 |
| 数据库锁 | ≤10 用户场景 SQLite 无问题，无需更换 |

---

## 八、环境变量

系统支持以下环境变量（可选配置）：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HF_ENDPOINT` | HuggingFace 镜像地址 | `https://hf-mirror.com` |
| `HF_HUB_OFFLINE` | 离线模式（不从网络下载） | `1` |
| `TRANSFORMERS_OFFLINE` | Transformers 离线模式 | `1` |
| `JWT_SECRET_KEY` | JWT 签名密钥 | 开发默认值（生产需更换） |
| `ENVIRONMENT` | 运行环境 | `development` |
| `DATABASE_URL` | 数据库路径 | `sqlite:///./data/llm_wiki.db` |

---

## 九、生产环境检查清单

部署到生产环境前，请确认以下事项：

- [ ] 修改 `JWT_SECRET_KEY` 环境变量为强随机字符串
- [ ] 设置 `ENVIRONMENT=production`
- [ ] 确认 `config.yaml` 中 API Key 正确
- [ ] 将前端构建为生产版本（`npm run build`）
- [ ] 使用 Nginx 或其他反向代理（可选）
- [ ] 配置定时健康检查（如 Windows 计划任务）
- [ ] 设置自动备份脚本

---

*如有未覆盖的问题，请查阅项目 CHANGELOG 或联系开发团队。*

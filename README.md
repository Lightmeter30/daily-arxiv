# Daily Arxiv CV/AI Briefing

这是一个自动化的 arXiv 论文简报系统，专注于 3D 重建、SLAM、VIO、相机定位、NeRF / Gaussian Splatting 等领域。

## 功能特点
- **自动化**: 每天早上 8 点（北京时间）自动运行，检索 arXiv 上**前一天**发表的相关论文。
- **精准检索**: 仅匹配关键词命中的论文，避免对宽泛主题进行全量抓取，节省 API 调用。
- **AI 总结**: 使用 DeepSeek 阅读摘要，生成标签、中文 TL;DR，以及 Motivation / Method / Result / Conclusion 四段结构化摘要。
- **动态保留**: 仅保留最近 7 天的论文记录。
- **零成本**: 基于 GitHub Actions 和 GitHub Pages 构建。

## 可配参数

以下参数全部支持通过环境变量覆盖，无需修改代码即可调整。在 GitHub 仓库中，可通过 `Settings → Secrets and variables → Actions → Variables` 设置。

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `ARXIV_KEYWORDS` | `3D Reconstruction,SLAM,...` | 检索关键词，英文逗号分隔（不含空格） |
| `ARXIV_CATEGORIES` | `cs.CV,cs.AI` | arXiv 分类，逗号分隔 |
| `ARXIV_MAX_DAYS` | `7` | 保留最近 N 天的论文 |
| `ARXIV_MAX_PAPERS_PER_RUN` | `40` | 单次最多处理的新论文数 |
| `ARXIV_BACKFILL_LIMIT` | `20` | 每次补全历史论文扩展字段的上限 |
| `DEEPSEEK_API_KEY` | — | **必填**，模型服务商的 API 密钥（通过 `Secrets` 设置） |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | 兼容 OpenAI 接口的模型服务地址 |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | 模型服务商提供的模型 ID |

## 如何部署到自己的仓库
1.  **新建仓库**: 在 GitHub 上创建一个新的仓库。
2.  **上传代码**: 将 `arxiv-daily` 文件夹中的内容上传到你的仓库。注意：`.github` 文件夹必须位于仓库的**根目录**下，GitHub Actions 才能正常识别并运行。如果你的仓库根目录下已有其他项目，请将 `arxiv-daily/.github` 移动到根目录。
3.  **设置 Secret**:
    - 前往仓库的 `Settings` -> `Secrets and variables` -> `Actions`。
    - 点击 `New repository secret`。
    - Name: `DEEPSEEK_API_KEY`
    - Value: 填入你的 DeepSeek API Key（可在 [DeepSeek Platform](https://platform.deepseek.com/) 获取）。
4.  **开启 Pages**:
    - 前往仓库的 `Settings` -> `Pages`。
    - Build and deployment -> Source: `Deploy from a branch`。
    - Branch: `main` (或你的主分支)，文件夹选择 `/arxiv-daily/docs`（或者如果你将 `docs` 移到了根目录，则选择 `/docs`）。
5.  **手动触发**:
    - 前往仓库的 `Actions` 标签。
    - 选择 `Daily Arxiv Update` 流程。
    - 点击 `Run workflow` 手动运行第一次抓取。

## 开发与本地运行
```bash
# 安装依赖
pip install -r scripts/requirements.txt

# 设置环境变量
export DEEPSEEK_API_KEY="your_api_key"
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
export DEEPSEEK_MODEL="deepseek-v4-flash"

# 或者使用 .env 文件（推荐）
cp .env.example .env
# 编辑 .env，填写密钥、服务地址和模型名

# 运行脚本
python scripts/fetch_and_summarize.py
```
数据将更新在 `docs/data.json` 中。

切换兼容 OpenAI 接口的模型服务商时，修改 `.env` 中的 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL` 和 `DEEPSEEK_MODEL` 即可，变量名保持不变。现有进程环境变量优先于 `.env`；`.env` 已被 Git 忽略，请勿提交真实密钥。在 GitHub Actions 中，密钥通过同名 Secret 设置，地址和模型名通过同名仓库 Variable 设置。

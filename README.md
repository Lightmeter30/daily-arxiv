# Daily Arxiv CV/AI Briefing

这是一个自动化的 arXiv 论文简报系统，专注于 3D 重建、SLAM、VIO 和相机定位等领域。

## 功能特点
- **自动化**: 每天早上 8 点（北京时间）自动运行。
- **AI 总结**: 使用 DeepSeek 阅读摘要，生成标签和中文 TL;DR。
- **动态保留**: 仅保留最近 7 天的论文记录。
- **零成本**: 基于 GitHub Actions 和 GitHub Pages 构建。

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

# 或者使用 .env 文件（推荐）
echo "DEEPSEEK_API_KEY=your_api_key" > .env

# 运行脚本
python scripts/fetch_and_summarize.py
```
数据将更新在 `docs/data.json` 中。

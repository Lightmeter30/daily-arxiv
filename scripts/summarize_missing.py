"""
补充总结脚本：对 data.json 中所有未完整总结的论文进行 AI 总结。

用法：
    python scripts/summarize_missing.py              # 处理全部未总结论文
    python scripts/summarize_missing.py --limit 10   # 限制处理数量
"""

import json
import os
import sys
import time
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

DATA_FILE = "docs/data.json"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
MODEL_ID = os.getenv("DEEPSEEK_MODEL") or "deepseek-v4-flash"

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")


def is_summarized(paper: dict) -> bool:
    """检查论文是否已经完整总结。"""
    extended_fields = ("motivation", "method", "result", "conclusion")
    failure_values = {"Unknown", "摘要生成失败。"}

    tags = paper.get("tags", [])
    if not tags or tags in (["Unknown"],):
        return False

    tldr = paper.get("tldr", "")
    if not tldr or tldr in failure_values:
        return False

    for field in extended_fields:
        value = paper.get(field, "")
        if not value:
            return False

    return True


def summarize_paper(paper: dict) -> dict:
    """对单篇论文进行 AI 总结，返回更新后的论文字典。"""
    system_prompt = """
You are a professional AI researcher. Analyze the following paper abstract and produce a structured JSON summary in Simplified Chinese.

Return ONLY valid JSON with exactly these fields (all string values must be in Simplified Chinese, except that proper nouns and method names may remain in English):
{
    "tags": ["tag1", "tag2", "tag3"],
    "tldr": "一句话中文总结",
    "motivation": "研究动机与要解决的问题",
    "method": "核心方法与技术路线",
    "result": "主要实验结果与量化指标",
    "conclusion": "结论、贡献与潜在影响"
}

Rules:
- "tags" should contain 3 to 5 concise English tags (e.g., SLAM, NeRF, Localization).
- "tldr" must be a single Chinese sentence within 80 characters.
- motivation / method / result / conclusion should each be 1-3 Chinese sentences; be specific and information-dense, avoid generic wording.
- If the abstract does not contain enough information for a field, write "摘要未提供相关信息" for that field.
"""
    user_prompt = f"""
Paper Title: {paper['title']}
Abstract: {paper['abstract']}
"""

    max_retries = 5
    base_delay = 10

    summary = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            summary = json.loads(response.choices[0].message.content)
            break
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                wait_time = base_delay * (2 ** attempt)
                print(f"DeepSeek 限流 '{paper['title']}'，等待 {wait_time}s（第 {attempt + 1}/{max_retries} 次重试）...")
                time.sleep(wait_time)
            else:
                print(f"总结失败 {paper['title']}: {e}")
                break
    else:
        print(f"总结 '{paper['title']}' 失败，已重试 {max_retries} 次。")

    defaults = {
        "tags": ["Unknown"],
        "tldr": "摘要生成失败。",
        "motivation": "摘要未提供相关信息",
        "method": "摘要未提供相关信息",
        "result": "摘要未提供相关信息",
        "conclusion": "摘要未提供相关信息",
    }
    if summary is None:
        paper.update(defaults)
    else:
        for k, v in defaults.items():
            paper[k] = summary.get(k, v) or v

    time.sleep(1)
    return paper


def main():
    limit = None
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])

    if not DEEPSEEK_API_KEY:
        print("错误: DEEPSEEK_API_KEY 未设置。")
        sys.exit(1)

    if not os.path.exists(DATA_FILE):
        print(f"错误: {DATA_FILE} 不存在。")
        sys.exit(1)

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    missing = [p for p in data if not is_summarized(p)]

    if not missing:
        print("所有论文已完成总结，无需处理。")
        return

    if limit and limit < len(missing):
        missing = missing[:limit]

    print(f"共 {len(data)} 篇论文，其中 {len(missing)} 篇未完整总结（限制 {limit or '无'}）")

    for i, paper in enumerate(missing):
        title = paper.get("title", "无标题")
        print(f"[{i+1}/{len(missing)}] 正在总结: {title}")
        summarize_paper(paper)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"补充总结完成，已更新 {len(missing)} 篇论文。")


if __name__ == "__main__":
    main()

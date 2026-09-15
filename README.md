# daily_news · 研究与智能日报

网站：https://wdqqdw.github.io/daily_news/

每日 3 篇研究论文 + 国内外 AI 公司新闻，支持手机浏览与独立 HTML 历史归档。

## 三个固定栏目

1. **LLM 对人的理解与建模**：认知、行为预测、心理理论、脑与模型表征；优先 Nature / Science / Cell 及名称含品牌的正式研究期刊。
2. **人的科学**：不限制期刊品牌，关注认知、行为、心理、神经和人机交互，自动候选至少有 5 次 Crossref 引用。
3. **跨领域热点**：从 Crossref 跨学科候选中选取高关注研究。以引用总数及每月引用率为热度代理，不能等同于全网实时最热。查询最近一年与最近 90 天的高引用论文，合并去重。

技术报告、模型卡、系统卡只归公司动态；不占论文名额。自动论文入口限定正式 `journal-article`，排除可识别的综述、社论、概念评论、勘误、撤稿等。纯预印本暂不自动纳入。

## 每天 09:00 自动更新

GitHub Actions 在北京时间每天 **09:00**（UTC 01:00）运行，依次抓取、筛选、检查、保存并发布 GitHub Pages。无需本地电脑开机、无需 API 密钥或付费模型服务。

- 代码和日报 JSON / HTML 均保存在本仓库。
- 每天只生成一份；重复运行不会覆盖当天或历史推送。
- 以 DOI 去重，优先未推送的研究；不足时明确标为历史重温。
- 第一栏优先近 180 天，必要时扩至 730 天；品牌期刊不足时才采用其他期刊并标注。第二栏综合影响力与新近程度，最多回溯 730 天。第三栏最多回溯 365 天。
- 无法获得 3 篇合格论文或没有可用公司动态时，任务报错并保留原网页，避免空白页面或编造内容。
- 原始日期与筛选数据保存在每期 JSON 中；网页显示实际生成时间。
- GitHub 定时触发可能排队延迟，不是精确到秒的定时服务。公开仓库连续 60 天无活动时，平台可能停用计划任务；正常每日提交会产生仓库活动。
- 本项目的“推送”指网站更新，没有发送邮件或手机通知。

## 内容来源与语言

论文使用 Crossref 公开元数据。官网核验的创刊期提供中文概述；后续无人值守更新使用**原文标题、短摘录与中文筛选说明**，不会将规则筛选冒充阅读全文的 AI 解读。若题录缺少摘要则直接链接原文。

公司源包括 OpenAI、Google DeepMind、Anthropic、DeepSeek、Qwen Code、NVIDIA、Microsoft Research；只使用官方 RSS、官网公告与正式版本发布。配置见 `data/sources.json`。每期最多 6 条、同一公司最多 2 条，优先公司多样性与未读动态；有国内候选时保留一个位置。新闻窗口为最近 21 天。

分类依赖公开题录的关键词和发表类型，无法完美替代人工编辑；引用数据有滞后及学科差异，公司自述性能也可能未经过独立评估。所有文章均链接一手来源。

## 项目结构

```text
data/issues/YYYY-MM-DD.json  每期数据及检索依据
data/sources.json            官方公司来源
scripts/update.py           自动抓取和筛选
scripts/build.py            静态网页生成器
scripts/check_site.py       页面与本地链接检查
site/index.html             最新推送
site/archive.html           历史目录
site/archive/YYYY-MM-DD.html 独立、不可变的 HTML 快照
site/style.css              新一期的样式；生成时嵌入 HTML
.github/workflows/daily.yml 定时更新与部署
```

## 维护

Python 3.12，无第三方依赖：

```sh
python3 scripts/update.py --dry-run  # 真实抓取，检查结果，不改已发布内容
python3 scripts/update.py           # 生成今天的日报；已有则保留
python3 scripts/build.py            # 重建首页和目录，保留已有历史 HTML
python3 scripts/check_site.py
python3 -m unittest discover -s tests -v
python3 -m http.server 8765 --directory site
```

历史 HTML 内嵌 CSS，不受之后的样式调整影响。只有明确需要修订历史页面时，才使用 `python3 scripts/build.py --rebuild-archive`。

手动更新：仓库 **Actions → Daily news · update and publish → Run workflow**。勾选 `verify_sources` 可检查实时来源，即使当天已有日报也会运行抓取试验。

GitHub Pages 发布源设置为 **GitHub Actions**。工作流只依赖仓库自带的 `GITHUB_TOKEN`；抓取不需要私密密钥。

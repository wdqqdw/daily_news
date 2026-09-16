# daily_news · 研究与智能日报

网站：https://wdqqdw.github.io/daily_news/

每日 3 篇研究论文 + 国内外 AI 公司新闻，支持手机浏览与独立 HTML 历史归档。

## 三个固定栏目

1. **LLM 对人的理解与建模**：认知、行为预测、心理理论、脑与模型表征；优先 Nature / Science / Cell 及名称含品牌的正式研究期刊。
2. **研究人的人工智能工作**：不限制期刊品牌，关注使用 AI 研究人的认知、行为、心理、神经机制的实证工作，自动候选至少有 5 次 Crossref 引用。
3. **跨领域热点**：从 Crossref 跨学科候选中选取高关注研究。以引用总数及每月引用率为热度代理，不能等同于全网实时最热。查询最近一年与最近 90 天的高引用论文，合并去重。

技术报告、模型卡、系统卡只归公司动态；不占论文名额。自动论文入口限定正式 `journal-article`，排除可识别的综述、社论、概念评论、勘误、撤稿等。纯预印本暂不自动纳入。

## 每天 09:00 自动更新

GitHub Actions 在北京时间每天 **09:00**（UTC 01:00）运行，依次抓取、筛选、检查、保存并发布 GitHub Pages。无需本地电脑开机、无需 API 密钥或付费模型服务。

- 代码和日报 JSON / HTML 均保存在本仓库。
- 每天只生成一份；重复运行不会覆盖当天或历史推送。
- 维护 `data/history.json` 永久已推送清单（首推日期、标题、DOI / 链接及匹配标识）；每天发布后自动提交更新。论文按 DOI、原文 / 中文标题去重；新闻按规范链接、原文 / 中文标题去重，追踪参数与 URL 片段不产生新条目。历史内容绝不再次推送，候选不足也不回退重温。
- 第一栏优先近 180 天，必要时扩至 730 天；品牌期刊不足时才采用其他期刊并标注。第二栏综合影响力与新近程度，最多回溯 730 天。第三栏最多回溯 365 天。
- 无法获得 3 篇从未推送的合格论文时，任务报错并保留原日期的网页；公司新闻没有新增时显示空栏，不用旧内容填充。来源整体故障时也保留上一期。
- 原始日期与筛选数据保存在每期 JSON 中；网页显示实际生成时间。
- GitHub 定时触发可能排队延迟，不是精确到秒的定时服务。公开仓库连续 60 天无活动时，平台可能停用计划任务；正常每日提交会产生仓库活动。
- 本项目的“推送”指网站更新，没有发送邮件或手机通知。

## 内容来源与语言

论文使用 Crossref 公开元数据。每篇论文和公司动态均提供**中文标题与独立摘要**。现有两期已按期刊和公司官网整理；后续自动更新先获取公开论文摘要或官方公告，再使用开源 Qwen2.5-1.5B-Instruct（Q4_K_M）生成中文标题与短摘要。模型通过 llama.cpp 在 GitHub Actions 本地 CPU 上运行，无需额外账号或付费 API。模型、运行器版本与 SHA-256 校验值固定在 `scripts/prepare_summary.py`，首次下载后使用 Actions 缓存。

没有足够原文、模型未能启动、摘要被截断或中文字段不完整时，更新失败并保留上一期，避免发布空白或英文占位摘要。自动摘要仅基于公开材料，可能存在翻译或概括偏差，不能代替阅读全文。每个自动摘要保留来源 URL 与模型标识。

公司源包括 OpenAI、Google DeepMind、Anthropic、DeepSeek、Qwen Code、NVIDIA、Microsoft Research；只使用官方 RSS、官网公告与正式版本发布。配置见 `data/sources.json`。每期最多 6 条、同一公司最多 2 条，严格排除历史动态，再考虑公司多样性；有国内候选时保留一个位置。新闻窗口为最近 21 天。

分类依赖公开题录的关键词和发表类型，无法完美替代人工编辑；引用数据有滞后及学科差异，公司自述性能也可能未经过独立评估。所有文章均链接一手来源。

## 阅读标记与历史搜索

- 每篇论文和动态均有“标记已了解”按钮，可再次点击撤销。
- 历史页汇总所有期刊日期的内容，分为“已了解”和“未了解”两栏；两栏分别搜索标题、摘要、公司、期刊、DOI、发表和推送日期。
- 标记保存在当前网站、当前浏览器的 `localStorage`，按 DOI / 规范链接生成稳定 ID；更改中文标题不会丢失标记。同一浏览器的首页、日期快照与历史页共享状态，多个标签页同步。不同设备不会同步，清理网站数据会删除记录。
- 阅读标记与永久已推送清单相互独立：撤销“已了解”不会使旧条目再次推送。
- 2026-09-16 的第二篇按新主题修订，原条目保存在 `previous_items` 中，仍可在历史页搜索、标记，并继续参与历史防重。

## 项目结构

```text
data/issues/YYYY-MM-DD.json  每期数据及检索依据
data/sources.json            官方公司来源
data/history.json            永久已推送清单（每日自动维护）
scripts/update.py           自动抓取和筛选
scripts/build.py            静态网页生成器
scripts/summarize.py        原文提取与中文摘要
scripts/prepare_summary.py  固定版本摘要模型准备
scripts/check_site.py       页面与本地链接检查
site/index.html             最新推送
site/archive.html           已了解 / 未了解搜索与历史目录
site/reading.js             阅读标记与搜索交互，构建时嵌入 HTML
site/archive/YYYY-MM-DD.html 独立、不可变的 HTML 快照
site/style.css              新一期的样式；生成时嵌入 HTML
.github/workflows/daily.yml 定时更新与部署
```

## 维护

Python 3.12 标准库；自动摘要另使用固定版本的开源 llama.cpp 和 Qwen 模型（仅存于 `.cache`，不发布到网站）。先准备摘要运行环境，再运行真实抓取：

```sh
python3 scripts/prepare_summary.py # 下载并校验摘要模型与运行器
python3 scripts/update.py --dry-run  # 真实抓取，检查结果，不改已发布内容
python3 scripts/update.py           # 生成今天的日报；已有则保留
python3 scripts/build.py            # 重建首页和目录，保留已有历史 HTML
python3 scripts/check_site.py
python3 -m unittest discover -s tests -v
python3 -m http.server 8765 --directory site
```

历史 HTML 内嵌 CSS 与阅读交互脚本，不受之后的样式调整影响。只有明确需要修订历史页面时，才使用 `python3 scripts/build.py --rebuild-archive`。

手动更新：仓库 **Actions → Daily news · update and publish → Run workflow**。勾选 `verify_sources` 仅试验真实抓取、历史去重与中文摘要，不提前生成今天的日报；取消勾选才会立即生成当天新一期。

GitHub Pages 发布源设置为 **GitHub Actions**。工作流只依赖仓库自带的 `GITHUB_TOKEN`；抓取不需要私密密钥。

创刊期归档为 **2026-09-15**，**2026-09-16** 已自动生成第二期，后续继续每天 09:00（北京时间）触发。历史记录同时从已有日报补齐，即使将来移除某份日报文件，永久清单仍保留其已推送标记。

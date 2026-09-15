"""Render static pages. Existing dated HTML files are immutable snapshots."""
from __future__ import annotations
import argparse
import datetime as dt
import html
import json
from pathlib import Path
from urllib.parse import urlsplit
from history import load_history, save_history, validate_edition_history

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site'
DATA = ROOT / 'data' / 'issues'
CATEGORIES = [('LLM 与人的理解', ''), ('人的科学', 'human'), ('跨领域热点', 'hot')]
ICONS = {
 'file': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h6"/>',
 'arrow': '<path d="M7 17 17 7M7 7h10v10"/>',
 'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
 'book': '<path d="M3 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-3H3zM21 4h-6a3 3 0 0 0-3 3v14a4 4 0 0 1 4-3h5z"/>',
}

def esc(s):
    return html.escape(str(s), quote=True)

def icon(name):
    return f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>'

def safe_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username:
        raise ValueError(f'Invalid public source URL: {url}')
    return esc(url)

def date_label(value):
    d = dt.date.fromisoformat(value)
    return f'{d.year} 年 {d.month:02} 月 {d.day:02} 日'

def validate(issue):
    date = dt.date.fromisoformat(issue['date'])
    papers = issue['papers']
    if len(papers) != 3 or {p['slot'] for p in papers} != {1, 2, 3}:
        raise ValueError('An edition must contain exactly one paper per slot')
    dois = [p['doi'].lower().strip() for p in papers]
    if len(set(dois)) != 3:
        raise ValueError('Duplicate DOI within edition')
    for p in papers:
        if p.get('type') != 'journal-article':
            raise ValueError('Technical reports / non-research items cannot fill paper slots')
        if dt.date.fromisoformat(p['published']) > date:
            raise ValueError('Future-dated paper')
        for field in ('title', 'journal', 'reason', 'url'):
            if not p.get(field):
                raise ValueError(f'Missing paper field: {field}')
        safe_url(p['url'])
    for n in issue['news']:
        safe_url(n['url'])
        if dt.date.fromisoformat(n['published']) > date:
            raise ValueError('Future-dated news')

def frame(title, body, prefix='', archive=False):
    css = (SITE / 'style.css').read_text()
    favicon = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'%3E%3Crect width='40' height='40' rx='9' fill='%23354fc4'/%3E%3Cpath d='M10 10h13l7 7v14H10zM22 10v8h8M15 23h10M15 27h7' fill='none' stroke='white' stroke-width='2'/%3E%3C/svg%3E"
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="每日三篇研究论文与国内外 AI 公司动态。关注 LLM 对人的理解、人的科学与跨领域热点。"><meta name="theme-color" content="#354fc4"><title>{esc(title)} · daily_news</title><link rel="icon" type="image/svg+xml" href="{favicon}"><style>{css}</style></head>
<body><div class="wrap"><header class="topbar"><a class="brand" href="{prefix}index.html" aria-label="daily_news 首页"><span class="brand-icon">{icon('book')}</span><span class="brand-word">daily<span>_</span>news</span><span class="brand-label">研究与智能日报</span></a><nav class="topnav" aria-label="主导航"><a class="nav-link {'active' if not archive else ''}" href="{prefix}index.html" {'aria-current="page"' if not archive else ''}>最新推送</a><a class="nav-link {'active' if archive else ''}" href="{prefix}archive.html" {'aria-current="page"' if archive else ''}>{icon('file')}历史推送</a></nav></header>{body}<footer class="footer"><span>daily_news &nbsp; / &nbsp; 为好奇心保留时间</span><span>北京时间 UTC+8 &nbsp; · &nbsp; <a href="https://github.com/wdqqdw/daily_news" target="_blank" rel="noopener noreferrer">GitHub</a></span></footer></div></body></html>'''

def paper_card(p):
    label, cls = CATEGORIES[p['slot'] - 1]
    title = p.get('title_zh') or p['title']
    english = f'<p class="english-title" lang="en">{esc(p["title"])}</p>' if p.get('title_zh') else ''
    summary = f'<p class="summary">{esc(p["summary"])}</p>' if p.get('summary') else ''
    excerpt = f'<p lang="en">{esc(p["excerpt"])}</p>' if p.get('excerpt') else ''
    return f'''<article class="paper-card"><div class="paper-meta"><span class="category {cls}"><span class="number">0{p['slot']}</span>{label}</span><span class="paper-age">{esc(p.get('freshness', '研究论文'))}</span></div><h3><a href="{safe_url(p['url'])}" target="_blank" rel="noopener noreferrer">{esc(title)}</a></h3>{english}<div class="source-row"><span class="journal">{esc(p['journal'])}</span><span class="separator">/</span><time datetime="{esc(p['published'])}">{esc(p['published'])}</time><span class="separator">/</span><span>{esc(p.get('authors',''))}</span></div>{summary}<div class="reason"><b>为什么读</b> &nbsp;{esc(p['reason'])}</div><details><summary>筛选依据与研究边界</summary><p>{esc(p.get('evidence', '根据公开题录与引用数据筛选；请以论文原文为准。'))}</p>{excerpt}<p>DOI：{esc(p['doi'])}</p></details><div class="paper-footer"><span class="tagline">{esc(p.get('tag', '研究论文'))}</span><a href="{safe_url(p['url'])}" target="_blank" rel="noopener noreferrer">阅读原文 {icon('arrow')}</a></div></article>'''

def news_card(n):
    badges = {'OpenAI':'O','Google DeepMind':'G','Anthropic':'A','DeepSeek':'D','Qwen':'Q','NVIDIA':'N','Microsoft Research':'M','MiniMax':'M'}
    return f'''<article class="news-item"><div class="news-meta"><span class="company-badge" aria-hidden="true">{esc(badges.get(n['company'],n['company'][0]))}</span><span class="company">{esc(n['company'])}</span><span class="news-type">{esc(n.get('kind','公司动态'))}</span><time datetime="{esc(n['published'])}">{esc(n['published'][5:].replace('-', '.'))}</time></div><h3><a href="{safe_url(n['url'])}" target="_blank" rel="noopener noreferrer">{esc(n['title'])}</a></h3>{f'<p>{esc(n["summary"])}</p>' if n.get('summary') else ''}<a class="news-link" href="{safe_url(n['url'])}" target="_blank" rel="noopener noreferrer">官方来源 {icon('arrow')}</a></article>'''

METHOD = '''<details class="method"><summary>关于这份日报 · 筛选规则</summary><ul><li><b>01 LLM 与人的理解：</b>关注人类行为预测、认知建模、心理理论及脑与语言模型。优先期刊名含 Nature、Science、Cell 的正式研究。优先近 180 天，必要时扩至 730 天并标注；仍不足才使用其他期刊。</li><li><b>02 人的科学：</b>不限制期刊品牌，聚焦认知、行为、心理、神经与人机交互；综合主题匹配、引用与新近程度。</li><li><b>03 跨领域热点：</b>跨学科检索近一年论文，以 Crossref 引用总数与每月引用率作为可核验的热度代理。数据库覆盖和引用速度存在学科差异，并非全网实时热榜。</li><li>维护永久已推送记录，论文按 DOI 与标题、新闻按规范链接与标题去重。历史内容不会再次推送；若新论文不足则保留上一期并报告，新闻没有新增时显示空栏。</li><li>公司动态来自官方公告、研究博客和官方技术报告；报告只出现在右栏。没有新消息的来源不会强行编造。</li><li>每日 09:00（北京时间）触发更新，实际上线可能受 GitHub 排队影响。抓取失败会保留上一期，并在工作流中记录错误。</li><li>自动推送保留原文标题与短摘录，中文筛选说明不是全文解读。每篇均附原始来源，日期为原始发表日期。</li></ul></details>'''

def render_issue(issue, number, historical=False):
    validate(issue)
    d = dt.date.fromisoformat(issue['date'])
    week = '一二三四五六日'[d.weekday()]
    prefix = '../' if historical else ''
    archive_notice = f'<p class="notice">正在阅读 {esc(issue["date"])} 的历史快照。<a href="../index.html">查看最新推送 →</a></p>' if historical else '<p id="stale-notice" class="notice hidden" role="status"></p>'
    papers = ''.join(paper_card(p) for p in sorted(issue['papers'], key=lambda p:p['slot']))
    news = ''.join(news_card(n) for n in issue['news']) or '<p class="empty">暂无未推送的公司动态，历史内容已排除。</p>'
    warnings = ''.join(f'<p class="notice">{esc(w)}</p>' for w in issue.get('notices', []))
    body = f'''<main><section class="masthead"><div><div class="eyebrow">THE DAILY BRIEF <span aria-hidden="true">/</span> VOL. {number:03}</div><h1>今天，值得读什么。</h1><p class="subhead">三篇研究，一览 AI 前沿。</p></div><div class="edition"><b>{date_label(issue['date'])} · 星期{week}</b><span>生成于 {esc(issue['generated_at'][11:16])} · 北京时间</span><span class="schedule">{icon('clock')}每日 09:00 更新</span></div></section><div class="edition-strip"><div class="strip-left"><span class="strip-label">{esc(issue.get('label','DAILY EDITION'))}</span><span><strong>03</strong> 篇论文 &nbsp; / &nbsp; <strong>{len(issue['news']):02}</strong> 条动态</span></div><span class="strip-right">人的理解 &nbsp; · &nbsp; 科学发现 &nbsp; · &nbsp; AI 进展</span></div>{archive_notice}{warnings}<div class="main-grid"><section aria-labelledby="papers-heading"><div class="column-title"><h2 id="papers-heading">论文精选<span class="small-en">RESEARCH</span></h2><span class="count">每日 3 篇</span></div><p class="section-intro">从理解人，到理解更大的世界。</p>{papers}</section><aside aria-labelledby="news-heading"><div class="column-title"><h2 id="news-heading">AI 公司动态<span class="small-en">INDUSTRY</span></h2><span class="count">国内 · 国际</span></div><p class="section-intro">产品发布、研究进展与技术报告。</p><div class="news-panel">{news}</div><div class="news-note">技术报告归入公司动态，不占每日 3 篇论文名额。<br>公司公布的性能与结论，以官方原文及后续独立评估为准。</div>{METHOD}</aside></div></main>'''
    if not historical:
        body += f'''<script>(()=>{{const parts=new Intl.DateTimeFormat('sv-SE',{{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',hourCycle:'h23'}}).formatToParts(new Date());const p=Object.fromEntries(parts.map(x=>[x.type,x.value]));const today=p.year+'-'+p.month+'-'+p.day;const issue={json.dumps(issue['date'])};const previous=new Date(Date.UTC(+p.year,+p.month-1,+p.day)-86400000).toISOString().slice(0,10);if(issue<previous||(issue<today&&+p.hour>=10)){{const e=document.getElementById('stale-notice');e.textContent='最新一期仍为 '+issue+'。今天的推送尚未上线，请稍后刷新或查看 GitHub 更新状态。';e.classList.remove('hidden');}}}})();</script>'''
    return frame(f'{issue["date"]} 每日推送', body, prefix, historical)

def build(rebuild_archive=False):
    SITE.mkdir(exist_ok=True)
    (SITE/'archive').mkdir(exist_ok=True)
    files = sorted(DATA.glob('????-??-??.json'))
    if not files:
        raise ValueError('No editions to publish')
    issues = [json.loads(f.read_text()) for f in files]
    validate_edition_history(issues)
    for i, issue in enumerate(issues, 1):
        validate(issue)
        path = SITE / 'archive' / f'{issue["date"]}.html'
        if rebuild_archive or not path.exists():
            path.write_text(render_issue(issue, i, True))
    (SITE/'index.html').write_text(render_issue(issues[-1], len(issues)))
    rows = ''.join(f'''<a class="archive-entry" href="archive/{esc(x['date'])}.html"><span class="file-icon">{icon('file')}</span><div><h2>{date_label(x['date'])} <span class="archive-tag">HTML</span></h2><p>第 {i:03} 期 &nbsp; · &nbsp; 3 篇论文 &nbsp; · &nbsp; {len(x['news'])} 条公司动态</p><p>{esc((x['papers'][0].get('title_zh') or x['papers'][0]['title'])[:90])}</p></div><span class="archive-arrow">{icon('arrow')}</span></a>''' for i,x in reversed(list(enumerate(issues,1))))
    body = f'''<main><section class="masthead"><div><div class="eyebrow">THE READING ARCHIVE</div><h1>把值得读的，留下来。</h1><p class="subhead">历史推送 · 共 {len(issues)} 期 · 每期保存为独立 HTML</p></div><a class="back-link" href="index.html">返回最新推送 →</a></section><div class="archive-list">{rows}</div></main>'''
    (SITE/'archive.html').write_text(frame('历史推送', body, archive=True))
    (SITE/'.nojekyll').touch()
    save_history(DATA, load_history(DATA))
    print(f'Built {len(issues)} editions; latest {issues[-1]["date"]}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rebuild-archive', action='store_true', help='Explicitly regenerate historical HTML; normally leave immutable')
    build(parser.parse_args().rebuild_archive)

"""Fetch public scholarly metadata and official AI company sources. No API key needed.

Selection is deterministic and auditable; it does not claim to read full papers.
Run --dry-run to exercise the real pipeline without changing the published issue.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import datetime as dt
from email.utils import parsedate_to_datetime
import html
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from build import ROOT, DATA, build, validate
from history import item_keys, load_history, history_keys, assert_unseen
from summarize import enrich, source_text

TZ = ZoneInfo('Asia/Shanghai')
USER_AGENT = 'daily_news/1.0 (+https://github.com/wdqqdw/daily_news)'
BAD_TITLE = re.compile(r'(^|\b)(correction|corrigendum|erratum|retraction|retracted|editorial|commentary|perspective|review|survey|meta.analysis|bibliometric|technical report|system card|model card|study protocol|conceptual analysis|consensus statement|guideline|reply to|comment on|news and views)(\b|:)', re.I)
LLM = re.compile(r'\b(large language model\w*|language model\w*|LLMs?|GPT[ -]?\d|ChatGPT|foundation model\w*)\b', re.I)
HUMAN = re.compile(r'\b(human\w*|cogni\w*|behavio\w*|psycholog\w*|theory of mind|mentaliz\w*|mental states?|beliefs?|personality|social cognition|brain\w*|neural|neuronal|decision.making)\b', re.I)
COGNITION = re.compile(r'\b(cogni\w*|behavio\w*|psycholog\w*|theory of mind|mentaliz\w*|mental states?|beliefs?|personality|brain\w*|neuronal|decision.making|human (?:choices?|preferences?|intentions?|emotions?))\b', re.I)
MODELLING = re.compile(r'\b(predict\w*|simulat\w*|model\w*|understand\w*|theory of mind|mentaliz\w*|represent\w*|align\w*|cogni\w*|reason\w*|beliefs?)\b', re.I)
AI = re.compile(r'\b(artificial intelligence|machine learning|deep learning|neural network\w*|transformer\w*|AI|computational model\w*)\b', re.I)
PERSON_TARGET = re.compile(r'\b(human (?:cogni\w*|behavio\w*|reason\w*|brain\w*|language|choices?|preferences?|decisions?|emotions?)|cogni\w*|psycholog\w*|theory of mind|mental states?|beliefs?|personality|neuronal|brain.guided|social behavio\w*)\b', re.I)
HUMAN_SUBJECT_TITLE = re.compile(r'\b(humans?|people|psycholog\w*|brain\w*|neuronal|personality|theory of mind)\b',re.I)
NSC = re.compile(r'^(Nature(?:\s+.+)?|Science(?:\s+.+)?|Cell(?:\s+.+)?)$', re.I)
NSC_PUBLISHERS = re.compile(r'springer|nature|american association for the advancement|elsevier|cell press', re.I)
ESTABLISHED_PUBLISHERS = re.compile(r'springer|nature|elsevier|wiley|american association for the advancement|cell press|american (?:chemical|physical|psychological) society|royal society|national academy of sciences|oxford|cambridge|association for computing machinery|ieee|iop publishing|sage|frontiers|public library of science|plos|massachusetts medical society|american medical association|bmj|aps', re.I)
THEORY_ONLY = re.compile(r'middle.range theoretical framework|synthesi[sz]ing .*theor|proposes? a research agenda|conceptual (?:analysis|framework)|narrative review|systematic review', re.I)

def clean(text):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', text or ''))).strip()

def excerpt(text, words=24):
    """Short attributed extracts only; never republish full abstracts or news posts."""
    text = clean(text)
    parts = text.split()
    if len(parts) > words:
        return ' '.join(parts[:words]) + '…'
    return text[:140] + ('…' if len(text) > 140 else '')

def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent':USER_AGENT, 'Accept':'application/json, application/xml, text/html;q=0.9, */*;q=0.8'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=35) as r:
                return r.read(12_000_000).decode('utf-8', errors='replace')
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

def crossref(query, today, days=730, rows=120, sort=None):
    params = {'filter':f'type:journal-article,from-pub-date:{today-dt.timedelta(days=days)},until-pub-date:{today}', 'rows':rows,
              'select':'DOI,title,author,container-title,publisher,published-online,published-print,published,issued,type,is-referenced-by-count,abstract,update-to'}
    if query:
        params['query.title'] = query
    if sort:
        params.update({'sort':sort,'order':'desc'})
    url = 'https://api.crossref.org/works?' + urllib.parse.urlencode(params)
    items = json.loads(fetch(url))['message']['items']
    return [p for x in items if (p := normalize_work(x, today))]

def normalize_work(x, today):
    title = clean(' '.join(x.get('title', [])))
    if x.get('type') != 'journal-article' or not x.get('DOI') or not title or BAD_TITLE.search(title):
        return None
    if any(u.get('type') in ('retraction','withdrawal') for u in x.get('update-to', [])):
        return None
    dates = []
    for k in ('published-online','published-print','published','issued'):
        parts = x.get(k,{}).get('date-parts',[[]])[0]
        if len(parts) == 3:
            try: dates.append(dt.date(*parts))
            except (TypeError, ValueError): pass
    if not dates:
        return None  # Do not invent a publication day from a year/month alone.
    published = min(dates)
    if published > today:
        return None
    journal = clean(' '.join(x.get('container-title',[])))
    if not journal or re.search(r'review|abstracts|proceedings|perspectives on|trends in',journal,re.I):
        return None
    authors = x.get('author', [])
    author = authors[0].get('family',authors[0].get('name','')) if authors else ''
    citations = int(x.get('is-referenced-by-count',0) or 0)
    return {'type':'journal-article','title':title,'doi':x['DOI'].lower(),'url':'https://doi.org/'+x['DOI'], 'journal':journal,
            'publisher':x.get('publisher',''),'published':str(published),'authors':author+(' et al.' if len(authors)>1 else ''),
            'citations':citations,'abstract':clean(x.get('abstract','')),'metadata_source':'Crossref',
            'metadata_url':'https://api.crossref.org/works/'+urllib.parse.quote(x['DOI'],safe='')}

def is_nsc(p):
    # Exclude e.g. Science of the Total Environment and unrelated Cell journals.
    j = p['journal'].lower()
    valid = j == 'nature' or j.startswith('nature ') or j in {
        'science','science advances','science robotics','science immunology',
        'science signaling','science translational medicine','cell','cell reports',
        'cell reports medicine','cell reports physical science','cell reports methods',
        'cell systems','cell metabolism','cell stem cell','cell chemical biology',
        'cell genomics','cell host & microbe','cell host and microbe'}
    return valid and bool(NSC_PUBLISHERS.search(p.get('publisher','')))

def relevant(p, slot):
    title = p['title']
    if BAD_TITLE.search(title): return False
    if THEORY_ONLY.search(p.get('abstract','')):return False
    if slot == 1:
        # Require cognition/people in title, LLM signal in title or abstract.
        text = title+' '+p.get('abstract','')[:1200]
        return bool(COGNITION.search(title) and PERSON_TARGET.search(text) and MODELLING.search(text) and LLM.search(text))
    if slot == 2:
        text = title + ' ' + p.get('abstract','')[:1400]
        return bool(COGNITION.search(title) and HUMAN_SUBJECT_TITLE.search(title) and PERSON_TARGET.search(text) and (LLM.search(text) or AI.search(text))) and p.get('citations',0) >= 5 and not re.search(r'conceptual|framework for|theoretical framework', title, re.I)
    return p.get('citations',0) > 0 and bool(ESTABLISHED_PUBLISHERS.search(p.get('publisher','')))

def score(p, slot, today):
    age = max((today-dt.date.fromisoformat(p['published'])).days,1)
    cites = p.get('citations',0)
    rate = cites / max(age/30,1)
    if slot == 3:
        return math.log1p(rate)*3 + math.log1p(cites) + 0.5*math.exp(-age/180)
    relevance = min(len(set(m.group().lower() for m in HUMAN.finditer(p['title']))),4)
    return relevance + 3*math.exp(-age/180) + 3*math.log1p(cites)

def select_papers(pool, seen, today):
    selected, used = [], set()
    for slot in (1,2,3):
        max_days = 365 if slot == 3 else 730
        candidates = [p for p in pool if not item_keys(p,'papers').intersection(used | seen) and relevant(p,slot) and 0 <= (today-dt.date.fromisoformat(p['published'])).days <= max_days]
        if not candidates:
            raise RuntimeError(f'No unpublished qualifying paper for slot {slot}; keep previous edition without repeating content')
        if slot == 1:
            preferred = [p for p in candidates if is_nsc(p)]
            candidates = preferred or candidates
        recent = [p for p in candidates if (today-dt.date.fromisoformat(p['published'])).days <= 180]
        if slot == 1:
            candidates = recent or candidates
        chosen = copy.deepcopy(max(candidates, key=lambda p:(score(p,slot,today),p['published'],p['doi'])))
        chosen['slot'] = slot
        age = (today-dt.date.fromisoformat(chosen['published'])).days
        chosen['freshness'] = '近期研究' if age <= 180 else '延伸阅读 · 较早发表'
        if slot == 1 and not is_nsc(chosen):
            chosen['freshness'] += ' · 其他期刊补充'
        cite = chosen.get('citations',0)
        rate = round(cite/max(age/30,1),2)
        chosen['reason'] = {
            1:'题录涉及语言模型与人的认知、行为或神经表征，适合追踪 LLM 对人的理解与建模。',
            2:'使用人工智能研究人的认知、行为或脑机制，综合主题匹配、引用数与发表时间入选。',
            3:f'本次跨领域候选中热度评分最高的未读研究：公开记录 {cite} 次引用，约 {rate} 次 / 月。'
        }[slot]
        chosen['evidence'] = f'检索时间：{today}；来源：Crossref；引用数 {cite}，距发表 {age} 天。'+ ('优先匹配期刊品牌与主题，再考虑新近程度和引用。' if slot == 1 else '评分依据公开题录、引用总数与发表时间。') + '引用统计可能滞后且存在学科偏差。题录规则筛选未替代人工阅读全文，请以原文为准。'
        abstract = chosen.pop('abstract','')
        chosen['_source_text'] = abstract
        chosen['summary'] = ''
        chosen['tag'] = ['认知与行为建模','研究人的人工智能工作','跨学科 / 引用热度'][slot-1]
        chosen['ranking_score'] = round(score(chosen,slot,today),4)
        selected.append(chosen)
        used.update(item_keys(chosen,'papers'))
    return selected

def parse_date(value):
    value = value.strip()
    try: return dt.datetime.fromisoformat(value.replace('Z','+00:00')).date()
    except ValueError: pass
    try: return parsedate_to_datetime(value).date()
    except (ValueError, TypeError): pass
    m = re.search(r'(20\d{2})[-/](\d{2})[-/](\d{2})',value)
    if m:
        try: return dt.date(*map(int,m.groups()))
        except ValueError: pass
    m = re.search(r'(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2}),?\s+(20\d{2})', value,re.I)
    if m:
        month = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'].index(m[1][:3].lower())+1
        try: return dt.date(int(m[3]),month,int(m[2]))
        except ValueError: pass
    return None

def news_kind(text):
    if re.search(r'technical report|system card|model card|技术报告',text,re.I): return '技术报告'
    if re.search(r'report|safety|misuse|security|安全',text,re.I): return '安全 / 报告'
    if re.search(r'introducing|release|launch|发布|^v\d',text,re.I): return '产品发布'
    return '研究 / 公司动态'

def parse_feed(content, config, today):
    root = ET.fromstring(content)
    items = root.findall('.//item') or root.findall('{http://www.w3.org/2005/Atom}entry')
    result = []
    def local(tag): return tag.rsplit('}',1)[-1]
    for item in items:
        fields = {local(x.tag):x for x in item}
        def txt(*keys):
            for k in keys:
                if k in fields: return ''.join(fields[k].itertext()).strip()
            return ''
        url = txt('link')
        if not url:
            for x in item:
                if local(x.tag)=='link' and x.get('rel','alternate')=='alternate':
                    url=x.get('href','');break
        published = parse_date(txt('pubDate','published','date','updated'))
        title = clean(txt('title'))
        if config['company'] == 'Qwen':
            if not re.fullmatch(r'(?:Release\s+)?v\d+\.\d+\.\d+',title):continue
            title = 'Qwen Code · '+title
        source_text = clean(txt('encoded','content','description','summary'))
        if not published or not title or not url.startswith('https://'): continue
        if not 0 <= (today-published).days <= 21: continue
        result.append({'company':config['company'],'kind':news_kind(title), 'published':str(published), 'title':title,'summary':'','_source_text':source_text,'url':url, 'source_feed':config['url']})
    return result

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__();self.links=[];self.current=None;self.skip=0;self.metas={};self.h1='';self.in_h1=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('script','style'):self.skip+=1
        if tag=='a': self.current={'href':a.get('href',''),'text':'','date':''}
        if tag=='time' and self.current is not None:self.current['date']=a.get('datetime','')
        if tag=='h1':self.in_h1=True
        if tag=='meta':self.metas[a.get('property',a.get('name',''))]=a.get('content','')
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.skip=max(0,self.skip-1)
        if tag=='a' and self.current is not None:self.links.append(self.current);self.current=None
        if tag=='h1':self.in_h1=False
        if self.current is not None:self.current['text']+=' '
    def handle_data(self,data):
        if self.skip:return
        if self.current is not None:self.current['text']+=data+' '
        if self.in_h1:self.h1+=data+' '

def parse_page(content, config, today):
    parser = LinkParser();parser.feed(content)
    result=[];used=set()
    for link in parser.links:
        url = urllib.parse.urljoin(config['url'],link['href'])
        parsed = urllib.parse.urlsplit(url)
        if parsed.hostname != urllib.parse.urlsplit(config['url']).hostname:continue
        if url in used or not any(parsed.path.startswith(p) for p in config['path_prefixes']):continue
        text = clean(link['text'])
        published = parse_date(link['date']) or parse_date(text)
        # DeepSeek docs encode YYMMDD in canonical article URLs; fetch metadata
        # to confirm dates when the link itself doesn't contain a full date.
        if not published and config['company']=='DeepSeek' and re.search(r'/news/news\d{6}/?$',parsed.path):
            if len(used)>=8:continue
            child=LinkParser();child.feed(fetch(url))
            published=parse_date(child.metas.get('article:published_time','')) or parse_date(child.h1)
            if not published:
                raw=re.search(r'news(\d{6})',parsed.path)[1]
                try: published=dt.date(2000+int(raw[:2]),int(raw[2:4]),int(raw[4:]))
                except ValueError:continue
        if not published or not 0 <= (today-published).days <= 21:continue
        title = re.sub(r'\b(?:Announcements|Products?|News|Research)\b','',text,flags=re.I)
        title = re.sub(r'\b[A-Z][a-z]{2,8}\s+\d{1,2},?\s+20\d{2}\b','',title)
        title = re.sub(r'20\d{2}[-/]\d{2}[-/]\d{2}','',title).strip(' ·|-')
        if not title:continue
        # Fetch the known company article for an exact headline when the listing
        # combines the headline and description in one anchor.
        if len(title.split())>18:
            child=LinkParser();child.feed(fetch(url))
            title=clean(child.h1 or child.metas.get('og:title','') or title)
        title=excerpt(title,24)
        result.append({'company':config['company'],'kind':news_kind(title),'published':str(published),'title':title,'summary':'','url':url,'source_page':config['url']})
        used.add(url)
    return result

def choose_news(news, seen):
    ordered=[]
    used=set(seen)
    for item in sorted(news,key=lambda x:x['published'],reverse=True):
        keys=item_keys(item,'news')
        if keys.intersection(used):continue
        ordered.append(item)
        used.update(keys)
    out=[];counts={}
    # Prefer diversity; reserve a slot for a domestic source when one is available.
    domestic=next((x for x in ordered if x['company'] in {'Qwen','DeepSeek','MiniMax'}),None)
    if domestic:out.append(domestic);counts[domestic['company']]=1
    for limit in (1,2):
        for n in ordered:
            if n in out or counts.get(n['company'],0)>=limit:continue
            out.append(n);counts[n['company']]=counts.get(n['company'],0)+1
            if len(out)>=6:break
        if len(out)>=6:break
    return sorted(out,key=lambda x:x['published'],reverse=True)

def generate(today):
    configs=json.loads((ROOT/'data/sources.json').read_text())
    jobs={
      'LLM human modelling':lambda:crossref('large language models human behavior prediction',today),
      'LLM cognition':lambda:crossref('language models human cognition brain theory of mind',today),
      'AI human behaviour':lambda:crossref('artificial intelligence human cognition psychology behavior',today,days=365),
      'Human interaction':lambda:crossref('human artificial intelligence interaction experiment',today,days=365),
      'AI human cognition impact':lambda:crossref('language models human cognition behavior psychology',today,days=730,rows=180,sort='is-referenced-by-count'),
      'Cross-discipline annual citations':lambda:crossref('',today,days=365,rows=200,sort='is-referenced-by-count'),
      'Cross-discipline recent citations':lambda:crossref('',today,days=90,rows=150,sort='is-referenced-by-count'),
    }
    for c in configs['feeds']:
        jobs['News '+c['company']]=lambda c=c:parse_feed(fetch(c['url']),c,today)
    for c in configs['pages']:
        jobs['Page '+c['url']]=lambda c=c:parse_page(fetch(c['url']),c,today)
    papers=[];news=[];statuses=[];paper_success=0;news_success=0
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures={executor.submit(fn):name for name,fn in jobs.items()}
        for fut in as_completed(futures):
            name=futures[fut]
            try:
                rows=fut.result()
                if name.startswith(('News ','Page ')):news.extend(rows);news_success+=1
                else:papers.extend(rows);paper_success+=1
                statuses.append({'source':name,'ok':True,'items':len(rows)})
                print(f'{name}: {len(rows)} items',flush=True)
            except Exception as e:
                statuses.append({'source':name,'ok':False,'error':str(e)[:240]})
                print(f'WARNING {name}: {e}',flush=True)
    if paper_success<2 or news_success<1:
        raise RuntimeError('Insufficient live sources; preserving previous publication')
    pool=list({p['doi']:p for p in papers}.values())
    history=load_history(DATA)
    # A Chinese summary needs substantive source text. Try the next eligible
    # unseen candidate if a publisher supplies only a title or blocks access.
    excluded_papers=history_keys(history,'papers')
    prepared={}
    for _ in range(12):
        selected=select_papers(pool,excluded_papers,today)
        unavailable=[]
        for item in selected:
            try:
                if item['doi'] not in prepared:
                    prepared[item['doi']]=source_text(item,'papers',fetch)
                text,url=prepared[item['doi']]
                item['_source_text']=text
                item['_summary_source']=url
            except ValueError:
                unavailable.append(item)
                print('Skipping paper without accessible abstract: '+item['title'],flush=True)
        if not unavailable:break
        for item in unavailable:excluded_papers.update(item_keys(item,'papers'))
    else:raise RuntimeError('Insufficient accessible paper abstracts; preserving previous edition')
    selected_news=[]
    unavailable_news=0
    for item in choose_news(news,history_keys(history,'news')):
        try:
            text,url=source_text(item,'news',fetch)
            item['_source_text']=text
            item['_summary_source']=url
            selected_news.append(item)
        except ValueError:
            unavailable_news+=1
            print('Skipping news without accessible body: '+item['title'],flush=True)
    notices=[]
    if unavailable_news:notices.append(f'有 {unavailable_news} 条新动态缺少可用原文，暂未收录。')
    failed=sum(not s['ok'] for s in statuses)
    if failed:notices.append(f'本期有 {failed} 个来源暂时不可用，内容来自其余可用来源。')
    if not selected_news:notices.append('本次没有发现未推送的公司动态；已排除所有历史内容。')
    issue={'date':str(today),'generated_at':dt.datetime.now(TZ).isoformat(timespec='seconds'),'label':'DAILY EDITION','papers':selected,'news':selected_news,'notices':notices,'sources':statuses,'candidate_count':len(pool)}
    validate(issue)
    assert_unseen(issue,history)
    enrich(issue,fetch)
    issue['generated_at']=dt.datetime.now(TZ).isoformat(timespec='seconds')
    validate(issue)
    assert_unseen(issue,history)
    return issue

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--output',type=Path,help='Write a dry-run result for inspection')
    args=parser.parse_args()
    today=dt.datetime.now(TZ).date()
    path=DATA/f'{today}.json'
    if path.exists() and not args.dry_run:
        print(f'{today} already published; preserving immutable edition')
        build();return
    issue=generate(today)
    encoded=json.dumps(issue,ensure_ascii=False,indent=2)+'\n'
    if args.dry_run:
        if args.output:args.output.write_text(encoded)
        print(json.dumps({'date':issue['date'],'papers':[{k:p[k] for k in ('slot','title','journal','published','citations','freshness')} for p in issue['papers']], 'news':[(n['company'],n['title']) for n in issue['news']]},ensure_ascii=False,indent=2))
        return
    DATA.mkdir(parents=True,exist_ok=True)
    # Refuse overwrite even if another process creates today's edition mid-fetch.
    with path.open('x') as f:f.write(encoded)
    build()

if __name__=='__main__':main()

import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build
from update import normalize_work, is_nsc, select_papers, relevant, parse_feed, parse_page, choose_news, parse_date

TODAY=dt.date(2026,9,16)

def paper(doi,title='Language models predict human cognition',**extra):
    p={'doi':doi,'title':title,'journal':'Nature Human Behaviour','publisher':'Springer Science and Business Media LLC',
       'published':'2026-07-01','citations':30,'abstract':'We model human choices using large language models.',
       'url':'https://doi.org/'+doi,'authors':'Test et al.','type':'journal-article'}
    p.update(extra);return p

class SelectionTests(unittest.TestCase):
    def test_reports_and_conceptual_items_do_not_fill_slots(self):
        for title in ('Qwen Technical Report','Human cognition: a systematic review','Human behaviour: a conceptual analysis','Retraction: Human cognition'):
            self.assertFalse(relevant(paper('10.1/no',title),1))
            self.assertFalse(relevant(paper('10.1/no',title),2))

    def test_nsc_requires_actual_journal_brand(self):
        self.assertTrue(is_nsc(paper('10.1/a')))
        self.assertFalse(is_nsc(paper('10.1/a',journal='Scientific Reports')))
        self.assertFalse(is_nsc(paper('10.1/a',journal='Science of The Total Environment',publisher='Elsevier')))

    def test_unique_doi_and_unseen_preference(self):
        pool=[paper('10.1/seen',citations=1000),paper('10.1/a'),paper('10.1/b'),paper('10.1/c','Quantum materials',journal='Physics',publisher='APS',citations=300)]
        result=select_papers(pool,{'10.1/seen'},TODAY)
        self.assertEqual(len({x['doi'] for x in result}),3)
        self.assertEqual([x['slot'] for x in result],[1,2,3])
        self.assertNotEqual(result[0]['doi'],'10.1/seen')

    def test_repeat_is_explicit(self):
        pool=[paper('10.1/a'),paper('10.1/b'),paper('10.1/c','Quantum materials')]
        result=select_papers(pool,{p['doi'] for p in pool},TODAY)
        self.assertTrue(all('历史重温' in x['freshness'] for x in result))

    def test_no_qualifying_papers_fails(self):
        with self.assertRaises(RuntimeError):select_papers([],set(),TODAY)

    def test_future_metadata_and_partial_dates_are_rejected(self):
        raw={'type':'journal-article','DOI':'10.1/x','title':['Human cognition'],'container-title':['Nature'],'published':{'date-parts':[[2027,1,1]]}}
        self.assertIsNone(normalize_work(raw,TODAY))
        raw['published']={'date-parts':[[2026,9]]}
        self.assertIsNone(normalize_work(raw,TODAY))

class ParsingTests(unittest.TestCase):
    def test_rss_filters_future_and_stale_items(self):
        rss='<rss><channel>'+''.join(f'<item><title>Release {i}</title><link>https://example.com/{i}</link><pubDate>{d}</pubDate></item>' for i,d in enumerate(['2026-09-15','2026-09-17','2025-09-15']))+'</channel></rss>'
        result=parse_feed(rss,{'company':'OpenAI','url':'https://example.com/rss'},TODAY)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['published'],'2026-09-15')

    def test_atom_stable_releases_only(self):
        atom='<feed xmlns="http://www.w3.org/2005/Atom">'+''.join(f'<entry><title>{v}</title><link href="https://github.com/QwenLM/qwen-code/releases/{i}"/><updated>2026-09-15T08:00:00Z</updated></entry>' for i,v in enumerate(['Release v1.2.3','Release v1.2.3-nightly','cua-driver-rs v1.2.3']))+'</feed>'
        r=parse_feed(atom,{'company':'Qwen','url':'https://example.com/feed'},TODAY)
        self.assertEqual(len(r),1)
        self.assertTrue(r[0]['title'].startswith('Qwen Code'))

    def test_html_dates_and_source_domain(self):
        content='<a href="/news/a"><time datetime="2026-09-10">Sep 10, 2026</time><h3>New model release</h3></a><a href="https://evil.example/news/b">Sep 10, 2026 Fake</a>'
        rows=parse_page(content,{'company':'Anthropic','url':'https://www.anthropic.com/news','path_prefixes':['/news/']},TODAY)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['title'],'New model release')

    def test_news_company_diversity_and_domestic_source(self):
        rows=[{'url':f'https://example.com/{c}/{i}','company':c,'published':'2026-09-15'} for c in ['OpenAI','DeepSeek','Anthropic','Google DeepMind','NVIDIA'] for i in range(3)]
        result=choose_news(rows,set())
        self.assertEqual(len(result),6)
        self.assertEqual(len({r['company'] for r in result}),5)

class PublicationTests(unittest.TestCase):
    def test_archive_is_immutable_and_html_is_escaped(self):
        seed=json.loads(next(build.DATA.glob('*.json')).read_text())
        seed['papers'][0]['title_zh']='<script>alert(1)</script>'
        rendered=build.render_issue(seed,1,True)
        self.assertIn('&lt;script&gt;',rendered)
        self.assertNotIn('<script>alert(1)',rendered)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);site=root/'site';data=root/'data';site.mkdir();data.mkdir()
            (site/'style.css').write_text('body{color:black}')
            (data/f"{seed['date']}.json").write_text(json.dumps(seed))
            with patch.object(build,'SITE',site),patch.object(build,'DATA',data):
                build.build()
                archive=site/'archive'/f"{seed['date']}.html"
                before=archive.read_bytes()
                (site/'style.css').write_text('body{color:blue}')
                build.build()
                self.assertEqual(before,archive.read_bytes())
                self.assertIn('color:blue',(site/'index.html').read_text())

    def test_duplicate_and_technical_report_rejected(self):
        seed=json.loads(next(build.DATA.glob('*.json')).read_text())
        seed['papers'][1]['doi']=seed['papers'][0]['doi']
        with self.assertRaises(ValueError):build.validate(seed)
        seed['papers'][1]['doi']='10.1/test';seed['papers'][1]['type']='technical-report'
        with self.assertRaises(ValueError):build.validate(seed)

if __name__=='__main__':unittest.main()

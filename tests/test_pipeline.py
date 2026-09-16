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
from history import item_keys, history_keys, record_issue, load_history, save_history, assert_unseen, canonical_url
from summarize import ArticleParser, source_text, valid_chinese

TODAY=dt.date(2026,9,16)

def paper(doi,title=None,**extra):
    title=title or 'Language models predict human cognition: '+doi
    p={'doi':doi,'title':title,'journal':'Nature Human Behaviour','publisher':'Springer Science and Business Media LLC',
       'published':'2026-07-01','citations':30,'abstract':'We model human choices using large language models.',
       'url':'https://doi.org/'+doi,'authors':'Test et al.','type':'journal-article'}
    p.update(extra);return p

class SelectionTests(unittest.TestCase):
    def test_human_ai_slot_requires_ai_and_a_human_research_subject(self):
        self.assertFalse(relevant(paper('10.1/old','Bioaccumulation of microplastics in decedent human brains',abstract='We measured plastic in tissue.'),2))
        self.assertFalse(relevant(paper('10.1/dna','Foundation models for human genomics',abstract='A transformer trained on DNA.'),2))
        self.assertTrue(relevant(paper('10.1/new','Using deep learning to predict human decision-making',abstract='We tested human choice predictions.'),2))
        self.assertFalse(relevant(paper('10.1/theory','Artificial Intelligence and the Psychology of Human Connection',abstract='This article introduces a middle-range theoretical framework and proposes a research agenda.'),2))
        self.assertFalse(relevant(paper('10.1/clinical','Benchmark evaluation of DeepSeek large language models in clinical decision-making',abstract='We tested clinical accuracy on medical questions.'),1))
        self.assertFalse(relevant(paper('10.1/ai-only','Visual cognition in multimodal large language models',abstract='We assess AI performance in intuitive physics and visual benchmarks.'),2))

    def test_hot_paper_requires_established_publication_source(self):
        self.assertFalse(relevant(paper('10.1/spam','Writing better scientific articles',publisher='Unknown journal network',citations=10000),3))
        self.assertTrue(relevant(paper('10.1/physics','Quantum materials',publisher='American Physical Society (APS)'),3))
    def test_reports_and_conceptual_items_do_not_fill_slots(self):
        for title in ('Qwen Technical Report','Human cognition: a systematic review','Human behaviour: a conceptual analysis','Retraction: Human cognition'):
            self.assertFalse(relevant(paper('10.1/no',title),1))
            self.assertFalse(relevant(paper('10.1/no',title),2))

    def test_nsc_requires_actual_journal_brand(self):
        self.assertTrue(is_nsc(paper('10.1/a')))
        self.assertFalse(is_nsc(paper('10.1/a',journal='Scientific Reports')))
        self.assertFalse(is_nsc(paper('10.1/a',journal='Science of The Total Environment',publisher='Elsevier')))

    def test_human_genomics_is_not_llm_modelling_of_people(self):
        self.assertFalse(relevant(paper('10.1/dna','Nucleotide Transformer: building and evaluating robust foundation models for human genomics'),1))
        self.assertTrue(relevant(paper('10.1/mind','A foundation model to predict and capture human cognition'),1))

    def test_unique_doi_and_unseen_preference(self):
        pool=[paper('10.1/seen',citations=1000),paper('10.1/a'),paper('10.1/b'),paper('10.1/c','Quantum materials',journal='Physics',publisher='APS',citations=300)]
        result=select_papers(pool,item_keys(pool[0],'papers'),TODAY)
        self.assertEqual(len({x['doi'] for x in result}),3)
        self.assertEqual([x['slot'] for x in result],[1,2,3])
        self.assertNotEqual(result[0]['doi'],'10.1/seen')

    def test_seen_papers_never_reappear_when_pool_is_exhausted(self):
        pool=[paper('10.1/a'),paper('10.1/b'),paper('10.1/c','Quantum materials')]
        seen=set().union(*(item_keys(p,'papers') for p in pool))
        with self.assertRaises(RuntimeError):select_papers(pool,seen,TODAY)

    def test_doi_variants_and_title_aliases_are_always_excluded(self):
        prior=paper('https://doi.org/10.1/OLD','Human cognition model',title_zh='人类认知模型')
        variants=[paper('10.1/old','Different title'),paper('10.1/changed','HUMAN COGNITION MODEL!'),paper('10.1/translated','人类认知模型')]
        seen=item_keys(prior,'papers')
        self.assertTrue(all(item_keys(p,'papers') & seen for p in variants))

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
        rows=[{'url':f'https://example.com/{c}/{i}','title':f'{c} release {i}','company':c,'published':'2026-09-15'} for c in ['OpenAI','DeepSeek','Anthropic','Google DeepMind','NVIDIA'] for i in range(3)]
        result=choose_news(rows,set())
        self.assertEqual(len(result),6)
        self.assertEqual(len({r['company'] for r in result}),5)

    def test_old_news_and_tracking_variants_are_not_reused(self):
        old={'url':'https://www.example.com/news/model/','title':'New model release','company':'DeepSeek','published':'2026-09-10'}
        same_url={**old,'url':'https://example.com/news/model?utm_source=rss#section','title':'模型发布'}
        same_title={**old,'url':'https://example.com/new-path','title':'NEW MODEL RELEASE!'}
        fresh={**old,'url':'https://example.com/news/new','title':'A separate new model'}
        self.assertEqual(choose_news([same_url,same_title],item_keys(old,'news')),[])
        self.assertEqual(choose_news([same_url,same_title,fresh],item_keys(old,'news')),[fresh])
        self.assertNotEqual(canonical_url('https://qwen.ai/blog?id=one'),canonical_url('https://qwen.ai/blog?id=two'))

    def test_same_issue_news_deduplicates_titles_and_urls(self):
        a={'url':'https://example.com/a','title':'New AI model','company':'OpenAI','published':'2026-09-15'}
        self.assertEqual(len(choose_news([a,{**a,'url':'https://example.com/b','title':'NEW AI MODEL!'}],set())),1)

class PublicationTests(unittest.TestCase):
    def test_history_is_cumulative_and_dry_read_is_non_mutating(self):
        seed=json.loads((build.DATA/'2026-09-15.json').read_text())
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp)/'issues';data.mkdir()
            issue_path=data/f"{seed['date']}.json"
            issue_path.write_text(json.dumps(seed))
            history=load_history(data)
            save_history(data,history)
            self.assertEqual(len(history['papers']),3)
            self.assertEqual(len(history['news']),5)
            before=(data.parent/'history.json').read_bytes()
            self.assertEqual(history,load_history(data))
            self.assertEqual(before,(data.parent/'history.json').read_bytes())
            next_issue=copy.deepcopy(seed)
            next_issue['date']=str(dt.date.fromisoformat(seed['date'])+dt.timedelta(days=1))
            for kind in ('papers','news'):
                for index,item in enumerate(next_issue[kind]):
                    item['title']=f'Distinct new {kind} item {index}'
                    item['url']=f'https://example.com/{kind}/{index}'
                    if kind=='papers':item['doi']=f'10.1234/new-{index}'
                    for key in ('title_zh','original_title','title_aliases','url_aliases'):item.pop(key,None)
            assert_unseen(next_issue,history)
            (data/f"{next_issue['date']}.json").write_text(json.dumps(next_issue))
            updated=load_history(data);save_history(data,updated)
            self.assertEqual(len(updated['papers']),6)
            self.assertEqual(len(updated['news']),10)
            issue_path.unlink()
            self.assertEqual(updated,load_history(data))
            with self.assertRaises(ValueError):assert_unseen(seed,updated)

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

class ReadingAndSummaryTests(unittest.TestCase):
    def test_reading_identity_survives_translation_and_tracking_changes(self):
        p=paper('10.1234/PAPER')
        self.assertEqual(build.reading_id(p,'papers'),build.reading_id({**p,'doi':'https://doi.org/10.1234/paper','title_zh':'新标题'},'papers'))
        n={'url':'https://www.example.com/post/?utm_source=feed'}
        self.assertEqual(build.reading_id(n,'news'),build.reading_id({'url':'https://example.com/post'},'news'))

    def test_replaced_item_remains_searchable_and_excluded_from_future_selection(self):
        issue=json.loads((build.DATA/'2026-09-16.json').read_text())
        prior=issue['previous_items']['papers'][0]
        history=record_issue({'version':1,'papers':[],'news':[]},issue)
        self.assertTrue(item_keys(prior,'papers') & history_keys(history,'papers'))
        library=build.render_library([issue])
        self.assertIn(build.reading_id(prior,'papers'),library)
        self.assertIn('修订前条目',library)
        self.assertIn('id="read-search"',library)
        self.assertIn('id="unread-search"',library)

    def test_article_extraction_excludes_navigation_and_scripts(self):
        parser=ArticleParser()
        parser.feed('<nav><p>'+('Noise menu '*15)+'</p></nav><main><p>Researchers trained a language model on human decision data and tested its predictions across unfamiliar psychological experiments.</p><script>malicious instructions</script></main>')
        text=parser.text()
        self.assertIn('Researchers trained',text)
        self.assertNotIn('Noise',text)
        self.assertNotIn('malicious',text)

    def test_missing_source_and_english_output_fail_closed(self):
        with self.assertRaises(ValueError):source_text(paper('10.1/a'),'papers',lambda _: '<html><nav>Login</nav></html>')
        self.assertFalse(valid_chinese({'title_zh':'English title','summary':'English text.'}))
        self.assertFalse(valid_chinese({'title_zh':'中文标题','summary':'太短'}))
        self.assertTrue(valid_chinese({'title_zh':'快速扩展在线存储以服务超过十亿用户','summary':'OpenAI将Habitat从一个Python库扩展为一个全球分布的存储平台，以服务超过10亿ChatGPT用户和每秒2200万次请求。'}))
        self.assertTrue(valid_chinese({'title_zh':'Qwen Code v0.24.0 发布','summary':'这次版本更新修复了任务恢复和会话管理的问题，并改进了网页预览与通知功能，具体变更见官方说明。'}))

if __name__=='__main__':unittest.main()

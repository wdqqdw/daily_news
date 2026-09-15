"""Check every generated document and project-relative navigation link."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote
from build import SITE

class Check(HTMLParser):
    def __init__(self):
        super().__init__();self.links=[];self.paper_count=0;self.title_count=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='article' and a.get('class')=='paper-card':self.paper_count+=1
        if tag=='title':self.title_count+=1
        if tag in ('a','script','img','link'):
            value=a.get('href') or a.get('src')
            if value:self.links.append(value)

def check():
    files=list(SITE.rglob('*.html'))
    assert (SITE/'index.html').exists() and (SITE/'archive.html').exists()
    for path in files:
        text=path.read_text();p=Check();p.feed(text)
        assert p.title_count==1, f'Missing title: {path}'
        if path.name!='archive.html':assert p.paper_count==3, f'Expected 3 papers: {path}'
        for link in p.links:
            u=urlsplit(link)
            if u.scheme or not u.path:continue
            assert (path.parent/unquote(u.path)).resolve().is_relative_to(SITE.resolve()),f'Link escapes site: {link}'
            assert (path.parent/unquote(u.path)).exists(),f'Broken local link: {path}: {link}'
    print(f'Checked {len(files)} HTML pages: 3 papers per edition and all local links exist')

if __name__=='__main__':check()

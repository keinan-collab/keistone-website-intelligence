from unittest.mock import patch
import pytest
from audit_engine import normalized_url, CrawlError, crawl
from report import build_pdf

class Raw:
    def __init__(self,content):
        import io
        self.io=io.BytesIO(content)
    def read(self,n=-1,decode_content=False): return self.io.read(n)

class FakeResponse:
    status_code=200
    headers={'Content-Type':'text/html'}
    def __init__(self,content):
        import io
        self.raw=Raw(content.encode())
    def close(self): pass
class FakeSession:
    trust_env=False
    def get(self,url,**kwargs):
        if url.endswith('/robots.txt'): return FakeResponse('User-agent: *\nAllow: /')
        if url.endswith('/missing'): 
            r=FakeResponse('not found');r.status_code=404;return r
        return FakeResponse('<html lang="en"><head><title>Home</title><meta name="viewport" content="width=device-width"><meta name="description" content="Test"></head><body><h1>Welcome</h1><a href="/missing">Broken</a><img src="/x.png"></body></html>')

def test_url_validation():
    assert normalized_url('example.com')=='https://example.com/'
    for url in ['file:///etc/passwd','http://localhost/','http://127.0.0.1','http://user:pass@example.com']:
        with pytest.raises(CrawlError): normalized_url(url)

def test_crawl_and_pdf():
    with patch('audit_engine.public_host'):
        result=crawl('https://example.com',max_pages=5,delay=0,session=FakeSession())
    assert result['crawled']==2
    assert any(f['code']=='broken_internal_link' for f in result['findings'])
    assert any(f['code']=='missing_alt' for f in result['findings'])
    assert build_pdf(result).startswith(b'%PDF')

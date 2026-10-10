"""Bounded, same-site website crawler and evidence-based SEO diagnostics."""
import ipaddress
import json
import re
import socket
import time
from collections import Counter, deque
from urllib.parse import urljoin, urlsplit, urlunsplit, urldefrag
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

USER_AGENT = 'KeistoneAuditBot/3.0 (+site-owner-authorized-audits)'
ISSUES = {
 'http_4xx': ('HTTP 4xx error', 'error', 'Technical SEO', 'Repair the broken page or update links pointing to it.'),
 'http_5xx': ('HTTP 5xx server error', 'error', 'Technical SEO', 'Investigate server logs and restore the affected page.'),
 'missing_title': ('Missing page title', 'warning', 'On-page SEO', 'Add a unique, descriptive title to this page.'),
 'duplicate_title': ('Duplicate page title', 'warning', 'On-page SEO', 'Write distinct titles that reflect each page’s purpose.'),
 'missing_description': ('Missing meta description', 'warning', 'On-page SEO', 'Add a helpful, unique summary of the page.'),
 'missing_h1': ('Missing H1 heading', 'warning', 'On-page SEO', 'Add one clear primary heading describing the page.'),
 'multiple_h1': ('Multiple H1 headings', 'notice', 'On-page SEO', 'Review heading hierarchy for clarity; multiple H1s are not inherently an SEO error.'),
 'missing_alt': ('Image missing alt attribute', 'warning', 'Accessibility', 'Provide meaningful alt text, or alt="" for decorative images.'),
 'missing_canonical': ('Canonical URL not declared', 'notice', 'Technical SEO', 'Review canonicalization; a canonical tag is not required on every page.'),
 'noindex': ('Page marked noindex', 'notice', 'Indexability', 'Confirm that excluding this page from search is intentional.'),
 'broken_internal_link': ('Internal link points to an error', 'error', 'Internal linking', 'Update the source link or repair the destination.'),
 'redirect': ('Page redirects', 'notice', 'Technical SEO', 'Review the redirect and update internal links to the final URL when appropriate.'),
 'fetch_error': ('Page could not be fetched', 'warning', 'Crawlability', 'Verify DNS, TLS, availability, and bot access.'),
 'blocked_robots': ('URL blocked by robots.txt', 'notice', 'Crawlability', 'Confirm the crawl restriction is intentional.'),
 'missing_lang': ('HTML language not declared', 'warning', 'Accessibility', 'Set the html lang attribute to the page language.'),
 'missing_viewport': ('Mobile viewport missing', 'warning', 'Mobile UX', 'Add a responsive viewport meta tag.'),
 'thin_content': ('Very little visible text', 'notice', 'Content', 'Review whether this page provides sufficient value for its purpose.'),
}

class CrawlError(Exception): pass

def normalized_url(url):
    url = (url or '').strip()
    if not url: raise CrawlError('Enter a website URL.')
    if '://' not in url: url = 'https://' + url
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise CrawlError('Only public HTTP(S) website URLs are allowed.')
    if p.port and p.port not in (80, 443): raise CrawlError('Only standard HTTP(S) ports are allowed.')
    host = p.hostname.lower().rstrip('.')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')) or '.' not in host or re.fullmatch(r'[0-9.]+', host):
        raise CrawlError('A public domain name is required.')
    return urlunsplit((p.scheme, p.netloc.lower(), p.path or '/', p.query, ''))

def public_host(host):
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise CrawlError('Domain could not be resolved.') from exc
    if not infos: raise CrawlError('Domain could not be resolved.')
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global: raise CrawlError('Private or non-public IP addresses cannot be crawled.')

def site_key(url):
    h = urlsplit(url).hostname.lower()
    return h[4:] if h.startswith('www.') else h

def clean_link(url):
    url = urldefrag(url)[0]
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path or '/', p.query, ''))

def issue(code, url, detail=''):
    title, severity, category, fix = ISSUES[code]
    return dict(code=code, title=title, severity=severity, category=category, url=url, detail=detail, fix=fix)

def guarded_get(session, url, root_key, timeout=10, max_redirects=5):
    """Reject off-site and non-public redirects; DNS checked before each hop."""
    current = url
    for step in range(max_redirects + 1):
        p = urlsplit(normalized_url(current))
        if site_key(current) != root_key: raise CrawlError('Redirect leaves the audited website.')
        public_host(p.hostname)
        r = session.get(current, headers={'User-Agent': USER_AGENT, 'Accept': 'text/html,application/xhtml+xml'},
                        timeout=timeout, allow_redirects=False, stream=True)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get('Location'):
            dest = clean_link(urljoin(current, r.headers['Location']))
            r.close()
            current = dest
            continue
        return r, current, step
    raise CrawlError('Too many redirects.')

def crawl(start_url, max_pages=100, delay=0.2, progress=None, session=None):
    start_url = normalized_url(start_url)
    root_key = site_key(start_url)
    public_host(urlsplit(start_url).hostname)
    max_pages = max(1, min(int(max_pages), 250))
    session = session or requests.Session()
    session.trust_env = False  # avoid proxy environment routing to private networks
    pages, findings, edges = [], [], []
    visited, queued = set(), {start_url}
    queue = deque([start_url])
    robots = RobotFileParser()
    robots_url = urljoin(start_url, '/robots.txt')
    try:
        rr, _, _ = guarded_get(session, robots_url, root_key)
        data = rr.raw.read(200000, decode_content=True).decode('utf-8', errors='replace') if rr.status_code == 200 else ''
        rr.close()
        robots.parse(data.splitlines())
    except (requests.RequestException, CrawlError):
        robots.parse([])  # inability to retrieve robots is reported, not treated as an explicit allow
        findings.append(issue('fetch_error', robots_url, 'Could not verify robots.txt; crawl policy may be incomplete.'))
    while queue and len(pages) < max_pages:
        url = queue.popleft()
        if url in visited: continue
        visited.add(url)
        if not robots.can_fetch(USER_AGENT, url):
            findings.append(issue('blocked_robots', url))
            continue
        record = dict(url=url, status=None, final_url=url, title='', description='', h1='', word_count=0, links=0)
        try:
            response, final, redirects = guarded_get(session, url, root_key)
            record['status'], record['final_url'] = response.status_code, final
            if redirects: findings.append(issue('redirect', url, f'{redirects} redirect(s); final destination: {final}'))
            if 400 <= response.status_code < 500: findings.append(issue('http_4xx', url, f'HTTP {response.status_code}'))
            if response.status_code >= 500: findings.append(issue('http_5xx', url, f'HTTP {response.status_code}'))
            content_type = response.headers.get('Content-Type', '').lower()
            if response.status_code == 200 and ('text/html' in content_type or 'application/xhtml+xml' in content_type):
                raw = response.raw.read(2_000_001, decode_content=True)
                if len(raw) > 2_000_000: raise CrawlError('Page HTML exceeds the 2 MB safety limit.')
                soup = BeautifulSoup(raw, 'html.parser')
                title = soup.title.get_text(' ', strip=True) if soup.title else ''
                description = soup.find('meta', attrs={'name': re.compile('^description$', re.I)})
                h1s = soup.find_all('h1')
                record.update(title=title, description=description.get('content', '').strip() if description else '',
                              h1=h1s[0].get_text(' ', strip=True) if h1s else '')
                if not title: findings.append(issue('missing_title', url))
                if not record['description']: findings.append(issue('missing_description', url))
                if not h1s: findings.append(issue('missing_h1', url))
                if len(h1s) > 1: findings.append(issue('multiple_h1', url, f'{len(h1s)} H1 headings'))
                if not soup.find('link', attrs={'rel': lambda v: v and 'canonical' in v}): findings.append(issue('missing_canonical', url))
                if not soup.html or not soup.html.get('lang'): findings.append(issue('missing_lang', url))
                if not soup.find('meta', attrs={'name': re.compile('^viewport$', re.I)}): findings.append(issue('missing_viewport', url))
                robot_meta = soup.find('meta', attrs={'name': re.compile('^robots$', re.I)})
                if robot_meta and 'noindex' in robot_meta.get('content', '').lower(): findings.append(issue('noindex', url))
                missing_alt = sum(1 for img in soup.find_all('img') if not img.has_attr('alt'))
                if missing_alt: findings.append(issue('missing_alt', url, f'{missing_alt} image(s) missing alt attributes'))
                for t in soup(['script','style','nav','footer','header']): t.decompose()
                words = len(soup.get_text(' ', strip=True).split())
                record['word_count'] = words
                if words < 80: findings.append(issue('thin_content', url, f'{words} visible words; contextual review required'))
                # parse links from original markup, not the content-filtered soup
                link_soup = BeautifulSoup(raw, 'html.parser')
                for a in link_soup.find_all('a', href=True):
                    href = a['href'].strip()
                    if not href or href.startswith(('#','mailto:','tel:','javascript:')): continue
                    try:
                        dest = clean_link(urljoin(final, href))
                        if urlsplit(dest).scheme not in ('http','https') or site_key(dest) != root_key: continue
                        normalized_url(dest)
                    except (ValueError, CrawlError): continue
                    edges.append((url, dest))
                    record['links'] += 1
                    if dest not in queued and dest not in visited and len(queued) < 2500:
                        queued.add(dest); queue.append(dest)
            response.close()
        except (requests.RequestException, CrawlError, ValueError) as exc:
            findings.append(issue('fetch_error', url, str(exc)[:240]))
        pages.append(record)
        if progress: progress(len(pages), max_pages)
        if delay: time.sleep(delay)
    status_by_url = {p['url']:p['status'] for p in pages}
    for src, dest in set(edges):
        if dest in status_by_url and status_by_url[dest] is not None and status_by_url[dest] >= 400:
            findings.append(issue('broken_internal_link', src, f'Links to {dest} (HTTP {status_by_url[dest]})'))
    titles = {}
    for p in pages:
        if p['title']:
            key = p['title'].casefold()
            if key in titles: findings.append(issue('duplicate_title', p['url'], f'Same title as {titles[key]}'))
            else: titles[key] = p['url']
    counts = Counter(f['severity'] for f in findings)
    # Transparent heuristic, not a Google or SEMrush score. Counts normalized per crawled page.
    n = max(1, len(pages))
    score = max(0, round(100 - min(65, counts['error'] * 20 / n * 10) - min(25, counts['warning'] * 3 / n * 10) - min(10, counts['notice'] * .5 / n * 10)))
    return dict(url=start_url, pages=pages, findings=findings, score=score,
                counts=dict(counts), crawled=len(pages), capped=bool(queue),
                methodology='Heuristic score: 100 minus capped penalties for errors, warnings, and notices per crawled page. Not comparable to SEMrush Site Health.',
                created_at=time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()))

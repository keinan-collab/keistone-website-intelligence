# Keistone Kollective 360° Website Intelligence v3

A deployable Flask website audit application with a real bounded crawler, issue inventory, heuristic technical health score, audit history (SQLite), responsive dashboard, and branded PDF reports.

## Quick start

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 and enter a public HTTP(S) website URL.

## Deploy with Docker

```bash
docker build -t keistone-intelligence .
docker run --rm -p 5000:5000 -e PORT=5000 -v keistone-data:/data -e AUDIT_DB=/data/audit_history.sqlite3 keistone-intelligence
```

Open http://localhost:5000. `Procfile` is also included for compatible Python hosting services.

## What is real vs. not yet connected

**Implemented:** bounded same-site HTTP crawling; basic robots.txt compliance; response status; broken internal links (for fetched pages); title/H1/meta description checks; duplicate titles; canonical, noindex, lang, viewport, alt attribute, and thin-content indicators; issue severity; transparent heuristic scoring; SQLite audit history; PDF report generation.

**Not implemented:** JavaScript rendering; browser screenshots; Core Web Vitals / PageSpeed Insights; GA4 or Google Search Console; organic traffic estimates; backlink authority; rank tracking; local directory checks; AI mentions; complete WCAG compliance; true conversion or UX assessment. Dashboard labels these as unconnected rather than fabricating numbers. Version 2 experimental enhancements are not carried over until they can be safely integrated and verified.

## Important operational and security limitations

This is a **deployable MVP, not a public multi-tenant SaaS**. It has no login, per-user access controls, billing, rate limiting, distributed job queue, or private client data isolation. **Do not expose it publicly without implementing authentication, authorization, quotas, persistent storage and production hardening.**

The crawler restricts URLs to public HTTP(S) hosts and same-site redirects, rejects non-global resolved IPs, and caps crawl pages and HTML size. DNS rebinding is still a risk because DNS is resolved again during HTTP connection; enforce outbound network egress rules to deny private, loopback, link-local and metadata IP ranges at the infrastructure layer. Do not grant access to internal networks. Proxies are disabled for the crawl session.

Crawl only websites you own or are authorized to audit. Follow the target site's robots.txt and rate limits. The crawler cannot reliably distinguish blocked resources from all crawl failures. A robots.txt fetch failure is reported and the current prototype continues conservatively with a low request rate; for stricter deployments, configure fail-closed behavior.

The in-process background thread is a single-instance MVP design. Production should use a durable job queue and a database such as PostgreSQL. SQLite data should live on a persistent volume. Gunicorn is configured with one worker to avoid SQLite/threaded-job coordination surprises; running jobs can be lost on restart.

Scoring is a heuristic derived from detected findings per crawled page, not Google's ranking signal or SEMrush's proprietary Site Health score. A missing canonical is only a notice; thin content is contextual; multiple H1 elements are not automatically errors. The score is not meaningful if only a few pages were successfully fetched.

## Test

```bash
python -m compileall -q .
python -m pytest -q
```

## Future production milestones

1. Authentication, accounts, audit quotas, PostgreSQL, durable jobs, egress protection.
2. Browser rendering, screenshots, PageSpeed API, manual UX review workflow.
3. Google Search Console integration, rank tracking, backlink provider, local SEO and AI visibility monitoring.
4. Custom branded client report templates, white-label portal, scheduled re-audits.

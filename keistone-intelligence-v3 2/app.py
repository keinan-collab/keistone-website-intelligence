import io
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, request, send_file
from audit_engine import CrawlError, crawl, normalized_url
from report import build_pdf

BASE = Path(__file__).resolve().parent
DB = Path(os.environ.get('AUDIT_DB', str(BASE / 'audit_history.sqlite3')))
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024
app.json.sort_keys = False
LOCK = threading.Lock()

def db():
    conn = sqlite3.connect(DB, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS audits (id TEXT PRIMARY KEY, url TEXT NOT NULL, status TEXT NOT NULL, progress INTEGER DEFAULT 0, created_at TEXT NOT NULL, result TEXT, error TEXT)')
init_db()

def update(audit_id, **fields):
    with LOCK, db() as c:
        c.execute('UPDATE audits SET '+', '.join(f'{k}=?' for k in fields)+' WHERE id=?', [*fields.values(), audit_id])

def execute(audit_id, url, max_pages):
    try:
        result = crawl(url, max_pages=max_pages, progress=lambda n, total: update(audit_id, progress=n))
        update(audit_id, status='complete', result=json.dumps(result), progress=result['crawled'])
    except Exception as exc:
        update(audit_id, status='failed', error=str(exc)[:500])

@app.get('/')
def index(): return render_template('index.html')

@app.get('/api/audits')
def history():
    with db() as c:
        rows = c.execute('SELECT id,url,status,progress,created_at,result,error FROM audits ORDER BY created_at DESC LIMIT 30').fetchall()
    items=[]
    for row in rows:
        d=dict(row); raw=d.pop('result')
        if raw:
            r=json.loads(raw); d.update(score=r['score'], crawled=r['crawled'], counts=r['counts'])
        items.append(d)
    return jsonify(items)

@app.post('/api/audits')
def start():
    data=request.get_json(silent=True) or {}
    try:
        url=normalized_url(data.get('url', ''))
        pages=max(1,min(int(data.get('max_pages', 100)),250))
    except (CrawlError, ValueError, TypeError) as exc:
        return jsonify(error=str(exc)),400
    audit_id=uuid.uuid4().hex
    with db() as c:
        c.execute('INSERT INTO audits(id,url,status,created_at) VALUES(?,?,?,?)', (audit_id,url,'running',datetime.now(timezone.utc).isoformat()))
    threading.Thread(target=execute,args=(audit_id,url,pages),daemon=True).start()
    return jsonify(id=audit_id,status='running'),202

@app.get('/api/audits/<audit_id>')
def detail(audit_id):
    with db() as c: row=c.execute('SELECT * FROM audits WHERE id=?',(audit_id,)).fetchone()
    if not row: abort(404)
    d=dict(row)
    if d['result']: d['result']=json.loads(d['result'])
    return jsonify(d)

@app.get('/api/audits/<audit_id>/report.pdf')
def pdf(audit_id):
    with db() as c: row=c.execute('SELECT status,result FROM audits WHERE id=?',(audit_id,)).fetchone()
    if not row: abort(404)
    if row['status']!='complete': return jsonify(error='Audit is not complete'),409
    content=build_pdf(json.loads(row['result']))
    return send_file(io.BytesIO(content), mimetype='application/pdf', as_attachment=True, download_name=f'keistone-audit-{audit_id[:8]}.pdf')

@app.get('/health')
def health(): return jsonify(status='ok')

if __name__=='__main__':
    app.run(host='127.0.0.1',port=int(os.environ.get('PORT',5000)),debug=False)

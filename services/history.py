"""누적 작업 이력: 승인한 작업을 SQLite에 한 줄씩 추가합니다(덮어쓰지 않음).

- 파일: runtime/history.db (저장소에는 올리지 않음)
- 세션 구분: 브라우저 주소의 ?sid= 값. 새로고침해도 같은 주소면 같은 이력을 봅니다.
- 한계: Streamlit Community Cloud의 디스크는 앱 재시작·재배포 때 초기화됩니다. 그때 이력도 지워집니다.
"""
import json
from contextlib import closing
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path

DB = Path(os.environ.get('STOWSYNC_HISTORY_DB') or Path(__file__).resolve().parents[1] / 'runtime' / 'history.db')
_LOCK = threading.Lock()
COLUMNS = ('job_id', 'sid', 'saved_at', 'sim_time', 'source', 'container', 'compared', 'approved', 'order_text',
           'total_min', 'base_total_min', 'saved_min', 'reason', 'status', 'detail')


def _conn(path=None):
    p = Path(path or os.environ.get('STOWSYNC_HISTORY_DB') or DB)
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, check_same_thread=False)
    c.execute('CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, sid TEXT, saved_at REAL, sim_time TEXT, source TEXT, '
              'container TEXT, compared TEXT, approved TEXT, order_text TEXT, total_min REAL, base_total_min REAL, saved_min REAL, '
              'reason TEXT, status TEXT, detail TEXT)')
    return c


def new_job_id():
    return 'JOB-' + time.strftime('%m%d') + '-' + uuid.uuid4().hex[:6].upper()


def add(entry, path=None):
    """entry: COLUMNS 중 일부(dict). job_id·saved_at은 없으면 만듭니다. 같은 job_id가 있으면 추가하지 않습니다."""
    row = {k: entry.get(k) for k in COLUMNS}
    row['job_id'] = row['job_id'] or new_job_id()
    row['saved_at'] = row['saved_at'] or time.time()
    for k in ('compared', 'detail'):
        if row[k] is not None and not isinstance(row[k], str):
            row[k] = json.dumps(row[k], ensure_ascii=False)
    with _LOCK, closing(_conn(path)) as c, c:
        c.execute(f'INSERT OR IGNORE INTO jobs ({",".join(COLUMNS)}) VALUES ({",".join("?" * len(COLUMNS))})',
                  [row[k] for k in COLUMNS])
    return row['job_id']


def update_status(job_id, status, path=None):
    with _LOCK, closing(_conn(path)) as c, c:
        c.execute('UPDATE jobs SET status=? WHERE job_id=?', (status, job_id))


def list_jobs(sid=None, path=None):
    with _LOCK, closing(_conn(path)) as c:
        q = f'SELECT {",".join(COLUMNS)} FROM jobs' + (' WHERE sid=?' if sid else '') + ' ORDER BY saved_at DESC'
        rows = c.execute(q, (sid,) if sid else ()).fetchall()
    out = []
    for r in rows:
        d = dict(zip(COLUMNS, r))
        for k in ('compared', 'detail'):
            try:
                d[k] = json.loads(d[k]) if d[k] else None
            except ValueError:
                pass
        out.append(d)
    return out

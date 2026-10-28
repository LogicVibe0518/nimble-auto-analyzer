"""Small durable job store. One SQLite connection per operation, no ORM required."""
import json
import sqlite3
from pathlib import Path
from threading import RLock

class JobStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = RLock()

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self):
        with self._lock, self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, payload TEXT NOT NULL, pdf BLOB)')
            rows = db.execute('SELECT id, payload FROM jobs').fetchall()
            for row in rows:
                job = json.loads(row['payload'])
                if job['status'] in ('queued', 'running'):
                    job.update(status='failed', stage='Interrupted by restart', error='The server restarted before this analysis finished. Submit a new analysis.')
                    db.execute('UPDATE jobs SET payload=? WHERE id=?', (json.dumps(job), row['id']))

    def create(self, job: dict):
        with self._lock, self._connect() as db:
            db.execute('INSERT INTO jobs(id,payload) VALUES (?,?)', (job['id'], json.dumps(job)))

    def update(self, id: str, *, pdf: bytes | None = None, **values):
        with self._lock, self._connect() as db:
            row = db.execute('SELECT payload FROM jobs WHERE id=?', (id,)).fetchone()
            if row is None:
                raise KeyError(id)
            job = json.loads(row['payload'])
            job.update(values)
            db.execute('UPDATE jobs SET payload=?, pdf=COALESCE(?,pdf) WHERE id=?', (json.dumps(job), pdf, id))

    def get(self, id: str):
        with self._lock, self._connect() as db:
            row = db.execute('SELECT payload FROM jobs WHERE id=?', (id,)).fetchone()
            return json.loads(row['payload']) if row else None

    def pdf(self, id: str):
        with self._lock, self._connect() as db:
            row = db.execute('SELECT pdf FROM jobs WHERE id=?', (id,)).fetchone()
            return row['pdf'] if row else None

    def list(self, limit=30):
        with self._lock, self._connect() as db:
            rows = db.execute('SELECT payload FROM jobs ORDER BY rowid DESC LIMIT ?', (limit,)).fetchall()
            return [json.loads(row['payload']) for row in rows]

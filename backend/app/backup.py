"""Verified local recovery copies. Never overwrite a source or an existing destination.

Run from backend: python -m app.backup backup --output <new.sqlite3>
                  python -m app.backup restore-copy --source <backup.sqlite3> --output <new.sqlite3>
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from .database import ClosingConnection

REQUIRED={'streams','event_versions','graph_nodes','graph_edges','corrections','draft_reviews',
          'review_requests','publications','publication_requests'}
OPTIONAL={'access_users','access_sessions','access_attempts'}


def verify(path):
    path=Path(path).resolve()
    if not path.is_file():raise ValueError('Source database does not exist.')
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,factory=ClosingConnection) as db:
        if db.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise ValueError('Database integrity check failed.')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not REQUIRED.issubset(tables):raise ValueError('Not a complete MatchMind foundation database.')
        counts={name:db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in sorted((REQUIRED|OPTIONAL)&tables)}
    with path.open('rb') as handle:checksum=hashlib.file_digest(handle,'sha256').hexdigest()
    return {'path':str(path),'integrity':'ok','counts':counts,'sha256':checksum}


def recovery_copy(source,output,restore=False):
    source=Path(source).resolve();output=Path(output).resolve()
    if source==output:raise ValueError('Source and destination must differ.')
    verify(source)
    output.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive reservation prevents accidental replacement or symlink following.
    fd=os.open(output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    try:
        deadline=time.monotonic()+30
        def progress(status,remaining,total):
            if time.monotonic()>deadline:raise TimeoutError('Database copy exceeded 30 seconds; retry when contention is lower.')
        with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=5,factory=ClosingConnection) as src:
            with sqlite3.connect(output,timeout=5,factory=ClosingConnection) as dst:
                src.backup(dst,pages=128,progress=progress,sleep=0.05)
                if restore:
                    exists=dst.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='access_sessions'").fetchone()
                    if exists:dst.execute('DELETE FROM access_sessions')
        result=verify(output)
        result['operation']='restore_copy' if restore else 'backup'
        result['sessions_revoked']=restore
        return result
    except Exception:
        # Remove only the new file reserved above; the source is never modified.
        output.unlink(missing_ok=True)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['backup','restore-copy','verify'])
    parser.add_argument('--source',default=os.getenv('MATCHMIND_FOUNDATION_DB',str(Path(__file__).resolve().parents[1]/'data/foundation.sqlite3')))
    parser.add_argument('--output')
    args=parser.parse_args()
    if args.operation=='verify':result=verify(args.source)
    else:
        if not args.output:parser.error('--output is required and must name a new file')
        result=recovery_copy(args.source,args.output,restore=args.operation=='restore-copy')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()

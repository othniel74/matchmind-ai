"""Transactional, seed-scoped SQLite storage for reproducible demo replays."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from .core import Event, GENERATOR_VERSION, generate_match, validate_event_stream
from .database import ClosingConnection


class EventStore:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS replays (replay_key TEXT PRIMARY KEY, digest TEXT NOT NULL, payload TEXT NOT NULL)')

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10, factory=ClosingConnection)

    def save(self, key: str, events: list[Event]) -> bool:
        validate_event_stream(events)
        payload = json.dumps([e.json() for e in events], sort_keys=True, separators=(',', ':'))
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT digest FROM replays WHERE replay_key=?', (key,)).fetchone()
            if existing:
                if existing[0] != digest:
                    raise ValueError('Replay key already contains different events')
                return False
            db.execute('INSERT INTO replays VALUES (?, ?, ?)', (key, digest, payload))
        return True

    def load(self, key: str) -> list[Event] | None:
        with self._connect() as db:
            row = db.execute('SELECT digest, payload FROM replays WHERE replay_key=?', (key,)).fetchone()
        if row is None:
            return None
        if hashlib.sha256(row[1].encode()).hexdigest() != row[0]:
            raise ValueError('Stored replay integrity check failed')
        events = [Event(**item) for item in json.loads(row[1])]
        validate_event_stream(events)
        return events

def replay_events(seed: int = 20261020) -> list[Event]:
    path = os.getenv('MATCHMIND_EVENT_DB')
    if not path:
        return generate_match(seed)
    store = EventStore(path)
    key = f'generator-{GENERATOR_VERSION}:seed-{seed}'
    events = store.load(key)
    if events is None:
        events = generate_match(seed)
        store.save(key, events)
    return events

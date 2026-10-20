"""Shared graph contract and portable Bolt/Cypher repository.

The event log remains canonical. Graph projections can be rebuilt by replay.
No DB access at module import; a repository is connected only on demand.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
from ..core import Event, validate_event_stream
from .analytics import network_snapshot

class GraphRepository(Protocol):
    def health(self) -> dict: ...
    def upsert_events(self, events: list[Event]) -> int: ...
    def read_events(self, match_id: str) -> list[dict]: ...
    def read_pass_edges(self, match_id: str, team: str) -> list[dict]: ...
    def close(self) -> None: ...

@dataclass
class BoltGraphRepository:
    backend: str
    uri: str
    user: str = ''
    password: str = ''
    database: str | None = None

    def __post_init__(self):
        if self.backend not in ('memgraph', 'neo4j'):
            raise ValueError('GRAPH_BACKEND must be memgraph or neo4j')
        from neo4j import GraphDatabase
        # Memgraph community deployments commonly run without authentication.
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password) if self.user else None,
                                           connection_timeout=3)

    def _session(self):
        return self.driver.session(database=self.database) if self.database else self.driver.session()

    def health(self) -> dict:
        with self._session() as session:
            session.run('RETURN 1 AS ok').single()
        return {'status': 'ok', 'backend': self.backend}

    def upsert_events(self, events: list[Event]) -> int:
        validate_event_stream(events)
        if not events:
            return 0
        # One query works on both engines; use match-scoped event IDs.
        rows = [e.json() for e in events]
        with self._session() as session, session.begin_transaction() as transaction:
            # Replace the match projection atomically, including obsolete actors
            # and edges from a previous seed. Other matches remain untouched.
            transaction.run("""MATCH (n) WHERE
                ((n:Match AND n.id=$match_id) OR
                ((n:Team OR n:Player OR n:MatchEvent) AND n.match_id=$match_id)) AND NOT n:KG
                DETACH DELETE n""", match_id=events[0].match_id).consume()
            transaction.run("""UNWIND $rows AS e
                MERGE (m:Match {id: e.match_id})
                MERGE (t:Team {id: e.team_id, match_id: e.match_id})
                MERGE (p:Player {id: e.player_id, match_id: e.match_id})
                FOREACH (recipient IN CASE WHEN e.recipient_player_id IS NULL THEN [] ELSE [e.recipient_player_id] END |
                    MERGE (receiver:Player {id: recipient, match_id: e.match_id})
                    MERGE (t)-[:HAS_PLAYER]->(receiver))
                FOREACH (substitute IN CASE WHEN e.replacement_player_id IS NULL THEN [] ELSE [e.replacement_player_id] END |
                    MERGE (bench:Player {id: substitute, match_id: e.match_id})
                    MERGE (t)-[:HAS_PLAYER]->(bench))
                MERGE (m)-[:HAS_TEAM]->(t)
                MERGE (t)-[:HAS_PLAYER]->(p)
                MERGE (v:MatchEvent {id: e.event_id, match_id: e.match_id})
                SET v.sequence=e.sequence, v.minute=e.minute, v.second=e.second,
                    v.event_type=e.event_type, v.team_id=e.team_id,
                    v.player_id=e.player_id, v.possession_id=e.possession_id,
                    v.x=e.x, v.y=e.y, v.end_x=e.end_x, v.end_y=e.end_y,
                    v.outcome=e.outcome, v.recipient_player_id=e.recipient_player_id,
                    v.set_piece=e.set_piece, v.xg=e.xg, v.replacement_player_id=e.replacement_player_id
                MERGE (m)-[:HAS_EVENT]->(v)
                MERGE (p)-[:PERFORMED]->(v)""", rows=rows).consume()
            # Replace materialized proxy relationships for this match. Event nodes
            # are idempotent, and pass edge IDs prevent duplicate projections.
            for team in sorted({e.team_id for e in events}):
                snapshot = network_snapshot(events, team, 0, 90)
                edges = [{'match_id': events[0].match_id, 'team': team, **edge} for edge in snapshot['edges']]
                if edges:
                    transaction.run("""UNWIND $edges AS e
                        MATCH (a:Player {id:e.source, match_id:e.match_id})
                        MATCH (b:Player {id:e.target, match_id:e.match_id})
                        MERGE (a)-[r:PROXY_PASSED_TO {match_id:e.match_id, team_id:e.team}]->(b)
                        SET r.weight=e.weight, r.event_ids=e.event_ids, r.receiver_method=$receiver_method """, edges=edges, receiver_method=snapshot['metrics']['receiver_method']).consume()
            transaction.commit()
        return len(events)

    def read_events(self, match_id: str) -> list[dict]:
        with self._session() as session:
            rows = session.run("""MATCH (:Match {id:$match_id})-[:HAS_EVENT]->(e:MatchEvent)
                RETURN e.id AS event_id, e.sequence AS sequence, e.minute AS minute,
                e.second AS second, e.team_id AS team_id, e.player_id AS player_id,
                e.event_type AS event_type, e.possession_id AS possession_id,
                e.recipient_player_id AS recipient_player_id, e.outcome AS outcome,
                e.x AS x, e.y AS y, e.end_x AS end_x, e.end_y AS end_y,
                e.match_id AS match_id
                ORDER BY sequence""", match_id=match_id)
            return [dict(row) for row in rows]

    def read_pass_edges(self, match_id: str, team: str) -> list[dict]:
        with self._session() as session:
            rows = session.run("""MATCH (a:Player {match_id:$match_id})-[r:PROXY_PASSED_TO {match_id:$match_id, team_id:$team}]->(b:Player)
                RETURN a.id AS source, b.id AS target, r.weight AS weight, r.event_ids AS event_ids
                ORDER BY source, target""", match_id=match_id, team=team)
            return [dict(row) for row in rows]

    # Knowledge graph projection. Labels and relationship types cannot be query parameters,
    # so they come from the fixed whitelists in knowledge.py, never from input.
    def ensure_indexes(self) -> None:
        statements = (['CREATE INDEX ON :KG(key)', 'CREATE INDEX ON :KG(match_id)'] if self.backend == 'memgraph' else
                      ['CREATE INDEX kg_key IF NOT EXISTS FOR (n:KG) ON (n.key)',
                       'CREATE INDEX kg_match IF NOT EXISTS FOR (n:KG) ON (n.match_id)'])
        for statement in statements:
            with self._session() as session:
                try:
                    session.run(statement).consume()
                except Exception:  # an existing index is not an error
                    pass

    def project_knowledge(self, g) -> dict:
        """Replace one match's knowledge graph atomically; rerunning gives the same graph."""
        from ..knowledge import NODE_KINDS, RELATIONS, projection_rows
        match_id = g.graph['match_id']
        nodes, edges = projection_rows(g)
        self.ensure_indexes()
        with self._session() as session, session.begin_transaction() as transaction:
            transaction.run('MATCH (n:KG {match_id:$match_id}) DETACH DELETE n', match_id=match_id).consume()
            for kind in NODE_KINDS:
                if nodes.get(kind):
                    transaction.run(f"""UNWIND $rows AS r
                        CREATE (n:KG:{kind} {{key: r.key, match_id: $match_id}}) SET n += r.props""",
                                    rows=nodes[kind], match_id=match_id).consume()
            for relation in RELATIONS:
                if edges.get(relation):
                    transaction.run(f"""UNWIND $rows AS r
                        MATCH (a:KG {{key: r.a, match_id: $match_id}})
                        MATCH (b:KG {{key: r.b, match_id: $match_id}})
                        CREATE (a)-[x:{relation}]->(b) SET x += r.props""",
                                    rows=edges[relation], match_id=match_id).consume()
            transaction.commit()
        return {'nodes': sum(map(len, nodes.values())), 'relationships': sum(map(len, edges.values()))}

    def _rows(self, query: str, **params) -> list[dict]:
        with self._session() as session:
            return [dict(row) for row in session.run(query, **params)]

    def kg_summary(self, match_id: str) -> dict:
        nodes = self._rows('MATCH (n:KG {match_id:$m}) RETURN n.kind AS kind, count(*) AS c', m=match_id)
        rels = self._rows('MATCH (a:KG {match_id:$m})-[r]->(:KG) RETURN type(r) AS t, count(*) AS c', m=match_id)
        return {'nodes': dict(sorted((r['kind'], r['c']) for r in nodes)),
                'relationships': dict(sorted((r['t'], r['c']) for r in rels))}

    def kg_pass_lanes(self, match_id: str, team: str, start: int, end: int) -> list[dict]:
        return self._rows("""MATCH (a:KG:Player {match_id:$m})-[:PERFORMED]->(e:KG:Event)-[:RECEIVED_BY]->(b:KG:Player)
            WHERE e.team_id = $team AND e.minute >= $start AND e.minute < $end
            WITH a.player_id AS source, b.player_id AS target, e ORDER BY e.clock, e.event_id
            RETURN source, target, count(e) AS weight, collect(e.event_id) AS event_ids
            ORDER BY weight DESC, source, target""", m=match_id, team=team, start=start, end=end)

    def kg_evidence(self, match_id: str, moment_id: str) -> list[str]:
        return [r['id'] for r in self._rows("""MATCH (e:KG:Event {match_id:$m})-[:EVIDENCES]->(x:KG:Moment {match_id:$m, moment_id:$id})
            RETURN e.event_id AS id, e.clock AS clock ORDER BY clock, id""", m=match_id, id=moment_id)]

    def kg_impact(self, match_id: str, event_id: str) -> dict:
        rows = self._rows("""MATCH (e:KG:Event {match_id:$m, event_id:$id})-[r:EVIDENCES|SUPPORTS]->(x:KG)
            RETURN type(r) AS rel, coalesce(x.moment_id, x.claim_id) AS id ORDER BY rel, id""", m=match_id, id=event_id)
        return {'moments': [r['id'] for r in rows if r['rel'] == 'EVIDENCES'],
                'claims': [r['id'] for r in rows if r['rel'] == 'SUPPORTS']}

    def kg_xg_chain(self, match_id: str, team: str) -> list[dict]:
        rows = self._rows("""MATCH (p:KG:Player {match_id:$m})-[:PERFORMED]->(e:KG:Event)-[:IN_POSSESSION]->(s:KG:Possession)
            WHERE s.team_id = $team AND e.team_id = $team AND s.xg > 0
            WITH DISTINCT p, s
            RETURN p.player_id AS player_id, sum(s.xg) AS xg_chain, count(s) AS possessions""", m=match_id, team=team)
        return sorted(({**r, 'xg_chain': round(r['xg_chain'], 2)} for r in rows),
                      key=lambda r: (-r['xg_chain'], r['player_id']))

    def kg_timeline(self, match_id: str) -> list[str]:
        rows = self._rows("""MATCH (x:KG:Moment {match_id:$m})
            OPTIONAL MATCH (p:KG:Moment)-[:FOLLOWS]->(x)
            RETURN x.moment_id AS id, p.moment_id AS previous""", m=match_id)
        after = {r['previous']: r['id'] for r in rows}
        order, current = [], after.get(None)
        while current is not None and len(order) <= len(rows):
            order.append(current)
            current = after.get(current)
        return order

    def close(self):
        self.driver.close()

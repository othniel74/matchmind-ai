> **17 October 2026 update:** Read [the current verification report](VERIFICATION_2026_10_17.md) before using this earlier plan. Frontend compilation and local browser checks now pass; synthetic scoring, explicit recipients, SQLite replay persistence and WebSocket resume are implemented. Optional SDK imports and client construction are checked with pinned dependencies. Docker/database integration, live Foundry inference and Azure deployment remain pending. The older milestone counts below are historical.

# MatchMind AI — M4 release checklist

## Verified in authoring environment

- [x] Backend automated tests (25 passing)
- [x] Five fixed-seed synthetic replays (40/40 offline checks)
- [x] Reject tampered statistical insight claims
- [x] Preserve evidence and numerical claims across English/Spanish overlays
- [x] Overlay expiry and WebSocket protocol unit tests
- [x] Machine-readable `evaluation-report.json` produced

## Must verify before public submission

- [ ] `npm install && npm run build` succeeds on a networked machine (dependency download timed out in authoring environment)
- [ ] `docker compose up --build` starts both services (Docker unavailable in authoring environment)
- [ ] Visit `http://localhost:8080`, confirm live replay and Broadcast Studio
- [ ] Connect a genuine Microsoft Foundry project and validate SDK calls and credentials
- [ ] Demonstrate actual Microsoft Agent Framework execution; fallback alone does not qualify
- [ ] Deploy on Azure, secure configuration and enable telemetry
- [ ] Public free demo, public GitHub repo, English instructions and <2-minute video
- [ ] Review Microsoft/Premier League submission IP license and synthetic media rights

## Local commands

```bash
cd backend
python -m pip install -r requirements.txt
PYTHONPATH=. python -m pytest -q
PYTHONPATH=. python -m evaluation.run --output ../evaluation-report.json
cd ../frontend
npm install
npm run build
cd ..
docker compose up --build
```

The evaluation is intentionally limited to synthetic internal consistency; it is **not** a performance benchmark, an assessment against real match labels, or a verification of Azure/Foundry integration.


## Graph release gates

- [ ] Memgraph real-container read/write and restart tests passed
- [ ] Neo4j real-container read/write and restart tests passed
- [ ] Seeded cross-backend graph parity verified
- [ ] Synthetic proxy passing edges clearly labeled; recipient schema improved
- [ ] Graph rebuild disabled or authenticated in deployed environment
- [ ] Database secrets, access controls, backups and licensing reviewed
- [ ] Graph insight evidence validated against canonical events

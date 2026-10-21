# Event-driven match feed (Azure Event Hubs)

In production, match events come from a data provider as a stream. Pitchlight's demo runs the same architecture on Azure:

```
"Kick off a live match"         Container Apps Job            Azure Event Hubs               Container App (API)              Browser
 (button, rate-limited)  ──ARM──▶ matchmind-feed       ──AMQP──▶ match-events          ──AMQP──▶ consumer task       ──WS /ws/feed──▶ live panel
 managed identity                python -m app.feed publish   partition key = match         StreamValidator → LiveMatch
                                 (Event Hubs Data Sender)      1 day retention               (Event Hubs Data Receiver)
```

| Piece | Azure service | Notes |
| --- | --- | --- |
| Producer | **Container Apps Job** `matchmind-feed` (manual trigger) | Same image as the app. It publishes a kick-off message, every event of a synthetic match in order (at 30× real time, so a match takes about 3 minutes), then full time. It runs only while a feed runs. |
| Transport | **Azure Event Hubs** namespace `matchmind-feed-ca7835` (Basic), hub `match-events`, 2 partitions | The partition key is the match, so a match's events stay in order. Local (SAS key) authentication is **disabled**; only Entra ID identities can connect. |
| Consumer | Background task in the `matchmind-demo` Container App ([app/feed.py](../backend/app/feed.py)) | It validates every event against the stream so far (`StreamValidator`), skips redeliveries, counts and reports invalid events without applying them, detects moments as events arrive (`LiveMatch`), and fans out to WebSocket clients. |
| Kick-off | `POST /api/feed/kickoff` | The app starts the job through Azure Resource Manager with its managed identity. One feed runs at a time, with a 60 s cooldown and the per-visitor limit in demo mode. |
| Identity | Managed identities and Azure RBAC | The job holds *Azure Event Hubs Data Sender* on the hub. The app holds *Data Receiver* on the hub and *Contributor* on the job only, so it can start it. There are no connection strings or keys. |

## Delivery guarantees

- **Order:** one partition key per match keeps its events in order. The consumer also validates order (sequence and clock), so an out-of-order event is rejected, not applied.
- **At-least-once delivery:** a redelivered event (the same event ID) is counted as a duplicate and skipped.
- **Bad data:** an invalid event is counted, shown with its reason, and not applied. The stream continues.
- **Recovery:** the consumer keeps its state in memory and rebuilds it from the log. On start, it reads the last 15 minutes of the hub and resumes from the latest kick-off. A restart mid-match therefore catches up without a separate checkpoint store. A multi-replica consumer would add Blob checkpointing; see [PATH_TO_PRODUCTION.md](PATH_TO_PRODUCTION.md), item 4.

## Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /api/feed` | Consumer status (connected partition), the current run, accepted, rejected and duplicate counts, the score and minute, and recent moments |
| `POST /api/feed/kickoff` | Start a feed (409 while one is running, 503 when not configured) |
| `WS /ws/feed` | Recent messages, then everything the consumer produces as it happens |

Configuration: `EVENTHUB_NAMESPACE`, `EVENTHUB_NAME` (default `match-events`), `FEED_JOB_RESOURCE_ID`, `FEED_REPLAY_MINUTES` (default 15). Without `EVENTHUB_NAMESPACE`, the feed is off and its panel is hidden.

## Verified

- **Unit tests** (`tests/test_feed.py`, no Azure needed): a full feed gives the same moments as batch analysis; duplicates are skipped and bad events rejected while the stream continues; messages from other runs are ignored; a new kick-off resets the run; stalled subscribers are dropped; the producer's message format and ordering are correct; the API works when the feed isn't configured.
- **Against real Event Hubs (20 October 2026):** one match published as 1,081 messages. The consumer accepted 1,079 of 1,079 events, with 0 rejected and 0 duplicates. The final score was 2–3, matching the batch analysis, and 59 moments were detected live.

## Cost

Event Hubs Basic is about $11 a month. The job runs only during a feed (0.25 vCPU for about 3 minutes).

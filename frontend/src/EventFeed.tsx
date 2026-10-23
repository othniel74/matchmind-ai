import { useEffect, useRef, useState } from "react";
import { CloudLightning } from "lucide-react";

// The match feed through Azure Event Hubs: a Container Apps Job publishes the match, the API
// consumes, validates and interprets each event, and this panel shows it as it happens.

type FeedStatus = {
  enabled: boolean; kickoff_available: boolean; hub: string;
  consumer: { status: string; partition?: string; error?: string };
  run: null | { feed_run: string; status: string; speed: number; source?: string };
  counts: { accepted: number; rejected: number; duplicates: number; moments: number };
  minute: number | null; score: null | { home: number; away: number };
};
type FeedEvent = { event_id: string; clock_seconds: number; team_id: string; player_name: string;
                   event_type: string; outcome: string; recipient_name: string | null };
type FeedMoment = { id: string; clock_seconds: number; headline: string; body: string };

const clock = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

export function EventFeedPanel({ clubs }: { clubs: Record<string, { short: string }> }) {
  const [status, setStatus] = useState<FeedStatus | null>(null);
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const [moments, setMoments] = useState<FeedMoment[]>([]);
  const [notice, setNotice] = useState("");
  const socket = useRef<WebSocket | null>(null);

  const refresh = () => fetch("/api/feed").then((r) => (r.ok ? r.json() : null)).then(setStatus).catch(() => undefined);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, []);
  // Reconnect when the connection closes: with several replicas, scaling in closes the viewers of a
  // replica that is removed. The server replays recent messages first, so the lists start empty.
  const [connection, setConnection] = useState(0);
  useEffect(() => {
    if (!status?.enabled) return;
    let unmounted = false;
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${scheme}://${location.host}/ws/feed`);
    socket.current = ws;
    ws.onopen = () => { setEvents([]); setMoments([]); };
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.type === "kickoff") { setEvents([]); setMoments([]); }
      else if (m.type === "event") setEvents((prev) => [m.event, ...prev].slice(0, 8));
      else if (m.type === "moment") setMoments((prev) => [m.moment, ...prev].slice(0, 6));
    };
    ws.onclose = () => {
      socket.current = null;
      if (!unmounted) setTimeout(() => setConnection((c) => c + 1), 1000 + Math.random() * 1500);
    };
    return () => { unmounted = true; ws.close(); socket.current = null; };
  }, [status?.enabled, connection]);

  if (!status?.enabled) return null;
  const live = status.run?.status === "live";
  const kickoff = () => {
    setNotice("Starting the feed job…");
    fetch("/api/feed/kickoff", { method: "POST" })
      .then(async (r) => setNotice(r.ok ? "Feed job started. Events arrive through Event Hubs in a few seconds."
        : (await r.json().catch(() => ({}))).detail ?? "Could not start the feed."))
      .catch(() => setNotice("Could not start the feed."));
  };
  return (
    <section className="panel live-panel feed-panel" aria-label="Azure Event Hubs feed">
      <div className="panel-title">
        <h2><CloudLightning size={17} />Live from Azure Event Hubs</h2>
        <span className="panel-kicker" data-testid="feed-consumer">
          CONSUMER {status.consumer.status.toUpperCase()}{status.consumer.partition ? ` · PARTITION ${status.consumer.partition}` : ""}
        </span>
      </div>
      <p className="subtle-note">
        A Container Apps Job publishes a synthetic match to the <b>{status.hub}</b> hub. This app consumes it,
        validates every event against the stream so far, and detects moments as they happen.
      </p>
      <div className="feed-stats">
        <div><span>Run</span><b>{status.run ? (live ? `Live · ${status.minute ?? 0}′` : "Full time") : "Waiting"}</b></div>
        <div><span>Source</span><b>{status.run?.source === "vision" ? "Recovered from video" : status.run ? "Data feed" : "—"}</b></div>
        <div><span>Score</span><b>{status.score ? `${clubs.home?.short ?? "Home"} ${status.score.home}–${status.score.away} ${clubs.away?.short ?? "Away"}` : "—"}</b></div>
        <div><span>Accepted</span><b>{status.counts.accepted}</b></div>
        <div><span>Rejected</span><b>{status.counts.rejected}</b></div>
        <div><span>Duplicates</span><b>{status.counts.duplicates}</b></div>
        <div><span>Moments</span><b>{status.counts.moments}</b></div>
      </div>
      {status.kickoff_available && (
        <button className="button primary" disabled={live} onClick={kickoff}>
          {live ? "Match in progress" : "Kick off a live match"}
        </button>
      )}
      {notice && <p className="subtle-note" role="status">{notice}</p>}
      <div className="live-columns">
        <ol className="live-events" aria-label="Events from Event Hubs">
          {events.map((e) => (
            <li key={e.event_id} className={`team-${e.team_id}`}>
              <span>{clock(e.clock_seconds)}</span> {e.player_name} · {e.event_type}
              {e.event_type === "pass" && e.recipient_name ? ` → ${e.recipient_name}` : ""}{e.outcome === "goal" ? " · GOAL" : ""}
            </li>
          ))}
        </ol>
        <ol className="live-moments" aria-label="Moments from Event Hubs">
          {moments.map((m) => (
            <li key={m.id}><b>{Math.floor(m.clock_seconds / 60) + 1}′ {m.headline}</b>{m.body && <span>{m.body}</span>}</li>
          ))}
        </ol>
      </div>
    </section>
  );
}

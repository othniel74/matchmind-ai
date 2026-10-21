import React from "react";
import { ShieldCheck } from "lucide-react";

export function Crest({
  away = false,
  small = false,
}: {
  away?: boolean;
  small?: boolean;
}) {
  return (
    <div
      aria-hidden="true"
      className={`crest ${away ? "away" : ""} ${small ? "small" : ""}`}
    >
      <ShieldCheck size={small ? 17 : 29} strokeWidth={1.6} />
      <span>{away ? "MER" : "CAL"}</span>
    </div>
  );
}
export function PanelTitle({
  icon,
  title,
  kicker,
}: {
  icon: React.ReactNode;
  title: string;
  kicker?: string;
}) {
  return (
    <div className="panel-title">
      <h2>
        {icon}
        {title}
      </h2>
      {kicker && <span className="panel-kicker">{kicker}</span>}
    </div>
  );
}
export function Comparison({
  label,
  home,
  away,
  suffix = "",
}: {
  label: string;
  home: number;
  away: number;
  suffix?: string;
}) {
  const total = home + away;
  return (
    <div className="comparison-row">
      <div>
        <strong>
          {home}
          {suffix}
        </strong>
        <span>{label}</span>
        <strong>
          {away}
          {suffix}
        </strong>
      </div>
      <div className="comparison-track">
        <i style={{ flex: total ? home : 1 }} />
        <i style={{ flex: total ? away : 1 }} />
      </div>
    </div>
  );
}

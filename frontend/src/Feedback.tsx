import { useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";

// "Was this useful?": one tap, no text, no identity. Counts go to Application Insights.

export function Feedback({ feature, language }: { feature: "ai_recap" | "fact_checker" | "ask" | "tour"; language: string }) {
  const [sent, setSent] = useState<boolean | null>(null);
  const send = (useful: boolean) => {
    setSent(useful);
    fetch("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
                             body: JSON.stringify({ feature, useful, language }) }).catch(() => undefined);
  };
  if (sent !== null) return <p className="feedback-thanks">Thanks for the feedback.</p>;
  return (
    <div className="feedback" role="group" aria-label="Was this useful?">
      <span>Was this useful?</span>
      <button onClick={() => send(true)} aria-label="Yes, useful"><ThumbsUp size={13} /></button>
      <button onClick={() => send(false)} aria-label="No, not useful"><ThumbsDown size={13} /></button>
    </div>
  );
}

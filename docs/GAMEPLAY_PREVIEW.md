> **Historical document.** It records MatchMind at the date it was written; its test counts, limitations and plans are not current. For the current state see the [README](../README.md) and the [documentation index](README.md).

# Gameplay preview — 18 October 2026

The local preview uses a shared player-and-ball simulation. The carrier keeps the ball at their feet, slows and turns before kicking, and releases it into a continuous flight. Receivers approach the ball and control it at foot-contact distance. Supporting attackers and pressing defenders move around possession; shots end in goalkeeper collections. Goals, a high-contrast ball, and a BALL tracking label make the action readable.

This is illustrative gameplay, not real match tracking or a reconstruction of the synthetic source events. The source match clock, score and verified insights remain independent of these illustrative actions. The frontend defaults to approximately one replay minute per real second. Inline and detached previews advance the same deterministic simulation from the match clock.

Verification: `node --experimental-strip-types tools/check-football-play.ts` passes a 90-second run covering ball continuity, ownership/contact, passes, receives, shots, goalkeeper collections, on-field bounds, a forced physical challenge and deterministic clock synchronization. The nominal run records 17 passes, 21 receives, 5 shots and 5 goalkeeper collections. Browser inspection confirmed the visible ball and connected passing play.

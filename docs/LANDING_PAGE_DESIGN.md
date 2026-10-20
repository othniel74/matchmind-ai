# Landing page design and artwork

## Experience

The local home page at `/` introduces MatchMind with a cinematic football editorial direction, a real backend-driven snapshot explorer, an evidence view, an explanation of the deterministic workflow, a Broadcast Studio showcase and an expandable FAQ. `/app` opens the match workspace; `/app?view=studio` opens Broadcast Studio directly. The existing `?preview=1&channel=...` detached-preview route takes precedence and remains supported.

The explorer requests state, NetworkX passing connections and narratives for the same selected minute. Audience and language controls request actual deterministic backend outputs. Empty detection windows do not invent an insight. No customer logos, testimonials, usage statistics or unverified live AI claims were added. All work remains local.

## Artwork

The built-in ImageGen tool generated the hero artwork. The project asset is `frontend/public/images/matchmind-stadium.png`. It depicts an anonymous fictional player in an imagined stadium; it is not licensed match footage or a real club/player image.

Final generation prompt:

> Create a cinematic premium sports technology website hero photograph, ultra-wide landscape composition ideally 1792x1024 or wider. A completely fictional empty professional football stadium at night, camera low over immaculate grass looking toward the far floodlit grandstand. One anonymous footballer seen from behind on the FAR RIGHT THIRD, small enough to show most of the stadium, wearing a plain ivory/off-white jersey and dark charcoal shorts, no logos, no writing, no branding, standing poised beside a football at their feet. The left half is atmospheric almost-black charcoal negative space, the right half reveals the player and pitch in moody silver stadium floodlight and subtle acid-lime reflections on wet grass. Fine ground mist, distant stadium lights, high contrast but photographic deep shadows. Frame the anonymous player from boots to shoulders with their head darkened, no identifiable real person. Refined, dramatic, tactile, high-end sports editorial photography, very subtle film grain. No text, no typography, no graphic overlays, no neon sci-fi effects, no logos, no crowds, no team or league branding, no watermarks. This image will sit behind an editorial typography composition on a premium football analytics landing page. The picture must feel like real aspirational night football with restrained olive-lime and cool white lighting.

## Verification

Production TypeScript/Vite build passes. Browser checks cover desktop and mobile layouts, mobile navigation, audience and language changes, snapshot scrubbing at minutes 20/67/90, no-insight states, FAQ expansion, direct Broadcast Studio entry and return to the landing page. Real data in the default snapshot shows 0 to 18 advanced-area events with 18 source IDs. These are synthetic replay facts, not claims about a real football match.

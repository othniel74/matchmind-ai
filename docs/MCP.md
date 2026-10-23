# Pitchlight MCP server

Pitchlight publishes its verified match intelligence as a [Model Context Protocol](https://modelcontextprotocol.io) server. Any MCP client can use the same facts the product shows. That includes an Agent Framework agent, GitHub Copilot agent mode in VS Code, Foundry, or Claude Desktop. Every tool is **read-only** and **time-scoped**: nothing after the requested minute is used. Every result cites the event IDs it rests on.

| Endpoint | Transport |
| --- | --- |
| `https://pitchlight.mangograss-8c9a0131.uksouth.azurecontainerapps.io/mcp` | Streamable HTTP, stateless, JSON responses |
| `python -m app.mcp_server` (from `backend/`) | stdio |

## Tools

| Tool | Returns |
| --- | --- |
| `match_state` | Score, team statistics, and control/chaos, tempo and momentum |
| `list_claims` / `validate_claim` | Evidence-backed statistical claims; recompute any claim and say why it fails |
| `key_moments` | Goals, chances, cards, key-link changes and momentum, with why each matters, in 7 languages |
| `why_moment` | Facts, evidence, the build-up, the players' pass-network roles before the moment, and the previous moment |
| `network_roles` | A team's pass network: hub, key link (betweenness), PageRank and lanes, for the whole match or a window |
| `xg_chain` / `goal_buildups` | xG chain and xG build-up per player; goals and shots as player chains |
| `story_so_far` | The developing story with the running score |
| `correction_impact` | Every moment, claim, overlay and recap that depends on an event |
| `match_recap` | Half-time, full-time or so-far recap, where every number is a validated claim |
| `answer_question` | A viewer's question answered from fixed templates with evidence. It takes a typed intent; off-topic questions are refused. |
| `tactical_changes` | Before/after impact of each substitution and red card, ranked against the match's own swings; coincidence only |
| `pressing_and_shape` | PPDA, high turnovers, defensive line height, width and compactness for both teams |
| `squads` | Both fictional squads |

Tool annotations declare `readOnlyHint: true` and `destructiveHint: false`. Invalid arguments return MCP tool errors with a reason, not server errors.

## Pitchlight's own agent is an MCP client

`/api/ask` (Ask the match) runs an Agent Framework agent on the Foundry model, with Pitchlight's MCP server as its tool (`MCPStreamableHTTPTool`, limited to `answer_question`). The agent does three things: it understands a question in any language, picks the typed intent (for example "main man in midfield" becomes `key_player`), and calls the tool. **The viewer sees the tool's verified result, never the model's text.** The tool validates the agent's arguments again. If the model is unavailable or the visitor's rate limit is reached, the same tool logic runs on a 7-language keyword router. The response's `router` field reports `mcp_agent` or `keywords`, and `tool_call` shows the arguments the agent chose.

## The recap researcher is an MCP client too

Every agent-written recap starts with `match-researcher`, an Agent Framework agent whose tools are this MCP server, limited to `match_state`, `list_claims`, `network_roles`, `key_moments` and `goal_buildups`. It decides which tools to call (typically 6–7 calls), then chooses the recap's angle as structured output. Code turns that choice into facts before any writer sees it. The calls it made are shown in the run view under the recap. See [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md).

## Use it from VS Code (GitHub Copilot agent mode)

`.vscode/mcp.json` registers the deployed server (`pitchlight-demo`) and a local stdio server (`pitchlight-local`). Open the repository in VS Code, start the server from the MCP view, and ask Copilot Chat in agent mode, for example "Why did Merridge's opener matter?".

## Security

- Read-only, with no model calls behind the tools, so there is no write path and no cost path.
- The HTTP transport accepts only the API's allowed hosts (DNS-rebinding protection) and no browser origins.
- It is stateless: no per-client sessions are kept, so any replica can answer.

## Tests

`backend/tests/test_mcp.py` covers the protocol (initialize, tools/list), the read-only annotations, time scoping, the structured intents, refusals, tool errors and host rejection. The agent → MCP path was verified live against Foundry `gpt-4.1-mini`, with questions in Spanish, English and French plus an off-topic question.

# Languages — 19 October 2026

Pitchlight supports seven languages. The supported set is identical across narratives, overlays, claim statements, the agent workflow, the API and the UI.

| Code | Language | Direction | Number style |
| --- | --- | --- | --- |
| en | English | left to right | 53.3%, score 1–3 |
| es | Spanish | left to right | 53,3 %, score 1–3 |
| fr | French | left to right | 53,3 % (non-breaking space), score 1–3 |
| pt | Portuguese (Brazil) | left to right | 53,3%, score 1–3 |
| de | German | left to right | 53,3 %, score 1:3 |
| it | Italian | left to right | 53,3%, score 1–3 |
| ar | Arabic | right to left | 53.3%, score 1–3 |

## Where it lives

`backend/app/languages.py` is the single registry. It holds team names, narrative templates for the fan, analyst and broadcast audiences, overlay metric labels, claim templates, metric names and number formats. `GET /api/languages` lists the languages, and `frontend/src/languages.ts` mirrors that list for the pickers.

## Adding a language

1. Add one `Language` entry in `languages.py`. The registry test fails until every template and metric label is present.
2. Add the same code to `frontend/src/languages.ts`.
3. Run the backend tests. They check every language for:
   - complete templates
   - identical facts and evidence across languages
   - claim validation
   - API acceptance
4. Have a native-speaking editor review the wording before broadcast use.

## How each layer handles language

- **Deterministic text** (template narratives, overlays, claim statements) is written from the registry. Every language carries the same numbers and evidence IDs, and the evaluation checks this parity for all seven languages.
- **Agent text:** the analyst and storyteller work in English, and the audience editor writes the final text in the requested language.
  - The digit check works in every script; Arabic-Indic digits are blocked too.
  - The word-list pre-filter covers English and Spanish only.
  - The semantic fact checker covers every language: it extracts statements in any language, and plain code verifies them.
- **Right-to-left:** Arabic overlays and narratives carry `direction: rtl`. The UI sets `dir` and `lang` on overlay and preview text and uses "←" instead of "→" in right-to-left value comparisons.

## Translation review — 19 October 2026

Every template was rendered with real values and reviewed with gpt-4.1-mini acting as a native-speaking sports editor, compared against the English source.

| Language | Result |
| --- | --- |
| French, German, Italian | no issues |
| Arabic | fan narrative lacked a verb; fixed to "حيث ارتفع عدد الأحداث من … إلى …" |
| Spanish | flagged "tiros a puerta"; kept, because it is standard in Spain (LaLiga statistics use it) |
| Portuguese | flagged "finalizações no gol"; kept, because it is established Brazilian usage and the suggested "no alvo" is less common in Brazil |

This review is a model's opinion, not native sign-off.

## Limits

- **Review:** the translations still need sign-off from native-speaking editors before broadcast use.
- **Portuguese variant:** Portuguese uses Brazilian wording (time, gols, escanteios). European Portuguese would be a separate entry (`pt-PT`).
- **Arabic numerals:** Arabic uses Western digits and a dot as the decimal separator.
- **More languages:** Nigerian languages (Hausa, Yoruba, Igbo) or others can be added through the registry. They need native editors for both the templates and the evaluation of agent output.

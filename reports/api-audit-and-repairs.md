# API evidence and focused repairs

The user's dashboard showed no new requests from the preceding application pass.
That discrepancy remains unresolved. The original report is corrected: its twelve
counts were SDK invocations, not dashboard-confirmed calls. No previous request
IDs can be recovered from those logs.

## New diagnostic evidence

One harmless inference probe used the normal `httpx2.HTTPTransport` and official
SDK, with no mock transport or substitute model configured:

- Marker: `jev-exp-probe-b22986c27cc0`.
- Client-recorded request: `POST https://api.typesafe.ai/v1/systemone`.
- Client-recorded response: HTTP 200 at `2026-09-20T00:47:06.319893+00:00`
  (September 19, 5:47:06 PM Pacific).
- Returned request ID: `req_01a0bc47eeba7ca69e2f291c27f96f64`.
- Returned model label: `jev-1.13.0`; usage: 391 input, 39 output tokens.
- Local trace: `runs/api-audit-01/probe.jsonl`.

The user checked again and still saw no request. No further desktop/task inference
was performed after that report. A single intentionally invalid, non-secret test
credential was rejected with `TypeSafeAuthenticationError`, request ID
`req_01a0bc4b364b72bca7b36bdd05aa847a`. No real credential was printed or modified.

A subsequent read-only `GET https://api.typesafe.ai/v1/models` returned HTTP 200,
request ID `req_01a0bc4d568e7d9ca8d75fa972aaaa79`. The response's network stream
reported TLSv1.3 and a certificate subject of `*.typesafe.ai`. The SDK used its
default endpoint and model, with no base-URL or proxy environment override
observed. These checks establish local connection/authentication evidence; they
do not identify the dashboard workspace or establish billing attribution.

Next external check: correlate the exact request ID with the intended dashboard
workspace and confirm that the runner's key is the same credential used in the
user's working 11 AM tests. Do not infer a dashboard outage, wrong key, or service
failure without that evidence. The official SDK documents environment-based key
configuration: https://github.com/typesafe-ai/typesafe-sdk-python .

Read-only inspection of the user's signed-in `https://console.typesafe.ai/usage`
confirmed 2 requests and 1,326 tokens, with All traffic, Last 7 days, and Hourly
selected. The page displayed Jimothy's org and warned that stats may be delayed.
No obvious traffic/date filter explains the missing probe. This warning is not
proof of a reporting delay; key-to-organization attribution remains unverified.
No keys or dashboard settings were changed.

## Implemented changes

- Retain credential-safe HTTP request/response events and reported token counts.
  Record provider answers before validation so rejected answers remain inspectable.
- Flatten nested MCP exception groups into structured causes. Preserve stable
  policy/Driver failure codes without dumping arbitrary exception bodies.
- Select one named window only when every other candidate is explicitly offscreen
  and untitled. Preserve ambiguity between named documents or visible dialogs.
- Project observations to window content by excluding menu roles and their
  descendants, before applying existing content/candidate limits. This is
  independent of task goals, answers, app names, or model choices. Original
  snapshot IDs, element IDs and tokens remain intact.
- Handle null labels as unnamed; do not offer unnamed controls as semantic actions.
- Prevent an explicitly incomplete observation from proving completion.

No Driver implementation, original example, provider threshold, screenshot
fallback, or app-specific action sequence was added or changed. Menu navigation,
browser research and generic report generation remain unsupported.

## Recorded-observation replay (no API calls or UI actions)

| Snapshot | Raw elements | Content elements | Excluded menu elements | Executable options |
|---|---:|---:|---:|---:|
| Calculator initial inspection | 173 | 26 | 147 | 22 |
| Obsidian | 213 | 4 | 209 | 0 |
| Notes | 155 | 5 | 150 | 1 |
| Reminders | 130 | 6 | 124 | 2 |

The overflow is removed without increasing the 62-option/200-content-element
limits. This also exposes missing evidence: all four snapshots have no nonempty
content values; Obsidian, Notes and Reminders explicitly report incomplete
elements. Therefore these replays do not establish task success. The Calculator
replay reconstructs the initial compact trace and lacks original completeness
metadata; its completion capability cannot be inferred from that reconstruction.

## Verification

Focused tests cover auxiliary windows, ambiguous named documents and dialogs,
menu descendants, null labels, retained snapshot bindings, unchanged candidate
limits, incomplete readbacks, nested errors, HTTP log redaction, SDK response
correlation, and rejected answers. The full regression run passed 70 Python tests,
24 TypeScript tests, and TypeScript typechecking. The read-only Driver doctor
passed; optional parse_visual_regions was not advertised. git diff --check passed.

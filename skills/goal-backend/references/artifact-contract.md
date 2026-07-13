# Goal Run Artifact Contract

New runs use `manifest.json` schema `goal-run/v1` and append-only
`events.jsonl`. Evidence status is one of `completed`, `missing`, `partial`,
`failed`, `blocked`, or `readiness_only`.

New artifacts carry Goal/session, owner, capability, expert authorization, and
independent-acceptance evidence. They do not carry historical mode or provider
authority. Legacy traces are read without mutation or replay.

**What works.** Detection p95 is 4.85s against a 120s target (90 runs). Exact-span
precision on recorded topology is 100% (10/10). Where pole ordering was never
recorded — 60% of transformers — the system refuses to emit a span and gives a
search corridor instead; the corridor contained the real fault 45/45. Silence is
never treated as darkness: only an explicit power-loss event counts as dark, so
dead batteries and the 8% of poles on firmware 1.2 don't manufacture tickets.
Tickets close on restoration telemetry, not on a crew's word (p95 1.90s).

**What doesn't.** Planned-outage matching is seed-sensitive. Across 100
noise-only runs, `planned_outage` opened 11 fault tickets; every other noise
scenario opened zero. It holds on the default seed and fails when the simulator
picks a different transformer, so the fault is in scope matching, not timing.
`feeder_fault` produced no incident on 10 of 10 non-default seeds — likely the
same class of bug, unconfirmed. Sustained ingest tops out at 70 req/s against a
500 target: fully diagnosed (one Uvicorn process sharing the event loop with the
inbox worker), not fixed. Backend tests aren't isolated from database state.

**What I cut, and why.** Authentication, crew routing, analytics, historical
trends, WebSocket push, and every customer-facing surface. All were out of scope
in the brief, and all of them would have come out of localization time — which is
where the real difficulty of this problem lives.

**The one thing I'd fix first.** Planned-outage seed sensitivity. It is the only
known defect that produces a wrong answer an operator would act on, and raising a
fault ticket during scheduled load shedding is the failure mode the brief names
directly. Everything else on the list is a throughput number or test hygiene.

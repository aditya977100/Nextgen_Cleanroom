# Cleanroom

A test room that proves an AI safety test was clean: if data leaks between red and blue, the diary shows it and findings get tainted.

Live dashboard: [link to be added]
Demo video: [link to be added]
Repository: [link to be added]

## Problem

It is hard to tell whether a red/blue test of an AI system was actually isolated. Leaks can happen through shared files, logs, a diary, direct connections, impersonation, or timing side channels. Without proof, it is not clear which findings to trust.

We did not find a tool that shows which channel leaked and which findings are still valid after a leak.

When something slips, it is easy to re-run everything instead of just the tainted findings.

## What Cleanroom does

- Sealed rooms: red and blue run in separate rooms with their own files and logs. A gateway is the only route between them.
- Tripwire words: a canary word is planted so any leak is visible when found in the other room.
- Signed diary: every event goes into a hash-chained diary signed with Ed25519. The text of messages is not stored, only hashes.
- Taint tracker: after each finding the tester checks for leaks. The first leak taints that finding and all after it; earlier findings stay valid. Each finding gets a receipt tied to the diary.
- Leak meter: estimates bits per second that could leak through each channel using mutual information.
- The Mole: a scripted attacker inside red tries a set of escape moves and reports how many land.

## Results

| Run | Channels leaked | Findings valid | Mole landed | Shared files (bits/s) |
| --- | --------------- | -------------- | ----------- | --------------------- |
| naive | 6 | 0 | 7 / 7 | 996.1 |
| cleanroom | 0 | 8 | 0 / 7 | 0.0 |
| slip-up | 1 | 4 | 2 / 7 | 984.2 |

## Architecture

`
red room --\
            \-- gateway -- model
blue room --/        \
                      diary (hash-chained)
`

Tester checks channels, runs the taint tracker, builds the meter, runs the Mole, writes results as JSON, and copies them to dashboard/data/.

## Quick start (no Docker)

`powershell
pip install -r requirements.txt
python -m pytest -q
python -m tester.run_test --no-export
python -m http.server 8080 -d dashboard
`

Open http://localhost:8080. The dashboard reads dashboard/data/*.json.

## Run the real Docker rooms

`powershell
docker compose up -d --build
python -m tester.run_test --engine docker --mode all
`

A full Docker run takes about 15 minutes. The tester uses docker compose exec from the host and never mounts the Docker socket into a container. After the run, results are copied to dashboard/data/.

## What is real vs simulated

- Real: Docker containers, networks, file systems, the signed diary, the gateway, and the channel checks run as written.
- Simulated: the toy model, cache-timing latency, and the bits/s estimates in the leak meter are assumptions. Anything simulated is marked in the results and labeled in the dashboard.

## Known limits

- Toy model, not a real LLM.
- Cache-timing numbers are estimates.
- The leak meter uses assumptions about uses per second.
- This is a test harness, not a hardened production system.

## Folder layout

- core/ - diary, taint, meter, canary, findings
- tester/ - simulation and Docker engines, runner, export
- gateway/ - gateway service
- model/ - toy model
- rooms/ - red/blue scripts, client, Mole
- dashboard/ - static site and data
- tests/ - tests
- docs/ - architecture, threat model, demo script, isolation proof

## Team

Team Next-gen, Hack in Hills '26: Aditya Raj Pandey (backend, Docker rooms, tester, dashboard) and Ranjeet Kumar (team member & researcher).

## License

MIT
# Architecture

```
HOST (your laptop)
  tester/run_test.py  --- the invigilator, OUTSIDE the rooms ---
       |  docker compose exec -T <room> ...   |  HTTP to localhost:8000
       v
  +------------------ Docker ------------------+
  |  net_red (internal)   net_blue (internal)    |
  |   [red]                [blue]                |
  |      \                  /                    |
  |       +---- [gateway] ---+---- net_model ---[model]
  |              |  (the only door; signs the diary)
  |            front (port 8000)
  +----------------------------------------------+
  results/<engine>-<mode>.json  ->  dashboard/data/<mode>.json  ->  dashboard/ (static page)
```

## The pieces

| Folder | What it is | Where it runs |
|---|---|---|
| `core/` | audit chain, taint rules, leak meter, canaries, the 8 findings | inside the gateway container and on the host |
| `gateway/` | FastAPI: caller identification, policy, hashing, signing | its own container |
| `model/` | toy LLM with a prompt-prefix cache (SIMULATED latency) | its own container |
| `rooms/` | the red and blue rooms: `server.py` (port 9000), `client.py` (commands), `mole.py` (the attacker) | two containers, one image |
| `tester/` | `run_test.py` (the invigilator), `engine_sim.py`, `engine_docker.py`, `export.py` | on the host, outside the rooms |
| `dashboard/` | static HTML/CSS/JS, no build step, GitHub Pages ready | a browser |

## Networks

- `net_red` 172.28.1.0/24 - internal, only `red` and `gateway`
- `net_blue` 172.28.2.0/24 - internal, only `blue` and `gateway`
- `net_model` 172.28.3.0/24 - internal, only `model` and `gateway`
- `front` - a normal bridge, so the gateway can be reached on localhost:8000

`internal: true` means the network has no route to the outside world. Red physically has no path to blue or to
the model; the only way out is the gateway.

## Hardening (docker-compose.yml)

Every service: non-root user `10001:10001`, `read_only: true`, `cap_drop: [ALL]`,
`security_opt: ["no-new-privileges:true"]`, `mem_limit: 256m`, `cpus: 0.5`, tmpfs for `/tmp` and `/data`.
No volumes are shared between rooms. The model gets `SALTED=true` so its cache key includes the tenant.

## The three setups

| File | What is wrong on purpose |
|---|---|
| `docker-compose.yml` | nothing - this is the hardened Cleanroom |
| `docker-compose.naive.yml` | one shared network, one shared volume, one shared model cache, plaintext logs, no hardening |
| `docker-compose.slip.yml` | adds a shared volume to red and blue; the tester applies it between finding 4 and finding 5 |

## The flow of one run

1. The tester makes two canaries and an admin token, and starts the stack.
2. For each of the 8 findings: blue writes its note, red writes its note, red asks the model something,
   blue asks the model something. Then the tester dumps both rooms and looks for the other team's canary.
3. On the first leak the tester appends a `LEAK` event to the diary; for every finding it appends a `finding`
   event and keeps that entry's hash as the finding's receipt.
4. Final probes: files, logs, diary contents, direct access, impersonation, cache timing.
5. Leak meter: 200 random bits through the shared-file channel and through the model's cache timing.
6. The Mole runs inside red and reports how many of its 7 escape moves landed.
7. The tester pulls `/audit`, verifies the chain with `core/audit.py`, writes the results file and exports it
   to `dashboard/data/`.

## Results format

One JSON file per run, the contract between the tester and the dashboard. See `tests/test_schema.py` for the
authoritative shape, and `docs/BUILD_PROMPT.md` section 4 for the original spec.

```json
{ "engine": "sim|docker", "mode": "naive|cleanroom|slip", "started": "ISO time",
  "findings": [{"id": "F1", "text": "...", "status": "VALID|TAINTED", "receipt": "10 hex chars or null"}],
  "first_leak_at": null, "channels": [...], "meter": [...], "mole": {...},
  "diary": {"public_key": "hex", "entries": [...]}, "verify": {...}, "certificate": "...",
  "labels": {"simulated": [...], "real": [...]} }
```

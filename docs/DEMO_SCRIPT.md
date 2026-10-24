# Demo script (5 minutes, laptop screen + projector)

Target: a judge who has never seen the project. The one sentence that matters is:
**"Cleanroom proves the test room was clean, and tells you which safety findings you can still trust."**

## 0. Before the demo (5 minutes of setup)

```
pip install -r requirements.txt
docker compose up -d --build
```

Open two browser tabs: `http://localhost:8080` (the dashboard) and
`http://localhost:8080/simulation.html` (the live browser model). Start the static server with
`python -m http.server 8080 -d dashboard`.

Have these ready in a second terminal, but do not run them yet:

```
python -m tester.run_test --engine docker --mode all     # the full real run (about 12 minutes)
python -m pytest -q                                       # 19 tests
```

## 1. The problem (30 seconds)

> "Red team attacks a model. Blue team defends it. If red can read blue's notes, or blue can read red's
> payloads, the whole evaluation is theatre - and nobody notices, because the report still has eight findings
> on it. Cleanroom is the room that tells you whether the test was real."

## 2. The three rooms on screen (30 seconds)

Point at the diagram in the dashboard, tab **B: Cleanroom**.

- Red, blue and the model each sit in their own network. The gateway is the only door.
- The gateway does not trust what a caller *says* it is. It looks at the caller's IP address, so red cannot
  walk in as blue.
- The diary stores `sha256(message)`, never the message.

## 3. The trap words (60 seconds)

> "Every run plants a unique word - a canary - in each side's notes: `CNRY-1a2b3c4d`. Afterwards we search
> every room for the *other* team's canary. If red finds blue's canary, red has read blue's notes, and the
> evaluation is over."

Switch to tab **A: Naive shared sandbox**. Files, logs, diary, direct access and cache timing are all red.

## 4. The taint tracker - the part judges remember (90 seconds)

Switch to tab **C: Slip-up mid-run**.

> "Here the mistake happens halfway: someone mounts one shared volume into red and blue. The tester notices at
> finding 5. And this is the point of the whole project: findings 1 to 4 happened *before* the leak, so they
> are still valid. Only findings 5 to 8 are tainted. You re-run four findings, not eight."

Read the sentence on the screen: *"4 of 8 findings are still valid. Re-run only the 4 tainted ones, not all 8."*

Point at the receipts: every finding points at a line in the sealed diary.

## 5. The diary (60 seconds)

Scroll to the diary, press **Tamper with entry 1**, then **Verify diary**.

> "The page recomputes the hash chain in your browser with Web Crypto. Change one entry and the chain breaks at
> exactly that entry. The signatures are checked by `python -m core.audit` - the browser does not have the key."

```
python -m core.audit dashboard/data/cleanroom.json     # -> VALID
```

## 6. The leak meter (60 seconds)

> "Not just 'leak or no leak'. How many bits per second could a cheating red team push to blue through this
> channel? Mutual information with a small-sample correction. Shared files, thousand uses a second: about one
> bit per use, so a 256-bit key in under a second. Cache timing, forty uses a second: about 38 bits per second."

Point at the "kind" column - the cache-timing row is flagged **simulated**. Say the word *simulated* out loud.

## 7. The Mole (45 seconds)

> "Inside red sits a script we call the Mole. It tries seven escape moves: read the shared folder, read the
> logs, connect straight to blue, connect straight to the model, pretend to be blue at the gateway, read the
> diary, and guess a foreign prompt from the model's cache timing. In the clean room it lands zero times. In
> the naive sandbox it lands seven."

## 8. The real thing (60 seconds)

```
docker compose exec -T red python /app/client.py tcp blue 9000      # blocked
docker compose exec -T red python /app/client.py send model "hello" # the gateway answers
```

> "That is not a drawing. Four real containers, three internal networks, non-root, read-only, no capabilities.
> The certificate is issued only after the tester has actually tried to break in."

## 9. What is real, and what is not (30 seconds)

Read the "Real vs simulated" box aloud. Say plainly:

> "The toy model and its cache timing are simulated, and the meter speeds are assumptions. The tripwire
> search, the signed diary, the taint tracking, the information-theory maths and the containers are real."

## 10. Limits (30 seconds)

> "Containers share one kernel, so a kernel escape would break all of this - we do not claim a trusted
> execution environment. The certificate only covers the channels we probed. If the host is compromised, or the
> signing key leaks, the guarantee is gone. The full threat model is in `docs/THREAT_MODEL.md`."

## 11. Close (15 seconds)

> "A safety evaluation without Cleanroom is a report without a chain of custody. Cleanroom is the chain of
> custody: proof the room was clean, and a list of the findings that survived it."

## Backup demo (if Docker is slow)

`simulation.html` runs the whole idea in the browser in four clicks, no Docker needed. Press
**Run A: naive shared sandbox**, then **Run B: Cleanroom**, then **Run C: slip-up mid-run**, then tamper with
the diary at the bottom. Use this if the containers are slow to build.

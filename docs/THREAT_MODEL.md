# Threat model

Cleanroom makes one claim: **after a test run, we can say which safety findings still deserve trust.**
Everything below is about that claim: what the claim covers, what it does not, and how it fails.

## The assets

| Asset | Why it matters |
|---|---|
| Red team's notes and payloads | red's attack strategies; if blue reads them, the blue score is a fiction |
| Blue team's rules and notes | blue's detection logic; if red reads them, the red score is a fiction |
| The model's prompt cache | holds prefixes of what each team asked; a shared cache tells one team what the other asked |
| The run diary | the evidence that the run was clean; if it can be edited afterwards, the certificate is worthless |
| The gateway's signing key | the thing that makes the diary's signatures mean anything |

## What Cleanroom protects against

- **Red reading blue's files, notes or logs** (and the reverse). Every room gets its own filesystem and its own
  log; no volume is shared. A tripwire word in each side's notes is planted and every room is searched for it.
- **Red or blue reaching the other, or the model, over the network.** Three `internal: true` networks
  (red / blue / model) and one gateway that is the only container attached to all three.
- **Red pretending to be blue at the gateway.** The gateway does not trust the `src` field: it maps the caller's
  IP address to a room and rejects any request whose claim does not match. The attempt is logged as `DENIED`.
- **Cache-timing leaks between teams.** The toy model keys its prompt-prefix cache by tenant, so a fast answer
  only ever reveals a prompt that the *same* team sent.
- **Plaintext ending up in the diary.** The gateway logs `sha256(message)[:12]`, never the message.
- **Tampering with the diary after the fact.** Each entry's hash covers `i|t|actor|event|data|prev`, each entry
  stores the previous entry's hash, and each entry is signed with Ed25519. Editing one entry breaks the chain at
  that entry; forging it needs the signing key.
- **The everyday mistakes.** A shared volume mounted into two rooms (the "slip"), plaintext room logs, a shared
  model cache, and a diary that holds plaintext are all simulated on purpose, so the tester can show that
  Cleanroom *catches* them instead of assuming they cannot happen.

## What it does not protect against

- **Shared-kernel or container escape.** All rooms run as plain containers on one Docker Desktop Linux VM and
  share the host kernel. A kernel exploit defeats every isolation guarantee here. This is the biggest limit.
- **Hypervisor- or hardware-level timing channels.** We measure the model's cache timing, not CPU cache, spectre
  style side channels, or the hypervisor's own timing.
- **No TEE.** There is no trusted execution environment, no confidential VM, no attested boot. The isolation is
  Docker's ordinary network and mount isolation.
- **A malicious or buggy tester.** The tester is trusted: it plants the canaries, reads the rooms and writes the
  findings. It runs on the host, outside the rooms.
- **DoS and resource abuse.** Memory and CPU limits keep one room from starving the others, but there is no
  rate limiting, no quota and no per-room budget.
- **Anything we did not probe.** The certificate covers exactly the channels listed in the results file. A channel
  that is not in that list is not certified - it is simply unknown.

## When the guarantees fail

- **The host or the tester is compromised.** Whoever controls the host can read the rooms, the diary and the
  signing key, and the run is worthless.
- **The signing key leaks.** The diary's signatures are the only thing that stops someone rewriting history.
  The key is generated in memory at gateway start and never written to disk, so it dies with the container - but
  a leak while the container is alive is still a leak.
- **A channel was never probed.** The certificate is a statement about tested channels only. If a new channel
  appears (a new shared mount, a new log file, a new cache), the certificate says nothing about it until the
  tester probes it.
- **The room's own code leaks its own secret.** If red writes its canary into a file blue can read, no amount of
  network hardening helps. That is exactly what the tripwire search is for.
- **Timing noise makes a channel look clean.** The cache-timing threshold (11 ms) is tuned to the toy model's
  2 ms / 20 ms simulated latencies. On a real model under real load, the threshold would have to be re-derived.

## Honest labels

| Real | Simulated / assumed |
|---|---|
| tripwire search, hash-chained signed diary, taint tracking, mutual-information maths | the toy model and its replies |
| containers, networks, mounts, room files and logs (Docker engine) | the cache-timing latency numbers (busy-waited, not a real LLM) |
| the shared-file leak-meter channel in the Docker engine | the leak-meter speeds (1000 uses/s, 40 uses/s) are assumptions |
| the gateway's policy, IP-based caller identification, Ed25519 signatures | the rooms in the simulation engine (Python objects, not containers) |

A channel that is simulated is flagged `real: false` in the results file, and the dashboard prints it in a
"simulated" column. Nothing in the dashboard claims more than the run measured.

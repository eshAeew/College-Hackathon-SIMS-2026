# API Sentinel — Hackathon Judge Q&A Cheatsheet
**Anticipated Technical Questions & Authoritative Responses**

---

### Q1: How does API Sentinel differ from Postman, Insomnia, or Thunder Client?
**Answer:**
> *“Postman and Thunder Client are primarily manual HTTP execution clients. API Sentinel is an **autonomous quality engineering and telemetry engine**.*
> *Sentinel handles the entire lifecycle automatically: from dereferencing OpenAPI specifications, generating combinatorial negative tests, detecting schema drifts and Shannon entropy flakiness, to packaging deterministic evidence bundles and generating AI remediations with closed-loop regression diff verification.”*

---

### Q2: What happens if the LLM (Google Gemini) is down, rate-limited, or offline?
**Answer:**
> *“Sentinel adheres strictly to our **Graceful Degradation Prime Directive**: the deterministic evaluation engine always decides pass/fail first. If Gemini is unavailable, rate-limited, or offline, Sentinel instantly falls back to its built-in rule-based heuristic diagnostic engine. The platform never crashes, never loses remediation capabilities, and records the fallback event in its resilience telemetry buffer.”*

---

### Q3: How do you prevent accidental destructive testing on production systems?
**Answer:**
> *“Stage 16 introduced our **Safety & Execution Controls Engine**. It enforces strict environment boundaries, host allowlisting, read-only constraints, and rate-limiting. For high-risk destructive actions (like mass DELETE or schema drops), Sentinel requires an explicit SHA-256 confirmation token and logs all operations to an immutable, cryptographically hash-chained audit ledger.”*

---

### Q4: How does Sentinel detect non-deterministic or flaky endpoints?
**Answer:**
> *“In Stage 10, we built the Inconsistent Behavior & Flakiness Engine. It calculates **Shannon Entropy** across repeated execution runs, detecting variance in HTTP status codes, latency spikes, and payload structures. If an endpoint intermittently flips between 200 and 500, Sentinel scores its flakiness entropy and flags it with high confidence.”*

---

### Q5: How do you measure regression between different deployments?
**Answer:**
> *“In Stage 21, we implemented the Run Comparison & Diff Tool. Sentinel compares any baseline test run against a target test run side-by-side, categorizing every test as `FIXED_FAILURE`, `NEW_FAILURE`, `PERSISTENT_FAILURE`, `DEGRADED_LATENCY`, or `CONSISTENT_PASS`, while highlighting metric deltas in pass rates and p95 latencies.”*

---

### Q6: Can this be embedded into GitHub Actions or CI/CD pipelines?
**Answer:**
> *“Yes! Sentinel includes both standard REST APIs (`/api/v1/self-test/*`, `/api/v1/demo/*`) and standalone CLI scripts (`scripts/self_test_runner.py`, `scripts/run_demo_story.py`). They produce machine-readable JSON reports and standard POSIX exit codes (`0` for success, non-zero for failure) for seamless integration into GitHub Actions, GitLab CI, and Jenkins.”*

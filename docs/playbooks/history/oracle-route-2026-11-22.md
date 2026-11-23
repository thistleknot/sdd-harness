# Superseded Oracle route decision — 2026-11-22

## SUPERSEDED 2026-11-22 — Shared party-oracle target

- Decision: Preserve the stable `party-oracle` alias and point it to the exact pulled NVIDIA Nemotron 3.5 Bolt E4B Q4_K_M tag through LiteLLM; set the Oracle effort to low and keep its 65,536 context cap. Preserve all other role aliases and Oracle's read-only permissions.
- Basis: The request names the new shared party-oracle and low thinking; Ollama confirms the exact tag is present and reports its 65,536 context. Keeping the alias avoids client-specific route changes.
- Status: LiteLLM was restarted; readiness is healthy, the `party-oracle` alias is listed, and `/model/info` reports the exact Nemotron Ollama target. No inference request has been sent, so tool use and effective reasoning behavior remain unverified.

Superseded after direct Ollama requests showed the model rejects `reasoning_effort: low`; see the current decision in `.specs/reqs/interpretations.md`.

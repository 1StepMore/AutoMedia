# Architecture Decision Records

Architecture Decision Records (ADRs) are the project's immutable record of
architectural decisions. Each ADR is one file, one decision — new decision,
new ADR. ADRs are never edited after acceptance; when a decision is revisited,
the change is recorded in a new ADR that marks the old one with
"Superseded by ADR-NNN" in its Status line rather than rewriting history.

## Index

| ADR | Decision |
|-----|----------|
| [ADR-001](ADR-001-singleton-registry-unification.md) | Unify `GateRegistry`, `AdapterRegistry`, and `OmniToolRegistry` under a common `BaseRegistry` singleton mixin |
| [ADR-002](ADR-002-hitl-decision-layer-decoupling.md) | Decouple the HITL framework from the decision layer via a `NodeProvider` Protocol and dependency injection |
| [ADR-003](ADR-003-platform-rename-stdlib-conflict.md) | Rename `automedia/platform/` to `platform_drafts/` to avoid shadowing the Python stdlib `platform` module |
| [ADR-004](ADR-004-mcp-server-decomposition.md) | Split the monolithic `mcp/server.py` into `allowlist.py`, `tools.py`, `resources.py`, and a thin `server.py` with backward-compatible re-exports |
| [ADR-005](ADR-005-issue-driven-commits.md) | Codify the repository's issue-driven commit discipline: one atomic, verifiable commit per issue or unit of work |

## How to Add a New ADR

1. Copy [`TEMPLATE.md`](TEMPLATE.md) to `docs/adr/ADR-NNN-<short-name>.md`,
   where `NNN` is the next free number and `<short-name>` is a kebab-case slug
   of the title (e.g. `ADR-006-lazy-registry-loading.md`).
2. Fill in the sections: Context, Decision, Alternatives Considered (and why
   they lost), Consequences — plus Status and Watch Out For as applicable.
3. Add a row for the new ADR to the index table above.

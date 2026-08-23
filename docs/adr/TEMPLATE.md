# ADR-NNN: <Short Title>

> **How to use this template**
> Copy this file to `docs/adr/ADR-NNN-<short-name>.md` where `NNN` is the next
> free number (e.g. ADR-006) and `<short-name>` is a kebab-case slug of the
> title. Fill in every section below, replacing the `<angle-bracket>` hints and
> the `<!-- HTML comments -->`. Delete this guidance block once the ADR is
> filled in. Do NOT renumber existing ADRs; decision records are immutable.

### Status
<!-- One of: Accepted · Effort: <Quick/Medium/Large> · or Proposed · or Implemented
     Match the style of existing ADRs, e.g. "Accepted · Effort: Medium (1–2 days)".
     If the ADR later becomes moot or superseded, append a note here or mark
     "Superseded by ADR-NNN" instead of editing the body. -->

### Context
<!-- What is the situation that forces this decision?
     State the problem, the constraints, and the current state of the code.
     Facts and data live here; opinions and conclusions live in Decision. -->

### Decision
<!-- What did we choose, and why does it resolve the context?
     Be concrete: name the modules, files, or interfaces affected.
     This is the immutable record — future readers must be able to reconstruct
     exactly what was decided without reading the code diff. -->

### Alternatives Considered
<!-- Document the options that lost and WHY they lost. This is what makes an
     ADR a decision record rather than a changelog. One subsection per option. -->

#### Option A: <Name of alternative>
<!-- Short description of the alternative. -->
- **Pros:** <why it was attractive>
- **Cons:** <why it lost>

#### Option B: <Name of alternative>
<!-- Repeat as needed. If only one option existed, say so explicitly
     ("No alternatives were viable because ...") rather than leaving this empty. -->
- **Pros:** ...
- **Cons:** ...

### Consequences
<!-- What changes as a result? Both positive and negative.
     What will be easier, what becomes harder, what must be watched.
     This section is where the long-term trade-offs live. -->

### Watch Out For
<!-- Optional but common in this repo's ADRs. List concrete implementation
     pitfalls, follow-up work, and anything a future editor must not break.
     Delete this section if it does not apply. -->

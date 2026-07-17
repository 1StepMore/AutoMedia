---
name: brand-strategy
description: "Use the `run_brand_strategy` MCP tool to generate LLM-driven brand positioning, audience analysis, competitive landscape, differentiators, and messaging suggestions. Triggers: 'brand strategy', 'brand positioning', 'brand analysis', 'competitive analysis', 'positioning statement', 'target audience analysis'."
---

# Brand Strategy — run_brand_strategy

Use this skill when the user asks for brand positioning, strategy, or market analysis. The MCP tool calls an LLM with a structured `BrandStrategyOutput` schema and returns five fields.

## When to Use

The user mentions any of: brand positioning, brand strategy, competitive landscape, audience analysis, key differentiators, messaging. Do NOT use for general content strategy or pipeline topics — those belong to `run_pipeline_from_strategy` or `research_topics`.

## Input Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `brand_name` | Yes | Name of the brand to analyse |
| `industry` | Yes | Industry or vertical (e.g. "SaaS", "e-commerce") |
| `target_audience` | Yes | Description of the target audience |
| `context` | No | Optional additional context or constraints |

## Example

When the user says "Help me define a brand strategy for my fintech startup targeting Gen Z":

```
MCP call: run_brand_strategy(
    brand_name="<their startup name>",
    industry="fintech",
    target_audience="Gen Z (18-26), mobile-first, value transparency and low fees",
    context="Pre-seed startup, launching Q3, mobile-only"
)
```

## Expected Output Structure

The tool returns a dict with these keys (from `BrandStrategyOutput`):

```
{
    "brand_positioning":       str   — Core positioning statement
    "audience_analysis":       str   — Deep dive on target demographics, psychographics, needs
    "competitive_landscape":   str   — Analysis of competitors and market gaps
    "key_differentiators":     list[str] — What sets the brand apart
    "suggested_messaging":     list[str] — Recommended message pillars, taglines
}
```

Each string field is a few paragraphs. The list fields typically contain 2-5 items.

## Error Handling

The LLM call can fail for these reasons:

- **Missing API key**: The `AUTOMEDIA_LLM_API_KEY` env var is not set. Tell the user to set it.
- **LLM timeout or rate limit**: The provider is slow or throttled. Retry once after informing the user. If it fails again, suggest switching providers or checking their quota.
- **Schema validation failure**: The LLM returned output that does not match `BrandStrategyOutput`. This is rare with structured output mode. If it happens, report it as an internal error and retry.
- **Empty context**: If the user provided minimal info, the output will be generic. Suggest they provide more specific details (industry, audience, competitors).

If the tool returns `{"error": "..."}`, relay the error to the user and do not fabricate results.

## Related Tools

- `run_pipeline_from_strategy` — generates content strategy AND runs the pipeline
- `research_topics` — researches trending topics within a category
- `evaluate_content_quality` — scores content against brand voice criteria

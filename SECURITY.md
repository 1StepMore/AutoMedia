# Security Policy

## Supported Versions

Only the latest stable release of AutoMedia receives security updates. We do not backport fixes to older versions.

| Version | Supported          |
|---------|--------------------|
| latest  | :white_check_mark: |
| < latest| :x:                |

Please ensure you are always running the most recent release.

## Coordinated Disclosure Policy

We are committed to working with security researchers and the community to protect the AutoMedia project and its users. We ask that all security vulnerabilities be reported privately and responsibly.

### Do's

- Report vulnerabilities as soon as you discover them.
- Provide sufficient detail to reproduce the issue.
- Allow us reasonable time to fix the issue before disclosing it publicly.
- Make a good-faith effort to avoid privacy violations, data destruction, and service interruption.

### Don'ts

- Do not disclose the vulnerability publicly before a fix is released.
- Do not exploit the vulnerability beyond what is necessary to demonstrate impact.
- Do not access or modify production user data without permission.

## Reporting a Vulnerability

### For Active Exploits or Critical Issues

If you have discovered an actively exploited vulnerability or a critical security issue, please report it privately via email:

**Email:** security@automedia.dev

We will acknowledge receipt within **48 hours** and provide an initial assessment.

### For Non-Critical Issues

For non-critical security concerns or questions, you may open a **GitHub Issue** using the "Bug Report" template. Please mark the issue as sensitive if appropriate.

**Do not** use GitHub Issues for reporting active security exploits — use the email channel instead.

### PGP Key

We do not yet have a PGP key established for encrypted communication. If sensitive information must be transmitted before we establish one, please use the email channel to coordinate an alternative secure method.

## Response Timeline

We aim to follow this timeline for confirmed vulnerabilities:

| Event                        | Target       |
|------------------------------|--------------|
| Acknowledgment of receipt    | 48 hours     |
| Initial assessment & triage  | 5 business days |
| Fix released (critical)      | 14 days      |
| Fix released (medium/low)    | 30 days      |
| Public disclosure after fix  | 14 days      |

These timelines are targets, not guarantees. Complex issues may require additional time, and we will communicate any delays to the reporter.

## Scope

The following are in scope for security reports:

- The `automedia/` Python package and its dependencies
- The MCP server and its tools
- The CLI application
- Authentication and credential handling
- Pipeline execution and data integrity

Out of scope:

- Third-party services used with AutoMedia (e.g., LLM providers, storage backends)
- Issues in dependencies that are already fixed in upstream versions

## Recognition

We thank security researchers who follow this policy and disclose vulnerabilities responsibly. With your permission, we will acknowledge your contribution in release notes and our security acknowledgments page.

---

Thank you for helping keep AutoMedia and its users safe.

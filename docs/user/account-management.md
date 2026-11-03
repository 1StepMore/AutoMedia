---
title: Account & Credential Management
description: Registering accounts, rotating credentials, and the master-key lifecycle for the encrypted credential store.
---

# Account & Credential Management

All platform credentials live in an **AES-256-GCM encrypted store** at
`~/.automedia/accounts/` — plaintext never touches disk, and nothing
credential-shaped ever enters the repository.

## Commands

| Command | Purpose |
|---|---|
| `automedia account add <platform> --cred k=v …` | Non-interactive registration (script/agent friendly); repeatable `--cred`, or `--from-json <file>` |
| `automedia account connect <platform>` | Interactive registration (prompts for key=value lines) |
| `automedia account login-capture <platform>` | Capture a browser login session (cookie auth) into the store |
| `automedia account rotate <id> --cred k=v …` | Replace credentials, keeping the account identity/label/history |
| `automedia account list [--platform …] [--status …]` | List accounts (metadata only — never credentials) |
| `automedia account health <id>` | Session health |
| `automedia account remove <id>` / `disconnect <id>` | Delete an account (confirm unless `--yes`) |

`add` never echoes values — output shows keys and the account id only.
`rotate` prints the new fingerprint prefix for audit trails.

## Master key lifecycle

The store derives its AES-256 key as `SHA-256(AUTOMEDIA_MASTER_KEY)`.
`AUTOMEDIA_MASTER_KEY` is resolved env-first, then from the `~/.automedia/.env`
overlay (`AUTOMEDIA_DOTENV_PATH` can relocate that overlay file).

### Generation

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
# → append AUTOMEDIA_MASTER_KEY=<value> to ~/.automedia/.env
```

(On first need the account commands tell you the variable is missing —
nothing is ever auto-generated into a place you weren't told about.)

### Backup — do it now, not later

**Losing the master key makes every stored credential permanently
undecryptable.** There is no recovery path by design (the key IS the root of
trust). Back the key up the way you back up SSH keys: a secrets manager, an
encrypted note, a paper copy in a drawer — any place that is not this
machine's only copy.

### Rotation

Key rotation = decrypt-everything-with-the-old-key and re-encrypt with the
new one. There is no in-place store migration today (tracked in the gap
register); the working procedure is:

1. `automedia account list` — note every account.
2. Export each credential (`get_credentials` via a short script) while the
   old key is active.
3. Replace `AUTOMEDIA_MASTER_KEY`, then re-register (`account add` /
   `login-capture`).
4. Verify with `account list` + one `account health` per platform.

### Never do this

- Never commit `AUTOMEDIA_MASTER_KEY`, `.env`, or any exported credential
  file (red line: credentials never enter the repository).
- Never paste cookies/keys into chat transcripts, tickets, or screenshots.
- Never point `AUTOMEDIA_DOTENV_PATH` at a file inside the repository.

## How publishers consume credentials

Easy-tier (API) adapters read env/config credentials directly. Hard-tier
(browser) adapters load the Playwright **storage_state** captured by
`login-capture` — see the
[capability matrix](platform-capability-matrix.md) for the per-platform
tier table.

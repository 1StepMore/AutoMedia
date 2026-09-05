#!/usr/bin/env bash
# AutoMedia - one-command MCP setup for AI agent clients.
#
# Detects which agent client is in use and writes/updates its MCP server
# config so the client can call AutoMedia's MCP tools:
#   python -m automedia.mcp.server
#
# Usage:
#   scripts/setup_agent_mcp.sh                    # auto-detect client, install/update
#   scripts/setup_agent_mcp.sh --list             # show detected clients + config state
#   scripts/setup_agent_mcp.sh --uninstall        # remove ONLY the automedia entry
#   scripts/setup_agent_mcp.sh --client-dir DIR   # operate on DIR (hermetic tests)
#   scripts/setup_agent_mcp.sh --client NAME      # force client type
#
# Supported clients and config targets (shapes mirror README
# "MCP Client Configuration Examples"):
#   opencode  <base>/.opencode/package.json  ->  mcpServers.automedia  {command,args}
#   claude    <base>/.claude/settings.json   ->  mcpServers.automedia  {command,args,env}
#   codex     <base>/.codex/config.json      ->  mcpServers.automedia  {command,args,env}
#   cursor    <base>/.cursor/mcp.json        ->  mcpServers.automedia  {command,args,env}
#   hermes    <base>/.hermes/config.yaml     ->  mcp_servers.automedia (YAML block)
#   openclaw  <base>/.openclaw/openclaw.json ->  mcp.servers.automedia {command,args,env}
#
# <base> is $PWD for project clients (opencode/claude/codex/cursor) and $HOME
# for personal clients (hermes/openclaw).
#
# --client-dir semantics: DIR is the client config directory ITSELF (e.g. a
# directory containing settings.json), not a workspace root. The client type is
# inferred from the config file present inside DIR (package.json -> opencode,
# settings.json -> claude, config.json -> codex, mcp.json -> cursor,
# config.yaml -> hermes, openclaw.json -> openclaw), falling back to the
# directory name convention (.claude, .codex, ...). All files are then managed
# directly inside DIR, regardless of client type.
#
# Design decisions (plan todo 19, productization-roadmap-20260902):
# - jq is required for JSON clients; degrade with a clear error if missing.
# - If a client's config FILE is missing but its directory exists, the file is
#   created containing only the automedia entry: the opencode/claude files are
#   expected to exist in a real workspace, codex gets {"mcpServers":{...}},
#   cursor's mcp.json is the dedicated MCP file, hermes/openclaw get their
#   minimal shape. Creation takes no .bak (nothing pre-existed to preserve).
# - YAML (Hermes): jq cannot edit YAML and no YAML tooling is guaranteed.
#   Strategy: if mcp_servers.automedia already exists -> leave untouched;
#   if a top-level "mcp_servers:" section exists WITHOUT automedia -> SKIP the
#   write (appending would duplicate the top-level key and risk clobbering
#   other servers) and print manual instructions (exit 2); otherwise append a
#   minimal block. Removal deletes only the automedia subtree. ALWAYS back up
#   before modifying.
# - Secrets: this script NEVER reads the value of AUTOMEDIA_LLM_API_KEY.
#   Config files get the literal "${AUTOMEDIA_LLM_API_KEY}" placeholder
#   (clients that expand env placeholders resolve it; the MCP server also
#   inherits your shell environment). Never put a real key in a repo config.
# - Idempotent: re-running converges. The automedia entry is upserted to the
#   canonical shape; no other keys are touched; no duplicate entries are created.
# - shellcheck: not installed on the authoring machine (documented); written
#   shellcheck-clean by construction (quoted expansions, no unsafe patterns).
#
# Exit codes:
#   0  success (installed / already current / removed / nothing to do / --list)
#   1  no supported client detected, or invalid/ambiguous arguments
#   2  tooling or data error (jq missing, invalid JSON target, unsafe YAML state)

set -euo pipefail

readonly SCRIPT_NAME="$(basename "$0")"
readonly CLIENTS="opencode claude codex cursor hermes openclaw"

MODE="install"
FORCE_CLIENT=""
CLIENT_DIR=""
BASE_PWD="${PWD}"

log()  { printf '%s\n' "$*"; }
ok()   { printf 'OK  %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*"; }
die()  { local msg="$1" code="${2:-1}"; printf 'ERROR: %s\n' "$msg" >&2; exit "$code"; }

usage() {
cat <<'USAGE'
Usage: scripts/setup_agent_mcp.sh [options]

Detect the agent client in use and configure its AutoMedia MCP server entry
(python -m automedia.mcp.server).

Options:
  (none)            Auto-detect client (cwd for opencode/claude/codex/cursor,
                    $HOME for hermes/openclaw) and install/update the entry
  --list            Show all detected clients and automedia config state
  --uninstall       Remove ONLY the automedia entry from the target client
  --client-dir DIR  Operate on DIR instead of cwd/home. DIR is the client
                    config directory itself; type inferred from its contents
  --client NAME     Force client type: opencode|claude|codex|cursor|hermes|openclaw
  -h, --help        Show this help

Exit codes: 0 success/no-op, 1 no client detected or bad usage, 2 tooling/data error
USAGE
}

is_valid_client() {
    local c
    for c in $CLIENTS; do
        if [[ "$c" == "$1" ]]; then
            return 0
        fi
    done
    return 1
}

# --- path resolution ---------------------------------------------------------

client_base() {
    local client="$1"
    if [[ -n "$CLIENT_DIR" ]]; then
        printf '%s\n' "$CLIENT_DIR"
        return
    fi
    case "$client" in
        hermes|openclaw) printf '%s\n' "${HOME:?HOME is not set}" ;;
        *)               printf '%s\n' "$BASE_PWD" ;;
    esac
}

client_file() {
    local client="$1" base
    base="$(client_base "$client")"
    if [[ -n "$CLIENT_DIR" ]]; then
        # DIR is the client config directory itself.
        case "$client" in
            opencode) printf '%s/package.json'  "$base" ;;
            claude)   printf '%s/settings.json' "$base" ;;
            codex)    printf '%s/config.json'   "$base" ;;
            cursor)   printf '%s/mcp.json'      "$base" ;;
            hermes)   printf '%s/config.yaml'   "$base" ;;
            openclaw) printf '%s/openclaw.json' "$base" ;;
        esac
    else
        case "$client" in
            opencode) printf '%s/.opencode/package.json'  "$base" ;;
            claude)   printf '%s/.claude/settings.json'   "$base" ;;
            codex)    printf '%s/.codex/config.json'      "$base" ;;
            cursor)   printf '%s/.cursor/mcp.json'        "$base" ;;
            hermes)   printf '%s/.hermes/config.yaml'     "$base" ;;
            openclaw) printf '%s/.openclaw/openclaw.json' "$base" ;;
        esac
    fi
}

# Auto-detection order (plan todo 19): opencode > claude > codex > cursor > hermes > openclaw.
detect_clients() {
    local c file
    for c in $CLIENTS; do
        file="$(client_file "$c")"
        if [[ -d "$(dirname "$file")" ]]; then
            printf '%s\n' "$c"
        fi
    done
}

# Type inference for --client-dir: file presence first, dir-name convention second.
detect_type_from_dir() {
    local dir="$1" base
    base="$(basename "$dir")"
    if [[ -f "$dir/package.json" ]];  then printf 'opencode\n'; return 0; fi
    if [[ -f "$dir/settings.json" ]]; then printf 'claude\n';   return 0; fi
    if [[ -f "$dir/config.json" ]];   then printf 'codex\n';    return 0; fi
    if [[ -f "$dir/mcp.json" ]];      then printf 'cursor\n';   return 0; fi
    if [[ -f "$dir/config.yaml" ]];   then printf 'hermes\n';   return 0; fi
    if [[ -f "$dir/openclaw.json" ]]; then printf 'openclaw\n'; return 0; fi
    case "$base" in
        .opencode|opencode) printf 'opencode\n'; return 0 ;;
        .claude|claude)     printf 'claude\n';   return 0 ;;
        .codex|codex)       printf 'codex\n';    return 0 ;;
        .cursor|cursor)     printf 'cursor\n';   return 0 ;;
        .hermes|hermes)     printf 'hermes\n';   return 0 ;;
        .openclaw|openclaw) printf 'openclaw\n'; return 0 ;;
    esac
    return 1
}

# --- shared helpers ----------------------------------------------------------

require_jq() {
    if ! command -v jq >/dev/null 2>&1; then
        die "jq is required to edit JSON configs safely. Install it (apt install jq / brew install jq) and re-run." 2
    fi
}

# Canonical automedia entry. with_env=0 for OpenCode (no env block, mirrors the
# README/OpenCode snippet); with_env=1 for claude/codex/cursor/openclaw.
entry_json() {
    local with_env="$1"
    if [[ "$with_env" == "1" ]]; then
        jq -cn '{command: "python", args: ["-m", "automedia.mcp.server"], env: {AUTOMEDIA_LLM_API_KEY: "${AUTOMEDIA_LLM_API_KEY}"}}'
    else
        jq -cn '{command: "python", args: ["-m", "automedia.mcp.server"]}'
    fi
}

backup_file() {
    # Only meaningful for existing files; overwrites any previous .bak.
    local file="$1"
    if [[ -f "$file" ]]; then
        cp -p "$file" "$file.bak"
    fi
}

write_atomic() {
    # stdin -> target, via a temp file in the same directory (same filesystem).
    local target="$1" tmp mode
    tmp="$(mktemp "$target.tmp.XXXXXX")"
    if [[ -f "$target" ]]; then
        mode="$(stat -c '%a' "$target" 2>/dev/null || true)"
        if [[ -n "$mode" ]]; then chmod "$mode" "$tmp" || true; fi
    else
        chmod 644 "$tmp" 2>/dev/null || true
    fi
    cat > "$tmp"
    mv -f "$tmp" "$target"
}

# --- JSON clients (opencode / claude / codex / cursor) -----------------------

install_standard_json() {
    local file="$1" entry="$2" current canonical merged
    if [[ ! -f "$file" ]]; then
        mkdir -p "$(dirname "$file")"
        if ! merged="$(jq -n --argjson entry "$entry" '{mcpServers: {automedia: $entry}}')"; then
            die "Failed to build config content for $file" 2
        fi
        printf '%s\n' "$merged" | write_atomic "$file"
        ok "Created $file with the automedia MCP entry"
        return 0
    fi
    if ! jq -e . "$file" >/dev/null 2>&1; then
        die "Existing config is not valid JSON: $file - fix or remove it, then re-run." 2
    fi
    current="$(jq -c '.mcpServers.automedia // empty' "$file" 2>/dev/null || true)"
    canonical="$(printf '%s' "$entry" | jq -Sc .)"
    if [[ -n "$current" && "$(printf '%s' "$current" | jq -Sc .)" == "$canonical" ]]; then
        ok "automedia entry already up to date in $file"
        return 0
    fi
    backup_file "$file"
    if ! merged="$(jq --argjson entry "$entry" '.mcpServers = ((.mcpServers // {}) + {automedia: $entry})' "$file")"; then
        die "Failed to merge the automedia entry into $file (is mcpServers an object?)" 2
    fi
    printf '%s\n' "$merged" | write_atomic "$file"
    if [[ -n "$current" ]]; then
        ok "Updated automedia MCP entry in $file (backup: $file.bak)"
    else
        ok "Added automedia MCP entry to $file (backup: $file.bak)"
    fi
}

uninstall_standard_json() {
    local file="$1" current merged
    if [[ ! -f "$file" ]]; then
        log "No config at $file - nothing to uninstall."
        return 0
    fi
    if ! jq -e . "$file" >/dev/null 2>&1; then
        die "Existing config is not valid JSON: $file - fix it manually." 2
    fi
    current="$(jq -c '.mcpServers.automedia // empty' "$file" 2>/dev/null || true)"
    if [[ -z "$current" ]]; then
        log "No automedia entry in $file - nothing to uninstall."
        return 0
    fi
    backup_file "$file"
    if ! merged="$(jq 'if (type == "object") and has("mcpServers") and (.mcpServers | type == "object") then .mcpServers |= del(.automedia) else . end' "$file")"; then
        die "Failed to remove the automedia entry from $file" 2
    fi
    printf '%s\n' "$merged" | write_atomic "$file"
    ok "Removed automedia entry from $file (backup: $file.bak)"
}

# --- OpenClaw (mcp.servers, per todo-18 finding) -----------------------------

install_openclaw() {
    local file="$1" entry="$2" current canonical merged
    if [[ ! -f "$file" ]]; then
        mkdir -p "$(dirname "$file")"
        if ! merged="$(jq -n --argjson entry "$entry" '{mcp: {servers: {automedia: $entry}}}')"; then
            die "Failed to build config content for $file" 2
        fi
        printf '%s\n' "$merged" | write_atomic "$file"
        ok "Created $file with the automedia MCP entry (mcp.servers)"
        return 0
    fi
    if ! jq -e . "$file" >/dev/null 2>&1; then
        die "Existing config is not valid JSON: $file - fix or remove it, then re-run." 2
    fi
    current="$(jq -c '.mcp.servers.automedia // empty' "$file" 2>/dev/null || true)"
    canonical="$(printf '%s' "$entry" | jq -Sc .)"
    if [[ -n "$current" && "$(printf '%s' "$current" | jq -Sc .)" == "$canonical" ]]; then
        ok "automedia entry already up to date in $file"
        return 0
    fi
    backup_file "$file"
    if ! merged="$(jq --argjson entry "$entry" '.mcp = ((.mcp // {}) + {servers: ((.mcp.servers // {}) + {automedia: $entry})})' "$file")"; then
        die "Failed to merge the automedia entry into $file (is mcp.servers an object?)" 2
    fi
    printf '%s\n' "$merged" | write_atomic "$file"
    if [[ -n "$current" ]]; then
        ok "Updated automedia MCP entry in $file (backup: $file.bak)"
    else
        ok "Added automedia MCP entry to $file (backup: $file.bak)"
    fi
}

uninstall_openclaw() {
    local file="$1" current merged
    if [[ ! -f "$file" ]]; then
        log "No config at $file - nothing to uninstall."
        return 0
    fi
    if ! jq -e . "$file" >/dev/null 2>&1; then
        die "Existing config is not valid JSON: $file - fix it manually." 2
    fi
    current="$(jq -c '.mcp.servers.automedia // empty' "$file" 2>/dev/null || true)"
    if [[ -z "$current" ]]; then
        log "No automedia entry in $file - nothing to uninstall."
        return 0
    fi
    backup_file "$file"
    if ! merged="$(jq 'if (type == "object") and (.mcp | type == "object") and (.mcp.servers | type == "object") then .mcp.servers |= del(.automedia) else . end' "$file")"; then
        die "Failed to remove the automedia entry from $file" 2
    fi
    printf '%s\n' "$merged" | write_atomic "$file"
    ok "Removed automedia entry from $file (backup: $file.bak)"
}

# --- Hermes (YAML: conservative append-if-absent + backup) -------------------

yaml_has_automedia() {
    awk '
        /^[A-Za-z_][A-Za-z0-9_-]*:/ { in_ms = ($0 ~ /^mcp_servers:/) ? 1 : 0 }
        in_ms && /^[[:space:]]+automedia:/ { found = 1 }
        END { if (found) exit 0; exit 1 }
    ' "$1"
}

yaml_append_block() {
    {
        printf '\n'
        cat <<'YAML'
# AutoMedia MCP server (added by scripts/setup_agent_mcp.sh)
mcp_servers:
  automedia:
    command: python
    args: ["-m", "automedia.mcp.server"]
    env:
      AUTOMEDIA_LLM_API_KEY: "${AUTOMEDIA_LLM_API_KEY}"
YAML
    } >> "$1"
}

install_hermes_yaml() {
    local file="$1"
    if [[ ! -f "$file" ]]; then
        mkdir -p "$(dirname "$file")"
        {
            cat <<'YAML'
# Hermes Agent config (written by scripts/setup_agent_mcp.sh)
mcp_servers:
  automedia:
    command: python
    args: ["-m", "automedia.mcp.server"]
    env:
      AUTOMEDIA_LLM_API_KEY: "${AUTOMEDIA_LLM_API_KEY}"
YAML
        } | write_atomic "$file"
        ok "Created $file with the automedia MCP entry"
        return 0
    fi
    if yaml_has_automedia "$file"; then
        ok "automedia entry already present in $file (left untouched)"
        return 0
    fi
    if grep -q '^mcp_servers:' "$file"; then
        die "Unsafe YAML state: $file already has a top-level 'mcp_servers:' section without an automedia entry. Auto-append would duplicate the key and risk clobbering your other servers. Add the automedia block under the existing section manually (see README 'MCP Client Configuration Examples', Hermes row). Nothing was written." 2
    fi
    backup_file "$file"
    yaml_append_block "$file"
    ok "Appended automedia MCP block to $file (backup: $file.bak)"
}

uninstall_hermes_yaml() {
    local file="$1" tmp marker
    if [[ ! -f "$file" ]]; then
        log "No config at $file - nothing to uninstall."
        return 0
    fi
    marker="# AutoMedia MCP server (added by scripts/setup_agent_mcp.sh)"
    tmp="$(mktemp "$file.tmp.XXXXXX")"
    if grep -qF "$marker" "$file"; then
        # The block was appended by this script (marker present): remove the
        # marker, the blank line before it, and the whole appended section
        # (top-level mcp_servers: line plus every indented/blank line after it,
        # until the next top-level non-blank line or EOF).
        awk -v marker="$marker" '
            in_block {
                if ($0 == "mcp_servers:") next
                if ($0 ~ /^[[:space:]]*$/) next
                if ($0 ~ /^[[:space:]]+/) next
                in_block = 0
            }
            $0 == marker {
                in_block = 1
                if (have_prev && prev ~ /^[[:space:]]*$/) { have_prev = 0 }
                if (have_prev) print prev
                have_prev = 0
                next
            }
            {
                if (have_prev) print prev
                prev = $0
                have_prev = 1
            }
            END { if (have_prev && prev !~ /^[[:space:]]*$/) print prev }
        ' "$file" > "$tmp"
    else
        # Entry was added manually under an existing section: remove ONLY the
        # automedia subtree; then prune the top-level mcp_servers: key if the
        # removal left it empty (null-valued key would be untidy).
        # 3-pass awk over the whole file: (1) mark the automedia subtree lines,
        # (2) prune a top-level mcp_servers: key left with no children,
        # (3) emit kept lines, collapsing blank runs. No streaming `next`
        # interplay with the line buffer - every decision sees all lines.
        awk '
            function indent_of(s,  i) {
                i = 0
                while (i < length(s) && substr(s, i + 1, 1) == " ") i++
                return i
            }
            { lines[NR] = $0 }
            END {
                for (i = 1; i <= NR; i++) drop[i] = 0
                in_ms = 0
                for (i = 1; i <= NR; i++) {
                    line = lines[i]
                    if (line ~ /^[A-Za-z_][A-Za-z0-9_-]*:/) in_ms = (line ~ /^mcp_servers:/) ? 1 : 0
                    if (in_ms && line ~ /^[[:space:]]+automedia:/) {
                        skip_ind = indent_of(line)
                        drop[i] = 1
                        for (j = i + 1; j <= NR; j++) {
                            l2 = lines[j]
                            if (l2 ~ /^[[:space:]]*$/) { drop[j] = 1; continue }
                            if (indent_of(l2) > skip_ind) { drop[j] = 1; continue }
                            break
                        }
                        i = j - 1
                    }
                }
                for (i = 1; i <= NR; i++) {
                    if (drop[i] || lines[i] !~ /^mcp_servers:/) continue
                    has_child = 0
                    for (j = i + 1; j <= NR; j++) {
                        if (drop[j]) continue
                        l2 = lines[j]
                        if (l2 ~ /^[[:space:]]*$/) continue
                        if (l2 ~ /^[[:space:]]+/) has_child = 1
                        break
                    }
                    if (!has_child) drop[i] = 1
                }
                started = 0
                for (i = 1; i <= NR; i++) {
                    if (drop[i]) continue
                    if (lines[i] ~ /^[[:space:]]*$/) { if (started) pending = 1; continue }
                    if (started) {
                        printf "\n"
                        if (pending) printf "\n"
                    }
                    started = 1
                    pending = 0
                    printf "%s", lines[i]
                }
                printf "\n"
            }
        ' "$file" > "$tmp"
    fi
    if cmp -s "$file" "$tmp"; then
        rm -f "$tmp"
        log "No automedia entry in $file - nothing to uninstall."
        return 0
    fi
    backup_file "$file"
    mv -f "$tmp" "$file"
    ok "Removed automedia block from $file (backup: $file.bak)"
}

# --- dispatch ----------------------------------------------------------------

install_for_client() {
    local client="$1" file entry
    file="$(client_file "$client")"
    case "$client" in
        opencode)
            entry="$(entry_json 0)"
            install_standard_json "$file" "$entry"
            ;;
        openclaw)
            entry="$(entry_json 1)"
            install_openclaw "$file" "$entry"
            ;;
        hermes)
            install_hermes_yaml "$file"
            ;;
        *)
            entry="$(entry_json 1)"
            install_standard_json "$file" "$entry"
            ;;
    esac
}

uninstall_for_client() {
    local client="$1" file
    file="$(client_file "$client")"
    case "$client" in
        openclaw) uninstall_openclaw "$file" ;;
        hermes)   uninstall_hermes_yaml "$file" ;;
        *)        uninstall_standard_json "$file" ;;
    esac
}

entry_state_for_list() {
    # prints "CONFIGURED <compact-entry>" or "absent" or "unreadable"
    local client="$1" file="$2" entry
    case "$client" in
        hermes)
            if yaml_has_automedia "$file"; then
                printf 'CONFIGURED %s\n' "(YAML mcp_servers.automedia, command: python)"
            else
                printf 'absent\n'
            fi
            ;;
        openclaw)
            entry="$(jq -c '.mcp.servers.automedia // empty' "$file" 2>/dev/null || true)"
            if [[ -n "$entry" ]]; then printf 'CONFIGURED %s\n' "$entry"; else printf 'absent\n'; fi
            ;;
        *)
            entry="$(jq -c '.mcpServers.automedia // empty' "$file" 2>/dev/null || true)"
            if [[ -n "$entry" ]]; then printf 'CONFIGURED %s\n' "$entry"; else printf 'absent\n'; fi
            ;;
    esac
}

list_all() {
    local c file base dir state
    log "AutoMedia MCP client config state (detection order: opencode > claude > codex > cursor > hermes > openclaw):"
    for c in $CLIENTS; do
        base="$(client_base "$c")"
        file="$(client_file "$c")"
        dir="$(dirname "$file")"
        log ""
        log "  $c"
        log "    config file: $file"
        if [[ ! -f "$file" ]]; then
            if [[ -d "$dir" ]]; then
                log "    state:       client dir present, config file missing (run without --list to create)"
            else
                log "    state:       not detected"
            fi
            continue
        fi
        state="$(entry_state_for_list "$c" "$file")"
        log "    state:       $state"
    done
}

post_install_notes() {
    local client="$1"
    log ""
    if [[ -n "${AUTOMEDIA_LLM_API_KEY:-}" ]]; then
        log "NOTE: AUTOMEDIA_LLM_API_KEY is set in your environment. The MCP server"
        log "      inherits it when your client launches it; the config file contains"
        log "      only the \${AUTOMEDIA_LLM_API_KEY} placeholder (never a real secret)."
    else
        log "NOTE: export AUTOMEDIA_LLM_API_KEY=... in the shell that launches your"
        log "      client, so the MCP server can reach your LLM provider."
    fi
    case "$client" in
        opencode)
            log "NOTE: the OpenCode entry has no env block - the server inherits your shell env."
            ;;
        hermes|openclaw)
            log "NOTE: clients that expand \${VAR} in env values resolve the placeholder"
            log "      automatically; if yours does not, edit the placeholder to your key."
            ;;
    esac
    log "NOTE: the entry runs: python -m automedia.mcp.server - make sure 'python'"
    log "      resolves to an interpreter with automedia installed (e.g. source .venv/bin/activate)."
}

main() {
    while (( $# > 0 )); do
        case "$1" in
            --list)       MODE="list" ;;
            --install)    MODE="install" ;;
            --uninstall)  MODE="uninstall" ;;
            --client)     shift; FORCE_CLIENT="${1:-}"; [[ -n "$FORCE_CLIENT" ]] || die "--client requires a value" 1 ;;
            --client-dir) shift; CLIENT_DIR="${1:-}"; [[ -n "$CLIENT_DIR" ]] || die "--client-dir requires a value" 1 ;;
            -h|--help)    usage; exit 0 ;;
            *)            printf 'ERROR: unknown option: %s\n\n' "$1" >&2; usage >&2; exit 1 ;;
        esac
        shift
    done

    if [[ -n "$FORCE_CLIENT" ]] && ! is_valid_client "$FORCE_CLIENT"; then
        die "Unknown client '$FORCE_CLIENT'. Valid: $CLIENTS" 1
    fi

    if [[ -n "$CLIENT_DIR" ]]; then
        if [[ ! -d "$CLIENT_DIR" ]]; then
            die "--client-dir does not exist: $CLIENT_DIR" 1
        fi
        CLIENT_DIR="$(cd "$CLIENT_DIR" && pwd)"
        if [[ -z "$FORCE_CLIENT" ]]; then
            local inferred
            if ! inferred="$(detect_type_from_dir "$CLIENT_DIR")"; then
                die "Cannot determine the client type from the contents of $CLIENT_DIR (looked for package.json, settings.json, config.json, mcp.json, config.yaml, openclaw.json, or a .claude-style directory name). Pass --client <name>." 1
            fi
            FORCE_CLIENT="$inferred"
        fi
    fi

    require_jq

    if [[ "$MODE" == "list" ]]; then
        list_all
        exit 0
    fi

    if [[ -z "$FORCE_CLIENT" ]]; then
        local -a detected=()
        mapfile -t detected < <(detect_clients)
        if (( ${#detected[@]} == 0 )); then
            log "No supported agent client detected."
            log "Looked for (in order): .opencode/ .claude/ .codex/ .cursor/ under $BASE_PWD, and ~/.hermes/ ~/.openclaw/ under ${HOME:-}."
            log "Create the client's config directory, or pass --client-dir DIR / --client NAME."
            log "Nothing was written."
            exit 1
        fi
        if (( ${#detected[@]} > 1 )); then
            warn "Multiple clients detected (${detected[*]}); using the first: ${detected[0]} (order: opencode > claude > codex > cursor > hermes > openclaw). Use --client to target another."
        fi
        FORCE_CLIENT="${detected[0]}"
    fi

    case "$MODE" in
        install)
            install_for_client "$FORCE_CLIENT"
            post_install_notes "$FORCE_CLIENT"
            ;;
        uninstall)
            uninstall_for_client "$FORCE_CLIENT"
            ;;
    esac
}

main "$@"

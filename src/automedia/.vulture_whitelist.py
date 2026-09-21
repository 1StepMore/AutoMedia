# Vulture false-positive whitelist for AutoMedia.
# See: https://github.com/jendrikseitz/vulture#whitelists

# automedia/cli/commands/cron.py:43 — CLI option accepted but not yet used
timeout  # unused variable

# automedia/mcp/parallel.py:104 — signal handler signature requires `frame`
frame  # unused variable

# automedia/omni/orf_adapter.py:49-50 — stub method params for future implementation
original_md  # unused variable
skeleton_path  # unused variable

# automedia/adapters/base.py:259 — `period` is part of the public adapter
# analytics signature (`get_analytics(account_id, period)`); overrides in
# platform adapters accept it, so it is an interface surface, not dead code.
period  # unused variable

# automedia/core/credential_loader.py:199 — `role` is part of the public
# `resolve_api_key(provider_name, role)` signature; callers may pass it by
# keyword, so it is kept as an interface surface.
role  # unused variable

# automedia/hitl/config.py:59 — explicitly marked "deprecated, kept for
# backward compat"; removing it would break existing callers.
node_provider  # unused variable

# automedia/pipelines/gate_engine.py:29 — `GateErrorResult` is re-exported from
# gate_types for backward compatibility (the import block's F401 is explicitly
# suppressed); it has no in-repo consumer but is a deliberate public re-export,
# so it stays.
GateErrorResult  # unused import

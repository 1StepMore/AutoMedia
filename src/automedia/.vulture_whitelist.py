# Vulture false-positive whitelist for AutoMedia.
# See: https://github.com/jendrikseitz/vulture#whitelists

# automedia/cli/commands/cron.py:43 — CLI option accepted but not yet used
timeout  # unused variable

# automedia/mcp/parallel.py:104 — signal handler signature requires `frame`
frame  # unused variable

# automedia/omni/orf_adapter.py:49-50 — stub method params for future implementation
original_md  # unused variable
skeleton_path  # unused variable

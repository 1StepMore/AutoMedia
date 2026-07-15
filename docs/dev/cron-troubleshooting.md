---
title: Cron Troubleshooting
description: Cron job debugging guide — troubleshooting AutoMedia scheduled tasks triggered by external crond or systemd timers.
---

# Cron Job Debugging Guide

AutoMedia fully externalizes scheduling responsibilities: it has no built-in
scheduler. System crond or systemd timers call `automedia cron run <job>`.

## Architecture

```mermaid
flowchart LR
    A[System crond] -->|"0 8 * * * automedia cron run hot-collection"| B[CLI]
    B --> C[automedia cron run]
    C --> D[Job handler]
    D --> E[Return code 0/non-zero]
```

Each cron job:

- Triggered by external crond on schedule
- Single execution, terminated by cron if it times out
- Execution results obtained via cron's MAILTO mechanism or system log
  (`/var/log/syslog`)
- No built-in persistence, relies on external cron logging

## Debugging Steps

### 1. Confirm Cron Service is Running

```bash
systemctl status cron    # Debian/Ubuntu
systemctl status crond   # CentOS/RHEL
```

### 2. Test the CLI Command Directly

```bash
# Run directly and observe output
automedia cron run pool-collect
automedia cron run pool-score
automedia cron run pool-prune
automedia cron run publish-check
```

### 3. Check Crontab Configuration

```bash
crontab -l
```

Expected entries example:

```cron
# AutoMedia daily scheduled tasks
0 8 * * * cd /var/automedia && automedia cron run hot-collection >> /var/log/automedia/cron.log 2>&1
5 8 * * * cd /var/automedia && automedia cron run semantic-audit >> /var/log/automedia/cron.log 2>&1
30 8 * * * cd /var/automedia && automedia cron run publish-check >> /var/log/automedia/cron.log 2>&1
30 9 * * * cd /var/automedia && automedia cron check-health >> /var/log/automedia/cron.log 2>&1
```

### 4. Check System Cron Logs

```bash
# Debian/Ubuntu
grep -i "automedia" /var/log/syslog

# CentOS/RHEL
grep -i "automedia" /var/log/cron
```

### 5. Check Application Logs

```bash
cat /var/log/automedia/cron.log
```

If the log directory does not exist, create it:

```bash
mkdir -p /var/log/automedia
```

### 6. Run Health Check

```bash
automedia cron check-health
```

Performs a 4-step check:

1. Python >= 3.11
2. ffmpeg available
3. `.automedia/` config directory exists
4. pool.db accessible

## Common Issues

### Job Did Not Execute on Time

- Confirm crond service is running: `systemctl status cron`
- Confirm the schedule expression in crontab is correct (note that cron uses
  the system timezone)
- Check `/var/log/syslog` for cron entries to see if the system attempted
  execution but failed
- Confirm the `cd` path in the command is correct — AutoMedia depends on the
  working directory

### Job Execution Timeout

- `automedia cron run` defaults to a 120 second timeout, adjustable via
  `--timeout`
- But the external cron timeout is independent, you need to check the cron
  configuration
- Add a `timeout` prefix to the command:
  `timeout 600 automedia cron run pool-collect`

### Grace Period Handling

The Hermes cron grace period mechanism no longer exists in the externalized
approach. You need to implement grace period semantics yourself:

```bash
# Wrapper script example: detect if the previous execution is still running
LOCKFILE=/tmp/automedia-cron-${JOB_NAME}.lock
if [ -f "$LOCKFILE" ] && [ -d /proc/$(cat $LOCKFILE) ]; then
    echo "Previous job still running, skipping"
    exit 0
fi
echo $$ > "$LOCKFILE"
trap 'rm -f "$LOCKFILE"' EXIT

automedia cron run "$JOB_NAME"
```

### Multi-Environment Consistency

The crontab syntax is consistent across environments. Cross-platform notes:

- macOS crontab path differs from Linux, requires `PATH=/usr/local/bin:$PATH`
- Cron service is not enabled by default in WSL, use `sudo service cron start`
- Docker containers typically use `supervisord` instead of crond

## Failure Recovery

```bash
# 1. Check cron service
systemctl is-active cron

# 2. View the last 20 cron log entries
grep "automedia" /var/log/syslog | tail -20

# 3. Manually execute the job to confirm
automedia cron run hot-collection
echo $?  # Confirm return code

# 4. Restore crontab (from backup)
crontab /path/to/backup/crontab.txt
```

## Recommended Crontab Template

```cron
# ┌───────────── minute (0-59)
# │ ┌───────────── hour (0-23)
# │ │ ┌───────────── day of month (1-31)
# │ │ │ ┌───────────── month (1-12)
# │ │ │ │ ┌───────────── day of week (0-7, 0=Sunday)
# │ │ │ │ │
# MAILTO="admin@example.com"
# PATH="/usr/local/bin:/usr/bin:/bin"
#
# AutoMedia daily scheduled tasks
0 8 * * * cd /var/automedia && automedia cron run pool-collect >> /var/log/automedia/cron.log 2>&1
5 8 * * * cd /var/automedia && automedia cron run pool-score >> /var/log/automedia/cron.log 2>&1
30 8 * * * cd /var/automedia && automedia cron run publish-check >> /var/log/automedia/cron.log 2>&1
30 9 * * * cd /var/automedia && automedia cron check-health >> /var/log/automedia/cron.log 2>&1
```

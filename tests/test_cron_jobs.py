"""
测试 automedia/cron/jobs.yaml — 内置定时任务配置。

验证项:
  1. YAML 文件可正常解析
  2. 包含且仅包含 4 个 job
  3. 每个 job 包含全部必要字段 (name, schedule, command, on_failure, timeout_s, description)
  4. 各 job 的 name 唯一
  5. 依赖关系 (depends_on) 指向的 job 必须存在
  6. 各 job 的顺序与预期一致
"""

from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
JOBS_YAML = PROJECT_ROOT / "automedia" / "cron" / "jobs.yaml"

EXPECTED_JOBS = ["hot-collection", "semantic-audit", "topic-push", "watchdog"]

REQUIRED_FIELDS = {"name", "schedule", "command", "on_failure", "timeout_s", "description"}

VALID_ON_FAILURE = {"stop", "skip", "retry"}


def _load_jobs():
    """Helper: load and return the jobs list from YAML."""
    assert JOBS_YAML.is_file(), f"YAML file not found: {JOBS_YAML}"
    with open(JOBS_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict) and "jobs" in data, "YAML root must contain 'jobs' key"
    jobs = data["jobs"]
    assert isinstance(jobs, list), "'jobs' must be a list"
    return jobs


# ===========================================================================
# Tests
# ===========================================================================


def test_yaml_is_parseable():
    """YAML 文件无语法错误, 可正常解析."""
    jobs = _load_jobs()
    assert len(jobs) > 0, "job list should not be empty"


def test_exactly_four_jobs():
    """包含且仅包含 4 个 job."""
    jobs = _load_jobs()
    assert len(jobs) == 4, f"expected 4 jobs, got {len(jobs)}"


def test_job_names_are_expected():
    """4 个 job 的 name 与预期完全一致且顺序正确."""
    jobs = _load_jobs()
    names = [j["name"] for j in jobs]
    assert names == EXPECTED_JOBS, f"expected {EXPECTED_JOBS}, got {names}"


def test_all_required_fields_present():
    """每个 job 都包含 name, schedule, command, on_failure, timeout_s, description."""
    jobs = _load_jobs()
    for job in jobs:
        missing = REQUIRED_FIELDS - set(job.keys())
        assert not missing, f"job '{job.get('name', '?')}' missing fields: {missing}"


def test_on_failure_valid():
    """on_failure 取值必须是 stop / skip / retry."""
    jobs = _load_jobs()
    for job in jobs:
        assert job["on_failure"] in VALID_ON_FAILURE, (
            f"job '{job['name']}' on_failure='{job['on_failure']}' "
            f"not in {VALID_ON_FAILURE}"
        )


def test_timeout_s_is_positive_int():
    """timeout_s 为正整数."""
    jobs = _load_jobs()
    for job in jobs:
        t = job["timeout_s"]
        assert isinstance(t, int) and t > 0, (
            f"job '{job['name']}' timeout_s={t!r} must be positive int"
        )


def test_depends_on_refer_to_existing_jobs():
    """depends_on 中引用的 job name 必须存在于 job 列表中."""
    jobs = _load_jobs()
    all_names = {j["name"] for j in jobs}
    for job in jobs:
        deps = job.get("depends_on")
        if not deps:
            continue
        if isinstance(deps, list):
            for dep in deps:
                assert dep in all_names, (
                    f"job '{job['name']}' depends on '{dep}' "
                    f"which does not exist in jobs list"
                )
        else:
            # depends_on 是单个字符串 (应为 None/~)
            assert dep is None, (
                f"job '{job['name']}' depends_on={deps!r} should be None or list"
            )


def test_depends_on_type():
    """depends_on 应为 None / ~ 或 list."""
    jobs = _load_jobs()
    for job in jobs:
        deps = job.get("depends_on")
        assert deps is None or isinstance(deps, list), (
            f"job '{job['name']}' depends_on={deps!r} must be None or a list"
        )


def test_schedule_is_valid_cron_like():
    """schedule 为 5 字段 cron 表达式."""
    jobs = _load_jobs()
    for job in jobs:
        parts = job["schedule"].split()
        assert len(parts) == 5, (
            f"job '{job['name']}' schedule='{job['schedule']}' "
            f"does not look like 5-field cron (got {len(parts)} parts)"
        )


def test_job_names_are_unique():
    """所有 job 的 name 必须唯一."""
    jobs = _load_jobs()
    names = [j["name"] for j in jobs]
    assert len(names) == len(set(names)), f"duplicate job names found: {names}"

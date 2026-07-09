"""RED tests for SOPRunner — execution handbook, daily tasks, progress report."""

from automedia.sop.runner import SOPRunner


class TestExecutionHandbook:
    def test_generates_handbook_with_brand_info(self):
        artifacts = []  # mock artifacts
        runner = SOPRunner(brand="TestBrand", artifacts=artifacts)
        handbook = runner.generate_execution_handbook()
        assert "TestBrand" in handbook
        assert len(handbook) > 100

    def test_handbook_includes_sections(self):
        runner = SOPRunner("TestBrand", [])
        h = runner.generate_execution_handbook()
        for section in [
            "Daily Tasks",
            "Weekly Tasks",
            "A/B Testing",
            "Review Template",
        ]:
            assert section in h

    def test_handbook_includes_ab_test_dimensions(self):
        runner = SOPRunner("TestBrand", [])
        h = runner.generate_execution_handbook()
        for dim in [
            "Title variants",
            "Cover image variants",
            "CTA variants",
            "Publish time variants",
        ]:
            assert dim in h


class TestDailyTasks:
    def test_daily_tasks_yaml_format(self):
        runner = SOPRunner("TestBrand", [])
        yaml_str = runner.generate_daily_tasks("2026-07-10")
        assert "date" in yaml_str
        assert "tasks" in yaml_str

    def test_daily_tasks_parses_as_valid_yaml(self):
        import yaml

        runner = SOPRunner("TestBrand", [])
        yaml_str = runner.generate_daily_tasks("2026-07-10")
        data = yaml.safe_load(yaml_str)
        assert isinstance(data, dict)
        assert data["date"] == "2026-07-10"
        assert isinstance(data["tasks"], list)
        assert len(data["tasks"]) > 0

    def test_daily_tasks_includes_brand(self):
        runner = SOPRunner("TestBrand", [])
        yaml_str = runner.generate_daily_tasks("2026-07-10")
        assert "TestBrand" in yaml_str


class TestProgressReport:
    def test_progress_report_has_kpi_section(self):
        runner = SOPRunner("TestBrand", [])
        report = runner.generate_progress_report()
        assert "KPI" in report or "kpi" in report.lower()

    def test_progress_report_includes_brand(self):
        runner = SOPRunner("TestBrand", [])
        report = runner.generate_progress_report()
        assert "TestBrand" in report

    def test_progress_report_has_recommendations(self):
        runner = SOPRunner("TestBrand", [])
        report = runner.generate_progress_report()
        assert "Recommendation" in report or "recommendation" in report.lower()

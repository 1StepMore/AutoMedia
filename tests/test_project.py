"""Tests for automedia.core.project — project init, slug, path safety."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from automedia.core.project import Project, _slugify, sanitize_path, slugify_topic

# ===================================================================
# _slugify
# ===================================================================


class TestSlugify:
    """Unit tests for :func:`_slugify`."""

    def test_basic_lowercase(self):
        assert _slugify("Hello World") == "hello-world"

    def test_leading_trailing_spaces(self):
        assert _slugify("  foo  ") == "foo"

    def test_underscores_become_hyphens(self):
        assert _slugify("foo_bar_baz") == "foo-bar-baz"

    def test_multiple_hyphens_collapsed(self):
        assert _slugify("foo---bar") == "foo-bar"

    def test_special_characters_removed(self):
        assert _slugify("hello!@#$%^&*()world") == "helloworld"

    def test_cjk_characters_stripped(self):
        # Chinese / Japanese / Korean characters are removed
        assert _slugify("AutoMedia 2024 项目启动") == "automedia-2024"

    def test_mixed_case(self):
        assert _slugify("UPPER lower MiXeD") == "upper-lower-mixed"

    def test_only_special_chars_returns_empty(self):
        assert _slugify("!!! @@@ ###") == ""

    def test_numbers_retained(self):
        assert _slugify("v2.0.1 release") == "v201-release"

    def test_already_clean(self):
        assert _slugify("hello-world") == "hello-world"

    def test_empty_string(self):
        assert _slugify("") == ""

    def test_only_whitespace(self):
        assert _slugify("   ") == ""


# ===================================================================
# slugify_topic — deterministic fallback for CJK / symbol / empty input
# ===================================================================


class TestSlugifyTopic:
    """Regression coverage for issue #228.

    ``_slugify`` still strips non-ASCII (its contract is unchanged), but the
    topic-level ``slugify_topic`` must never return an empty string: a pure
    CJK topic keeps its characters, and anything with no readable content
    falls back to a reproducible ``topic-<sha1>`` hash.
    """

    def test_chinese_topic_is_non_empty_and_readable(self):
        slug = slugify_topic("小团队内容排期的实用做法")
        assert slug
        assert slug == "小团队内容排期的实用做法"

    def test_mixed_chinese_english_uses_ascii_part(self):
        # Unchanged behaviour: the ASCII portion is the slug.
        assert slugify_topic("AutoMedia 2024 项目启动") == "automedia-2024"

    def test_symbols_fall_back_to_hash(self):
        text = "!!! @@@ ###"
        slug = slugify_topic(text)
        assert slug == f"topic-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:8]}"

    def test_empty_string_falls_back_to_hash(self):
        slug = slugify_topic("")
        assert slug == f"topic-{hashlib.sha1(b'').hexdigest()[:8]}"

    def test_fallback_is_deterministic(self):
        """Same input must always yield the same slug (reproducible renders)."""
        assert slugify_topic("!!! @@@ ###") == slugify_topic("!!! @@@ ###")
        cjk = "小团队内容排期的实用做法"
        assert slugify_topic(cjk) == slugify_topic(cjk)


# ===================================================================
# sanitize_path
# ===================================================================


class TestSanitizePath:
    """Unit tests for :func:`sanitize_path`."""

    def test_normal_path(self):
        result = sanitize_path("/tmp/foo/bar")
        assert result == os.path.realpath("/tmp/foo/bar")

    def test_relative_path(self):
        result = sanitize_path("relative/path")
        assert "relative/path" in result

    def test_double_dot_rejected(self):
        with pytest.raises(ValueError, match=r"\.\."):
            sanitize_path("../etc/passwd")

    def test_double_dot_mid_path_rejected(self):
        with pytest.raises(ValueError, match=r"\.\."):
            sanitize_path("foo/../../bar")

    def test_tilde_rejected(self):
        with pytest.raises(ValueError, match=r"~"):
            sanitize_path("~/config")

    def test_tilde_mid_path_rejected(self):
        with pytest.raises(ValueError, match=r"~"):
            sanitize_path("foo/~bar/baz")

    def test_double_slash_rejected(self):
        with pytest.raises(ValueError, match=r"//"):
            sanitize_path("foo//bar")

    def test_double_slash_prefix_rejected(self):
        with pytest.raises(ValueError, match=r"//"):
            sanitize_path("//etc/hosts")

    def test_empty_path_rejected(self):
        with pytest.raises(ValueError, match="empty"):
            sanitize_path("")

    def test_unicode_path_allowed(self):
        # Unicode characters in path are fine; only .. ~ // are blocked
        result = sanitize_path("/tmp/贯维/项目")
        assert result == os.path.realpath("/tmp/贯维/项目")


# ===================================================================
# Project.init — directory creation & metadata
# ===================================================================


class TestProjectInit:
    """Integration tests for :meth:`Project.init`."""

    def test_creates_directory_structure(self, tmp_path):
        """All expected subdirectories are created under the project root."""
        project = Project.init("test-topic", "acme", base_dir=str(tmp_path))

        root = Path(project.project_dir)
        assert root.is_dir()

        expected = [
            "01_content/drafts",
            "02_images/cover",
            "03_video",
            "04_subtitle",
            "05_review",
            "06_publish",
        ]
        for sub in expected:
            assert (root / sub).is_dir(), f"Missing subdirectory: {sub}"

    def test_writes_00_project_info_json(self, tmp_path):
        """00_project_info.json is created with correct fields."""
        project = Project.init("test-info", "acme", tenant_id="t1", base_dir=str(tmp_path))

        info_path = Path(project.project_dir) / "00_project_info.json"
        assert info_path.is_file()

        with open(info_path, encoding="utf-8") as fh:
            data = json.load(fh)

        assert data["project_id"] == project.project_id
        assert data["topic"] == "test-info"
        assert data["brand"] == "acme"
        assert data["tenant_id"] == "t1"
        assert "created_at" in data

    def test_returns_project_dataclass(self, tmp_path):
        """Returned object is a Project with correct attributes."""
        project = Project.init("my-topic", "mybrand", base_dir=str(tmp_path))

        assert isinstance(project, Project)
        assert project.topic == "my-topic"
        assert project.brand == "mybrand"
        assert project.tenant_id == "default"
        assert len(project.project_id) == 12  # uuid4().hex[:12]
        assert os.path.isdir(project.project_dir)
        assert project.created_at  # non-empty ISO string

    def test_tenant_id_default(self, tmp_path):
        """tenant_id defaults to 'default'."""
        project = Project.init("default-tenant", "acme", base_dir=str(tmp_path))
        assert project.tenant_id == "default"

    def test_custom_tenant_id(self, tmp_path):
        """tenant_id can be overridden."""
        project = Project.init(
            "custom-tenant", "acme", tenant_id="workspace-42", base_dir=str(tmp_path)
        )
        assert project.tenant_id == "workspace-42"

    def test_slug_used_as_dirname(self, tmp_path):
        """Directory name is {YYYYMMDD}_{slug}."""
        project = Project.init("Hello World", "acme", base_dir=str(tmp_path))
        dirname = os.path.basename(project.project_dir)
        # dirname e.g. "20260707_hello-world"
        parts = dirname.split("_", 1)
        assert len(parts) == 2
        assert parts[0].isdigit() and len(parts[0]) == 8  # date
        assert parts[1] == "hello-world"

    def test_cjk_topic_slugified(self, tmp_path):
        """CJK characters are stripped from the directory name."""
        project = Project.init("AutoMedia 项目启动 2024", "acme", base_dir=str(tmp_path))
        dirname = os.path.basename(project.project_dir)
        assert "automedia-2024" in dirname
        for ch in "项目启动":
            assert ch not in dirname

    def test_empty_slug_falls_back(self, tmp_path):
        """A topic that produces an empty ASCII slug falls back, never raises."""
        project = Project.init("!!! @@ @@@", "acme", base_dir=str(tmp_path))
        dirname = os.path.basename(project.project_dir)
        slug = dirname.split("_", 1)[1]
        assert slug == f"topic-{hashlib.sha1(b'!!! @@ @@@').hexdigest()[:8]}"

    def test_cjk_only_topic_keeps_readable_slug(self, tmp_path):
        """Bug #228: pure-CJK topic no longer hard-fails; keeps a readable slug."""
        project = Project.init("壹目贯维投资策略分析", "acme", base_dir=str(tmp_path))
        dirname = os.path.basename(project.project_dir)
        assert "壹目贯维投资策略分析" in dirname

    def test_invalid_brand_path_rejected(self):
        """A brand containing path traversal is rejected."""
        with pytest.raises(ValueError, match=r"\.\."):
            Project.init("topic", "../malicious")

    def test_invalid_base_dir_rejected(self):
        """A base_dir containing path traversal is rejected."""
        with pytest.raises(ValueError, match=r"\.\."):
            Project.init("topic", "acme", base_dir="/tmp/../etc")

    def test_base_dir_default_is_cwd(self, monkeypatch):
        """When base_dir is None, cwd is used."""
        monkeypatch.chdir("/tmp")
        project = Project.init("cwd-test", "acme")
        assert project.project_dir.startswith("/tmp/")

    def test_project_dir_is_absolute(self, tmp_path):
        """project_dir is an absolute path."""
        project = Project.init("abs-path", "acme", base_dir=str(tmp_path))
        assert os.path.isabs(project.project_dir)

    def test_id_is_unique_per_call(self, tmp_path):
        """Each init() call generates a different project_id."""
        p1 = Project.init("topic", "acme", base_dir=str(tmp_path))
        p2 = Project.init("topic", "acme", base_dir=str(tmp_path))
        assert p1.project_id != p2.project_id

    def test_topic_slug_original_preserved(self, tmp_path):
        """The original topic_slug string is stored, not the slugified version."""
        project = Project.init("Hello World!!", "acme", base_dir=str(tmp_path))
        assert project.topic == "Hello World!!"

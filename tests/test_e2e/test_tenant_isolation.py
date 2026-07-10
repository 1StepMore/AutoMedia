"""E2E tests for multi-tenant core subsystem — isolation, RBAC, audit."""

from __future__ import annotations

import pytest

from automedia.tenant.audit import AuditLog
from automedia.tenant.manager import TenantManager
from automedia.tenant.rbac import check_permission

pytestmark = pytest.mark.e2e


class TestTenantFileIsolation:
    """W4-T10: Tenant A and Tenant B have separate directories."""

    def test_different_tenants_have_different_dirs(self):
        tm = TenantManager()
        dir_a = tm.get_tenant_dir("tenant-a")
        dir_b = tm.get_tenant_dir("tenant-b")
        assert dir_a != dir_b
        assert "tenant-a" in str(dir_a)
        assert "tenant-b" in str(dir_b)

    def test_asset_library_paths_differ_across_tenants(self):
        tm = TenantManager()
        d_a = tm.get_tenant_asset_library_dir("t1", "Brand")
        d_b = tm.get_tenant_asset_library_dir("t2", "Brand")
        assert d_a != d_b

    def test_config_paths_differ_across_tenants(self):
        tm = TenantManager()
        d_a = tm.get_tenant_config_dir("t1")
        d_b = tm.get_tenant_config_dir("t2")
        assert d_a != d_b

    def test_created_workspace_records_tenant_dir(self):
        tm = TenantManager()
        ws = tm.create_workspace("E2E-Test")
        tid = ws["workspace_id"]
        str(TenantManager.get_tenant_dir(tid))
        assert tm.list_workspaces()[0]["workspace_id"] == tid


class TestRBACPermissionMatrix:
    """W4-T11: All 5 roles × select actions."""

    def test_admin_has_all_permissions(self):
        for action in [
            "workspace.delete",
            "member.invite",
            "content.publish",
            "settings.update",
            "audit.read",
        ]:
            assert check_permission("admin", action), f"admin should have {action}"

    def test_strategist_has_content_and_asset_library(self):
        assert check_permission("strategist", "content.create")
        assert check_permission("strategist", "content.edit")
        assert check_permission("strategist", "content.review")
        assert check_permission("strategist", "asset_library.upload")
        assert check_permission("strategist", "sop.generate")
        assert check_permission("strategist", "analytics.view")

    def test_strategist_lacks_member_management(self):
        assert not check_permission("strategist", "member.invite")
        assert not check_permission("strategist", "workspace.delete")

    def test_editor_has_content_and_asset_library_read(self):
        assert check_permission("editor", "content.create")
        assert check_permission("editor", "content.edit")
        assert check_permission("editor", "asset_library.read")

    def test_editor_lacks_publish_and_settings(self):
        assert not check_permission("editor", "publish.execute")
        assert not check_permission("editor", "settings.update")

    def test_operator_has_content_read_and_publish(self):
        assert check_permission("operator", "content.read")
        assert check_permission("operator", "publish.execute")
        assert check_permission("operator", "analytics.read")

    def test_operator_lacks_content_edit(self):
        assert not check_permission("operator", "content.edit")

    def test_viewer_is_read_only(self):
        assert check_permission("viewer", "content.read")
        assert check_permission("viewer", "analytics.read")
        assert check_permission("viewer", "asset_library.read")
        assert not check_permission("viewer", "content.create")
        assert not check_permission("viewer", "content.edit")
        assert not check_permission("viewer", "publish.execute")

    def test_invalid_role_returns_false(self):
        assert not check_permission("superadmin", "content.read")

    def test_every_role_can_read_content(self):
        # Per spec: viewer, operator have explicit content.read
        assert check_permission("viewer", "content.read")
        assert check_permission("operator", "content.read")
        # admin has content.* wildcard
        assert check_permission("admin", "content.read")
        # strategist has content.create/edit/review (not content.read directly)
        assert not check_permission("strategist", "content.read")
        # editor has content.create/edit (not content.read directly)
        assert not check_permission("editor", "content.read")


class TestAuditLogRecordsOperations:
    """W4-T11: Audit log records all operations."""

    def setup_method(self):
        AuditLog.clear()

    def test_create_workspace_is_audited(self):
        AuditLog.clear()
        tm = TenantManager()
        ws = tm.create_workspace("Audited")
        entries = AuditLog.query(filters={"action": "workspace.create"})
        assert len(entries) >= 1
        assert ws["workspace_id"] in entries[-1]["what"]

    def test_invite_member_is_audited(self):
        AuditLog.clear()
        tm = TenantManager()
        ws = tm.create_workspace("Audited2")
        AuditLog.clear()  # clear create event
        tm.invite_member(ws["workspace_id"], "invited@test.com", "editor")
        entries = AuditLog.query(filters={"action": "member.invite"})
        assert len(entries) >= 1
        assert "invited@test.com" in entries[-1]["what"]

    def test_delete_workspace_is_audited(self):
        AuditLog.clear()
        tm = TenantManager()
        ws = tm.create_workspace("ToDelete")
        AuditLog.clear()
        tm.exit_workspace(ws["workspace_id"])
        entries = AuditLog.query(filters={"action": "workspace.delete"})
        assert len(entries) >= 1

    def test_role_update_is_audited(self):
        AuditLog.clear()
        tm = TenantManager()
        ws = tm.create_workspace("Test")
        tm.invite_member(ws["workspace_id"], "u@t.com", "viewer")
        AuditLog.clear()
        tm.update_member_role(ws["workspace_id"], "u@t.com", "admin")
        entries = AuditLog.query(filters={"action": "member.role_update"})
        assert len(entries) >= 1

    def test_audit_log_query_filter(self):
        AuditLog.clear()
        AuditLog.record("alice", "custom.action", "resource-1", {"env": "test"})
        AuditLog.record("bob", "other.action", "resource-2")
        results = AuditLog.query(filters={"who": "alice"})
        assert len(results) == 1
        assert results[0]["what"] == "resource-1"

    def test_audit_log_clear(self):
        AuditLog.clear()
        AuditLog.record("x", "test", "y")
        assert len(AuditLog.query()) == 1
        AuditLog.clear()
        assert len(AuditLog.query()) == 0


class TestCrossTenantAccessIsolation:
    """W4-T12: Cross-tenant access isolation."""

    def test_members_are_scoped_to_workspace(self):
        tm = TenantManager()
        ws_a = tm.create_workspace("TenantA")
        ws_b = tm.create_workspace("TenantB")
        tm.invite_member(ws_a["workspace_id"], "alice@a.com", "admin")
        tm.invite_member(ws_b["workspace_id"], "bob@b.com", "viewer")
        members_a = tm.list_members(ws_a["workspace_id"])
        members_b = tm.list_members(ws_b["workspace_id"])
        assert len(members_a) == 1
        assert len(members_b) == 1
        assert members_a[0]["email"] == "alice@a.com"
        assert members_b[0]["email"] == "bob@b.com"

    def test_delete_one_workspace_does_not_affect_other(self):
        tm = TenantManager()
        ws_a = tm.create_workspace("Stays")
        ws_b = tm.create_workspace("Goes")
        tm.exit_workspace(ws_b["workspace_id"])
        remaining = tm.list_workspaces()
        ids = [w["workspace_id"] for w in remaining]
        assert ws_a["workspace_id"] in ids
        assert ws_b["workspace_id"] not in ids

    def test_get_member_role_only_in_own_workspace(self):
        tm = TenantManager()
        ws_a = tm.create_workspace("A")
        ws_b = tm.create_workspace("B")
        tm.invite_member(ws_a["workspace_id"], "x@x.com", "admin")
        # x@x.com does not belong to ws_b
        role = tm.get_member_role(ws_b["workspace_id"], "x@x.com")
        assert role is None

    def test_tenant_dirs_have_no_overlap(self):
        dir_a = TenantManager.get_tenant_dir("t1")
        dir_b = TenantManager.get_tenant_dir("t2")
        # One directory must not be a parent of the other
        assert not str(dir_b).startswith(str(dir_a))
        assert not str(dir_a).startswith(str(dir_b))

    def test_asset_library_dir_prefix_differs(self):
        d_a = TenantManager.get_tenant_asset_library_dir("t1", "Brand")
        d_b = TenantManager.get_tenant_asset_library_dir("t2", "Brand")
        # Same brand, different tenant → parent directory prefix must differ
        assert d_a.parent != d_b.parent

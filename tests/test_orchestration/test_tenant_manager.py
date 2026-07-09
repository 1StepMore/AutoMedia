"""RED tests for TenantManager — workspace lifecycle & member management."""

from __future__ import annotations

from automedia.tenant.manager import TenantManager


class TestTenantCreation:
    def test_create_workspace_returns_info(self):
        tm = TenantManager()
        ws = tm.create_workspace("TestWorkspace")
        assert "workspace_id" in ws
        assert ws["name"] == "TestWorkspace"

    def test_create_two_workspaces_different_ids(self):
        tm = TenantManager()
        ws1 = tm.create_workspace("A")
        ws2 = tm.create_workspace("B")
        assert ws1["workspace_id"] != ws2["workspace_id"]

    def test_list_workspaces_returns_all(self):
        tm = TenantManager()
        tm.create_workspace("X")
        tm.create_workspace("Y")
        all_ws = tm.list_workspaces()
        assert len(all_ws) == 2


class TestMemberManagement:
    def test_invite_member(self):
        tm = TenantManager()
        ws = tm.create_workspace("Test")
        result = tm.invite_member(ws["workspace_id"], "test@example.com", "editor")
        assert result is True

    def test_list_members(self):
        tm = TenantManager()
        ws = tm.create_workspace("Test")
        tm.invite_member(ws["workspace_id"], "a@b.com", "admin")
        members = tm.list_members(ws["workspace_id"])
        assert len(members) == 1
        assert members[0]["email"] == "a@b.com"

    def test_invite_invalid_role_returns_false(self):
        tm = TenantManager()
        ws = tm.create_workspace("Test")
        result = tm.invite_member(ws["workspace_id"], "x@y.com", "superadmin")
        assert result is False

    def test_invite_nonexistent_workspace_returns_false(self):
        tm = TenantManager()
        result = tm.invite_member("nonexistent", "a@b.com", "admin")
        assert result is False

    def test_duplicate_invite_returns_false(self):
        tm = TenantManager()
        ws = tm.create_workspace("Test")
        tm.invite_member(ws["workspace_id"], "a@b.com", "admin")
        result = tm.invite_member(ws["workspace_id"], "a@b.com", "admin")
        assert result is False


class TestExitWorkspace:
    def test_exit_existing_workspace(self):
        tm = TenantManager()
        ws = tm.create_workspace("ToDelete")
        result = tm.exit_workspace(ws["workspace_id"])
        assert result is True
        assert tm.list_members(ws["workspace_id"]) == []

    def test_exit_nonexistent_workspace_returns_false(self):
        tm = TenantManager()
        result = tm.exit_workspace("nonexistent")
        assert result is False


class TestRoleManagement:
    def test_get_member_role(self):
        tm = TenantManager()
        ws = tm.create_workspace("Test")
        tm.invite_member(ws["workspace_id"], "a@b.com", "strategist")
        role = tm.get_member_role(ws["workspace_id"], "a@b.com")
        assert role == "strategist"

    def test_get_member_role_nonexistent(self):
        tm = TenantManager()
        ws = tm.create_workspace("Test")
        role = tm.get_member_role(ws["workspace_id"], "nobody@b.com")
        assert role is None

    def test_update_member_role(self):
        tm = TenantManager()
        ws = tm.create_workspace("Test")
        tm.invite_member(ws["workspace_id"], "a@b.com", "viewer")
        ok = tm.update_member_role(ws["workspace_id"], "a@b.com", "admin")
        assert ok is True
        assert tm.get_member_role(ws["workspace_id"], "a@b.com") == "admin"

    def test_remove_member(self):
        tm = TenantManager()
        ws = tm.create_workspace("Test")
        tm.invite_member(ws["workspace_id"], "a@b.com", "editor")
        ok = tm.remove_member(ws["workspace_id"], "a@b.com")
        assert ok is True
        assert tm.list_members(ws["workspace_id"]) == []


class TestDataIsolation:
    def test_different_tenants_have_different_dirs(self):
        tm = TenantManager()
        dir1 = tm.get_tenant_dir("tenant_a")
        dir2 = tm.get_tenant_dir("tenant_b")
        assert dir1 != dir2

    def test_tenant_dir_structure(self):
        tm = TenantManager()
        tid = "test-tenant-42"
        base = tm.get_tenant_dir(tid)
        assert str(tid) in str(base)
        assert base.name == tid

    def test_asset_library_dir_contains_brand(self):
        tm = TenantManager()
        d = tm.get_tenant_asset_library_dir("tid", "BrandX")
        assert "asset-library" in str(d)
        assert "BrandX" in str(d)

    def test_config_dir_is_separate(self):
        tm = TenantManager()
        d = tm.get_tenant_config_dir("tid")
        assert d.name == "config"

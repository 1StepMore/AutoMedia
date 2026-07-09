# Open-Core Model

AutoMedia follows an **open-core** licensing model: the core automation engine
is free and open-source, while advanced enterprise features require a commercial
license.

---

## Community Edition (Open Source)

The Community Edition is available under the license in `LICENSE` and includes:

| Feature | Available |
|---------|-----------|
| Production Pipeline (`pipeline.run_full_pipeline`) | Yes |
| All 14+ Production Gates | Yes |
| 4-track media production (text/image/video/audio) | Yes |
| CLI and MCP interface | Yes |
| Decision Layer (Diagnostic, Build, Scale, Strategy) | Yes |
| Asset Library (SQLite + Chroma) | Yes |
| HITL Framework (2 presets) | Yes |
| SOP Runner (handbook generation) | Yes |
| Single-brand workspace | Yes |
| Omni Adapter integration | Yes |

## Commercial Edition

Requires a valid license key. Adds:

| Feature | Description |
|---------|-------------|
| **Multi-tenant** | Isolated workspaces per tenant with `tenant_id` enforcement |
| **RBAC** | Role-based access control (admin, strategist, editor, operator, viewer) |
| **Audit Log** | Full operation audit trail (create, update, delete, approve, reject) |
| **SAML SSO** | Single sign-on via SAML 2.0 |
| **Web UI** | Drag-and-drop node configuration, workspace management |

---

## License Check Mechanism

License verification uses RSA-signed keys verified against a public key stored
at `~/.automedia/license/public.pem`. The flow:

```
LicenseManager.check()
    │
    ├─ AUTOMEDIA_LICENSE_KEY env var → verify signature → status
    ├─ ~/.automedia/license/license.key → verify signature → status
    └─ No key → OS_COMMUNITY
```

### Statuses

| Status | Meaning |
|--------|---------|
| `os_community` | Running open-source edition. Commercial features disabled. |
| `commercial` | Valid commercial license. All features available. |
| `expired` | License key expired. Downgraded to community features. |

### Feature Gating

```python
from automedia.license import LicenseManager

# Check license status
status = LicenseManager.check()

# Check specific feature availability
if LicenseManager.is_commercial_feature_available("tenant"):
    enable_multi_tenant()
```

Commercial features are listed in `COMMERCIAL_FEATURES`:

```python
COMMERCIAL_FEATURES = ["tenant", "rbac", "audit", "saml", "web_ui"]
```

---

## Install & Configure License

### Community Edition (No License)

```bash
pip install automedia
# All community features available immediately
```

### Commercial License

```bash
# Method 1: Environment variable
export AUTOMEDIA_LICENSE_KEY="<base64-encoded-license-key>"

# Method 2: License file
mkdir -p ~/.automedia/license
echo "<base64-encoded-license-key>" > ~/.automedia/license/license.key

# Verify
automedia license check
# => License status: commercial
```

---

## CLI Commands

```bash
# Check current license status
automedia license check

# List all commercial features and their availability
automedia license features
```

Example output:

```
$ automedia license check
License status: os_community
You are running the open-source community edition.
Commercial features: not available.
```

---

## Key Management

License keys are RSA-SHA256 signed. The key pair is auto-generated on first use:

```
~/.automedia/license/
├── private.pem     # Private key (keep secret)
├── public.pem      # Public key (used for verification)
└── license.key     # Your license key
```

To generate a license key (admin tool):

```python
from automedia.license.verifier import LicenseGenerator

key = LicenseGenerator.generate(tenant_id="customer-001", days_valid=365)
print(key)  # base64-encoded license string
```

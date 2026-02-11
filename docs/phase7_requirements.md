# Phase 7: Enterprise Features and Compliance -- Component Specification

> **Status**: PLANNED  
> **Timeline**: 12+ weeks (ongoing)  
> **Impact**: Revenue enabler (unlocks $100k+ enterprise contracts)  
> **Target**: Regulated industries (healthcare, finance, government)  

---

## 1. Objective

Enable enterprise deployments with role-based governance, compliance certifications (HIPAA, SOC 2, GDPR), multi-tenancy, audit trails, and white-label support.  This phase transforms Asahi from a developer tool into an enterprise-grade platform.

---

## 2. Component 1: GovernanceEngine

### 2.1 Purpose

Enforce organization-level policies on model usage, cost budgets, and access control.

### 2.2 File

`src/phase7/governance.py`

### 2.3 Public Interface

```python
class Role(BaseModel):
    name: str                    # "admin", "developer", "viewer", "billing"
    permissions: List[str]       # ["infer", "view_metrics", "manage_models", "manage_users", ...]

class OrganizationPolicy(BaseModel):
    org_id: str
    allowed_models: List[str]    # whitelist; empty = all allowed
    blocked_models: List[str]    # blacklist; takes precedence over allowed
    max_cost_per_day: Optional[float]
    max_cost_per_request: Optional[float]
    max_requests_per_day: Optional[int]
    default_quality_threshold: float
    default_latency_budget_ms: int
    require_audit_log: bool
    data_residency: Optional[str]  # "us", "eu", "ap"

class GovernanceEngine:
    def __init__(self, config: GovernanceConfig) -> None: ...
    
    def check_permission(
        self,
        user_id: str,
        org_id: str,
        action: str
    ) -> bool: ...
    
    def enforce_policy(
        self,
        request: InferenceRequest,
        org_policy: OrganizationPolicy
    ) -> Tuple[bool, Optional[str]]: ...
    # Returns: (allowed, rejection_reason)
    
    def check_budget(
        self,
        org_id: str,
        estimated_cost: float
    ) -> Tuple[bool, Optional[str]]: ...
    
    def get_user_role(self, user_id: str, org_id: str) -> Role: ...
    def assign_role(self, user_id: str, org_id: str, role_name: str) -> None: ...
    def list_org_users(self, org_id: str) -> List[Dict[str, Any]]: ...
    
    def create_policy(self, policy: OrganizationPolicy) -> None: ...
    def update_policy(self, org_id: str, updates: Dict[str, Any]) -> None: ...
    def get_policy(self, org_id: str) -> OrganizationPolicy: ...
```

### 2.4 RBAC Permissions Matrix

| Permission | Admin | Developer | Viewer | Billing |
|-----------|-------|-----------|--------|---------|
| `infer` | yes | yes | no | no |
| `view_metrics` | yes | yes | yes | yes |
| `view_cost` | yes | yes | no | yes |
| `manage_models` | yes | no | no | no |
| `manage_users` | yes | no | no | no |
| `manage_policy` | yes | no | no | no |
| `view_audit_log` | yes | no | no | yes |
| `manage_billing` | yes | no | no | yes |

### 2.5 Policy Enforcement Flow

```
1. Check user has "infer" permission for org
2. Check model is not in org's blocked_models list
3. Check model is in allowed_models (if list is non-empty)
4. Check estimated cost <= max_cost_per_request
5. Check daily spend + estimated cost <= max_cost_per_day
6. Check daily request count < max_requests_per_day
7. If all pass: allow request
8. If any fail: reject with specific reason
```

### 2.6 Error Handling

| Scenario | HTTP Status | Response |
|----------|-------------|----------|
| Insufficient permissions | 403 | `{"error": "forbidden", "required_permission": "infer"}` |
| Budget exceeded | 429 | `{"error": "budget_exceeded", "daily_limit": 100, "current_spend": 98.5}` |
| Model blocked | 403 | `{"error": "model_blocked", "model": "gpt-4", "org_policy": "cost_control"}` |
| Org not found | 404 | `{"error": "organization_not_found"}` |

### 2.7 Testing Requirements

- 15+ tests: each permission check, policy enforcement rules, budget tracking, role assignment, edge cases (empty allowlist = all allowed).

---

## 3. Component 2: AuditLogger

### 3.1 Purpose

Immutable, tamper-evident audit trail of all actions taken through the platform.  Required for HIPAA, SOC 2, and GDPR compliance.

### 3.2 File

`src/phase7/audit_logger.py`

### 3.3 Public Interface

```python
class AuditEntry(BaseModel):
    entry_id: str              # uuid
    timestamp: datetime
    org_id: str
    user_id: str
    action: str                # "inference", "model_change", "user_add", "policy_update", ...
    resource: str              # what was acted upon
    details: Dict[str, Any]    # action-specific data
    ip_address: Optional[str]
    user_agent: Optional[str]
    result: Literal["success", "denied", "error"]
    data_classification: Literal["public", "internal", "confidential", "restricted"]

class AuditLogger:
    def __init__(self, config: AuditConfig) -> None: ...
    
    def log(self, entry: AuditEntry) -> None: ...
    
    def query(
        self,
        org_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        action: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100
    ) -> List[AuditEntry]: ...
    
    def export(
        self,
        org_id: str,
        format: Literal["json", "csv"] = "json"
    ) -> bytes: ...
    
    def verify_integrity(self, org_id: str) -> bool: ...
    # Verify no entries have been tampered with (hash chain)
```

### 3.4 Integrity Mechanism

- Each entry includes `prev_hash = sha256(previous_entry)`.
- Chain can be verified by recomputing hashes from the first entry.
- Any tampering breaks the chain.

### 3.5 Data Classification Rules

| Action | Classification |
|--------|---------------|
| inference (with prompt) | restricted (if HIPAA) or confidential |
| inference (without prompt) | internal |
| model change | internal |
| user management | confidential |
| policy change | confidential |
| metrics viewing | public |

### 3.6 Testing Requirements

- 10+ tests: log, query by filters, export formats, integrity verification, chain break detection.

---

## 4. Component 3: ComplianceManager

### 4.1 Purpose

Enforce compliance requirements based on the organization's regulatory profile (HIPAA, SOC 2, GDPR).

### 4.2 File

`src/phase7/compliance.py`

### 4.3 Public Interface

```python
class ComplianceProfile(BaseModel):
    org_id: str
    frameworks: List[Literal["hipaa", "soc2", "gdpr", "pci_dss", "ccpa"]]
    data_residency: Optional[str]
    encryption_required: bool
    prompt_storage_allowed: bool
    retention_days: int
    pii_detection_enabled: bool

class ComplianceManager:
    def __init__(self, config: ComplianceConfig) -> None: ...
    
    def check_request(
        self,
        request: InferenceRequest,
        profile: ComplianceProfile
    ) -> Tuple[bool, List[str]]: ...
    # Returns: (compliant, list_of_violations)
    
    def redact_pii(self, text: str) -> Tuple[str, List[str]]: ...
    # Returns: (redacted_text, pii_types_found)
    
    def check_data_residency(
        self,
        model: str,
        required_region: str
    ) -> bool: ...
    
    def enforce_retention(self, org_id: str) -> int: ...
    # Delete data older than retention_days; return count deleted
    
    def generate_compliance_report(
        self,
        org_id: str,
        framework: str
    ) -> Dict[str, Any]: ...
```

### 4.4 Framework Requirements

**HIPAA**:
- Encrypt all data at rest and in transit (TLS 1.3+)
- PII detection and redaction before caching
- Audit logging mandatory
- BAA (Business Associate Agreement) tracking
- Prompt/response storage prohibited unless explicitly consented

**SOC 2 Type II**:
- 99.9% uptime SLA
- Incident response procedures
- Regular security assessments logged
- Access control audit trail

**GDPR**:
- Data subject access requests (DSAR)
- Right to deletion
- Data portability (export in machine-readable format)
- Privacy impact assessment
- Consent tracking

### 4.5 PII Detection

| PII Type | Pattern | Redaction |
|----------|---------|-----------|
| Email | `[\w.]+@[\w.]+` | `[EMAIL_REDACTED]` |
| Phone | `\+?[\d\s-()]{10,}` | `[PHONE_REDACTED]` |
| SSN | `\d{3}-\d{2}-\d{4}` | `[SSN_REDACTED]` |
| Credit card | `\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}` | `[CC_REDACTED]` |
| IP address | `\d{1,3}(\.\d{1,3}){3}` | `[IP_REDACTED]` |

Use regex for MVP; upgrade to ML-based NER in future.

### 4.6 Testing Requirements

- 12+ tests: each framework check, PII detection for each type, data residency validation, retention enforcement, compliance report generation.

---

## 5. Component 4: EncryptionManager

### 5.1 Purpose

Handle encryption at rest for cached data and sensitive fields.

### 5.2 File

`src/phase7/encryption.py`

### 5.3 Public Interface

```python
class EncryptionManager:
    def __init__(self, key_env: str = "ASAHI_ENCRYPTION_KEY") -> None: ...
    
    def encrypt(self, plaintext: str) -> str: ...
    def decrypt(self, ciphertext: str) -> str: ...
    def rotate_key(self, new_key_env: str) -> None: ...
    def hash_for_audit(self, text: str) -> str: ...  # one-way hash for audit logs
```

### 5.4 Implementation

- Use AES-256-GCM for symmetric encryption.
- Key derived from env var using PBKDF2.
- Each encrypted value includes a random nonce.
- `hash_for_audit` uses SHA-256; irreversible.

### 5.5 Testing Requirements

- 8+ tests: encrypt/decrypt roundtrip, different keys produce different ciphertext, key rotation, tamper detection.

---

## 6. Component 5: MultiTenancyManager

### 6.1 Purpose

Isolate data and operations between organizations.  Ensure one tenant cannot access another's data.

### 6.2 File

`src/phase7/multi_tenancy.py`

### 6.3 Public Interface

```python
class Tenant(BaseModel):
    org_id: str
    name: str
    plan: Literal["starter", "professional", "enterprise"]
    created_at: datetime
    settings: Dict[str, Any]

class MultiTenancyManager:
    def __init__(self) -> None: ...
    
    def create_tenant(self, tenant: Tenant) -> None: ...
    def get_tenant(self, org_id: str) -> Tenant: ...
    def validate_access(self, org_id: str, resource_org_id: str) -> bool: ...
    def get_tenant_cache_namespace(self, org_id: str) -> str: ...
    def get_tenant_metrics(self, org_id: str) -> Dict[str, Any]: ...
```

### 6.4 Isolation Strategy

- Cache keys prefixed with `org_id`: `{org_id}:{cache_key}`
- Vector DB namespaces per tenant: `{org_id}` namespace in Pinecone
- Audit logs scoped by `org_id`
- Metrics labelled with `org_id`

### 6.5 Testing Requirements

- 8+ tests: tenant creation, cross-tenant access denied, namespace isolation, metrics scoping.

---

## 7. Component 6: AuthenticationMiddleware

### 7.1 Purpose

Authenticate API requests and extract identity for governance checks.

### 7.2 File

`src/phase7/auth.py`

### 7.3 Public Interface

```python
class AuthResult(BaseModel):
    authenticated: bool
    user_id: Optional[str]
    org_id: Optional[str]
    plan: Optional[str]
    scopes: List[str]

class AuthMiddleware:
    def __init__(self, config: AuthConfig) -> None: ...
    
    def authenticate(self, request: Request) -> AuthResult: ...
    def generate_api_key(self, user_id: str, org_id: str, scopes: List[str]) -> str: ...
    def revoke_api_key(self, key_prefix: str) -> bool: ...
    def validate_api_key(self, key: str) -> AuthResult: ...
```

### 7.4 Authentication Methods

| Method | Phase | Description |
|--------|-------|-------------|
| API Key (header) | 7.0 | `Authorization: Bearer ask_...` |
| OAuth2 / OIDC | 7.1 | SSO integration |
| SAML | 7.1 | Enterprise SSO |

### 7.5 API Key Format

```
ask_{org_prefix}_{random_32_chars}

Example: ask_acme_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
```

- Stored as bcrypt hash in database.
- Key prefix (first 8 chars) used for identification without exposing full key.
- Expiration configurable per key (default 90 days).

### 7.6 Testing Requirements

- 10+ tests: valid key, expired key, revoked key, missing header, malformed key, scope checking.

---

## 8. SLA and Uptime

| Metric | Target |
|--------|--------|
| Uptime | 99.9% (8.7 hours downtime/year max) |
| Response time p99 | < 500 ms (excluding LLM inference) |
| Data durability | 99.99% |
| Incident response | < 15 min acknowledgement, < 4 hour resolution |

---

## 9. Acceptance Criteria

- [ ] RBAC correctly enforces all permission combinations
- [ ] Organization policies block non-compliant requests
- [ ] Budget enforcement prevents overspend
- [ ] Audit log chain integrity verifiable
- [ ] PII detection catches email, phone, SSN, CC, IP
- [ ] Data residency checks prevent routing to wrong region
- [ ] Multi-tenancy isolates all data paths
- [ ] API key authentication works end-to-end
- [ ] Encryption at rest for all cached sensitive data
- [ ] 60+ unit tests with >90% coverage
- [ ] Compliance report generation for HIPAA and SOC 2

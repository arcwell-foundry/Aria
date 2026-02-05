"""Security module for ARIA.

Provides data classification, trust levels, sanitization, sandboxing, audit
capabilities, and skill audit trail for the skills integration system.
"""

from src.security.data_classification import (
    ClassifiedData,
    DataClass,
    DataClassifier,
)
from src.security.sandbox import (
    SANDBOX_BY_TRUST,
    SandboxConfig,
    SandboxResult,
    SandboxViolation,
    SkillSandbox,
)
from src.security.sanitization import (
    DataSanitizer,
    LeakageReport,
    TokenMap,
)
from src.security.skill_audit import (
    SkillAuditEntry,
    SkillAuditService,
)
from src.security.trust_levels import (
    TRUST_DATA_ACCESS,
    TRUSTED_SKILL_SOURCES,
    SkillTrustLevel,
    can_access_data,
    determine_trust_level,
)

__all__ = [
    # Data classification
    "ClassifiedData",
    "DataClass",
    "DataClassifier",
    # Trust levels
    "SkillTrustLevel",
    "TRUST_DATA_ACCESS",
    "TRUSTED_SKILL_SOURCES",
    "determine_trust_level",
    "can_access_data",
    # Sanitization
    "TokenMap",
    "LeakageReport",
    "DataSanitizer",
    # Sandbox
    "SandboxConfig",
    "SandboxViolation",
    "SandboxResult",
    "SkillSandbox",
    "SANDBOX_BY_TRUST",
    # Skill audit
    "SkillAuditEntry",
    "SkillAuditService",
]

"""Decoder domain constants - framework metadata and default templates."""

from __future__ import annotations

from .schemas import (
    CitationSlot,
    ExplanationTemplate,
    ExplanationTier,
    TemplateSection,
    TemplateVariable,
)

# =============================================================================
# Framework Metadata
# =============================================================================

FRAMEWORK_METADATA = {
    "MiCA": {
        "full_name": "Markets in Crypto-Assets Regulation",
        "regulation_id": "Regulation (EU) 2023/1114",
        "url_base": "https://eur-lex.europa.eu/eli/reg/2023/1114",
        "effective_date": "2024-06-30",
    },
    "FCA": {
        "full_name": "Financial Conduct Authority Cryptoasset Rules",
        "regulation_id": "FCA Handbook",
        "url_base": "https://www.handbook.fca.org.uk",
        "effective_date": "2024-01-01",
    },
    "SEC": {
        "full_name": "Securities and Exchange Commission",
        "regulation_id": "Securities Act of 1933 / Exchange Act of 1934",
        "url_base": "https://www.sec.gov/rules",
        "effective_date": None,
    },
    "MAS": {
        "full_name": "Monetary Authority of Singapore",
        "regulation_id": "Payment Services Act 2019",
        "url_base": "https://www.mas.gov.sg",
        "effective_date": "2020-01-28",
    },
    "FINMA": {
        "full_name": "Swiss Financial Market Supervisory Authority",
        "regulation_id": "DLT Act",
        "url_base": "https://www.finma.ch",
        "effective_date": "2021-08-01",
    },
}

ARTICLE_PATTERNS: dict[str, dict[str, list[str]]] = {
    "MiCA": {
        "authorization": ["Art. 16", "Art. 36", "Art. 59"],
        "stablecoin": ["Art. 48", "Art. 49", "Art. 50"],
        "exemptions": ["Art. 76", "Art. 77"],
        "definitions": ["Art. 3"],
        "casp": ["Art. 59", "Art. 60", "Art. 61"],
    },
    "FCA": {
        "crypto_promotion": ["COBS 4", "PS 23/6"],
        "custody": ["CASS"],
        "aml": ["MLR 2017"],
    },
}

RISK_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


# =============================================================================
# Default Templates
# =============================================================================

DEFAULT_TEMPLATES: list[ExplanationTemplate] = [
    ExplanationTemplate(
        id="mica_compliant_general",
        name="MiCA Compliant - General",
        version="1.0",
        activity_types=["public_offer", "trading", "custody", "swap", "general"],
        frameworks=["MiCA"],
        outcome="compliant",
        tiers={
            ExplanationTier.RETAIL: [
                TemplateSection(
                    type="headline", template="This activity is allowed under EU rules.", llm_enhance=False
                ),
                TemplateSection(
                    type="body",
                    template="Your {{activity_type}} activity complies with MiCA regulations. No additional actions required.",
                    llm_enhance=True,
                ),
            ],
            ExplanationTier.PROTOCOL: [
                TemplateSection(type="headline", template="Compliance Status: APPROVED", llm_enhance=False),
                TemplateSection(
                    type="body",
                    template="Activity: {{activity_type}} | Framework: MiCA | Status: Compliant | Rule: {{rule_id}}",
                    llm_enhance=False,
                ),
            ],
            ExplanationTier.INSTITUTIONAL: [
                TemplateSection(type="headline", template="Compliance Status: APPROVED", llm_enhance=False),
                TemplateSection(
                    type="body",
                    template="**Regulatory Basis:** MiCA (EU) 2023/1114\n**Activity:** {{activity_type}}\n**Compliance:** Verified\n**Risk Rating:** LOW",
                    llm_enhance=False,
                ),
            ],
            ExplanationTier.REGULATOR: [
                TemplateSection(type="headline", template="Regulatory Decision: APPROVED", llm_enhance=False),
                TemplateSection(
                    type="body",
                    template="## Compliance Assessment\n\nActivity {{activity_type}} evaluated under MiCA framework.\nRule {{rule_id}} applied.\nOutcome: Compliant.\n\n## Legal Basis\n{{primary_citation}}",
                    llm_enhance=False,
                ),
            ],
        },
        variables=[
            TemplateVariable(name="activity_type", source="decision", required=True),
            TemplateVariable(name="rule_id", source="decision", required=True),
            TemplateVariable(name="primary_citation", source="rag", required=False),
        ],
        citation_slots=[CitationSlot(slot_id="primary_citation", framework="MiCA", article_pattern="Art. {{article}}")],
    ),
    ExplanationTemplate(
        id="mica_conditional_general",
        name="MiCA Conditional - General",
        version="1.0",
        activity_types=["public_offer", "trading", "custody", "swap", "general"],
        frameworks=["MiCA"],
        outcome="conditional",
        tiers={
            ExplanationTier.RETAIL: [
                TemplateSection(
                    type="headline", template="This activity may be allowed with conditions.", llm_enhance=False
                ),
                TemplateSection(
                    type="body",
                    template="Your {{activity_type}} activity requires meeting certain conditions under MiCA rules. Review the requirements below.",
                    llm_enhance=True,
                ),
            ],
            ExplanationTier.PROTOCOL: [
                TemplateSection(type="headline", template="Compliance Status: CONDITIONAL", llm_enhance=False),
                TemplateSection(
                    type="body",
                    template="Activity: {{activity_type}} | Framework: MiCA | Status: Conditional | Conditions: See below",
                    llm_enhance=False,
                ),
            ],
            ExplanationTier.INSTITUTIONAL: [
                TemplateSection(type="headline", template="Compliance Status: CONDITIONAL", llm_enhance=False),
                TemplateSection(
                    type="body",
                    template="**Regulatory Basis:** MiCA (EU) 2023/1114\n**Activity:** {{activity_type}}\n**Compliance:** Conditional\n**Risk Rating:** MEDIUM\n\n**Action Required:** Review and satisfy conditions listed below.",
                    llm_enhance=False,
                ),
            ],
            ExplanationTier.REGULATOR: [
                TemplateSection(
                    type="headline", template="Regulatory Decision: CONDITIONAL APPROVAL", llm_enhance=False
                ),
                TemplateSection(
                    type="body",
                    template="## Conditional Assessment\n\nActivity {{activity_type}} evaluated under MiCA framework.\nConditional approval granted pending satisfaction of requirements.\n\n## Outstanding Conditions\n{{conditions}}",
                    llm_enhance=False,
                ),
            ],
        },
        variables=[
            TemplateVariable(name="activity_type", source="decision", required=True),
            TemplateVariable(name="conditions", source="decision", required=False),
        ],
        citation_slots=[],
    ),
    ExplanationTemplate(
        id="mica_non_compliant_general",
        name="MiCA Non-Compliant - General",
        version="1.0",
        activity_types=["public_offer", "trading", "custody", "swap", "general"],
        frameworks=["MiCA"],
        outcome="non_compliant",
        tiers={
            ExplanationTier.RETAIL: [
                TemplateSection(type="headline", template="This activity is not allowed.", llm_enhance=False),
                TemplateSection(
                    type="body",
                    template="Your {{activity_type}} activity does not comply with MiCA regulations. Consider restructuring or consulting a compliance advisor.",
                    llm_enhance=True,
                ),
            ],
            ExplanationTier.PROTOCOL: [
                TemplateSection(type="headline", template="Compliance Status: DENIED", llm_enhance=False),
                TemplateSection(
                    type="body",
                    template="Activity: {{activity_type}} | Framework: MiCA | Status: Non-Compliant | Action: Restructure required",
                    llm_enhance=False,
                ),
            ],
            ExplanationTier.INSTITUTIONAL: [
                TemplateSection(type="headline", template="Compliance Status: DENIED", llm_enhance=False),
                TemplateSection(
                    type="body",
                    template="**Regulatory Basis:** MiCA (EU) 2023/1114\n**Activity:** {{activity_type}}\n**Compliance:** Non-Compliant\n**Risk Rating:** HIGH\n\n**Recommendation:** Do not proceed. Consult compliance team.",
                    llm_enhance=False,
                ),
            ],
            ExplanationTier.REGULATOR: [
                TemplateSection(type="headline", template="Regulatory Decision: DENIED", llm_enhance=False),
                TemplateSection(
                    type="body",
                    template="## Non-Compliance Assessment\n\nActivity {{activity_type}} evaluated under MiCA framework.\nDecision: Non-compliant.\n\n## Violations\n{{violations}}\n\n## Required Actions\nCease activity or restructure to achieve compliance.",
                    llm_enhance=False,
                ),
            ],
        },
        variables=[
            TemplateVariable(name="activity_type", source="decision", required=True),
            TemplateVariable(name="violations", source="decision", required=False),
        ],
        citation_slots=[],
    ),
    ExplanationTemplate(
        id="fca_compliant_general",
        name="FCA Compliant - General",
        version="1.0",
        activity_types=["public_offer", "trading", "custody", "promotion", "general"],
        frameworks=["FCA"],
        outcome="compliant",
        tiers={
            ExplanationTier.RETAIL: [
                TemplateSection(
                    type="headline", template="This activity is allowed under UK rules.", llm_enhance=False
                ),
                TemplateSection(
                    type="body",
                    template="Your {{activity_type}} activity complies with FCA regulations.",
                    llm_enhance=True,
                ),
            ],
            ExplanationTier.INSTITUTIONAL: [
                TemplateSection(type="headline", template="Compliance Status: APPROVED", llm_enhance=False),
                TemplateSection(
                    type="body",
                    template="**Regulatory Basis:** FCA Handbook\n**Activity:** {{activity_type}}\n**Compliance:** Verified",
                    llm_enhance=False,
                ),
            ],
        },
        variables=[TemplateVariable(name="activity_type", source="decision", required=True)],
        citation_slots=[],
    ),
    ExplanationTemplate(
        id="generic_fallback",
        name="Generic Fallback",
        version="1.0",
        activity_types=["general"],
        frameworks=["Unknown"],
        outcome="compliant",
        tiers={
            ExplanationTier.RETAIL: [
                TemplateSection(type="headline", template="Compliance assessment complete.", llm_enhance=False),
                TemplateSection(
                    type="body", template="Please review the detailed assessment below.", llm_enhance=False
                ),
            ],
            ExplanationTier.INSTITUTIONAL: [
                TemplateSection(type="headline", template="Compliance Assessment", llm_enhance=False),
                TemplateSection(
                    type="body",
                    template="Assessment completed. Review details and citations for full analysis.",
                    llm_enhance=False,
                ),
            ],
        },
        variables=[],
        citation_slots=[],
    ),
]

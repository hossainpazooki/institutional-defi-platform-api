"""Tests for DeFi risk scoring domain."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.defi_risk import (
    REPUTABLE_AUDITORS,
    DeFiCategory,
    DeFiScoreRequest,
    EconomicRisk,
    GovernanceRisk,
    GovernanceType,
    OracleProvider,
    OracleRisk,
    RiskGrade,
    SmartContractRisk,
    get_protocol_defaults,
    list_protocol_defaults,
    score_defi_protocol,
)
from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestDeFiScoreRequestValidation:
    def test_valid_protocol_id(self):
        valid_ids = ["aave_v3", "uniswap-v3", "GMX", "compound_v2", "test123"]
        for protocol_id in valid_ids:
            request = DeFiScoreRequest(protocol_id=protocol_id, category=DeFiCategory.LENDING)
            assert request.protocol_id == protocol_id

    def test_invalid_protocol_id_empty(self):
        with pytest.raises(ValidationError) as exc_info:
            DeFiScoreRequest(protocol_id="", category=DeFiCategory.LENDING)
        assert "protocol_id" in str(exc_info.value)

    def test_invalid_protocol_id_special_chars(self):
        with pytest.raises(ValidationError):
            DeFiScoreRequest(protocol_id="aave@v3!", category=DeFiCategory.LENDING)

    def test_invalid_protocol_id_too_long(self):
        with pytest.raises(ValidationError):
            DeFiScoreRequest(protocol_id="a" * 101, category=DeFiCategory.LENDING)

    def test_smart_contract_risk_defaults(self):
        risk = SmartContractRisk()
        assert risk.audit_count == 0
        assert risk.admin_can_drain is False
        assert risk.is_upgradeable is True

    def test_smart_contract_risk_validation(self):
        with pytest.raises(ValidationError):
            SmartContractRisk(audit_count=-1)
        with pytest.raises(ValidationError):
            SmartContractRisk(tvl_usd=-100)

    def test_economic_risk_percentage_validation(self):
        with pytest.raises(ValidationError):
            EconomicRisk(token_concentration_top10_pct=150)
        with pytest.raises(ValidationError):
            EconomicRisk(team_token_pct=-10)

    def test_oracle_risk_defaults(self):
        risk = OracleRisk()
        assert risk.primary_oracle == OracleProvider.CHAINLINK

    def test_governance_risk_multisig_threshold(self):
        risk = GovernanceRisk(governance_type=GovernanceType.MULTISIG, multisig_threshold="3/5")
        assert risk.multisig_threshold == "3/5"


class TestDeFiRiskScoring:
    def test_score_high_risk_protocol(self):
        score = score_defi_protocol(
            protocol_id="high_risk_protocol",
            category=DeFiCategory.LENDING,
            smart_contract=SmartContractRisk(
                audit_count=0,
                admin_can_drain=True,
                exploit_history_count=2,
                total_exploit_loss_usd=50_000_000,
            ),
            economic=EconomicRisk(token_concentration_top10_pct=90, treasury_runway_months=6),
            oracle=OracleRisk(
                primary_oracle=OracleProvider.CUSTOM, has_fallback_oracle=False, oracle_manipulation_resistant=False
            ),
            governance=GovernanceRisk(governance_type=GovernanceType.CENTRALIZED, has_timelock=False),
        )
        assert score.overall_grade in [RiskGrade.D, RiskGrade.F]
        assert len(score.critical_risks) > 0
        assert "admin can drain" in " ".join(score.critical_risks).lower()

    def test_score_low_risk_protocol(self):
        score = score_defi_protocol(
            protocol_id="low_risk_protocol",
            category=DeFiCategory.DEX,
            smart_contract=SmartContractRisk(
                audit_count=5,
                auditors=["trail of bits", "openzeppelin", "certik"],
                formal_verification=True,
                is_upgradeable=False,
                admin_can_drain=False,
                tvl_usd=5_000_000_000,
                contract_age_days=500,
                bug_bounty_max_usd=2_000_000,
            ),
            economic=EconomicRisk(
                token_concentration_top10_pct=30,
                treasury_runway_months=48,
                treasury_diversified=True,
                has_protocol_revenue=True,
                revenue_30d_usd=5_000_000,
            ),
            oracle=OracleRisk(primary_oracle=OracleProvider.NONE),
            governance=GovernanceRisk(
                governance_type=GovernanceType.TOKEN_VOTING,
                has_timelock=True,
                timelock_hours=72,
                governance_participation_pct=20,
            ),
        )
        assert score.overall_grade in [RiskGrade.A, RiskGrade.B]
        assert len(score.strengths) > 0
        assert score.overall_score >= 70

    def test_regulatory_flags_for_lending(self):
        score = score_defi_protocol(
            protocol_id="test_lending",
            category=DeFiCategory.LENDING,
            smart_contract=SmartContractRisk(),
            economic=EconomicRisk(),
            oracle=OracleRisk(),
            governance=GovernanceRisk(),
        )
        assert any("licensing" in flag.lower() for flag in score.regulatory_flags)

    def test_regulatory_flags_for_derivatives(self):
        score = score_defi_protocol(
            protocol_id="test_derivatives",
            category=DeFiCategory.DERIVATIVES,
            smart_contract=SmartContractRisk(),
            economic=EconomicRisk(),
            oracle=OracleRisk(),
            governance=GovernanceRisk(),
        )
        assert any("cftc" in flag.lower() for flag in score.regulatory_flags)

    def test_regulatory_flags_for_stablecoin(self):
        score = score_defi_protocol(
            protocol_id="test_stablecoin",
            category=DeFiCategory.STABLECOIN,
            smart_contract=SmartContractRisk(),
            economic=EconomicRisk(),
            oracle=OracleRisk(),
            governance=GovernanceRisk(),
        )
        assert any("genius" in flag.lower() for flag in score.regulatory_flags)

    def test_critical_risk_caps_grade(self):
        score = score_defi_protocol(
            protocol_id="critical_risk",
            category=DeFiCategory.LENDING,
            smart_contract=SmartContractRisk(audit_count=5, admin_can_drain=True),
            economic=EconomicRisk(),
            oracle=OracleRisk(),
            governance=GovernanceRisk(),
        )
        assert score.overall_grade in [RiskGrade.D, RiskGrade.F]
        assert score.overall_score <= 35

    def test_score_includes_metrics_summary(self):
        score = score_defi_protocol(
            protocol_id="test",
            category=DeFiCategory.DEX,
            smart_contract=SmartContractRisk(tvl_usd=1_000_000),
            economic=EconomicRisk(),
            oracle=OracleRisk(),
            governance=GovernanceRisk(governance_type=GovernanceType.MULTISIG),
        )
        assert "category" in score.metrics_summary
        assert "tvl_usd" in score.metrics_summary
        assert score.metrics_summary["category"] == "dex"


class TestProtocolDefaults:
    def test_list_protocol_defaults(self):
        protocols = list_protocol_defaults()
        assert isinstance(protocols, list)
        assert "aave_v3" in protocols
        assert "uniswap_v3" in protocols

    def test_get_aave_defaults(self):
        config = get_protocol_defaults("aave_v3")
        assert config is not None
        assert config["category"] == DeFiCategory.LENDING
        assert config["smart_contract"]["audit_count"] >= 3

    def test_get_uniswap_defaults(self):
        config = get_protocol_defaults("uniswap_v3")
        assert config is not None
        assert config["category"] == DeFiCategory.DEX
        assert config["smart_contract"]["is_upgradeable"] is False

    def test_get_nonexistent_protocol(self):
        config = get_protocol_defaults("nonexistent_protocol")
        assert config is None

    def test_case_insensitive_lookup(self):
        config1 = get_protocol_defaults("AAVE_V3")
        config2 = get_protocol_defaults("aave_v3")
        assert config1 == config2


class TestReputableAuditors:
    def test_top_tier_auditors(self):
        top_tier = ["trail of bits", "openzeppelin", "consensys diligence", "spearbit"]
        for auditor in top_tier:
            assert REPUTABLE_AUDITORS.get(auditor) == 1.0

    def test_competition_auditors(self):
        competitions = ["code4rena", "sherlock"]
        for auditor in competitions:
            assert REPUTABLE_AUDITORS.get(auditor) == 0.9


class TestDeFiRiskEndpoints:
    def test_score_protocol_endpoint(self, client):
        response = client.post(
            "/defi-risk/score",
            json={
                "protocol_id": "test_protocol",
                "category": "lending",
                "smart_contract": {"audit_count": 3},
                "economic": {"token_concentration_top10_pct": 40},
                "oracle": {"primary_oracle": "chainlink"},
                "governance": {"governance_type": "token_voting"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["protocol_id"] == "test_protocol"
        assert "overall_grade" in data
        assert data["overall_grade"] in ["A", "B", "C", "D", "F"]

    def test_score_protocol_validation_error(self, client):
        response = client.post("/defi-risk/score", json={"protocol_id": "", "category": "lending"})
        assert response.status_code == 422

    def test_list_protocols_endpoint(self, client):
        response = client.get("/defi-risk/protocols")
        assert response.status_code == 200
        data = response.json()
        assert "protocols" in data
        assert "aave_v3" in data["protocols"]

    def test_get_protocol_config_endpoint(self, client):
        response = client.get("/defi-risk/protocols/aave_v3")
        assert response.status_code == 200
        data = response.json()
        assert data["protocol_id"] == "aave_v3"

    def test_get_protocol_config_not_found(self, client):
        response = client.get("/defi-risk/protocols/nonexistent")
        assert response.status_code == 404

    def test_score_known_protocol_endpoint(self, client):
        response = client.post("/defi-risk/protocols/aave_v3/score")
        assert response.status_code == 200
        data = response.json()
        assert data["protocol_id"] == "aave_v3"
        assert data["overall_grade"] in ["A", "B"]

    def test_score_known_protocol_not_found(self, client):
        response = client.post("/defi-risk/protocols/nonexistent/score")
        assert response.status_code == 404

    def test_list_categories_endpoint(self, client):
        response = client.get("/defi-risk/categories")
        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert "lending" in data["categories"]
        assert "dex" in data["categories"]


class TestDeFiRiskEdgeCases:
    def test_all_categories(self):
        for category in DeFiCategory:
            score = score_defi_protocol(
                protocol_id=f"test_{category.value}",
                category=category,
                smart_contract=SmartContractRisk(),
                economic=EconomicRisk(),
                oracle=OracleRisk(),
                governance=GovernanceRisk(),
            )
            assert score.category == category

    def test_all_governance_types(self):
        for gov_type in GovernanceType:
            score = score_defi_protocol(
                protocol_id="test",
                category=DeFiCategory.LENDING,
                smart_contract=SmartContractRisk(),
                economic=EconomicRisk(),
                oracle=OracleRisk(),
                governance=GovernanceRisk(governance_type=gov_type),
            )
            assert score.governance_grade in RiskGrade

    def test_all_oracle_providers(self):
        for oracle in OracleProvider:
            score = score_defi_protocol(
                protocol_id="test",
                category=DeFiCategory.LENDING,
                smart_contract=SmartContractRisk(),
                economic=EconomicRisk(),
                oracle=OracleRisk(primary_oracle=oracle),
                governance=GovernanceRisk(),
            )
            assert score.oracle_grade in RiskGrade

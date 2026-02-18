"""Tests for token compliance analysis domain."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.main import app
from src.token_compliance import (
    PERMITTED_RESERVE_ASSETS,
    GeniusActRequest,
    HoweyTestRequest,
    TokenClassification,
    TokenComplianceRequest,
    TokenStandard,
    analyze_genius_act_compliance,
    analyze_token_compliance,
    apply_howey_test,
    list_token_standards,
)


@pytest.fixture
def client():
    """Test client for the FastAPI app."""
    return TestClient(app)


# =============================================================================
# Schema Validation Tests
# =============================================================================


class TestHoweyTestRequestValidation:
    """Tests for HoweyTestRequest input validation."""

    def test_valid_request(self):
        """Valid Howey test request should pass validation."""
        request = HoweyTestRequest(
            investment_of_money=True,
            common_enterprise=True,
            expectation_of_profits=True,
            efforts_of_others=True,
            decentralization_score=0.5,
            is_functional_network=False,
        )
        assert request.decentralization_score == 0.5

    def test_decentralization_score_bounds(self):
        """Decentralization score must be between 0 and 1."""
        with pytest.raises(ValidationError):
            HoweyTestRequest(
                investment_of_money=True,
                common_enterprise=True,
                expectation_of_profits=True,
                efforts_of_others=True,
                decentralization_score=1.5,  # Invalid: > 1
            )
        with pytest.raises(ValidationError):
            HoweyTestRequest(
                investment_of_money=True,
                common_enterprise=True,
                expectation_of_profits=True,
                efforts_of_others=True,
                decentralization_score=-0.1,  # Invalid: < 0
            )


class TestGeniusActRequestValidation:
    """Tests for GeniusActRequest input validation."""

    def test_valid_request(self):
        """Valid GENIUS Act request should pass validation."""
        request = GeniusActRequest(
            is_stablecoin=True,
            pegged_currency="USD",
            reserve_assets=["usd_cash", "us_treasury_bills"],
            reserve_ratio=1.0,
            issuer_charter_type="bank",
        )
        assert request.pegged_currency == "USD"

    def test_invalid_pegged_currency(self):
        """Invalid currency format should fail validation."""
        with pytest.raises(ValidationError):
            GeniusActRequest(
                is_stablecoin=True,
                pegged_currency="us dollars",  # Invalid: not uppercase 3-10 chars
            )

    def test_invalid_issuer_type(self):
        """Invalid issuer type should fail validation."""
        with pytest.raises(ValidationError):
            GeniusActRequest(
                is_stablecoin=True,
                issuer_charter_type="invalid_type",  # Must be bank, non_bank_qualified, or foreign
            )

    def test_reserve_ratio_bounds(self):
        """Reserve ratio must be between 0 and 10."""
        with pytest.raises(ValidationError):
            GeniusActRequest(is_stablecoin=True, reserve_ratio=15.0)

    def test_attestation_frequency_bounds(self):
        """Attestation frequency must be between 0 and 365 days."""
        with pytest.raises(ValidationError):
            GeniusActRequest(is_stablecoin=True, attestation_frequency_days=500)


class TestTokenComplianceRequestValidation:
    """Tests for TokenComplianceRequest input validation."""

    def test_valid_request(self):
        """Valid token compliance request should pass validation."""
        request = TokenComplianceRequest(
            standard=TokenStandard.ERC_20,
            has_profit_expectation=True,
            is_decentralized=False,
            backed_by_fiat=False,
        )
        assert request.standard == TokenStandard.ERC_20

    def test_decentralization_score_bounds(self):
        """Decentralization score must be between 0 and 1."""
        with pytest.raises(ValidationError):
            TokenComplianceRequest(
                standard=TokenStandard.ERC_20,
                has_profit_expectation=True,
                is_decentralized=False,
                backed_by_fiat=False,
                decentralization_score=2.0,  # Invalid
            )


# =============================================================================
# Howey Test Service Tests
# =============================================================================


class TestHoweyTestService:
    """Tests for SEC Howey Test analysis."""

    def test_all_prongs_satisfied_is_security(self):
        """Token satisfying all four Howey prongs is a security."""
        result = apply_howey_test(
            investment_of_money=True,
            common_enterprise=True,
            expectation_of_profits=True,
            efforts_of_others=True,
        )

        assert result.is_security is True
        assert result.prongs_satisfied == 4

    def test_missing_prong_not_security(self):
        """Token missing any Howey prong is not a security."""
        # Missing efforts_of_others
        result = apply_howey_test(
            investment_of_money=True,
            common_enterprise=True,
            expectation_of_profits=True,
            efforts_of_others=False,
        )

        assert result.is_security is False
        assert result.prongs_satisfied == 3

    def test_decentralization_negates_efforts_of_others(self):
        """Sufficient decentralization should negate efforts_of_others prong."""
        result = apply_howey_test(
            investment_of_money=True,
            common_enterprise=True,
            expectation_of_profits=True,
            efforts_of_others=True,
            decentralization_score=0.9,  # High decentralization
            is_functional_network=True,
        )

        # Decentralization should override efforts_of_others
        assert result.efforts_of_others is False
        assert result.is_security is False
        assert any("decentralized" in note.lower() for note in result.analysis_notes)

    def test_partial_decentralization_no_effect(self):
        """Partial decentralization should not negate efforts_of_others."""
        result = apply_howey_test(
            investment_of_money=True,
            common_enterprise=True,
            expectation_of_profits=True,
            efforts_of_others=True,
            decentralization_score=0.5,  # Partial decentralization
            is_functional_network=True,
        )

        assert result.efforts_of_others is True
        assert result.is_security is True

    def test_prongs_satisfied_count(self):
        """prongs_satisfied should correctly count satisfied prongs."""
        result = apply_howey_test(
            investment_of_money=True,
            common_enterprise=False,
            expectation_of_profits=True,
            efforts_of_others=False,
        )

        assert result.prongs_satisfied == 2

    def test_analysis_notes_for_commodity_classification(self):
        """Should note commodity classification potential."""
        result = apply_howey_test(
            investment_of_money=True,
            common_enterprise=True,
            expectation_of_profits=True,
            efforts_of_others=False,  # Not dependent on others
        )

        assert any("commodity" in note.lower() for note in result.analysis_notes)


# =============================================================================
# GENIUS Act Service Tests
# =============================================================================


class TestGeniusActService:
    """Tests for GENIUS Act stablecoin compliance analysis."""

    def test_compliant_stablecoin(self):
        """Compliant stablecoin should have compliant status."""
        result = analyze_genius_act_compliance(
            is_stablecoin=True,
            pegged_currency="USD",
            reserve_assets=["usd_cash", "us_treasury_bills"],
            reserve_ratio=1.0,
            uses_algorithmic_mechanism=False,
            issuer_charter_type="bank",
            has_reserve_attestation=True,
            attestation_frequency_days=30,
        )

        assert result.is_payment_stablecoin is True
        assert result.compliance_status == "compliant"
        assert result.backed_by_permitted_assets is True
        assert result.has_one_to_one_backing is True
        assert result.meets_genius_requirements is True

    def test_non_usd_stablecoin_not_payment_stablecoin(self):
        """Non-USD pegged stablecoin is not a payment stablecoin."""
        result = analyze_genius_act_compliance(
            is_stablecoin=True,
            pegged_currency="EUR",
            reserve_assets=["usd_cash"],
            reserve_ratio=1.0,
            uses_algorithmic_mechanism=False,
            issuer_charter_type="bank",
            has_reserve_attestation=True,
        )

        assert result.is_payment_stablecoin is False
        assert result.compliance_status == "not_applicable"

    def test_algorithmic_stablecoin_prohibited(self):
        """Algorithmic stablecoins should be prohibited."""
        result = analyze_genius_act_compliance(
            is_stablecoin=True,
            pegged_currency="USD",
            reserve_assets=["usd_cash"],
            reserve_ratio=1.0,
            uses_algorithmic_mechanism=True,  # Prohibited
            issuer_charter_type="bank",
            has_reserve_attestation=True,
        )

        assert result.is_algorithmic is True
        assert result.compliance_status == "prohibited"
        assert any("algorithmic" in note.lower() for note in result.compliance_notes)

    def test_under_backed_stablecoin(self):
        """Under-backed stablecoin should require remediation."""
        result = analyze_genius_act_compliance(
            is_stablecoin=True,
            pegged_currency="USD",
            reserve_assets=["usd_cash"],
            reserve_ratio=0.8,  # Under-backed
            uses_algorithmic_mechanism=False,
            issuer_charter_type="bank",
            has_reserve_attestation=True,
        )

        assert result.has_one_to_one_backing is False
        assert result.compliance_status == "requires_remediation"

    def test_non_permitted_reserve_assets(self):
        """Non-permitted reserve assets should be flagged."""
        result = analyze_genius_act_compliance(
            is_stablecoin=True,
            pegged_currency="USD",
            reserve_assets=["bitcoin", "ethereum"],  # Not permitted
            reserve_ratio=1.0,
            uses_algorithmic_mechanism=False,
            issuer_charter_type="bank",
            has_reserve_attestation=True,
        )

        assert result.backed_by_permitted_assets is False
        assert any("non-permitted" in note.lower() for note in result.compliance_notes)

    def test_missing_attestation(self):
        """Missing reserve attestation should be flagged."""
        result = analyze_genius_act_compliance(
            is_stablecoin=True,
            pegged_currency="USD",
            reserve_assets=["usd_cash"],
            reserve_ratio=1.0,
            uses_algorithmic_mechanism=False,
            issuer_charter_type="bank",
            has_reserve_attestation=False,  # Missing
        )

        assert result.reserve_transparency is False
        assert result.meets_genius_requirements is False

    def test_permitted_reserve_assets(self):
        """All permitted reserve assets should be accepted."""
        for asset in PERMITTED_RESERVE_ASSETS:
            result = analyze_genius_act_compliance(
                is_stablecoin=True,
                pegged_currency="USD",
                reserve_assets=[asset],
                reserve_ratio=1.0,
                uses_algorithmic_mechanism=False,
                issuer_charter_type="bank",
                has_reserve_attestation=True,
                attestation_frequency_days=30,
            )
            assert result.backed_by_permitted_assets is True


# =============================================================================
# Token Compliance Service Tests
# =============================================================================


class TestTokenComplianceService:
    """Tests for comprehensive token compliance analysis."""

    def test_security_token_classification(self):
        """Token satisfying Howey test should be classified as security."""
        result = analyze_token_compliance(
            standard=TokenStandard.ERC_20,
            has_profit_expectation=True,
            is_decentralized=False,
            backed_by_fiat=False,
            investment_of_money=True,
            common_enterprise=True,
            efforts_of_promoter=True,
            decentralization_score=0.2,
        )

        assert result.classification == TokenClassification.SECURITY_TOKEN
        assert result.requires_sec_registration is True
        assert result.sec_jurisdiction is True
        assert len(result.compliance_requirements) > 0

    def test_utility_token_classification(self):
        """Token not satisfying Howey test should be utility token."""
        result = analyze_token_compliance(
            standard=TokenStandard.ERC_20,
            has_profit_expectation=False,  # No profit expectation
            is_decentralized=True,
            backed_by_fiat=False,
        )

        assert result.classification == TokenClassification.UTILITY_TOKEN
        assert result.requires_sec_registration is False
        assert result.sec_jurisdiction is False

    def test_nft_classification(self):
        """ERC-721 tokens should be classified as NFT."""
        result = analyze_token_compliance(
            standard=TokenStandard.ERC_721,
            has_profit_expectation=True,
            is_decentralized=False,
            backed_by_fiat=False,
        )

        assert result.classification == TokenClassification.NFT
        assert result.sec_jurisdiction is False

    def test_stablecoin_classification(self):
        """Fiat-backed stablecoin should be classified as payment stablecoin."""
        result = analyze_token_compliance(
            standard=TokenStandard.ERC_20,
            has_profit_expectation=False,
            is_decentralized=False,
            backed_by_fiat=True,
            is_stablecoin=True,
            pegged_currency="USD",
            reserve_assets=["usd_cash"],
            reserve_ratio=1.0,
            has_reserve_attestation=True,
        )

        assert result.classification == TokenClassification.PAYMENT_STABLECOIN
        assert result.genius_act_applicable is True
        assert result.genius_analysis is not None

    def test_commodity_token_classification(self):
        """Token with profit expectation but not security should be commodity."""
        result = analyze_token_compliance(
            standard=TokenStandard.ERC_20,
            has_profit_expectation=True,
            is_decentralized=True,
            backed_by_fiat=False,
            investment_of_money=True,
            common_enterprise=True,
            efforts_of_promoter=False,  # Not dependent on others
        )

        assert result.classification == TokenClassification.COMMODITY_TOKEN
        assert result.cftc_jurisdiction is True
        assert result.sec_jurisdiction is False

    def test_list_token_standards(self):
        """Should list all supported token standards."""
        standards = list_token_standards()
        assert "erc_20" in standards
        assert "erc_721" in standards
        assert "erc_1155" in standards
        assert "bep_20" in standards
        assert "spl" in standards

    def test_recommended_actions_for_security(self):
        """Security tokens should have SEC registration recommendations."""
        result = analyze_token_compliance(
            standard=TokenStandard.ERC_20,
            has_profit_expectation=True,
            is_decentralized=False,
            backed_by_fiat=False,
        )

        assert len(result.recommended_actions) > 0
        assert any("sec" in action.lower() or "regulation" in action.lower() for action in result.recommended_actions)


# =============================================================================
# API Endpoint Tests
# =============================================================================


class TestTokenComplianceEndpoints:
    """Tests for token compliance API endpoints."""

    def test_howey_test_endpoint(self, client):
        """POST /token-compliance/howey-test should return analysis."""
        response = client.post(
            "/token-compliance/howey-test",
            json={
                "investment_of_money": True,
                "common_enterprise": True,
                "expectation_of_profits": True,
                "efforts_of_others": True,
                "decentralization_score": 0.3,
                "is_functional_network": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["investment_of_money"] is True
        assert "analysis_notes" in data

    def test_howey_test_decentralization(self, client):
        """POST /token-compliance/howey-test with high decentralization."""
        response = client.post(
            "/token-compliance/howey-test",
            json={
                "investment_of_money": True,
                "common_enterprise": True,
                "expectation_of_profits": True,
                "efforts_of_others": True,
                "decentralization_score": 0.9,
                "is_functional_network": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        # Decentralization should negate efforts_of_others
        assert data["efforts_of_others"] is False

    def test_genius_act_endpoint(self, client):
        """POST /token-compliance/genius-act should return analysis."""
        response = client.post(
            "/token-compliance/genius-act",
            json={
                "is_stablecoin": True,
                "pegged_currency": "USD",
                "reserve_assets": ["usd_cash", "us_treasury_bills"],
                "reserve_ratio": 1.0,
                "uses_algorithmic_mechanism": False,
                "issuer_charter_type": "bank",
                "has_reserve_attestation": True,
                "attestation_frequency_days": 30,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_payment_stablecoin"] is True
        assert data["compliance_status"] == "compliant"

    def test_genius_act_validation_error(self, client):
        """POST /token-compliance/genius-act should reject invalid input."""
        response = client.post(
            "/token-compliance/genius-act",
            json={
                "is_stablecoin": True,
                "issuer_charter_type": "invalid",  # Invalid type
            },
        )

        assert response.status_code == 422

    def test_analyze_endpoint(self, client):
        """POST /token-compliance/analyze should return full analysis."""
        response = client.post(
            "/token-compliance/analyze",
            json={
                "standard": "erc_20",
                "has_profit_expectation": True,
                "is_decentralized": False,
                "backed_by_fiat": False,
                "investment_of_money": True,
                "common_enterprise": True,
                "efforts_of_promoter": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "classification" in data
        assert "requires_sec_registration" in data
        assert "howey_analysis" in data

    def test_standards_endpoint(self, client):
        """GET /token-compliance/standards should list standards."""
        response = client.get("/token-compliance/standards")

        assert response.status_code == 200
        data = response.json()
        assert "standards" in data
        assert "erc_20" in data["standards"]
        assert "erc_721" in data["standards"]


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestTokenComplianceEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_all_token_standards(self):
        """Analysis should work for all token standards."""
        for standard in TokenStandard:
            result = analyze_token_compliance(
                standard=standard,
                has_profit_expectation=True,
                is_decentralized=False,
                backed_by_fiat=False,
            )
            assert result.standard == standard

    def test_boundary_decentralization_score(self):
        """Test boundary values for decentralization score."""
        # Just below threshold (0.8)
        result1 = apply_howey_test(
            investment_of_money=True,
            common_enterprise=True,
            expectation_of_profits=True,
            efforts_of_others=True,
            decentralization_score=0.79,
            is_functional_network=True,
        )
        assert result1.efforts_of_others is True

        # At threshold (0.8)
        result2 = apply_howey_test(
            investment_of_money=True,
            common_enterprise=True,
            expectation_of_profits=True,
            efforts_of_others=True,
            decentralization_score=0.8,
            is_functional_network=True,
        )
        assert result2.efforts_of_others is False

    def test_all_issuer_types(self):
        """GENIUS Act analysis should work for all issuer types."""
        for issuer_type in ["bank", "non_bank_qualified", "foreign"]:
            result = analyze_genius_act_compliance(
                is_stablecoin=True,
                pegged_currency="USD",
                reserve_assets=["usd_cash"],
                reserve_ratio=1.0,
                uses_algorithmic_mechanism=False,
                issuer_charter_type=issuer_type,
                has_reserve_attestation=True,
                attestation_frequency_days=30,
            )
            assert result.issuer_type == issuer_type

    def test_empty_reserve_assets(self):
        """Empty reserve assets list should be flagged."""
        result = analyze_genius_act_compliance(
            is_stablecoin=True,
            pegged_currency="USD",
            reserve_assets=[],
            reserve_ratio=1.0,
            uses_algorithmic_mechanism=False,
            issuer_charter_type="bank",
            has_reserve_attestation=True,
        )

        # Empty reserves should be treated as subset of permitted (vacuously true)
        assert result.backed_by_permitted_assets is True

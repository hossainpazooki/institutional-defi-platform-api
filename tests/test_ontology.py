"""Tests for ontology types."""

from datetime import date

from src.ontology import (
    Activity,
    ActivityType,
    Actor,
    ActorType,
    Condition,
    ConditionGroup,
    Instrument,
    InstrumentType,
    Obligation,
    Permission,
    Prohibition,
    Provision,
    ProvisionType,
    Scenario,
    SourceReference,
)


class TestActor:
    def test_create_issuer(self):
        actor = Actor(
            id="issuer_1",
            type=ActorType.ISSUER,
            name="Acme Token Corp",
            jurisdiction="EU",
        )
        assert actor.id == "issuer_1"
        assert actor.type == ActorType.ISSUER
        assert actor.jurisdiction == "EU"

    def test_actor_with_attributes(self):
        actor = Actor(
            id="bank_1",
            type=ActorType.ISSUER,
            attributes={"is_credit_institution": True},
        )
        assert actor.attributes["is_credit_institution"] is True


class TestInstrument:
    def test_create_art(self):
        instrument = Instrument(
            id="art_1",
            type=InstrumentType.ART,
            name="Euro Stablecoin",
            reference_asset="EUR",
        )
        assert instrument.type == InstrumentType.ART
        assert instrument.reference_asset == "EUR"

    def test_create_emt(self):
        instrument = Instrument(
            id="emt_1",
            type=InstrumentType.EMT,
            reference_asset="EUR",
        )
        assert instrument.type == InstrumentType.EMT


class TestActivity:
    def test_create_public_offer(self):
        activity = Activity(
            id="offer_1",
            type=ActivityType.PUBLIC_OFFER,
            actor_id="issuer_1",
            instrument_id="art_1",
            jurisdiction="EU",
        )
        assert activity.type == ActivityType.PUBLIC_OFFER
        assert activity.jurisdiction == "EU"


class TestProvision:
    def test_create_provision(self):
        provision = Provision(
            id="mica_art36_1",
            type=ProvisionType.REQUIREMENT,
            source=SourceReference(
                document_id="mica_2023",
                article="36(1)",
                pages=[65],
            ),
            text="No person shall make a public offer...",
            effective_from=date(2024, 6, 30),
        )
        assert provision.type == ProvisionType.REQUIREMENT
        assert provision.source.article == "36(1)"
        assert provision.effective_from == date(2024, 6, 30)


class TestNormativeContent:
    def test_create_obligation(self):
        obligation = Obligation(
            id="obl_1",
            provision_id="mica_art36_1",
            action="obtain authorization",
            applies_to_actor=ActorType.ISSUER,
            applies_to_instrument=InstrumentType.ART,
        )
        assert obligation.type == "obligation"
        assert obligation.action == "obtain authorization"

    def test_create_permission(self):
        permission = Permission(
            id="perm_1",
            provision_id="mica_art36_2",
            action="make public offer",
            applies_to_actor=ActorType.ISSUER,
            limits="only if authorized",
        )
        assert permission.type == "permission"

    def test_create_prohibition(self):
        prohibition = Prohibition(
            id="prohib_1",
            provision_id="mica_art76",
            action="market manipulation",
            exceptions=["market_making_exception"],
        )
        assert prohibition.type == "prohibition"
        assert "market_making_exception" in prohibition.exceptions


class TestCondition:
    def test_simple_condition(self):
        condition = Condition(
            field="instrument_type",
            operator="==",
            value="art",
        )
        assert condition.field == "instrument_type"
        assert condition.operator == "=="

    def test_condition_group_all(self):
        group = ConditionGroup(
            all=[
                Condition(field="type", operator="==", value="art"),
                Condition(field="jurisdiction", operator="==", value="EU"),
            ]
        )
        assert len(group.all) == 2


class TestScenario:
    def test_create_scenario(self):
        scenario = Scenario(
            instrument_type="stablecoin",
            activity="public_offer",
            jurisdiction="EU",
            authorized=False,
        )
        assert scenario.instrument_type == "stablecoin"
        assert scenario.authorized is False

    def test_scenario_get(self):
        scenario = Scenario(
            instrument_type="art",
            extra={"custom_field": "value"},
        )
        assert scenario.get("instrument_type") == "art"
        assert scenario.get("custom_field") == "value"
        assert scenario.get("missing", "default") == "default"

    def test_scenario_has(self):
        scenario = Scenario(
            instrument_type="art",
            authorized=None,
        )
        assert scenario.has("instrument_type") is True
        assert scenario.has("authorized") is False

    def test_scenario_to_flat_dict(self):
        scenario = Scenario(
            instrument_type="art",
            activity="public_offer",
            extra={"custom": "value"},
        )
        flat = scenario.to_flat_dict()
        assert flat["instrument_type"] == "art"
        assert flat["activity"] == "public_offer"
        assert flat["custom"] == "value"
        assert "extra" not in flat

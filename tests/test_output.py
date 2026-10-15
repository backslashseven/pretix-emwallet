from datetime import datetime, timezone
from decimal import Decimal

import pytest
from django_scopes import scopes_disabled
from i18nfield.strings import LazyI18nString
from rest_framework.test import APIClient

from pretix.base.models import Order, OrderPosition, Team

from pretix_emwallet.output import EmWalletOutput


@pytest.fixture
@scopes_disabled()
def position(event):
    event.location = LazyI18nString({"en": "Kraftwerk Berlin\nKöpenicker Str. 70\n10179 Berlin"})
    event.date_admission = datetime(2030, 12, 27, 9, 0, 0, tzinfo=timezone.utc)
    event.save()
    item = event.items.create(name="Tagesticket", default_price=Decimal("0.00"), admission=True)
    order = Order.objects.create(
        event=event, status=Order.STATUS_PAID, email="guest@example.org", locale="en",
        datetime=datetime(2030, 1, 1, tzinfo=timezone.utc), total=Decimal("0.00"),
        sales_channel=event.organizer.sales_channels.get(identifier="web"),
    )
    return OrderPosition.objects.create(order=order, item=item, price=Decimal("0.00"))


def fields(position):
    data = EmWalletOutput(position.order.event).generate_pass(position).passInformation.json_dict()
    return {
        section: {f["key"]: f for f in data.get(section, [])}
        for section in ("headerFields", "primaryFields", "secondaryFields", "auxiliaryFields", "backFields")
    }


@pytest.mark.django_db
@scopes_disabled()
def test_layout(position):
    event = position.order.event
    event.settings.emwallet_website_url = "https://example.org/eventmanagement/"
    event.settings.emwallet_back_text = "Garderobe im 1. OG"

    f = fields(position)

    assert f["headerFields"]["admission"]["label"] == "Admission"
    assert "doorsAdmissionHeader" not in f["headerFields"]
    assert "doorsAdmission" not in f["backFields"]
    assert f["primaryFields"]["eventName"]["value"] == "Dummy"
    assert f["secondaryFields"]["ticket"]["value"] == "Tagesticket"
    assert f["secondaryFields"]["location"]["value"] == "Kraftwerk Berlin"
    assert f["backFields"]["locationFull"]["value"] == "Kraftwerk Berlin\nKöpenicker Str. 70\n10179 Berlin"
    assert f["backFields"]["emwalletInfo"]["value"] == "Garderobe im 1. OG"
    assert f["backFields"]["website"]["value"] == "https://example.org/eventmanagement/"


@pytest.mark.django_db
@scopes_disabled()
def test_keys_unique(position):
    position.attendee_name_parts = {"_legacy": "Erika Muster"}
    position.save()
    data = EmWalletOutput(position.order.event).generate_pass(position).passInformation.json_dict()
    keys = [f["key"] for section in data.values() for f in section]
    assert "attendeeName" in keys
    assert len(keys) == len(set(keys))


@pytest.mark.django_db
@scopes_disabled()
def test_no_website_and_german_labels(position):
    position.order.event.settings.emwallet_locale = "de"

    f = fields(position)

    assert "website" not in f["backFields"]
    assert "emwalletInfo" not in f["backFields"]
    assert f["headerFields"]["admission"]["label"] == "Einlass"
    assert f["secondaryFields"]["location"]["label"] == "Ort"
    assert f["secondaryFields"]["ticket"]["label"] == "Produkt"


@pytest.mark.django_db
@scopes_disabled()
def test_settings_api(event):
    team = Team.objects.create(organizer=event.organizer, all_events=True, all_event_permissions=True)
    token = team.tokens.create(name="EM")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Token " + token.token)
    url = f"/api/v1/organizers/{event.organizer.slug}/events/{event.slug}/settings/"

    resp = client.patch(url, {
        "ticketoutput_emwallet__enabled": True,
        "emwallet_website_url": "https://example.org/",
        "emwallet_back_text": "Info",
        "ticketoutput_passbook_bg_color": "#112233",
    }, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["emwallet_website_url"] == "https://example.org/"
    assert event.settings.get("ticketoutput_emwallet__enabled", as_type=bool) is True
    assert event.settings.ticketoutput_passbook_bg_color == "#112233"

    resp = client.patch(url, {"ticketoutput_passbook_bg_color": "red"}, format="json")
    assert resp.status_code == 400

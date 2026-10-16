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


def labels(section):
    return [(f["key"], f["label"], f["value"], f["textAlignment"]) for f in section.values()]


@pytest.mark.django_db
@scopes_disabled()
def test_front_like_template(position):
    position.attendee_name_parts = {"_legacy": "Erika Muster"}
    position.save()
    position.order.event.settings.emwallet_locale = "de"

    f = fields(position)

    # event in Europe/Berlin: admission 09:00 UTC = 10:00, begin 10:00 UTC = 11:00
    assert labels(f["headerFields"]) == [("admission", "EINLASS", "27.12. · 10:00", "PKTextAlignmentRight")]
    assert f["primaryFields"]["eventName"]["label"] == "VERANSTALTUNG"
    assert labels(f["secondaryFields"]) == [
        ("name", "NAME TEILNEHMER*IN", "Erika Muster", "PKTextAlignmentLeft"),
        ("ticket", "PRODUKT", "Tagesticket", "PKTextAlignmentRight"),
    ]
    assert labels(f["auxiliaryFields"]) == [
        ("location", "ORT", "Kraftwerk Berlin", "PKTextAlignmentLeft"),
        ("begin", "BEGINN", "11:00 Uhr", "PKTextAlignmentRight"),
    ]


@pytest.mark.django_db
@scopes_disabled()
def test_back(position):
    event = position.order.event
    event.settings.emwallet_website_url = "https://example.org/eventmanagement/"
    event.settings.emwallet_back_text = "Garderobe im 1. OG"

    back = fields(position)["backFields"]

    assert list(back) == ["locationFull", "emwalletInfo", "website"]
    assert back["locationFull"]["value"] == "Kraftwerk Berlin\nKöpenicker Str. 70\n10179 Berlin"
    assert back["emwalletInfo"]["value"] == "Garderobe im 1. OG"
    assert back["website"]["value"] == "https://example.org/eventmanagement/"


@pytest.mark.django_db
@scopes_disabled()
def test_without_optional_values(position):
    event = position.order.event
    event.location = None
    event.date_admission = None
    event.save()

    f = fields(position)

    assert f["headerFields"] == {}
    assert list(f["secondaryFields"]) == ["ticket"]
    assert list(f["auxiliaryFields"]) == ["begin"]
    assert f["backFields"] == {}


@pytest.mark.django_db
@scopes_disabled()
def test_keys_unique(position):
    position.attendee_name_parts = {"_legacy": "Erika Muster"}
    position.save()
    data = EmWalletOutput(position.order.event).generate_pass(position).passInformation.json_dict()
    keys = [f["key"] for section in data.values() for f in section]
    assert len(keys) == len(set(keys))


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


@pytest.mark.django_db
@scopes_disabled()
def test_cached_passes_are_deleted_once_per_version(position):
    from django.core.files.base import ContentFile
    from pretix.base.models import CachedTicket
    from pretix.base.settings import GlobalSettingsObject

    from pretix_emwallet import __version__
    from pretix_emwallet.signals import invalidate_on_version_change

    def cache():
        ct = CachedTicket.objects.create(order_position=position, provider="emwallet", type="application/vnd.apple.pkpass",
                                         extension=".pkpass")
        ct.file.save("t.pkpass", ContentFile(b"x"))
        return ct

    GlobalSettingsObject().settings.set("emwallet_cache_version", "0.0.1")
    cache()
    invalidate_on_version_change()
    assert not CachedTicket.objects.filter(provider="emwallet").exists()
    assert GlobalSettingsObject().settings.get("emwallet_cache_version") == __version__

    cache()
    invalidate_on_version_change()
    assert CachedTicket.objects.filter(provider="emwallet").count() == 1


@pytest.mark.django_db
@scopes_disabled()
def test_migrate_triggers_version_check(position):
    from django.apps import apps
    from django.db.models.signals import post_migrate
    from pretix.base.settings import GlobalSettingsObject

    from pretix_emwallet import __version__

    GlobalSettingsObject().settings.set("emwallet_cache_version", "0.0.1")
    post_migrate.send(sender=apps.get_app_config("pretixbase"), app_config=apps.get_app_config("pretixbase"),
                      verbosity=0, interactive=False, using="default", apps=apps, plan=[])
    assert GlobalSettingsObject().settings.get("emwallet_cache_version") == __version__

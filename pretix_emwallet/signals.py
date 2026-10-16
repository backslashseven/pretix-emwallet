from django.core.validators import RegexValidator
from django.db import transaction
from django.db.models.signals import post_delete, post_migrate, post_save
from django.dispatch import receiver
from pretix.api.serializers.fields import UploadedFileField
from pretix.base.models import Event, Event_SettingsStore
from pretix.base.signals import api_event_settings_fields, periodic_task, register_ticket_outputs
from rest_framework import serializers

PLUGIN = "pretix_emwallet"
PROVIDER = "emwallet"

# Settings that change the generated pass. The images and colors use the keys of
# pretix-passbook, because its generate_pass() reads them hardcoded.
PASS_SETTINGS_PREFIXES = ("emwallet_", "ticketoutput_passbook_", "ticketoutput_emwallet_")

COLOR_VALIDATOR = RegexValidator(r"^#[0-9a-fA-F]{6}$", "Use the format #RRGGBB.")


@receiver(register_ticket_outputs, dispatch_uid="output_emwallet")
def register_ticket_output(sender, **kwargs):
    from .output import EmWalletOutput

    return EmWalletOutput


@receiver(api_event_settings_fields, dispatch_uid="emwallet_api_settings")
def api_settings_fields(sender, **kwargs):
    def png():
        return UploadedFileField(allowed_types=("image/png",), allow_null=True)

    def color():
        return serializers.CharField(allow_null=True, allow_blank=True, validators=[COLOR_VALIDATOR])

    return {
        "ticketoutput_emwallet__enabled": serializers.BooleanField(),
        "emwallet_locale": serializers.CharField(allow_null=True, allow_blank=True, max_length=10),
        "emwallet_website_url": serializers.URLField(allow_null=True, allow_blank=True),
        "emwallet_back_text": serializers.CharField(allow_null=True, allow_blank=True),
        "ticketoutput_passbook_logo": png(),
        "ticketoutput_passbook_icon": png(),
        "ticketoutput_passbook_background": png(),
        "ticketoutput_passbook_bg_color": color(),
        "ticketoutput_passbook_fg_color": color(),
        "ticketoutput_passbook_label_color": color(),
    }


def _invalidate_passes(event: Event):
    if PLUGIN not in event.get_plugins():
        return
    from pretix.base.services.tickets import invalidate_cache

    # The settings API and event PATCH don't invalidate cached ticket files
    transaction.on_commit(
        lambda: invalidate_cache.apply_async(kwargs={"event": event.pk, "provider": PROVIDER})
    )


@receiver(post_save, sender=Event_SettingsStore, dispatch_uid="emwallet_settings_saved")
@receiver(post_delete, sender=Event_SettingsStore, dispatch_uid="emwallet_settings_deleted")
def settings_changed(sender, instance, **kwargs):
    if instance.key.startswith(PASS_SETTINGS_PREFIXES):
        _invalidate_passes(instance.object)


@receiver(post_save, sender=Event, dispatch_uid="emwallet_event_saved")
def event_changed(sender, instance, created, **kwargs):
    if not created:
        _invalidate_passes(instance)


def invalidate_on_version_change():
    """
    Cached passes are only rebuilt when they are deleted. A new plugin version changes the layout, so all cached
    passes of this output are deleted once per version.
    """
    from pretix.base.models import CachedCombinedTicket, CachedTicket
    from pretix.base.settings import GlobalSettingsObject

    from . import __version__

    gs = GlobalSettingsObject()
    if gs.settings.get("emwallet_cache_version") == __version__:
        return
    for ct in CachedTicket.objects.filter(provider=PROVIDER):
        ct.delete()
    for ct in CachedCombinedTicket.objects.filter(provider=PROVIDER):
        ct.delete()
    gs.settings.set("emwallet_cache_version", __version__)


@receiver(post_migrate, dispatch_uid="emwallet_post_migrate")
def after_migrate(sender, **kwargs):
    # pretix migrates on every container start (unless AUTOMIGRATE=skip)
    if getattr(sender, "name", None) == PLUGIN:
        invalidate_on_version_change()


@receiver(periodic_task, dispatch_uid="emwallet_periodic")
def periodic(sender, **kwargs):
    invalidate_on_version_change()

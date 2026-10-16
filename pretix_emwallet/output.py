from django.utils.formats import date_format
from django.utils.translation import gettext, pgettext
from pretix.base.i18n import language
from pretix.base.models import OrderPosition
from pretix.base.ticketoutput import BaseTicketOutput
from pretix_passbook.passbook import PassbookOutput


def _pop_field(fields: list, key: str):
    for f in list(fields):
        if f.key == key:
            fields.remove(f)


class EmWalletOutput(PassbookOutput):
    """
    Stock pretix-passbook pass with an EM specific layout:

    header:     Einlass (admission time)
    primary:    Event
    secondary:  Produkt, Ort
    auxiliary:  attendee / seat, From, To (unchanged)
    back:       Ort with address, Informationen, website from EM (or none), no order details
    """

    identifier = "emwallet"
    verbose_name = "EM Wallet"

    @property
    def settings_form_fields(self) -> dict:
        # Images and colors are read from the stock ticketoutput_passbook_* keys and set
        # by EM through the settings API, so only offer the enable switch here.
        return BaseTicketOutput.settings_form_fields.fget(self)

    def generate_pass(self, order_position: OrderPosition):
        locale = self.event.settings.get("emwallet_locale") or order_position.order.locale
        with language(locale, self.event.settings.region):
            return self._generate_pass(order_position)

    def _generate_pass(self, order_position: OrderPosition):
        passfile = super().generate_pass(order_position)
        card = passfile.passInformation
        ev = order_position.subevent or order_position.order.event
        tz = self.event.timezone
        settings = self.event.settings

        # Order details of pretix are not meaningful for guests: organizer account, buyer email, order code, purchase date
        for key in ("organizer", "email", "orderCode", "purchaseDate"):
            _pop_field(card.backFields, key)

        # Keys must be unique in the whole pass, pretix-passbook uses "name" on the front and the back
        for f in card.backFields:
            if f.key == "name":
                f.key = "attendeeName"

        # Admission time is shown in the header even without a custom logo
        _pop_field(card.headerFields, "doorsAdmissionHeader")
        _pop_field(card.backFields, "doorsAdmission")
        if ev.date_admission:
            card.addHeaderField(
                "admission",
                date_format(ev.date_admission.astimezone(tz), "SHORT_DATETIME_FORMAT"),
                pgettext("emwallet", "Admission"),
            )

        location = str(ev.location or "").strip()
        if location:
            lines = [line.strip() for line in location.splitlines() if line.strip()]
            card.addSecondaryField("location", lines[0], pgettext("emwallet", "Location"))
            card.addBackField("locationFull", "\n".join(lines), pgettext("emwallet", "Location"))

        back_text = (settings.get("emwallet_back_text") or "").strip()
        if back_text:
            card.addBackField("emwalletInfo", back_text, pgettext("emwallet", "Information"))

        # Replace the pretix shop URL, which is internal for EM events
        _pop_field(card.backFields, "website")
        website = (settings.get("emwallet_website_url") or "").strip()
        if website:
            card.addBackField("website", website, gettext("Website"))

        return passfile

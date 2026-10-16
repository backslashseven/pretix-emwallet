from django.utils.formats import date_format
from django.utils.translation import gettext, pgettext
from pretix.base.i18n import language
from pretix.base.models import OrderPosition
from pretix.base.ticketoutput import BaseTicketOutput
from pretix_passbook.passbook import PassbookOutput
from wallet.models import Alignment, Field


def _field(key: str, value: str, label: str, alignment: str = Alignment.LEFT) -> Field:
    f = Field(key, value, label.upper())
    f.textAlignment = alignment
    return f


def _pop_field(fields: list, key: str):
    for f in list(fields):
        if f.key == key:
            fields.remove(f)


class EmWalletOutput(PassbookOutput):
    """
    Stock pretix-passbook pass with an EM specific layout:

    header:     EINLASS (admission date and time)
    primary:    VERANSTALTUNG
    secondary:  NAME TEILNEHMER*IN | PRODUKT
    auxiliary:  ORT | BEGINN
    back:       Ort with address, Informationen, website from EM (or none)
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
        product = next((f.value for f in card.secondaryFields if f.key == "ticket"), str(order_position.item.name))

        # The front is built from scratch (template of the customer), labels in capitals:
        # header: EINLASS / primary: VERANSTALTUNG / NAME TEILNEHMER*IN | PRODUKT / ORT | BEGINN
        card.headerFields = []
        if ev.date_admission:
            admission = ev.date_admission.astimezone(tz)
            card.headerFields.append(_field("admission", "%s · %s" % (
                date_format(admission, "d.m."), date_format(admission, "H:i")
            ), pgettext("emwallet", "Admission"), Alignment.RIGHT))

        for f in card.primaryFields:
            f.label = f.label.upper()

        card.secondaryFields = []
        if order_position.attendee_name:
            card.secondaryFields.append(_field("name", order_position.attendee_name, pgettext("emwallet", "Attendee name")))
        card.secondaryFields.append(_field("ticket", product, gettext("Product"), Alignment.RIGHT))

        location_lines = [line.strip() for line in str(ev.location or "").splitlines() if line.strip()]
        card.auxiliaryFields = []
        if location_lines:
            card.auxiliaryFields.append(_field("location", location_lines[0], pgettext("emwallet", "Location")))
        card.auxiliaryFields.append(_field("begin", pgettext("emwallet", "{time}").format(
            time=date_format(ev.date_from.astimezone(tz), "H:i")
        ), pgettext("emwallet", "Begin"), Alignment.RIGHT))

        # Back: only what EM configures. The name is on the front, pretix order details are not meaningful for
        # guests (organizer account, buyer email, order code, purchase date)
        for key in ("name", "organizer", "email", "orderCode", "purchaseDate", "doorsAdmission", "doorsClose", "website"):
            _pop_field(card.backFields, key)

        if location_lines:
            card.addBackField("locationFull", "\n".join(location_lines), pgettext("emwallet", "Location"))

        back_text = (settings.get("emwallet_back_text") or "").strip()
        if back_text:
            card.addBackField("emwalletInfo", back_text, pgettext("emwallet", "Information"))

        # Replaces the pretix shop URL, which is internal for EM events
        website = (settings.get("emwallet_website_url") or "").strip()
        if website:
            card.addBackField("website", website, gettext("Website"))

        return passfile

pretix EM Wallet
================

Apple Wallet ticket output (``emwallet``) based on `pretix-passbook`_:

* Header: EINLASS, admission date and time (``Event.date_admission``)
* Front, labels in capitals: VERANSTALTUNG, NAME TEILNEHMER*IN | PRODUKT, ORT (first line of
  ``Event.location``) | BEGINN (start time)
* Back: full location, free text (``emwallet_back_text``), website (``emwallet_website_url``,
  hidden if empty; replaces the pretix shop URL); no organizer, buyer email, order code or purchase date

Images and colors use pretix-passbook's ``ticketoutput_passbook_*`` settings. All settings are
exposed in ``/api/v1/organizers/{org}/events/{event}/settings/`` once the plugin is enabled for the
event, together with ``ticketoutput_emwallet__enabled`` and ``emwallet_locale`` (language of the
pass labels, defaults to the order locale). Cached passes are invalidated when any of these
settings or the event change.

Requires ``pretix-passbook`` to be installed and its global certificate settings to be configured.

Development
-----------

::

    source ../.venv/bin/activate
    pip install -e .
    make
    py.test tests

.. _pretix-passbook: https://github.com/pretix/pretix-passbook

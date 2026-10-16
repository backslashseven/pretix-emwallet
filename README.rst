pretix EM Wallet
================

Apple Wallet ticket output (``emwallet``) based on `pretix-passbook`_:

* Header: admission time (``Event.date_admission``)
* Front: event, product, location (first line of ``Event.location``)
* Back: full location, free text (``emwallet_back_text``), website (``emwallet_website_url``,
  hidden if empty; replaces the pretix shop URL); no organizer

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

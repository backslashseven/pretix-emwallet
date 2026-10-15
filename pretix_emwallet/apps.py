from django.utils.translation import gettext_lazy

from . import __version__

try:
    from pretix.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2.7 or above to run this plugin!")


class PluginApp(PluginConfig):
    default = True
    name = "pretix_emwallet"
    verbose_name = "EM Wallet"

    class PretixPluginMeta:
        name = gettext_lazy("EM Wallet")
        author = "Backslash Seven"
        description = gettext_lazy(
            "Apple Wallet tickets with admission time, location and custom back "
            "information, configured via the event settings API."
        )
        visible = True
        version = __version__
        category = "FORMAT"
        compatibility = "pretix>=2024.1.0"

    def ready(self):
        from . import signals  # NOQA

"""The one place a refusal becomes screen text (FIBR-0425 § 4.3).

The importers and services are Qt-free, so they raise a ``UserMessage`` whose
English template was marked for the catalog where it was written. This
translates the template first and substitutes the values after, so the lookup
matches the catalog's source text.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QCoreApplication, QLocale

from finbreak.errors import UserMessage, message_of

log = logging.getLogger(__name__)


def user_text(source: BaseException | UserMessage) -> str:
    message = source if isinstance(source, UserMessage) else message_of(source)
    values = {
        name: QLocale().toString(value) if isinstance(value, int) else value
        for name, value in message.values.items()
    }
    # Not a literal, and the i18n guard's one named exception: every template
    # reaching here is a QT_TRANSLATE_NOOP("Refusal", …) literal (INV-2).
    translated = QCoreApplication.translate("Refusal", message.template)
    try:
        return translated.format(**values)
    except (KeyError, IndexError, ValueError):
        # The template, never the values: they can hold statement text (INV-7).
        log.warning("a translation does not fit its refusal: %r", message.template)
        return message.template.format(**values)

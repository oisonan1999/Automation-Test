# automation/form_handler/__init__.py
# Backward-compatible package: re-exports FormHandlerMixin composed
# from category sub-mixins (split from the old 8267-line monolith).

from .form_core import FormCoreMixin
from .field_finder import FieldFinderMixin
from .field_filler import FieldFillerMixin
from .dropdown_handler import DropdownHandlerMixin
from .datetime_handler import DateTimeHandlerMixin
from .special_panels import SpecialPanelsMixin
from .rbe_task_panel import RbeTaskPanelMixin
from .form_save import FormSaveMixin
from .tab_scanner import TabScannerMixin


class FormHandlerMixin(
    FormCoreMixin,
    FieldFinderMixin,
    FieldFillerMixin,
    DropdownHandlerMixin,
    DateTimeHandlerMixin,
    SpecialPanelsMixin,
    RbeTaskPanelMixin,
    FormSaveMixin,
    TabScannerMixin,
):
    """Chứa logic tương tác với Form: điền form, dropdown, radio, datetime, save.

    Composed from category sub-mixins; method resolution via self works across
    all mixins once mixed into BrickAutomation.
    """
    pass

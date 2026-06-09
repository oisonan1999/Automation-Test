# automation/table_handler/__init__.py
# Backward-compatible: re-exports TableHandlerMixin composed from sub-mixins.

from .table_filter import TableFilterMixin
from .table_checkbox import TableCheckboxMixin
from .table_rows import TableRowsMixin
from .table_reorder import TableReorderMixin


class TableHandlerMixin(
    TableFilterMixin,
    TableCheckboxMixin,
    TableRowsMixin,
    TableReorderMixin,
):
    """Table operations: filter, checkbox, row actions (edit/clone), reorder."""
    pass

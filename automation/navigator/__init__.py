# automation/navigator/__init__.py
# Backward-compatible: re-exports NavigatorMixin composed from sub-mixins.

from .navigator_core import NavigatorCoreMixin
from .click_handler import ClickHandlerMixin
from .deployment import DeploymentMixin
from .pve_navigation import PveNavigationMixin


class NavigatorMixin(
    NavigatorCoreMixin,
    ClickHandlerMixin,
    DeploymentMixin,
    PveNavigationMixin,
):
    """Menu/tab navigation, multi-strategy click, deployment, PVE accordion."""
    pass

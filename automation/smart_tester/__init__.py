# automation/smart_tester/__init__.py
# Backward-compatible: re-exports SmartTesterMixin + standalone fuzz classes.

from .tester_core import SmartTesterCoreMixin
from .upload_handler import UploadHandlerMixin
from .popup_classifier import PopupClassifierMixin
from .fuzz_generator import RBESmartTester, RBEFuzzGenerator, GenericCSVFuzzer


class SmartTesterMixin(
    SmartTesterCoreMixin,
    UploadHandlerMixin,
    PopupClassifierMixin,
):
    """CSV fuzz campaign, upload, popup classification."""
    pass


__all__ = ["SmartTesterMixin", "RBESmartTester", "RBEFuzzGenerator", "GenericCSVFuzzer"]

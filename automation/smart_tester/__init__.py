# automation/smart_tester/__init__.py
# Backward-compatible: re-exports SmartTesterMixin + standalone fuzz classes.

from .tester_core import SmartTesterCoreMixin
from .upload_handler import UploadHandlerMixin
from .popup_classifier import PopupClassifierMixin
from .fuzz_generator import RBESmartTester, RBEFuzzGenerator, GenericCSVFuzzer
from .pve_book_csv_fuzzer import PVEBookFuzzTesterMixin, PVEBookCSVFuzzer


class SmartTesterMixin(
    SmartTesterCoreMixin,
    UploadHandlerMixin,
    PopupClassifierMixin,
    PVEBookFuzzTesterMixin,
):
    """CSV fuzz campaign, upload, popup classification."""
    pass


__all__ = [
    "SmartTesterMixin",
    "RBESmartTester",
    "RBEFuzzGenerator",
    "GenericCSVFuzzer",
    "PVEBookCSVFuzzer",
]

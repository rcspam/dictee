"""Tray ASR menu: four Parakeet entries (Ultra / v3 x fp32 / int8).

Pure helpers are extracted from dictee-tray.py without importing it (the
module pulls in Qt or GTK at import time)."""
import os
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dictee-tray.py")


def _load_func(name):
    with open(SCRIPT, encoding="utf-8") as f:
        lines = f.readlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(f"def {name}("))
    end = next((j for j in range(start + 1, len(lines))
                if lines[j].startswith(("def ", "class "))), len(lines))
    ns = {}
    exec("".join(lines[start:end]), ns)
    return ns[name]


switch_cmd = _load_func("_asr_switch_command")
checked = _load_func("_asr_entry_checked")


class SwitchCommandTests(unittest.TestCase):
    def test_same_entry_does_nothing(self):
        self.assertIsNone(switch_cmd("parakeet", "ultra:fp32", "parakeet", "ultra", "fp32"))

    def test_other_parakeet_variant_is_one_call(self):
        self.assertEqual(switch_cmd("parakeet", "ultra:int8", "parakeet", "v3", "fp32"),
                         ["dictee-switch-backend", "parakeet", "ultra", "int8"])

    def test_model_change_with_same_quant(self):
        self.assertEqual(switch_cmd("parakeet", "v3:fp32", "parakeet", "ultra", "fp32"),
                         ["dictee-switch-backend", "parakeet", "v3", "fp32"])

    def test_from_another_backend_chains_variant_then_asr(self):
        self.assertEqual(
            switch_cmd("parakeet", "ultra:fp32", "whisper", "v3", "fp32"),
            ["bash", "-c", "dictee-switch-backend parakeet ultra fp32 && "
                           "dictee-switch-backend asr parakeet"])

    def test_from_another_backend_same_variant_is_asr_only(self):
        self.assertEqual(switch_cmd("parakeet", "v3:fp32", "whisper", "v3", "fp32"),
                         ["dictee-switch-backend", "asr", "parakeet"])

    def test_other_backend(self):
        self.assertEqual(switch_cmd("vosk", None, "parakeet", "ultra", "fp32"),
                         ["dictee-switch-backend", "asr", "vosk"])


class CheckedTests(unittest.TestCase):
    def test_parakeet_entry_needs_model_and_quant(self):
        self.assertTrue(checked("parakeet", "ultra:int8", "parakeet", "ultra", "int8"))
        self.assertFalse(checked("parakeet", "v3:int8", "parakeet", "ultra", "int8"))
        self.assertFalse(checked("parakeet", "ultra:fp32", "parakeet", "ultra", "int8"))

    def test_other_backend(self):
        self.assertTrue(checked("vosk", None, "vosk", "v3", "fp32"))
        self.assertFalse(checked("parakeet", "v3:fp32", "vosk", "v3", "fp32"))


if __name__ == "__main__":
    unittest.main()

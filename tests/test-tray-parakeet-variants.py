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
    ns = {"_": lambda s: s}   # gettext stand-in
    exec("".join(lines[start:end]), ns)
    return ns[name]


switch_cmd = _load_func("_asr_switch_command")
checked = _load_func("_asr_entry_checked")
force_cpu = _load_func("_force_cpu_state")


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


class ForceCpuToggleTests(unittest.TestCase):
    """(checked, enabled, tooltip); the toggle never writes DICTEE_FORCE_CPU
    when it is greyed out, so a locked state must not depend on it."""

    def test_parakeet_int8_locked_on_cpu_whatever_the_flag(self):
        for fc in ("0", "1"):
            c, e, _t = force_cpu("parakeet", "int8", fc, 8.0, True)
            self.assertEqual((c, e), (True, False))

    def test_parakeet_fp32_follows_the_flag(self):
        self.assertEqual(force_cpu("parakeet", "fp32", "0", 8.0, True)[:2], (False, True))
        self.assertEqual(force_cpu("parakeet", "fp32", "1", 8.0, True)[:2], (True, True))

    def test_int8_quant_only_locks_parakeet(self):
        # The Parakeet quant stays in the conf while Whisper is active
        self.assertEqual(force_cpu("whisper", "int8", "0", 8.0, True)[:2], (False, True))

    def test_vosk_no_gpu_and_cpu_package_are_locked(self):
        self.assertEqual(force_cpu("vosk", "fp32", "0", 8.0, True)[:2], (True, False))
        self.assertEqual(force_cpu("parakeet", "fp32", "0", 0.0, True)[:2], (True, False))
        self.assertEqual(force_cpu("canary", "fp32", "0", 8.0, False)[:2], (True, False))


if __name__ == "__main__":
    unittest.main()

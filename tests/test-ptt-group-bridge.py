#!/usr/bin/env python3
"""How dictee-ptt gains the input group when its session does not have it yet.

The post-install adds the user to `input`, but the user manager and everything
it starts keep the groups fixed at login. Until 1.3.6 the unit hard-coded
`sg input -c`, and Arch dropped /usr/bin/sg from shadow 4.20.0.arch1-1, so
dictee-ptt.service looped on 203/EXEC there (#35). The bridge is now chosen
at runtime: nothing when the group is already there, sg where shadow ships it
(Debian, Ubuntu, Fedora), util-linux's `newgrp -c` on Arch, and a logged
warning when neither exists.

No evdev, no device: only input_group_bridge() is exercised, with its
lookups injected.

Run: python3 tests/test-ptt-group-bridge.py [-v]
"""
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

spec = importlib.util.spec_from_file_location("ptt_under_test", os.path.join(ROOT, "dictee-ptt.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

SHADOW_NEWGRP_HELP = "Usage: newgrp [-] [group]\n"
UTIL_LINUX_NEWGRP_HELP = ("Usage:\n newgrp <group> [[-c] <command>]\n\n"
                          "Options:\n -c, --command <command>  pass a command to the user's shell with -c\n")


def which_of(*names):
    return lambda name: f"/usr/bin/{name}" if name in names else None


class BridgeTests(unittest.TestCase):

    def test_group_already_effective(self):
        self.assertEqual(
            mod.input_group_bridge(has_group=True, which=which_of("sg", "newgrp"),
                                   newgrp_help=lambda: UTIL_LINUX_NEWGRP_HELP),
            [])

    def test_debian_fedora_use_sg(self):
        self.assertEqual(
            mod.input_group_bridge(has_group=False, which=which_of("sg", "newgrp"),
                                   newgrp_help=lambda: SHADOW_NEWGRP_HELP),
            ["sg", "input", "-c"])

    def test_arch_uses_util_linux_newgrp(self):
        self.assertEqual(
            mod.input_group_bridge(has_group=False, which=which_of("newgrp"),
                                   newgrp_help=lambda: UTIL_LINUX_NEWGRP_HELP),
            ["newgrp", "input", "-c"])

    def test_sg_wins_over_newgrp_when_both_work(self):
        self.assertEqual(
            mod.input_group_bridge(has_group=False, which=which_of("sg", "newgrp"),
                                   newgrp_help=lambda: UTIL_LINUX_NEWGRP_HELP),
            ["sg", "input", "-c"])

    def test_shadow_newgrp_without_sg_is_no_bridge(self):
        self.assertIsNone(
            mod.input_group_bridge(has_group=False, which=which_of("newgrp"),
                                   newgrp_help=lambda: SHADOW_NEWGRP_HELP))

    def test_nothing_installed_is_no_bridge(self):
        self.assertIsNone(
            mod.input_group_bridge(has_group=False, which=which_of(),
                                   newgrp_help=lambda: ""))

    def test_newgrp_help_failure_is_no_bridge(self):
        def boom():
            raise OSError("no newgrp")
        self.assertIsNone(
            mod.input_group_bridge(has_group=False, which=which_of("newgrp"), newgrp_help=boom))


class HasInputGroupTests(unittest.TestCase):

    def test_real_process_answer_matches_id(self):
        import subprocess
        expected = "input" in subprocess.run(["id", "-nG"], capture_output=True, text=True).stdout.split()
        self.assertEqual(mod.has_input_group(), expected)


if __name__ == "__main__":
    unittest.main()

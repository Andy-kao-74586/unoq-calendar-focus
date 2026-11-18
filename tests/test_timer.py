import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from timer_core import FocusTimer


class TimerTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.timer = FocusTimer(lambda: self.now)

    def advance(self, seconds):
        self.now += seconds
        return self.timer.snapshot()

    def test_pause_does_not_consume_time_and_resume_keeps_fraction(self):
        self.timer.command("start")
        self.advance(10.75)
        self.timer.command("pause")
        self.assertEqual(self.advance(900)["remaining_seconds"], 1490)
        self.timer.command("resume")
        self.assertEqual(self.advance(.5)["remaining_seconds"], 1489)

    def test_finish_counts_once_and_break_stops_ready(self):
        self.timer.command("start")
        state = self.advance(1500)
        self.assertEqual((state["completed"], state["phase"], state["remaining_seconds"]), (1, "break", 300))
        for _ in range(10):
            self.assertEqual(self.timer.snapshot()["completed"], 1)
        self.assertEqual(self.advance(300)["status"], "ready")
        self.advance(50000)
        self.assertEqual(self.timer.completed, 1)

    def test_duplicate_start_resume_pause_are_idempotent(self):
        self.timer.command("start")
        self.advance(5)
        self.timer.command("start")
        self.assertEqual(self.timer.snapshot()["remaining_seconds"], 1495)
        self.timer.command("pause")
        self.advance(20)
        self.timer.command("pause")
        self.timer.command("resume")
        self.advance(5)
        self.timer.command("resume")
        self.assertEqual(self.timer.snapshot()["remaining_seconds"], 1490)

    def test_demo_does_not_pollute_real_count(self):
        self.timer.command("configure", {"demo": True})
        self.timer.command("start")
        state = self.advance(30)
        self.assertEqual((state["completed"], state["demo_completed"], state["remaining_seconds"]), (0, 1, 10))

    def test_long_scheduler_gap_does_not_invent_cycles(self):
        self.timer.command("start")
        state = self.advance(100000)
        self.assertEqual(state["completed"], 1)
        self.assertEqual(state["remaining_seconds"], 300)

    def test_reset_abandons_partial_round_but_preserves_count(self):
        self.timer.command("start")
        self.advance(1500)
        self.timer.command("reset")
        state = self.timer.snapshot()
        self.assertEqual((state["completed"], state["status"], state["remaining_seconds"]), (1, "idle", 1500))

    def test_invalid_settings_are_atomic(self):
        for values in [{"focus_minutes": 0}, {"focus_minutes": True}, {"break_minutes": 1.5}, {"demo": "false"}, {"focus_minutes": 181}]:
            with self.assertRaises(ValueError):
                self.timer.command("configure", values)
        self.assertEqual(self.timer.focus_seconds, 1500)
        self.timer.command("start")
        with self.assertRaises(ValueError):
            self.timer.command("configure", {"demo": True})
        self.assertFalse(self.timer.demo)

    def test_snapshot_uses_elapsed_time_without_browser(self):
        self.timer.command("start")
        self.now += 124.2
        self.assertEqual(self.timer.snapshot()["remaining_seconds"], 1376)
        self.assertEqual(self.timer.snapshot()["remaining_seconds"], 1376)


if __name__ == "__main__":
    unittest.main()

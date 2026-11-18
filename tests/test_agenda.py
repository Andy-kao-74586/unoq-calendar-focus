import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from agenda import agenda_scene, board_label, scene_frame, take_priority
from timer_core import FocusTimer


class AgendaTests(unittest.TestCase):
    def setUp(self):
        self.events = [{"title":"晚餐", "start":2000, "end":5600, "all_day":False}]

    def scene(self, now, events=None):
        return agenda_scene({"fresh": True, "events": self.events if events is None else events}, now)

    def test_free_prepare_event_end_boundaries(self):
        self.assertEqual(self.scene(1699)["mode"], "free")
        self.assertEqual(self.scene(1700)["mode"], "prepare")
        self.assertEqual(self.scene(2000)["mode"], "event")
        self.assertEqual(self.scene(3200)["remaining_seconds"], 2400)
        self.assertEqual(self.scene(5600)["mode"], "free")
        self.assertIsNone(self.scene(5600)["end"])

    def test_title_mapping_and_custom_labels(self):
        self.assertEqual(board_label("家庭晚餐"), "DINNER")
        self.assertEqual(board_label("專題討論"), "MEETING")
        self.assertEqual(board_label("生日 [CAKE]"), "CAKE")
        self.assertEqual(board_label("未辨識中文"), "EVENT")

    def test_overlapping_and_back_to_back(self):
        events = self.events + [{"title":"上課","start":5500,"end":6000}]
        self.assertEqual(self.scene(5500, events)["overlap"], 2)
        self.assertEqual(self.scene(5500, events)["title"], "晚餐")
        self.assertEqual(self.scene(5600, events)["title"], "上課")

    def test_all_day_does_not_hide_timed_event(self):
        events = [{"title":"假期","start":0,"end":86400,"all_day":True}] + self.events
        self.assertEqual(self.scene(2100, events)["title"], "晚餐")
        self.assertEqual(self.scene(2100, events)["all_day_count"], 1)

    def test_reschedule_cancel_and_stale(self):
        self.events[0]["end"] = 7000
        self.assertEqual(self.scene(3200)["remaining_seconds"], 3800)
        self.assertEqual(self.scene(3200, [])["mode"], "free")
        self.assertEqual(agenda_scene({"fresh":False},3200)["mode"], "unavailable")

    def test_interrupt_does_not_count_or_auto_resume(self):
        now = [1500]
        timer = FocusTimer(lambda:now[0],lambda:now[0])
        timer.command("start")
        now[0] = 1700
        take_priority(timer, self.scene(now[0]))
        remaining = timer.remaining
        self.assertEqual(timer.status, "paused")
        now[0] = 5600
        take_priority(timer, self.scene(now[0]))
        self.assertEqual(timer.snapshot()["remaining_seconds"], remaining)
        self.assertEqual(timer.completed, 0)
        timer.command("resume")
        self.assertEqual(timer.status,"running")

    def test_bitmap_is_bounded_and_marquee_alternates(self):
        scene = self.scene(3200)
        frames = [scene_frame(scene, t / 10) for t in range(200)]
        self.assertEqual({mode for _, mode in frames}, {"marquee","countdown"})
        self.assertGreater(len({tuple(frame) for frame, _ in frames}), 10)
        for frame, _ in frames:
            self.assertEqual(len(frame),4)
            self.assertTrue(all(0 <= part < 2**26 for part in frame))

    def test_long_event_does_not_overflow_matrix(self):
        scene = self.scene(2000, [{"title":"Travel", "start":2000, "end":200000}])
        for t in range(20):
            frame, _ = scene_frame(scene, t)
            self.assertTrue(all(0 <= part < 2**26 for part in frame))


if __name__ == "__main__": unittest.main()

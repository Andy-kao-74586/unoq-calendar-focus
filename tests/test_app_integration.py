"""App wiring with simulated Google/Arduino; no hardware or credentials required."""
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from calendar_api import CalendarSession
from timer_core import FocusTimer


class AppIntegrationTests(unittest.TestCase):
    def setUp(self):
        fake_utils = types.ModuleType("arduino.app_utils")
        self.frames = []
        fake_utils.App = types.SimpleNamespace(run=lambda **kw:None)
        fake_utils.Bridge = types.SimpleNamespace(call=lambda *args:self.frames.append(args) or True)
        fake_ui = types.ModuleType("arduino.app_bricks.web_ui")
        fake_ui.WebUI = lambda:types.SimpleNamespace(expose_api=lambda *args:None)
        fake_fastapi = types.ModuleType("fastapi")
        fake_fastapi.Request = object
        fake_fastapi.HTTPException = RuntimeError
        spec = importlib.util.spec_from_file_location("agenda_app_test", Path(__file__).resolve().parents[1]/"python/main.py")
        self.app = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"arduino.app_utils":fake_utils,"arduino.app_bricks.web_ui":fake_ui,"fastapi":fake_fastapi}), patch("threading.Thread.start"):
            spec.loader.exec_module(self.app)
        self.now = 1500
        self.clock_patch = patch.object(self.app, "time", types.SimpleNamespace(time=lambda:self.now,monotonic=lambda:self.now,sleep=lambda n:None))
        self.clock_patch.start()
        self.addCleanup(self.clock_patch.stop)
        self.events = [{"title":"晚餐", "start":2000,"end":5600,"all_day":False}]
        self.app.timer = FocusTimer(lambda:self.now,lambda:self.now)
        self.app.CalendarSession = lambda token,expires:CalendarSession(token,expires,lambda t,n:self.events,lambda:self.now)
        self.request = types.SimpleNamespace(method="POST",headers={"origin":"http://localhost:7000","x-focus-app":"1"})
        result = self.app.connect_calendar({"access_token":"fake-token-for-tests","expires_in":3600},self.request)
        self.key = result["session"]
        self.request.headers["x-calendar-session"] = self.key

    def refresh_at(self, now):
        self.now = now
        session = self.app.calendar.get(self.key)
        session.expires_at = now + 3600
        session.refresh(force=True)

    def test_connect_drives_hardware_without_browser_start(self):
        self.refresh_at(2000)
        self.app.loop()
        self.assertEqual(self.frames[-1][0], "calendar_frame_v1")
        state = self.app.get_state(self.request)
        self.assertEqual(state["agenda"]["title"], "晚餐")
        self.assertEqual(state["agenda"]["remaining_seconds"],3600)

    def test_focus_preempt_resume_and_no_hidden_completion(self):
        self.app.command({"action":"start"},self.request)
        self.refresh_at(1700)
        state = self.app.build_state(self.key)
        self.assertEqual(state["status"],"paused")
        self.assertEqual(state["remaining_seconds"],1300)
        self.assertFalse(self.app.command({"action":"resume"},self.request)["ok"])
        self.refresh_at(5600)
        state = self.app.build_state(self.key)
        self.assertFalse(state["agenda"]["visible"])
        self.assertEqual(state["completed"],0)
        self.assertTrue(self.app.command({"action":"resume"},self.request)["ok"])
        self.assertEqual(self.app.timer.status,"running")

    def test_private_title_and_label_not_in_public_state(self):
        self.refresh_at(2000)
        public = json.dumps(self.app.build_state(),ensure_ascii=False)
        self.assertNotIn("晚餐",public)
        self.assertNotIn("DINNER",public)
        self.assertNotIn("fake-token",public)

    def test_follow_toggle_and_disconnect(self):
        self.assertTrue(self.app.follow_calendar({"enabled":False,"buffer":1},self.request)["ok"])
        self.assertIsNone(self.app.build_state()["agenda"])
        self.app.follow_calendar({"enabled":True,"buffer":1},self.request)
        self.refresh_at(1900)
        self.assertEqual(self.app.build_state(self.key)["agenda"]["mode"],"free")
        self.app.disconnect_calendar(self.request)
        self.assertIsNone(self.app.build_state()["agenda"])

    def test_data_failure_does_not_invent_event(self):
        self.now = 2000  # cached snapshot is stale; no refresh
        self.assertEqual(self.app.build_state(self.key)["agenda"]["mode"],"unavailable")


if __name__ == "__main__": unittest.main()

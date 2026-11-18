import datetime as dt
import io
import json
import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from calendar_api import normalize_events, plan_focus, fetch_google_events, CalendarSession, CalendarStore
from timer_core import FocusTimer


class CalendarTests(unittest.TestCase):
    def test_allocate_focus_rest_and_preparation(self):
        p = plan_focus([{"title":"Class","start":2500,"end":6000}], 1000, 25, 5, 5)
        self.assertEqual(p["focus_minutes"], 15)
        self.assertEqual(p["cutoff"], 2200)
        self.assertTrue(p["can_start"])

    def test_busy_and_insufficient_windows_do_not_start(self):
        self.assertFalse(plan_focus([{"start":900,"end":2000}],1000)["can_start"])
        self.assertFalse(plan_focus([{"start":1500,"end":2000}],1000)["can_start"])

    def test_free_calendar_and_finished_events(self):
        p = plan_focus([{"start":900,"end":1000}],1000,40,5,5)
        self.assertEqual(p["focus_minutes"],40)
        self.assertIsNone(p["cutoff"])

    def test_invalid_numbers(self):
        for value in (0, -1, True, 1.5, "25", 181):
            with self.assertRaises(ValueError): plan_focus([],1000,value)

    def test_declined_free_and_cancelled_are_ignored(self):
        event = {"summary":"Class","start":{"dateTime":"2026-11-16T14:00:00+08:00"},"end":{"dateTime":"2026-11-16T15:00:00+08:00"}}
        items = [event, dict(event,status="cancelled"),dict(event,transparency="transparent"),
                 dict(event,attendees=[{"self":True,"responseStatus":"declined"}]),dict(event,eventType="workingLocation")]
        self.assertEqual(len(normalize_events(items)),1)

    def test_all_day_end_is_exclusive(self):
        events = normalize_events([{"start":{"date":"2026-11-16"},"end":{"date":"2026-11-17"}}],"UTC")
        now = dt.datetime(2026,11,16,12,tzinfo=dt.timezone.utc).timestamp()
        self.assertFalse(plan_focus(events,now)["can_start"])
        self.assertTrue(plan_focus(events,events[0]["end"])["can_start"])

    def test_offsets_refer_to_same_instant(self):
        events = normalize_events([{"start":{"dateTime":"2026-11-16T14:00:00+08:00"},"end":{"dateTime":"2026-11-16T07:00:00Z"}}])
        self.assertEqual(events[0]["end"]-events[0]["start"],3600)

    def test_fetch_expands_recurrence_and_paginates(self):
        calls = []
        pages = [{"items":[],"nextPageToken":"next","timeZone":"UTC"},
                 {"items":[{"start":{"date":"2026-11-17"},"end":{"date":"2026-11-18"}}],"timeZone":"UTC"}]
        def opener(req,timeout):
            calls.append(req)
            self.assertEqual(timeout,8)
            return io.StringIO(json.dumps(pages.pop(0)))
        result = fetch_google_events("test-token-only",1000,opener)
        self.assertEqual(len(result),1)
        self.assertIn("singleEvents=true",calls[0].full_url)
        self.assertIn("pageToken=next",calls[1].full_url)
        self.assertNotIn("test-token-only",calls[0].full_url)
        self.assertEqual(calls[0].get_header("Authorization"),"Bearer test-token-only")

    def test_stale_or_failed_data_cannot_start(self):
        now = [1000]
        session = CalendarSession("test-token-only",3600,lambda token,now:[],lambda:now[0])
        session.refresh()
        self.assertTrue(session.snapshot()["plan"]["can_start"])
        now[0] += 121
        self.assertFalse(session.snapshot()["plan"]["can_start"])
        def failing(token,now): raise OSError("test")
        session.fetcher = failing
        session.refresh()
        self.assertFalse(session.snapshot()["fresh"])
        self.assertNotIn("test-token-only",json.dumps(session.snapshot()))

    def test_expired_token_and_disconnect(self):
        now = [1000]
        session = CalendarSession("test-token-only",100,lambda token,now:[],lambda:now[0])
        store = CalendarStore()
        key = store.add(session)
        session.refresh()
        now[0] += 100
        self.assertTrue(session.snapshot()["expired"])
        self.assertFalse(session.snapshot()["plan"]["can_start"])
        with self.assertRaises(ValueError): store.get("wrong-key")
        store.remove(key)
        self.assertEqual(session.token,"")
        with self.assertRaises(ValueError): store.get(key)

    def test_calendar_limit_still_applies_while_paused(self):
        clock = [1000]
        timer = FocusTimer(lambda:clock[0],lambda:clock[0])
        timer.command("start")
        timer.set_calendar_cutoff(1050)
        clock[0] += 10
        timer.command("pause")
        clock[0] += 40
        state = timer.snapshot()
        self.assertEqual(state["status"],"calendar_due")
        self.assertEqual(state["completed"],0)
        timer.command("resume")
        self.assertEqual(timer.status,"calendar_due")
        timer.command("reset")
        self.assertIsNone(timer.calendar_cutoff)

    def test_new_earlier_event_tightens_but_later_does_not_extend(self):
        timer = FocusTimer()
        timer.set_calendar_cutoff(2000)
        timer.set_calendar_cutoff(1900)
        timer.set_calendar_cutoff(3000)
        self.assertEqual(timer.calendar_cutoff,1900)


if __name__ == "__main__": unittest.main()

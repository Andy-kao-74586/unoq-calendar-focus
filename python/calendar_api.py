"""Google Calendar read-only API, ephemeral sessions and scheduling policy."""
import datetime as dt
import json
import math
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"


def event_timestamp(value, calendar_timezone):
    if "dateTime" in value:
        parsed = dt.datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(value.get("timeZone", calendar_timezone)))
    else:
        zone = dt.timezone.utc if calendar_timezone == "UTC" else ZoneInfo(calendar_timezone)
        parsed = dt.datetime.combine(dt.date.fromisoformat(value["date"]), dt.time(), zone)
    return parsed.timestamp()


def normalize_events(items, calendar_timezone="Asia/Taipei"):
    result = []
    for item in items:
        if item.get("status") == "cancelled" or item.get("transparency") == "transparent":
            continue
        if item.get("eventType") == "workingLocation":
            continue
        if any(a.get("self") and a.get("responseStatus") == "declined" for a in item.get("attendees", [])):
            continue
        # Malformed busy events fail the refresh rather than silently freeing time.
        start = event_timestamp(item["start"], calendar_timezone)
        end = event_timestamp(item["end"], calendar_timezone)
        if end <= start:
            raise ValueError("Invalid calendar event")
        result.append({"title": str(item.get("summary") or "未命名行程")[:160],
                       "start": start, "end": end, "all_day": "date" in item["start"]})
    return sorted(result, key=lambda event: (event["start"], event["end"]))


def plan_focus(events, now, focus_minutes=25, break_minutes=5, buffer_minutes=5):
    for value, maximum in [(focus_minutes, 180), (break_minutes, 60), (buffer_minutes, 60)]:
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError("請填入有效的整數分鐘：專注 1–180、休息及準備各 1–60。")
    events = sorted((e for e in events if e["end"] > now), key=lambda e: e["start"])
    current = next((e for e in events if e["start"] <= now), None)
    upcoming = next((e for e in events if e["start"] > now), None)
    result = {"current": current, "next": upcoming, "focus_minutes": 0,
              "break_minutes": break_minutes, "buffer_minutes": buffer_minutes,
              "cutoff": None, "can_start": False}
    if current:
        result["reason"] = "目前有忙碌行程，等行程結束後再安排。"
        return result
    available = focus_minutes
    if upcoming:
        result["cutoff"] = upcoming["start"] - buffer_minutes * 60
        available = math.floor((result["cutoff"] - now) / 60) - break_minutes
    selected = min(focus_minutes, available)
    if selected < 1:
        result["reason"] = "扣除休息與準備時間後，已不足一分鐘專注時間。"
        return result
    result.update(can_start=True, focus_minutes=selected,
                  reason=f"可安排 {selected} 分鐘專注＋{break_minutes} 分鐘休息。" if upcoming else
                  f"未來 24 小時沒有忙碌行程，安排 {selected} 分鐘專注。")
    return result


def fetch_google_events(token, now, opener=urllib.request.urlopen):
    iso = lambda stamp: dt.datetime.fromtimestamp(stamp, dt.timezone.utc).isoformat()
    params = {"timeMin": iso(now), "timeMax": iso(now + 86400), "singleEvents": "true",
              "orderBy": "startTime", "maxResults": 250, "timeZone": "Asia/Taipei",
              "fields": "items(summary,start,end,status,transparency,attendees(self,responseStatus),eventType),nextPageToken,timeZone"}
    items = []
    calendar_timezone = "Asia/Taipei"
    for _ in range(10):
        url = "https://www.googleapis.com/calendar/v3/calendars/primary/events?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
        with opener(req, timeout=8) as response:
            page = json.load(response)
        items.extend(page.get("items", []))
        calendar_timezone = page.get("timeZone", calendar_timezone)
        if not page.get("nextPageToken"):
            return normalize_events(items, calendar_timezone)
        params["pageToken"] = page["nextPageToken"]
    raise ValueError("Calendar page limit reached")


class CalendarSession:
    def __init__(self, token, expires_in, fetcher=fetch_google_events, clock=time.time):
        if not isinstance(token, str) or not 10 <= len(token) <= 4096 or any(c.isspace() for c in token):
            raise ValueError("Google 授權資料格式錯誤。")
        if type(expires_in) not in (int, float) or not math.isfinite(expires_in) or expires_in <= 0:
            raise ValueError("Google 授權有效時間錯誤。")
        self.token = token
        self.clock = clock
        self.expires_at = clock() + min(expires_in, 3600) - 30
        self.fetcher = fetcher
        self.lock = threading.RLock()
        self.fetch_lock = threading.Lock()
        self.events = []
        self.updated_at = None
        self.last_attempt = None
        self.error = "尚未同步"
        self.closed = False

    def close(self):
        with self.lock:
            self.closed = True
            self.token = ""
            self.events = []

    def refresh(self, force=False):
        # Serialize requests without blocking the timer or returning credentials.
        if not self.fetch_lock.acquire(blocking=False):
            return
        try:
            with self.lock:
                now = self.clock()
                if self.closed or now >= self.expires_at:
                    self.error = "Google 授權已到期，請重新連接日曆。"
                    return
                interval = 10 if force else 60
                if self.last_attempt is not None and now - self.last_attempt < interval:
                    return
                self.last_attempt = now
                token = self.token
            try:
                events = self.fetcher(token, now)
                error = None
            except urllib.error.HTTPError as exc:
                error = {401: "Google 授權已失效，請重新連接日曆。",
                         403: "Google 拒絕讀取：請確認已啟用 Calendar API 並同意唯讀權限。",
                         429: "Google 暫時限制請求，稍後再同步。"}.get(exc.code, "Google 日曆暫時無法讀取。")
                if exc.code == 401:
                    with self.lock:
                        self.expires_at = self.clock()
            except Exception:
                error = "日曆同步失敗，請確認板子可以上網；暫停提供新排程。"
            with self.lock:
                if self.closed:
                    return
                self.error = error
                if error is None:
                    self.events = events
                    self.updated_at = self.clock()
        finally:
            self.fetch_lock.release()

    def snapshot(self, focus=25, rest=5, buffer=5, complete=False):
        with self.lock:
            now = self.clock()
            expired = self.closed or now >= self.expires_at
            fresh = not expired and not self.error and self.updated_at is not None and now - self.updated_at < 120
            events = [dict(e) for e in self.events]
            plan = plan_focus(events, now, focus, rest, buffer)
            if not fresh:
                plan["can_start"] = False
                plan["reason"] = "授權已到期，請重新連接。" if expired else (self.error or "資料超過兩分鐘，請重新同步。")
            return {"fresh": bool(fresh), "expired": expired, "updated_at": self.updated_at,
                    "events": events if complete else events[:12], "plan": plan, "source": "Google Calendar API", "now": now}


class CalendarStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.sessions = {}

    def add(self, session):
        with self.lock:
            for key, old in list(self.sessions.items()):
                if old.closed or old.clock() >= old.expires_at:
                    old.close()
                    del self.sessions[key]
            if len(self.sessions) >= 4:
                raise ValueError("連線數已滿，請先中斷舊連線或重新啟動 App。")
            key = secrets.token_urlsafe(32)
            self.sessions[key] = session
            return key

    def get(self, key):
        with self.lock:
            session = self.sessions.get(key)
        if session is None or session.closed:
            raise ValueError("請先連接 Google 日曆。")
        return session

    def remove(self, key):
        with self.lock:
            session = self.sessions.pop(key, None)
        if session:
            session.close()

    def refresh_all(self):
        with self.lock:
            sessions = list(self.sessions.values())
        for session in sessions:
            session.refresh()

"""UNO Q Smart Calendar Timer: credentials stay in RAM, outside source and UI output."""
import threading
import time
from arduino.app_utils import App, Bridge
from arduino.app_bricks.web_ui import WebUI
from fastapi import HTTPException, Request
from timer_core import FocusTimer
from calendar_api import CalendarSession, CalendarStore
from agenda import agenda_scene, take_priority, scene_frame

timer = FocusTimer()
lock = threading.RLock()
calendar = CalendarStore()
active_calendar_key = None
active_buffer = 5
calendar_notice = ""
last_ack = None
bridge_error = "等待板上 LED 回應"
ui = WebUI()
follow_key = None
follow_buffer = 5
scene_identity = None
scene_since = 0


def current_scene():
    if not follow_key:
        return None
    try:
        result = calendar.get(follow_key).snapshot(complete=True)
    except ValueError:
        result = None
    return agenda_scene(result, time.time(), follow_buffer)


def local_request(request):
    allowed = {"http://localhost:7000", "http://127.0.0.1:7000"}
    origin = request.headers.get("origin")
    if origin and origin not in allowed:
        raise HTTPException(403, "請使用 localhost:7000 連線")
    if request.method == "POST" and (origin not in allowed or request.headers.get("x-focus-app") != "1"):
        raise HTTPException(403, "請由本機專注助手網頁操作")


def session_key(request):
    local_request(request)
    return request.headers.get("x-calendar-session", "")


def build_state(key="", internal=False):
    global scene_identity, scene_since, active_calendar_key, calendar_notice
    with lock:
        scene = current_scene()
        if scene:
            if scene["mode"] in ("event", "prepare") and timer.status in ("running", "paused"):
                active_calendar_key = None
                calendar_notice = "行程優先：原本的專注／休息已暫停，行程結束後可手動繼續。"
            take_priority(timer, scene)
        state = timer.snapshot()
        state["display_connected"] = last_ack is not None and time.monotonic() - last_ack < 4
        state["display_message"] = "LED 已連線" if state["display_connected"] else bridge_error
        state["calendar_notice"] = calendar_notice
        state["agenda"] = None
        if scene:
            scene["visible"] = scene["mode"] in ("event", "prepare") or state["status"] in ("idle", "ready", "calendar_due")
            identity = (follow_key, scene["mode"], scene["title"], scene["end"], scene["visible"])
            if identity != scene_identity:
                scene_identity, scene_since = identity, time.monotonic()
            scene["elapsed"] = max(0, time.monotonic() - scene_since)
            if not internal and key != follow_key:
                scene["title"] = "請在此分頁連接日曆以查看活動名稱"
                scene["label"] = "EVENT" if scene["mode"] == "event" else scene["label"]
            scene["frame"], scene["display_phase"] = scene_frame(scene, scene["elapsed"])
            state["agenda"] = scene
        return state


def get_state(request: Request):
    return build_state(request.headers.get("x-calendar-session", ""))


def command(body: dict, request: Request):
    global active_calendar_key, calendar_notice
    local_request(request)
    key = request.headers.get("x-calendar-session", "")
    with lock:
        try:
            action = body.get("action")
            scene = current_scene()
            if scene and scene["mode"] in ("event", "prepare") and action in ("start", "resume"):
                raise ValueError("日曆正在進行或準備行程。結束後可繼續專注，或先關閉自動跟隨。")
            was_idle = timer.status in ("idle", "ready")
            if action == "resume" and scene and scene["mode"] == "free":
                timer.calendar_cutoff = None
            timer.command(action, body)
            if scene and scene["mode"] == "free" and action in ("start", "resume"):
                timer.set_calendar_cutoff(scene["end"] - follow_buffer * 60 if scene["end"] else None)
            if action in ("reset", "configure") or (action == "start" and was_idle):
                active_calendar_key = None
                calendar_notice = ""
            return {"ok": True, "state": build_state(key)}
        except ValueError as error:
            return {"ok": False, "message": str(error), "state": build_state(key)}


def connect_calendar(body: dict, request: Request):
    global active_calendar_key, follow_key, follow_buffer
    local_request(request)
    try:
        buffer = body.get("buffer", 5)
        if type(buffer) is not int or not 1 <= buffer <= 60:
            raise ValueError("準備時間請輸入 1–60 的整數分鐘。")
        session = CalendarSession(body.get("access_token"), body.get("expires_in"))
        session.refresh()
        preview = session.snapshot()
        if not preview["fresh"]:
            session.close()
            return {"ok": False, "message": preview["plan"]["reason"]}
        old_key = request.headers.get("x-calendar-session", "")
        if old_key:
            calendar.remove(old_key)
        key = calendar.add(session)
        with lock:
            follow_key, follow_buffer = key, buffer
            if old_key and active_calendar_key == old_key:
                active_calendar_key = key
        return {"ok": True, "session": key, "calendar": preview}
    except ValueError as error:
        return {"ok": False, "message": str(error)}


def calendar_state(request: Request, focus: int = 25, rest: int = 5, buffer: int = 5):
    try:
        session = calendar.get(session_key(request))
        result = session.snapshot(focus, rest, buffer)
        result["following"] = follow_key == session_key(request)
        return {"ok": True, "calendar": result}
    except ValueError as error:
        return {"ok": False, "message": str(error)}


def refresh_calendar(request: Request):
    try:
        session = calendar.get(session_key(request))
        session.refresh(force=True)
        return {"ok": True}
    except ValueError as error:
        return {"ok": False, "message": str(error)}


def disconnect_calendar(request: Request):
    global active_calendar_key, calendar_notice, follow_key
    key = session_key(request)
    calendar.remove(key)
    with lock:
        if follow_key == key:
            follow_key = None
        if active_calendar_key == key:
            active_calendar_key = None
            calendar_notice = "日曆已中斷；保留本輪原訂停止時間。"
    return {"ok": True}


def follow_calendar(body: dict, request: Request):
    global follow_key, follow_buffer
    try:
        key = session_key(request)
        calendar.get(key)
        enabled, buffer = body.get("enabled"), body.get("buffer", 5)
        if type(enabled) is not bool or type(buffer) is not int or not 1 <= buffer <= 60:
            raise ValueError("準備時間請輸入 1–60 的整數分鐘。")
        with lock:
            if enabled:
                follow_key, follow_buffer = key, buffer
            elif follow_key == key:
                follow_key = None
        return {"ok": True, "state": build_state(key)}
    except ValueError as error:
        return {"ok": False, "message": str(error)}


def start_calendar(body: dict, request: Request):
    global active_calendar_key, active_buffer, calendar_notice
    try:
        key = session_key(request)
        session = calendar.get(key)
        focus, rest, buffer = body.get("focus", 25), body.get("rest", 5), body.get("buffer", 5)
        with lock:
            timer.tick()
            if timer.status not in ("idle", "ready"):
                raise ValueError("請先重設本輪，再套用行事曆安排。")
            result = session.snapshot(focus, rest, buffer)
            plan = result["plan"]
            if not plan["can_start"]:
                raise ValueError(plan["reason"])
            timer.command("configure", {"focus_minutes": plan["focus_minutes"], "break_minutes": rest})
            timer.command("start")
            timer.set_calendar_cutoff(plan["cutoff"])
            active_calendar_key, active_buffer = key, buffer
            calendar_notice = "已依主日曆安排；每分鐘同步，提早的行程會縮短本輪可用時間。"
            return {"ok": True, "state": build_state(key)}
    except ValueError as error:
        return {"ok": False, "message": str(error), "state": build_state()}


def calendar_worker():
    global calendar_notice
    while True:
        calendar.refresh_all()
        with lock:
            key, buffer = active_calendar_key, active_buffer
        if key:
            try:
                result = calendar.get(key).snapshot(buffer=buffer)
            except ValueError:
                result = None
            with lock:
                if active_calendar_key == key:
                    if not result or not result["fresh"]:
                        calendar_notice = "日曆尚未同步或授權已到期；保留原訂停止時間，無法掌握新變動。"
                    else:
                        plan = result["plan"]
                        cutoff = time.time() if plan["current"] else plan["cutoff"]
                        timer.set_calendar_cutoff(cutoff)
                        calendar_notice = "主日曆已同步；準備時間到時會停止本輪並提醒。"
        time.sleep(1)


ui.expose_api("GET", "/api/state", get_state)
ui.expose_api("POST", "/api/command", command)
ui.expose_api("POST", "/api/calendar/connect", connect_calendar)
ui.expose_api("GET", "/api/calendar", calendar_state)
ui.expose_api("POST", "/api/calendar/refresh", refresh_calendar)
ui.expose_api("POST", "/api/calendar/disconnect", disconnect_calendar)
ui.expose_api("POST", "/api/calendar/start", start_calendar)
ui.expose_api("POST", "/api/calendar/follow", follow_calendar)


def loop():
    global last_ack, bridge_error
    state = build_state(internal=True)
    mode = 1 if state["phase"] == "focus" else 2
    if state["status"] == "paused":
        mode += 2
    elif state["status"] == "idle":
        mode = 0
    elif state["status"] == "ready":
        mode = 5
    elif state["status"] == "calendar_due":
        mode = 6
    try:
        scene = state["agenda"]
        if scene and scene["visible"]:
            packed, _ = scene_frame(scene, scene["elapsed"])
            ack = Bridge.call("calendar_frame_v1", *packed)
        else:
            ack = Bridge.call("focus_display_v2", mode, state["remaining_seconds"], state["remaining_percent"], state["alert"])
        if ack is not True:
            raise RuntimeError("No display acknowledgement")
        with lock:
            last_ack = time.monotonic()
            bridge_error = "LED 回應逾時，正在重新連線"
    except Exception as error:
        with lock:
            last_ack = None
            bridge_error = "LED 尚未連線，請查看 Sketch 主控台"
        print("LED bridge:", type(error).__name__, flush=True)
    time.sleep(0.1)


threading.Thread(target=calendar_worker, daemon=True).start()
App.run(user_loop=loop)

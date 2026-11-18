"""Board-side timer. No Arduino dependencies, so timing can be tested on a PC."""
import math
import time


class FocusTimer:
    def __init__(self, clock=time.monotonic, wall_clock=time.time):
        self.clock = clock
        self.wall_clock = wall_clock
        self.focus_seconds = 25 * 60
        self.break_seconds = 5 * 60
        self.demo = False
        self.completed = 0
        self.demo_completed = 0
        self.alert_until = 0
        self.reset()

    def reset(self):
        self.phase = "focus"
        self.status = "idle"
        self.remaining = float(self.focus_seconds)
        self.deadline = None
        self.alert_until = 0
        self.calendar_cutoff = None

    def set_calendar_cutoff(self, cutoff):
        if cutoff is not None:
            if self.calendar_cutoff is None or cutoff < self.calendar_cutoff:
                self.calendar_cutoff = cutoff

    def tick(self):
        now = self.clock()
        if (self.calendar_cutoff is not None and self.status in ("running", "paused")
                and self.wall_clock() >= self.calendar_cutoff):
            self.status = "calendar_due"
            self.remaining = 0
            self.deadline = None
            self.alert_until = now + 3
            return
        if self.status != "running":
            return
        self.remaining = max(0.0, self.deadline - now)
        if self.remaining > 0:
            return
        self.alert_until = now + 3
        if self.phase == "focus":
            if self.demo:
                self.demo_completed += 1
            else:
                self.completed += 1
            self.phase = "break"
            self.remaining = float(self.break_seconds)
            # Start a full break when completion is processed; never invent missed cycles.
            self.deadline = now + self.remaining
        else:
            self.phase = "focus"
            self.status = "ready"
            self.remaining = float(self.focus_seconds)
            self.deadline = None

    def command(self, action, values=None):
        self.tick()
        values = values or {}
        if action == "configure":
            if self.status not in ("idle", "ready"):
                raise ValueError("請先重設，再修改時間。")
            demo = values.get("demo", False)
            if type(demo) is not bool:
                raise ValueError("示範模式格式錯誤。")
            focus = values.get("focus_minutes", 25)
            rest = values.get("break_minutes", 5)
            if (type(focus) is not int or not 1 <= focus <= 180 or
                    type(rest) is not int or not 1 <= rest <= 60):
                raise ValueError("專注請輸入 1–180 的整數，休息請輸入 1–60 的整數。")
            self.demo = demo
            self.focus_seconds = 30 if demo else focus * 60
            self.break_seconds = 10 if demo else rest * 60
            self.reset()
        elif action == "start":
            if self.status in ("idle", "ready"):
                self.calendar_cutoff = None
                self.status = "running"
                self.deadline = self.clock() + self.remaining
        elif action == "pause":
            if self.status == "running":
                self.status = "paused"
                self.deadline = None
        elif action == "resume":
            if self.status == "paused":
                self.status = "running"
                self.deadline = self.clock() + self.remaining
        elif action == "reset":
            self.reset()
        else:
            raise ValueError("無法識別的操作。")
        return self.snapshot()

    def snapshot(self):
        self.tick()
        total = self.focus_seconds if self.phase == "focus" else self.break_seconds
        return {
            "phase": self.phase, "status": self.status,
            "remaining_seconds": math.ceil(self.remaining),
            "remaining_percent": min(100, max(0, math.ceil(100 * self.remaining / total))),
            "focus_seconds": self.focus_seconds, "break_seconds": self.break_seconds,
            "demo": self.demo, "completed": self.completed,
            "demo_completed": self.demo_completed,
            "alert": self.clock() < self.alert_until,
            "calendar_cutoff": self.calendar_cutoff,
        }

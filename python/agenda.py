"""Calendar-driven scenes; pure logic, independent of the browser and MCU."""
import math
import re


def board_label(title):
    # Small matrix: readable ASCII labels; the web always retains the full title.
    tags = re.search(r"\[([A-Za-z0-9 -]{1,20})\]", title)
    if tags:
        return tags[1].upper()
    for words, label in [
        (("晚餐", "晚饭", "晚飯", "dinner"), "DINNER"),
        (("午餐", "午饭", "午飯", "lunch"), "LUNCH"),
        (("早餐", "breakfast"), "BREAKFAST"),
        (("會議", "会议", "討論", "讨论", "meeting"), "MEETING"),
        (("上課", "上课", "課程", "课程", "class"), "CLASS"),
        (("讀書", "读书", "讀", "复习", "複習", "study"), "STUDY"),
        (("運動", "运动", "健身", "跑步", "workout"), "SPORT"),
        (("睡覺", "睡觉", "睡眠", "sleep"), "SLEEP"),
    ]:
        if any(word in title.lower() for word in words):
            return label
    if title and all(ord(c) < 128 for c in title):
        return re.sub(r"[^A-Z0-9 -]", " ", title.upper()).strip()[:20] or "EVENT"
    return "EVENT"


def agenda_scene(snapshot, now, buffer=5):
    if not snapshot or not snapshot["fresh"]:
        return {"mode": "unavailable", "title": "日曆資料未更新", "label": "SYNC",
                "remaining_seconds": 0, "remaining_percent": 0, "end": None,
                "overlap": 0, "all_day_count": 0}
    # Use the complete cached list, not the UI's first twelve events.
    events = snapshot["events"]
    timed = sorted((e for e in events if not e.get("all_day") and e["end"] > now),
                   key=lambda e: (e["start"], e["end"], e["title"]))
    current = [e for e in timed if e["start"] <= now]
    upcoming = next((e for e in timed if e["start"] > now), None)
    all_day = sum(1 for e in events if e.get("all_day") and e["start"] <= now < e["end"])
    event = current[0] if current else upcoming
    mode = "event" if current else "prepare" if upcoming and upcoming["start"] - now <= buffer * 60 else "free"
    end = event["end"] if current else event["start"] if event else None
    remaining = max(0, math.ceil(end - now)) if end is not None else 0
    duration = event["end"] - event["start"] if current else buffer * 60
    return {"mode": mode, "title": event["title"] if event else "目前沒有定時行程",
            "label": board_label(event["title"]) if current else "READY" if mode == "prepare" else "FREE",
            "remaining_seconds": remaining,
            "remaining_percent": min(100, math.ceil(100 * remaining / duration)) if end else 0,
            "end": end, "overlap": len(current), "all_day_count": all_day}


def take_priority(timer, scene):
    """Preserve interrupted focus/rest; never resume it automatically after events."""
    if scene["mode"] in ("prepare", "event"):
        if timer.status in ("running", "paused"):
            timer.calendar_cutoff = None
            if timer.status == "running":
                timer.command("pause")
        elif timer.status == "calendar_due":
            timer.reset()


# Original 3x5 pixel font for ASCII marquee and numeric frames.
FONT = dict(zip("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ- ", [
    [7,5,5,5,7],[2,6,2,2,7],[7,1,7,4,7],[7,1,7,1,7],[5,5,7,1,1],
    [7,4,7,1,7],[7,4,7,5,7],[7,1,1,1,1],[7,5,7,5,7],[7,5,7,1,7],
    [2,5,7,5,5],[6,5,6,5,6],[7,4,4,4,7],[6,5,5,5,6],[7,4,6,4,7],
    [7,4,6,4,4],[7,4,5,5,7],[5,5,7,5,5],[7,2,2,2,7],[1,1,1,5,7],
    [5,5,6,5,5],[4,4,4,4,7],[5,7,7,5,5],[5,7,7,7,5],[7,5,5,5,7],
    [7,5,7,4,4],[7,5,5,7,1],[6,5,6,5,5],[7,4,7,1,7],[7,2,2,2,2],
    [5,5,5,5,7],[5,5,5,5,2],[5,5,7,7,5],[5,5,2,5,5],[5,5,2,2,2],
    [7,1,2,4,7],[0,0,7,0,0],[0,0,0,0,0],
]))


def scene_frame(scene, elapsed):
    """One full marquee pass, then five seconds of countdown, repeatedly."""
    label = scene["label"][:20]
    scroll_seconds = (len(label) * 4 + 13) * 0.18
    position = elapsed % (scroll_seconds + 5)
    pixels = [0] * 104

    def glyph(rows, left):
        for r, row in enumerate(rows):
            for c in range(3):
                if 0 <= left + c < 13 and row & (1 << (2-c)):
                    pixels[(r+1)*13+left+c] = 1

    scrolling = position < scroll_seconds
    if scrolling:
        left = 12 - int(position / 0.18)
        for i, char in enumerate(label):
            glyph(FONT.get(char, FONT[" "]), left + i*4)
    elif scene["end"] is None:
        for left in (1,5,9):
            glyph(FONT["-"], left)
    else:
        seconds = scene["remaining_seconds"]
        value = math.ceil(seconds/3600) if seconds >= 60000 else math.ceil(seconds/60) if seconds >= 60 else seconds
        if value >= 100:
            for char, left in zip(str(min(value,999)), (1,5,9)):
                glyph(FONT[char], left)
        else:
            for char, left in zip(f"{value:02}", (1,5)):
                glyph(FONT[char], left)
            glyph(FONT["H"] if seconds >= 60000 else [0,7,7,5,5] if seconds >= 60 else [0,3,4,2,6],9)
    # Middle top dots identify calendar mode; bottom row keeps event progress.
    pixels[5] = pixels[6] = pixels[7] = 1
    if scene["mode"] in ("event", "prepare"):
        for c in range(math.ceil(scene["remaining_percent"] * 13 / 100)):
            pixels[91+c] = 1
    packed = [sum(pixels[i*26+j] << j for j in range(26)) for i in range(4)]
    return packed, "marquee" if scrolling else "countdown"

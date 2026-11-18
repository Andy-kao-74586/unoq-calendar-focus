"use strict";
const $ = id => document.getElementById(id);
let state = null, online = false, busy = false, initialized = false;
let serial = 0, applied = 0;

function render(s) {
  state = s;
  const paused = s.status === "paused", running = s.status === "running";
  const idle = s.status === "idle" || s.status === "ready";
  $("time").textContent = `${String(Math.floor(s.remaining_seconds / 60)).padStart(2,"0")}:${String(s.remaining_seconds % 60).padStart(2,"0")}`;
  $("phase").textContent = paused ? "已暫停" : s.status === "ready" ? "一輪完成，準備好了" : s.status === "idle" ? "準備專注" : s.phase === "focus" ? "專注時間" : "休息時間";
  if (s.status === "calendar_due") $("phase").textContent = "該準備下一個行程了";
  const end = new Date(Date.now() + s.remaining_seconds * 1000).toLocaleTimeString("zh-TW", {hour:"2-digit", minute:"2-digit", hour12:false});
  $("end-time").textContent = running ? `剩餘時間 · 分：秒　｜　預計 ${end} 結束` : "剩餘時間 · 分：秒";
  $("demo").hidden = !s.demo;
  $("progress-fill").style.width = `${s.remaining_percent}%`;
  $("hint").textContent = paused ? "先喘口氣。繼續時會從剩餘時間開始。" : s.status === "ready" ? "休息結束，準備好再開始下一輪。" : s.status === "idle" ? "按下開始，把這段時間留給你要完成的事。" : s.phase === "focus" ? "倒數由板子執行，現在可以把這個網頁收起來。" : "放鬆眼睛、伸展一下。這段時間留給休息。";
  $("primary").textContent = running ? "暫停" : paused ? "繼續" : "開始專注";
  $("primary").disabled = !online || busy || s.status === "calendar_due";
  $("reset").disabled = !online || busy;
  $("apply").disabled = !online || busy || !idle;
  $("count").textContent = s.completed;
  $("demo-count").textContent = s.demo_completed;
  $("board-status").textContent = s.display_message;
  $("calendar-notice").textContent = s.calendar_notice || "";
  if (s.calendar_cutoff && ["running","paused"].includes(s.status)) {
    $("calendar-notice").textContent += ` 最晚 ${new Date(s.calendar_cutoff * 1000).toLocaleTimeString("zh-TW",{hour:"2-digit",minute:"2-digit",hour12:false})} 停止（暫停也不延後）。`;
  }
  if (s.status === "calendar_due") $("hint").textContent = "已保留行程前準備時間。本輪已停止；未完成的專注不計入輪數，請重設後安排下一輪。";
  document.body.classList.toggle("rest", s.phase === "break");
  $("connection").textContent = online ? "UNO Q 已連線" : "連線中斷";
  $("connection").classList.toggle("warning", !online);
  if (!initialized) {
    $("demo-setting").checked = s.demo;
    if (!s.demo) {
      $("focus-minutes").value = s.focus_seconds / 60;
      $("break-minutes").value = s.break_seconds / 60;
    }
    initialized = true;
  }
  const n = s.remaining_seconds >= 60 ? Math.ceil(s.remaining_seconds / 60) : s.remaining_seconds;
  $("matrix-number").textContent = s.status === "calendar_due" ? "!" : s.status === "ready" ? "✓" : `${String(n).padStart(2,"0")}${n >= 100 ? "" : s.remaining_seconds >= 60 ? "m" : "s"}`;
  const agenda = s.agenda;
  $("matrix-live").hidden = !agenda?.visible;
  if (agenda?.visible) {
    const seconds = agenda.remaining_seconds;
    const clock = `${String(Math.floor(seconds / 60)).padStart(2,"0")}:${String(seconds % 60).padStart(2,"0")}`;
    $("time").textContent = agenda.end === null ? "--:--" : clock;
    $("phase").textContent = agenda.mode === "event" ? `正在進行：${agenda.title}` : agenda.mode === "prepare" ? `準備出發：${agenda.title}` : agenda.mode === "free" ? "目前空閒" : "等待日曆同步";
    $("end-time").textContent = agenda.end === null ? "目前沒有可用的行程倒數" : `${agenda.mode === "event" ? "距離行程結束" : "距離下一個行程"} · 分：秒 ｜ ${new Date(agenda.end*1000).toLocaleTimeString("zh-TW",{timeZone:"Asia/Taipei",hour:"2-digit",minute:"2-digit",hour12:false})}`;
    $("hint").textContent = agenda.mode === "event" ? "依 Google 日曆自動倒數；板子輪播活動提示與剩餘時間。" : agenda.mode === "prepare" ? "準備時間到了。專注已暫停，行程開始時會自動切換。" : agenda.mode === "free" ? "現在沒有定時行程，可以開始專注；行程到來時會自動切換。" : "同步失敗或授權到期，已停止自動判斷活動；請重新同步或連接。";
    if (agenda.overlap > 1) $("hint").textContent += ` 目前有 ${agenda.overlap} 個重疊行程，優先顯示最早開始的一個。`;
    if (agenda.all_day_count) $("hint").textContent += " 今日另有全天忙碌活動，請參考下方日曆；不啟動全天倒數。";
    $("progress-fill").style.width = `${agenda.remaining_percent}%`;
    if (["event","prepare"].includes(agenda.mode)) {
      $("primary").disabled = true;
      $("primary").textContent = "日曆自動倒數中";
    }
    $("demo").hidden = true;
    $("matrix-number").textContent = agenda.label;
    $("matrix-live").innerHTML = Array.from({length:104}, (_,i) => `<i class="${((agenda.frame?.[Math.floor(i/26)] || 0) >>> (i%26)) & 1 ? "on" : ""}"></i>`).join("");
    document.body.classList.toggle("rest", false);
  }
  document.dispatchEvent(new CustomEvent("timer-state", {detail:s}));
}

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 4500);
  try {
    const headers = {"X-Focus-App":"1", "X-Calendar-Session":sessionStorage.getItem("focus-calendar-session") || "", ...options.headers};
    const response = await fetch(path, {...options, headers, cache:"no-store", signal:controller.signal});
    if (!response.ok) throw new Error("HTTP " + response.status);
    return await response.json();
  } finally { clearTimeout(timeout); }
}

function disconnected() {
  online = false;
  $("connection").textContent = "連線中斷";
  $("connection").classList.add("warning");
  $("primary").disabled = $("reset").disabled = $("apply").disabled = true;
  $("hint").textContent = "目前顯示最後收到的時間；正在重新連線，請確認 UNO Q 與 App 仍在執行。";
  $("board-status").textContent = "無法取得最新的 LED 狀態";
}

async function poll() {
  if (!busy) {
    const version = ++serial;
    try {
      const s = await request("api/state");
      if (version >= applied && !busy) { applied = version; online = true; render(s); }
    } catch (_) { if (version >= applied && !busy) disconnected(); }
  }
  setTimeout(poll, 500);
}

async function send(action, values = {}) {
  if (busy) return;
  busy = true;
  const version = ++serial;
  applied = version;
  if (state) render(state);
  $("error").textContent = "";
  try {
    const result = await request("api/command", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({action, ...values})
    });
    online = true;
    state = result.state;
    if (!result.ok) $("error").textContent = result.message;
  } catch (_) {
    disconnected();
    $("error").textContent = "未收到操作結果；重新連線後請先確認狀態。";
  } finally {
    busy = false;
    if (online && state) render(state);
  }
}

$("primary").addEventListener("click", () => {
  if (state) send(state.status === "running" ? "pause" : state.status === "paused" ? "resume" : "start");
});
$("reset").addEventListener("click", () => send("reset"));
$("settings").addEventListener("submit", event => {
  event.preventDefault();
  send("configure", {focus_minutes:Number($("focus-minutes").value), break_minutes:Number($("break-minutes").value), demo:$("demo-setting").checked});
});
poll();

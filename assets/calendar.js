"use strict";
(() => {
  const el = id => document.getElementById(id);
  const scope = "https://www.googleapis.com/auth/calendar.events.readonly";
  let key = sessionStorage.getItem("focus-calendar-session") || "";
  let last = null, working = false, fetching = false, googleToken = "", tokenClient = null;
  let generation = 0;
  const values = () => ({focus:Number(el("focus-minutes").value),rest:Number(el("break-minutes").value),buffer:Number(el("buffer-minutes").value)});
  const stamp = seconds => new Date(seconds * 1000).toLocaleString("zh-TW", {timeZone:"Asia/Taipei",month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit",hour12:false});
  const message = text => { el("calendar-message").textContent = text; };

  async function call(path, body) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const headers = {"X-Focus-App":"1", "X-Calendar-Session":key};
      if (body !== undefined) headers["Content-Type"] = "application/json";
      const response = await fetch(path, {method:body === undefined ? "GET" : "POST",headers,
        body:body === undefined ? undefined : JSON.stringify(body),cache:"no-store",signal:controller.signal});
      if (!response.ok) throw new Error(`連線失敗（HTTP ${response.status}）`);
      const result = await response.json();
      if (!result.ok) throw new Error(result.message || "日曆操作失敗");
      return result;
    } finally { clearTimeout(timeout); }
  }

  function updateButton() {
    const idle = state && ["idle","ready"].includes(state.status);
    el("calendar-start").disabled = working || !online || !idle || !last?.fresh || !last?.plan.can_start;
  }

  function show(data) {
    last = data;
    el("calendar-content").hidden = false;
    el("calendar-badge").textContent = data.fresh ? "Google 已同步" : data.expired ? "請重新授權" : "資料未更新";
    const p = data.plan;
    const event = p.current || p.next;
    el("event-caption").textContent = p.current ? "目前的忙碌行程" : "下一個忙碌行程";
    if (typeof data.following === "boolean") el("follow-calendar").checked = data.following;
    el("next-event-title").textContent = event ? event.title : "未來 24 小時沒有忙碌行程";
    el("next-event-time").textContent = event ? `${p.current ? "進行中 · " : ""}${event.all_day ? "全天 · " : ""}${stamp(event.start)} — ${stamp(event.end)}` : "範圍：Google 主日曆";
    el("plan-text").textContent = p.reason;
    message(data.fresh ? "每分鐘更新主日曆；已讀取的行程會由板子自動準時切換與倒數。" : p.reason);
    el("calendar-updated").textContent = data.updated_at ? `最後同步：${stamp(data.updated_at)}（台北時間）。只讀取，不修改 Google 行程。` : "尚未同步";
    updateButton();
  }

  async function loadCalendar() {
    if (!key || fetching) return;
    fetching = true;
    const g = generation;
    try {
      const q = new URLSearchParams(values());
      const result = await call("api/calendar?" + q);
      if (g === generation) show(result.calendar);
    } catch (error) {
      if (g === generation) { last = null; updateButton(); message(error.message); el("calendar-badge").textContent = "無法同步"; }
    } finally { fetching = false; }
  }

  el("load-google").addEventListener("click", () => {
    if (!["http://localhost:7000","http://127.0.0.1:7000"].includes(location.origin)) {
      message("Google 登入請改用 http://localhost:7000 開啟此 App。"); return;
    }
    if (window.google?.accounts?.oauth2) { el("connect-google").disabled = false; return; }
    el("load-google").disabled = true;
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => { el("connect-google").disabled = false; message("登入元件已就緒。填入用戶端 ID 後，按連接 Google 日曆。"); };
    script.onerror = () => { script.remove(); el("load-google").disabled = false; message("無法載入 Google 登入元件，請確認電腦網路。"); };
    document.head.appendChild(script);
  });

  el("connect-google").addEventListener("click", () => {
    const id = el("google-client-id").value.trim();
    if (!id.endsWith(".apps.googleusercontent.com")) { message("請貼上 Google Cloud 的 Web OAuth 用戶端 ID。"); return; }
    working = true;
    updateButton();
    el("connect-google").disabled = true;
    tokenClient = google.accounts.oauth2.initTokenClient({
      client_id:id, scope, include_granted_scopes:false,
      error_callback:() => { working = false; el("connect-google").disabled = false; updateButton(); message("登入視窗已關閉或被阻擋，可再按一次連接。"); },
      callback:async response => {
        try {
          if (response.error || !google.accounts.oauth2.hasGrantedAllScopes(response, scope)) throw new Error("未取得日曆唯讀權限，請重新授權。");
          googleToken = response.access_token;
          message("正在由 UNO Q 讀取 Google 日曆…");
          const result = await call("api/calendar/connect", {access_token:response.access_token,expires_in:Number(response.expires_in),buffer:Number(el("buffer-minutes").value)});
          generation++;
          key = result.session;
          el("follow-calendar").checked = true;
          sessionStorage.setItem("focus-calendar-session", key);
          el("google-settings").open = false;
          el("google-client-id").value = "";
          show(result.calendar);
          await loadCalendar();
        } catch (error) { message(error.message); }
        finally { working = false; el("connect-google").disabled = false; updateButton(); }
      }
    });
    tokenClient.requestAccessToken({prompt:"consent"});
  });

  el("calendar-refresh").addEventListener("click", async () => {
    if (working) return;
    working = true; updateButton();
    try { message("正在同步…"); await call("api/calendar/refresh", {}); await loadCalendar(); }
    catch (error) { message(error.message); last = null; }
    finally { working = false; updateButton(); }
  });

  el("calendar-disconnect").addEventListener("click", async () => {
    if (working) return;
    working = true; updateButton();
    try {
      await call("api/calendar/disconnect", {});
      if (googleToken && window.google?.accounts?.oauth2) google.accounts.oauth2.revoke(googleToken, () => {});
      googleToken = ""; key = ""; last = null; generation++;
      sessionStorage.removeItem("focus-calendar-session");
      el("calendar-content").hidden = true;
      el("calendar-badge").textContent = "未連接日曆";
      message("已中斷本 App 的日曆連線，暫存資料已清除。");
    } catch (error) { message(error.message); }
    finally { working = false; updateButton(); }
  });

  el("calendar-start").addEventListener("click", async () => {
    if (working || busy) return;
    working = true; busy = true; applied = ++serial;
    if (state) render(state);
    updateButton();
    try {
      const result = await call("api/calendar/start", values());
      state = result.state; online = true;
      el("demo-setting").checked = false;
      el("focus-minutes").value = state.focus_seconds / 60;
      message("已依 Google 日曆安排並開始專注。");
    } catch (error) { message(error.message); }
    finally { working = false; busy = false; if (state) render(state); updateButton(); }
  });

  for (const id of ["focus-minutes","break-minutes","buffer-minutes"]) {
    el(id).addEventListener("input", () => { last = null; updateButton(); });
    el(id).addEventListener("change", loadCalendar);
  }
  async function saveFollow() {
    if (!key) return;
    try {
      await call("api/calendar/follow", {enabled:el("follow-calendar").checked,buffer:Number(el("buffer-minutes").value)});
      await loadCalendar();
    } catch (error) { message(error.message); await loadCalendar(); }
  }
  el("follow-calendar").addEventListener("change", saveFollow);
  el("buffer-minutes").addEventListener("change", saveFollow);
  document.addEventListener("timer-state", updateButton);
  setInterval(loadCalendar, 5000);
  loadCalendar();
})();

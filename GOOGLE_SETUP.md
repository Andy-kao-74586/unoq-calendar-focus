# Google 日曆連線設定（Windows＋UNO Q）

## 先更新專題

1. 在 Arduino App Lab 停止舊的 UNO Q Focus Timer，保留它作為備份。
2. 匯入 `unoq-smart-calendar-timer.zip`，開啟新的 **UNO Q 智慧日曆計時器**，按 Run。
3. 用 Edge 或 Chrome 開啟 **http://localhost:7000**。此版會將 App Lab 開啟的 `http://127.0.0.1:7000` 自動轉到 `localhost`，統一 Google 登入來源；舊版需手動更換網址。兩個來源的瀏覽器暫存各自獨立，切換後若顯示未連接，請重新連接 Google 日曆。
4. 先測試一般／示範模式；板子應顯示 `25m` 或 `30s`，不是舊版的大片進度條。

Google 登入需要電腦連網；Google API 請求由 UNO Q 發出，所以板子也要能上網。USB 可以連上網頁，不代表板子已連上 Internet。

## 在 Google Cloud 建立自己的 OAuth 用戶端

這是讓「你做的專題」取得你同意的日曆唯讀權限，不是把 Google 密碼寫進程式。

1. 在自己的瀏覽器進入 https://console.cloud.google.com/ ，建立或選擇專題用的專案，例如 `unoq-calendar-focus`。
2. 到「API 和服務 → 程式庫」，搜尋 **Google Calendar API** 並啟用。
3. 開啟 **Google Auth Platform**。若尚未初始化，依畫面建立應用程式，名稱可填 `UNO Q 智慧日曆計時器`，支援及聯絡電子郵件填自己的帳號。
4. 在 **Audience／目標對象** 選 External（個人 Google 帳號），保持 Testing／測試狀態，將實際登入的 Google 帳號加入 Test users／測試使用者。學校 Workspace 帳號可能受管理員限制；遇到限制可用自己的個人帳號。
5. 在 **Data Access／資料存取** 加入以下唯讀範圍：

   `https://www.googleapis.com/auth/calendar.events.readonly`

6. 在 **Clients／用戶端 → Create client**，應用程式類型選 **Web application／網頁應用程式**。這版使用瀏覽器登入，請不要選 Desktop app。
7. 在 **Authorized JavaScript origins／已授權的 JavaScript 來源** 加入：

   ```text
   http://localhost
   http://localhost:7000
   ```

   這版採 popup token 流程，不需要填重新導向 URI。登入網頁必須用上面相同的 `localhost:7000` 來源。
8. 建立後複製 **Client ID／用戶端 ID**。不需要下載 JSON、不需要 Client secret，也不需要 API key。

用戶端 ID 是公開識別碼，不是密碼；為配合課程提交習慣，本專題仍不把你的實際值寫進程式、截圖或 repo。Google access token 才是敏感授權資料，不要貼進對話或主控台。

## 在專題網頁授權

1. 展開「設定 Google 日曆連線」。
2. 將自己的 Web 用戶端 ID 貼入遮罩輸入框。
3. 按「載入 Google 登入元件」，等它顯示就緒。
4. 按「連接 Google 日曆」，在 Google 的視窗登入，允許讀取日曆活動。
5. 網頁顯示「Google 已同步」，並顯示主日曆下一個忙碌行程。

這版只讀取你登入帳號的 **主日曆（primary）**；其他訂閱、課表或另外建立的日曆尚未合併。測試活動請先放在主日曆。

## 第一次測試

1. 在 Google 日曆自己的主日曆建立一個約 20–30 分鐘後的測試行程，名稱可用「專題測試」，設為忙碌。
2. 回到專題按「重新同步」。設定希望專注 25 分鐘、休息 5 分鐘、準備 5 分鐘。
3. 看建議是否自動縮短，按「依建議開始專注」。例如距離行程剛好 25 分鐘，會安排最多 15 分鐘專注＋5 分鐘休息＋5 分鐘準備；操作花了幾秒可能向下取整少一分鐘，這是預留足夠時間的設計。
4. 測試暫停、繼續。自動跟隨模式會在準備時間暫停專注，行程開始後切換成活動倒數。
5. 若要短時間驗證行程提醒，可另設 2–3 分鐘後的測試行程，將希望專注、休息、準備各設 1 分鐘；剩餘時間不足完整三分鐘時，應拒絕開始。要確實開始，可先建立 4 分鐘後的行程。
6. v2 也可不啟動專注，直接等行程到來：準備時板上顯示 READY 跑馬燈，晚餐活動開始後顯示 DINNER 與剩餘時間輪播。行程結束回到空閒或保留暫停的專注，未完成的專注不加計輪數。更多驗收步驟見 README。

一般示範模式仍是 30 秒／10 秒；「依日曆安排」會切回正式分鐘模式。影片請用真實 API 同步的測試活動，不要把示範倒數稱為日曆資料。

## 常見問題

| 畫面／問題 | 檢查 |
|---|---|
| origin_mismatch | 用 `http://localhost:7000` 開啟；OAuth 用戶端類型為 Web；已授權來源包含完整埠號。新設定可能需要稍候再試 |
| access_denied／無法登入 | 確認登入的是已加入 Test users 的帳號，並同意唯讀範圍；學校帳號需符合管理員政策 |
| Google 拒絕讀取（403） | 確認 Calendar API 已在建立 Client ID 的同一專案啟用，已授予範圍 |
| 網頁能開，日曆同步失敗 | 確認 UNO Q 的 Wi-Fi／Internet，不只檢查 Windows 的網路 |
| 登入視窗沒有出現 | 允許 localhost 的彈出式視窗，再按連接 |
| Google 已同步但沒看到測試行程 | 確認活動在登入帳號的主日曆、24 小時內、設為忙碌，且未拒絕邀請 |
| 顯示授權到期 | 再填入 Client ID 並按連接授權；本版不儲存長期 refresh token |
| 重啟 App 後要求連接 | 正常，板子記憶體中的授權資料已清除 |

## 帳號與資料

Google access token 只放在網頁／UNO Q 的記憶體；不寫入磁碟，不出現在 API 回應、主控台、Git 或 ZIP。瀏覽器 sessionStorage 只保留本機隨機連線代碼，供同一分頁重新整理後讀回日曆；它也是暫時授權資訊，勿拍攝開發者工具。

「中斷日曆連線」會清除板子暫存資料。若網頁尚保留 Google token，也會嘗試撤回授權；重新整理後 token 已不在瀏覽器記憶體，完整撤權可到 Google 帳號的第三方連線設定移除此專題。登入有效期屆滿需重新授權。日曆功能限 localhost USB 轉送使用。

## 官方依據

- Google Identity Services token 模型：https://developers.google.com/identity/oauth2/web/guides/use-token-model
- Web 用戶端與 localhost 來源設定：https://developers.google.com/identity/oauth2/web/guides/get-google-api-clientid
- Calendar events.list：https://developers.google.com/workspace/calendar/api/v3/reference/events/list

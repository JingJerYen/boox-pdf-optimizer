# Google Drive 自動化教學：以 boox-pdf-optimizer 為例

## 整體架構

```
BOOX 裝置
  └─ 匯出 PDF → 同步到 Google Drive 資料夾
                        │
                        │ (每 10 分鐘輪詢)
                        ▼
              Google Apps Script
              ├─ 發現新 PDF？
              └─ 呼叫 Cloud Function（帶 file_id + upload_token）
                          │
                          ▼
                    Cloud Function
                    ├─ 用 service account 下載 PDF
                    ├─ 壓縮（pdfsimpler）
                    └─ 用 upload_token（你的帳號）上傳回 Drive
                          │
                          ▼
              Drive 資料夾出現 xxx_optimized.pdf
```

---

## 三個元件詳解

### 1. Google Apps Script

**是什麼：**
Google 提供的雲端腳本環境，用 JavaScript 寫，跑在 Google 的伺服器上。可以直接操作 Google 服務（Drive、Gmail、Sheets 等）。

**權限模型：**
Apps Script 跑在**你的 Google 帳號**下，繼承你所有的權限。你能看到的 Drive 檔案它都能讀寫，不需要額外授權。

**觸發方式：**
- 時間驅動（每 N 分鐘）
- 表單提交、文件開啟等事件

**費用：**
完全免費。每天有 90 分鐘執行時間上限，我們每分鐘跑不到 1 秒，一天才用 24 分鐘，遠低於上限。

**限制：**
- 單次執行最長 6 分鐘（所以我們每次只處理一個 PDF）
- 無法安裝 Python 套件，不能直接做 PDF 壓縮

---

### 2. Google Cloud Function

**是什麼：**
GCP 提供的無伺服器運算環境。可以跑 Python/Node.js/Go 等，支援安裝任意套件（pikepdf 等）。有請求才啟動，沒用就不計費。

**權限模型：**
Cloud Function 跑在 **service account** 下，不是你的個人帳號。Service account 是一個機器帳號，預設沒有任何 Drive 權限，需要明確授予。

本專案用的 service account：
```
309929667153-compute@developer.gserviceaccount.com
```
（Compute Engine 預設 service account，Cloud Functions gen2 使用這個）

**重要限制：**
Service account 沒有 Google Drive 儲存空間配額，**無法建立新的 Drive 檔案**。因此本專案的架構是：Cloud Function 壓縮完後，用 Apps Script 傳來的 OAuth token（代表你的帳號）直接呼叫 Drive API 上傳，繞過 service account 的配額限制。

**費用：**
每月免費額度：
- 200 萬次呼叫
- 40 萬 GB-秒運算時間
- 每次壓縮約 1 GB × 60 秒 = 60 GB-秒

→ 每月可以免費壓縮約 6,600 個 PDF，實際用量遠低於此。

**需要綁信用卡**，但在免費額度內不會被收費。建議設 $1 預算上限防止意外。

---

### 3. Google Drive API

**是什麼：**
讓程式存取 Drive 檔案的 REST API。

**兩種存取方式：**

| 方式 | 使用者 | 權限範圍 |
|---|---|---|
| Apps Script (`DriveApp`) | 你的帳號 | 你所有的 Drive |
| Drive API + service account | 機器帳號 | 只有明確分享給它的檔案 |

**費用：**
Drive API 本身免費，沒有用量費用。

---

## 權限流程圖

```
你的帳號
  ├─ Apps Script → 直接讀寫你的 Drive（不需要分享）
  └─ Drive 資料夾「共用」給 service account
              │
              ▼
        service account
          └─ Cloud Function 用這個帳號下載 PDF（唯讀）
```

**為什麼需要共用給 service account：**
Cloud Function 用 service account 存取 Drive，而 Drive 的權限是基於「誰存取」，不是「誰部署」。就算你部署了 Cloud Function，它用的是機器帳號，不是你的帳號，所以需要明確分享。

---

## 設定步驟（完整版）

### Step 1：建立 GCP 專案並啟用帳單

1. 去 [console.cloud.google.com](https://console.cloud.google.com)
2. 建立新專案（記下 Project ID）
3. 去 [console.cloud.google.com/billing](https://console.cloud.google.com/billing) 建立帳單帳戶並連結專案
4. 建議設 $1 預算上限：Billing > Budgets & alerts > Create budget

### Step 2：部署 Cloud Function

在 Google Cloud Shell（[shell.cloud.google.com](https://shell.cloud.google.com)）：

```bash
# 上傳 boox-deploy.tar.gz 後
tar xzf boox-deploy.tar.gz
chmod +x deploy.sh
./deploy.sh YOUR_PROJECT_ID
```

記下輸出的：
- Cloud Function URL
- Auth Token
- Service Account email（格式：`PROJECT_NUMBER-compute@developer.gserviceaccount.com`）

### Step 3：分享 Drive 資料夾給 service account

1. 在 Google Drive 找到 BOOX 同步的資料夾
2. 右鍵 > 共用
3. 加入 service account email，權限設為**編輯者**

> 注意：service account 只需要讀取權限下載 PDF，上傳由 Apps Script 負責。
> 但 Drive API 分享時沒有「唯讀」選項，給編輯者也沒關係（它沒有儲存配額，反正無法上傳）。

### Step 4：設定 Apps Script

1. 去 [script.google.com](https://script.google.com)，建立新專案
2. 把 `apps_script/Code.gs` 的內容貼進去，存檔
3. 設定 Script Properties（專案設定 > 指令碼屬性）：

| 屬性 | 值 |
|---|---|
| `FOLDER_ID` | Drive 資料夾 URL 最後那段 ID |
| `CLOUD_FUNCTION_URL` | deploy 印出的 URL |
| `AUTH_TOKEN` | deploy 印出的 Token |

> **FOLDER_ID 取得方式：**
> 打開資料夾，URL 長這樣：
> `https://drive.google.com/drive/folders/1aBcDeFg...?hl=zh-TW`
> 只取 `?` 前面那段：`1aBcDeFg...`

4. 加觸發器：觸發條件 > 新增 > `watchFolder` > 時間驅動 > 每 10 分鐘

> **為什麼用 10 分鐘？** 壓縮一份 126 MB 的 PDF 約需 2-3 分鐘。若觸發間隔太短（如 1 分鐘），同一個 PDF 可能被重複送出多次壓縮。10 分鐘確保上一次壓縮已完成並上傳，避免重複處理。

### Step 5：測試

在 Apps Script 編輯器手動執行 `watchFolder`，看執行記錄是否出現：
```
Optimizing: xxx.pdf
Done: xxx.pdf → 29.6 MB (4.2x smaller)
```

然後去 Drive 資料夾確認 `xxx_optimized.pdf` 出現。

---

## 常見問題

### 404 File not found
Drive 資料夾沒有正確分享給 service account，或分享的 email 錯誤。確認用的是 `PROJECT_NUMBER-compute@developer.gserviceaccount.com`（注意是 project **number** 不是 project ID）。

### 403 storageQuotaExceeded
Service account 沒有 Drive 儲存空間，不能直接上傳檔案。需要讓 Apps Script 負責上傳（本專案已改為此架構）。

### Apps Script 執行超時
單次執行超過 6 分鐘會被強制中斷。本專案每次只處理一個 PDF，下一個留給下一次觸發。

### Cloud Function timeout
預設 540 秒。126 MB 的 PDF 壓縮約需 2-3 分鐘，在限制內。若有更大的 PDF 可調高 timeout（最大 3600 秒）。

---

## 費用試算

每月壓縮 100 個 BOOX PDF（約 130 MB 每個）：

| 元件 | 用量 | 費用 |
|---|---|---|
| Apps Script | 每天 2.4 分鐘（遠低於 90 分鐘上限） | $0 |
| Cloud Function 呼叫次數 | 100 次（免費額度 200 萬次） | $0 |
| Cloud Function 運算時間 | 100 × 60s × 1GB = 6,000 GB-秒（免費額度 40 萬） | $0 |
| Drive API | 無用量費用 | $0 |
| **總計** | | **$0** |

# Jumping Point!! 株Tube 文字起こし自動収集・Googleドライブ保存パイプライン

YouTubeチャンネル「Jumping Point!! の株Tube」（チャンネルID: `UCgDa6dxD3jPElw6eCvL1T2g`）の新着動画を毎日定時に検知し、タイムスタンプ付き文字起こしテキスト（`YYYYMMDD_<動画タイトル>.txt`）を生成して Googleドライブへ自動保存する **GitHub Actions + Python** パイプラインです。

---

## ディレクトリ構成

```text
.
├── .github/
│   └── workflows/
│       └── daily_transcribe.yml    # 毎日定時実行ワークフロー（JST 21:00）
├── scripts/
│   ├── main.py                     # エントリポイント（新着検知〜文字起こし〜Drive保存〜履歴更新）
│   ├── youtube_fetcher.py          # 新着動画一覧取得＆文字起こし取得・フォーマット整形
│   └── drive_uploader.py           # Google Drive API によるファイルアップロード処理
├── data/
│   └── processed_ids.json          # 処理済み動画ID管理ファイル
├── requirements.txt                # 必要なPythonパッケージ一覧
├── .env.example                    # ローカル動作確認用の環境変数サンプル
└── README.md                       # 本ドキュメント
```

---

## 出力ファイル仕様

- **ファイル名**: `YYYYMMDD_<動画タイトル>.txt`（公開日は日本時間 JST 基準）
- **本文フォーマット**:
  ```text
  0:000 秒ジャンピンポイントカムチューブ...

  1:081 分 8 秒お願いします。...
  ```

---

## セットアップ手順

### 1. Google Cloud サービスアカウントの作成
1. [Google Cloud Console](https://console.cloud.google.com/) にログインし、新しいプロジェクトを作成（または既存プロジェクトを選択）します。
2. 左メニューの「APIとサービス」→「ライブラリ」から **Google Drive API** を検索し、「有効にする」をクリックします。
3. 「APIとサービス」→「認証情報」→「認証情報を作成」→「**サービスアカウント**」を選択し、任意の名前（例: `youtube-transcribe-bot`）で作成します。
4. 作成したサービスアカウントの詳細画面から「キー」タブを開き、「鍵を追加」→「新しい鍵を作成」→「**JSON**」を選択してキーファイル（`.json`）をダウンロードします。
5. サービスアカウントのメールアドレス（`xxx@xxx.iam.gserviceaccount.com`）を控えておきます。

### 2. Googleドライブ対象フォルダの共有設定
1. Googleドライブで文字起こしテキストを保存したいフォルダを開きます（または新規作成します）。
2. フォルダのURL末尾にある **フォルダID**（`https://drive.google.com/drive/folders/<ここがフォルダID>`）を控えます。
3. フォルダの「共有」メニューを開き、手順1で控えた **サービスアカウントのメールアドレス** を「**編集者**」権限で追加・共有します。

### 3. GitHub Secrets への登録
本リポジトリをGitHubへプッシュした後、リポジトリページの「Settings」→「Secrets and variables」→「Actions」→「New repository secret」から以下の2つを登録します。

| Secret名 | 設定する値 |
| :--- | :--- |
| `GDRIVE_SERVICE_ACCOUNT_JSON` | 手順1でダウンロードしたJSONキーファイルの**中身（全文）** |
| `GDRIVE_FOLDER_ID` | 手順2で控えたGoogleドライブの**フォルダID** |

※ GitHub Actions 上で `data/processed_ids.json` を自動コミットするため、リポジトリの「Settings」→「Actions」→「General」→「Workflow permissions」が `Read and write permissions`（またはワークフロー内の `permissions: contents: write` が許可されている状態）であることを確認してください。

### 4. 初回手動実行（`workflow_dispatch`）での確認手順
1. GitHubリポジトリの「Actions」タブを開きます。
2. 左側一覧から「**Jumping Point 株Tube 文字起こし自動収集・Drive保存**」を選択します。
3. 右側の「**Run workflow**」ボタンをクリックします。
   - まずはテストとして `dry_run` を `true` にして実行すると、Driveアップロードと履歴コミットを行わずに新着検知と文字起こし整形の動作を確認できます。
   - 問題なければ `dry_run` を `false`（デフォルト）にして再度実行し、Googleドライブに `.txt` ファイルが保存され、`data/processed_ids.json` が自動コミットされることを確認してください。
4. 以降は毎日 **日本時間 21:00（UTC 12:00）** に自動実行されます。

---

## ローカル環境での動作確認

```bash
# 仮想環境作成・パッケージインストール
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 環境変数ファイルを作成して値を設定
cp .env.example .env

# ドライラン（Driveへはアップロードしない）
python scripts/main.py --dry-run --output-dir ./tmp_out
```

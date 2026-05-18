# 匿名化フローシステム

このプロジェクトは、クローズ環境で文章を匿名化し、DMZ 経由で JSON 形式のプロンプトを渡し、Open 環境で整形結果を JSON に戻してクローズ環境へ復元するための基本システムです。

## 構成

- `anonymizer/`: 匿名化機能と復元機能を実装した Python モジュール
- `webapp/`: Django ベースの簡易 Web UI
- `requirements.txt`: Python 依存関係

## 使い方

### 1. 開発環境セットアップ

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Django サーバー起動

```bash
cd webapp
python manage.py migrate
python manage.py runserver
```

ブラウザで `http://127.0.0.1:8000/` にアクセスし、匿名化 JSON を生成できます。

### 3. CLI で匿名化・復元

#### 匿名化

```bash
python -m anonymizer.cli anonymize --template "入院時サマリー" --text "患者は38歳女性..." --output prompt.json
```

#### 復元

```bash
python -m anonymizer.cli restore --result result.json --restore-metadata restore_meta.json --output restored.txt
```

### 4. DMZ JSON 形式

- 入力プロンプト: `prompt_YYYYMMDD_HHMM.json`
- 出力結果: `result_YYYYMMDD_HHMM.json`

## 補足

このシステムは仕様書に基づき、JSON ベースの DMZ 受け渡しと復元用メタデータ保存を前提にしています。ChatGPT への貼り付けは `prompt_text` を利用すると運用しやすいです。

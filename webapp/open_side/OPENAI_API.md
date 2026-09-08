# OpenSideの回答生成

`webapp/manage.py` で起動するサイトの `/open/` → プロンプト一覧から取り込んだプロンプトを開きます。
プロンプト入力欄を編集して「回答を生成」を押すと、OpenAI APIの回答が右側（狭い画面では下側）に表示されます。
回答を確認・編集し、レビュワーを入力して「生成文章をDMZへ送信」で返却します。
生成のみではDMZへの送信は行いません。生成結果は画面上に保持され、再読み込みすると消えます。

サーバー環境変数または `webapp/.env` に設定してください。

```dotenv
OPENAI_API_KEY=your-api-key
OPENAI_OPEN_MODEL=gpt-4.1-mini
```

APIキーはブラウザーへ渡しません。モデルは `OPENAI_OPEN_MODEL` で変更できます。
入力上限は30,000文字、出力上限は4,096トークン、タイムアウトは60秒です。
OpenSideのログイン・ネットワーク制限と取り込み元の所有者権限を適用します。
操作ログには生成成否とモデルを記録し、プロンプト・回答・APIキーは記録しません。

公式仕様: https://developers.openai.com/api/reference/python/resources/responses/methods/create

テスト（API呼び出しはモック）:

```sh
cd webapp
../.venv/bin/python manage.py test open_side
```

# チャットでの画像生成

「回答の種類」で「画像を生成」を選ぶと、質問と添付をResponses APIの
image_generationツールに渡し、返されたPNGを回答欄に表示する。
PNG原本とJPEG変換版を本人認証付きURLから取得できる。
回答文の画像化・PDFプレビューは別の機能として維持する。

## 設定・運用

- `python manage.py migrate` で生成画像の保存用フィールドを追加する。
- 既存のOPENAI_API_KEYと、画像生成ツール対応のチャットモデルを使用する。
  API組織の画像生成利用権限が必要。画像モデルはgpt-image-1、
  1024x1024、medium、PNGで固定。
- 通信タイムアウトは180秒。プロキシ・Webサーバー側のタイムアウトも合わせる。
  自動再試行は無効化し、重複生成の発生を抑える。
- 生成画像はUsageLogのJSONフィールドにBase64で保存する。
  DB容量・バックアップ容量は画像の利用量に応じて増える。
- Responsesの通常トークン料金に加えて、生成画像1枚につき社内管理用概算
  0.20 USDを計上する。Django設定 `AI_IMAGE_ESTIMATED_USD` で変更可能。
  この値はAPIの正確な請求額でも上限保証でもない。
  画面・ログのimage_cost_estimatedに概算であることを明示する。
  既存の月額制限にはこの概算を含む記録額を使用する。

公式仕様: https://developers.openai.com/api/docs/guides/tools-image-generation

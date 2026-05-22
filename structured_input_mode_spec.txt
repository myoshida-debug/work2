# 匿名化前データ入力方式選択機能 仕様書

## 1. 目的

CloseSide の匿名化入力画面に、次の 2 種類の入力方式を追加する。

1. テンプレート項目入力
2. フリー入力

これにより、利用者は従来どおり自由記述で匿名化前本文を入力できる一方、プロンプトテンプレートの出力構成に沿った入力欄を使って、抜け漏れの少ない匿名化前データを作成できるようにする。

本仕様書は Codex に読み込ませ、既存 Django アプリケーションを修正するための実装資料である。

---

## 2. 現行仕様の前提

### 2.1 現行フロー

現行の CloseSide 匿名化入力では、`/close/anonymize/` で `AnonymizeForm` によりテンプレートと本文を受け取る。

処理順は以下のとおり。

1. `anonymize_text()` を実行する
2. 匿名化後本文と `restore_map` を取得する
3. `source_id` を生成する
4. `build_prompt_payload()` でプロンプト JSON を作成する
5. `RestoreMetadata` を保存する
6. `Prompt` を保存する
7. 画面に匿名化前後の差分、ラベル一覧、JSON を表示する

今回の修正では、この処理順の前段に「入力方式選択」と「テンプレート項目入力の本文化」を追加する。

### 2.2 変更しない範囲

以下の既存仕様は原則変更しない。

- `anonymize_text()` の匿名化処理
- `restore_map` の生成・保存方式
- `build_prompt_payload()` の基本構造
- DMZ 出力方式
- OpenSide の取り込み・ChatGPT 用表示
- OpenSide から CloseSide への返却 JSON
- CloseSide 返却取り込み・復元処理

---

## 3. 機能概要

### 3.1 入力方式

匿名化画面に `input_mode` を追加する。

| 値 | 表示名 | 内容 |
|---|---|---|
| `structured` | テンプレート項目入力 | 文書種別ごとに定義された項目欄へ入力し、匿名化前本文を自動生成する |
| `free` | フリー入力 | 従来どおり 1 つの本文欄に自由入力する |

初期値は `free` とする。

理由：既存運用との互換性を優先し、利用者が従来の入力方法をそのまま使えるようにするため。

---

## 4. 画面仕様

### 4.1 対象画面

対象画面は CloseSide の匿名化画面。

- URL: `/close/anonymize/`
- 主な修正対象候補:
  - `webapp/close_side/views.py`
  - `webapp/anonymizer_app/forms.py`
  - `webapp/anonymizer_app/templates/anonymizer_app/index.html` または現行の匿名化入力テンプレート

実際のテンプレートファイル名は既存実装に合わせて確認すること。

### 4.2 画面構成

匿名化画面の入力エリアを以下の構成にする。

```text
文書種別
[select]

入力方式
( ) テンプレート項目入力
( ) フリー入力

[テンプレート項目入力エリア]
  ※ input_mode=structured のとき表示

[フリー入力エリア]
  ※ input_mode=free のとき表示

[匿名化する]
```

### 4.3 表示切り替え

- `input_mode=structured` の場合
  - テンプレート項目入力エリアを表示する
  - フリー入力エリアは非表示、または折りたたむ
- `input_mode=free` の場合
  - フリー入力エリアを表示する
  - テンプレート項目入力エリアは非表示、または折りたたむ

JavaScript で即時切り替えする。
JavaScript が無効でも POST 時に `input_mode` を見て処理できるようにする。

### 4.4 文書種別変更時の項目更新

文書種別を変更すると、テンプレート項目入力の入力欄を変更する。

実装方法は次のいずれかとする。

#### 案 A: サーバー描画方式

文書種別変更後にフォームを再表示し、該当する項目欄を描画する。

#### 案 B: クライアント埋め込み方式

画面表示時に全テンプレート分の field schema を JSON として埋め込み、JavaScript で表示を切り替える。

推奨は案 B。
理由：既存の単一画面での入力体験を保ちやすく、文書種別変更のたびに再読み込みが不要なため。

---

## 5. テンプレート項目定義

### 5.1 新規定義ファイル

以下の新規ファイルを追加する。

```text
webapp/anonymizer_app/template_input_schemas.py
```

このファイルに、文書種別ごとの入力項目を定義する。

### 5.2 データ構造

```python
TEMPLATE_INPUT_SCHEMAS = {
    "入院時サマリー": [
        {"key": "chief_complaint", "label": "主訴", "required": True},
        {"key": "present_history", "label": "現病歴", "required": True},
        {"key": "past_history", "label": "既往歴", "required": False},
        {"key": "family_social_history", "label": "家族歴・生活歴", "required": False},
        {"key": "medication_allergy", "label": "内服薬・アレルギー", "required": False},
        {"key": "physical_findings", "label": "入院時身体所見", "required": False},
        {"key": "test_findings", "label": "検査所見", "required": False},
        {"key": "clinical_assessment", "label": "臨床評価", "required": False},
        {"key": "admission_purpose", "label": "入院目的", "required": True},
        {"key": "treatment_plan", "label": "治療方針", "required": True},
        {"key": "notes", "label": "留意点", "required": False},
    ],
    "退院時サマリー": [
        {"key": "admission_reason", "label": "入院理由", "required": True},
        {"key": "hospital_course", "label": "入院後経過", "required": True},
        {"key": "treatments", "label": "実施治療", "required": False},
        {"key": "main_test_results", "label": "主要検査結果", "required": False},
        {"key": "discharge_status", "label": "退院時状態", "required": True},
        {"key": "discharge_medication", "label": "退院処方・継続治療", "required": False},
        {"key": "future_plan", "label": "今後の方針", "required": True},
    ],
    "中間サマリー": [
        {"key": "background", "label": "入院目的・背景", "required": True},
        {"key": "course", "label": "現在までの経過", "required": True},
        {"key": "current_status", "label": "現在の状態", "required": True},
        {"key": "problems", "label": "問題点", "required": False},
        {"key": "treatment_response", "label": "治療・対応", "required": False},
        {"key": "future_plan", "label": "今後の方針", "required": True},
    ],
    "インシデントレポート": [
        {"key": "datetime_place", "label": "発生日時・場所", "required": True},
        {"key": "incident_level", "label": "インシデントレベル", "required": False},
        {"key": "event_detail", "label": "発生内容", "required": True},
        {"key": "discovery", "label": "発見経緯", "required": False},
        {"key": "patient_impact", "label": "患者への影響", "required": False},
        {"key": "response", "label": "実施対応", "required": True},
        {"key": "prevention", "label": "再発防止策", "required": False},
    ],
    "委員会議事録": [
        {"key": "overview", "label": "開催概要", "required": True},
        {"key": "agenda", "label": "議題", "required": True},
        {"key": "discussion", "label": "主な議論", "required": True},
        {"key": "decisions", "label": "決定事項", "required": False},
        {"key": "next_actions", "label": "今後の対応", "required": False},
    ],
    "看護計画": [
        {"key": "patient_status", "label": "患者の状態", "required": True},
        {"key": "nursing_problem", "label": "看護問題", "required": True},
        {"key": "nursing_goal", "label": "看護目標", "required": True},
        {"key": "observation", "label": "観察項目", "required": False},
        {"key": "care", "label": "ケア内容", "required": False},
        {"key": "evaluation", "label": "評価視点", "required": False},
    ],
}
```

### 5.3 未定義テンプレートの扱い

文書種別に対応する schema がない場合は、以下のように扱う。

- `structured` は選択可能でもよいが、項目は `本文` 1 項目のみとする
- または `structured` を非活性にし、`free` のみ利用可能にする

推奨は「`本文` 1 項目にフォールバック」。
理由：テンプレート追加時に画面が壊れにくいため。

---

## 6. フォーム仕様

### 6.1 追加フィールド

`AnonymizeForm` に以下を追加する。

```python
input_mode = forms.ChoiceField(
    choices=[
        ("structured", "テンプレート項目入力"),
        ("free", "フリー入力"),
    ],
    initial="free",
    required=True,
)

structured_input = forms.JSONField(required=False)
```

既存の本文フィールドは維持する。
仮に既存フィールド名が `text` または `body` の場合、その名前を維持すること。

### 6.2 POST データ形式

#### フリー入力

```json
{
  "template_type": "入院時サマリー",
  "input_mode": "free",
  "text": "患者は..."
}
```

#### テンプレート項目入力

HTML フォームでは次のように送信してよい。

```text
structured__chief_complaint=...
structured__present_history=...
structured__past_history=...
```

ビュー側で `structured__` prefix を持つ POST 値を集めて辞書化する。

内部表現は以下。

```json
{
  "template_type": "入院時サマリー",
  "input_mode": "structured",
  "structured_input": {
    "chief_complaint": "...",
    "present_history": "...",
    "past_history": "..."
  }
}
```

---

## 7. 匿名化前本文生成仕様

### 7.1 関数追加

以下の関数を追加する。

```text
webapp/anonymizer_app/structured_input.py
```

```python
def build_source_text_from_structured_input(template_type: str, structured_input: dict) -> str:
    ...
```

### 7.2 生成形式

テンプレート項目入力の場合、匿名化前本文は以下の形式で生成する。

```text
【主訴】
入力内容

【現病歴】
入力内容

【既往歴】
記載なし
```

### 7.3 空欄の扱い

空欄の扱いは以下とする。

| 項目種別 | 空欄時の扱い |
|---|---|
| required=True | エラーにする |
| required=False | 見出しごと省略する |

ただし、利用者が明示的に「記載なし」と入力した場合は、そのまま出力する。

### 7.4 バリデーション

`input_mode=structured` の場合、schema 上 `required=True` の項目が空欄であればエラーにする。

エラーメッセージ例：

```text
「主訴」は必須項目です。入力するか、「記載なし」と明記してください。
```

### 7.5 本文生成例

入力：

```json
{
  "chief_complaint": "発熱、食欲低下",
  "present_history": "2026年5月上旬より発熱あり。",
  "past_history": "高血圧",
  "treatment_plan": "抗菌薬投与を開始予定。"
}
```

出力：

```text
【主訴】
発熱、食欲低下

【現病歴】
2026年5月上旬より発熱あり。

【既往歴】
高血圧

【治療方針】
抗菌薬投与を開始予定。
```

この生成本文を既存の `anonymize_text()` に渡す。

---

## 8. ビュー処理仕様

### 8.1 処理分岐

`/close/anonymize/` の POST 処理で以下の分岐を行う。

```python
input_mode = request.POST.get("input_mode", "free")

template_type = form.cleaned_data["template_type"]

if input_mode == "structured":
    structured_input = collect_structured_input(request.POST)
    validate_structured_input(template_type, structured_input)
    source_text = build_source_text_from_structured_input(template_type, structured_input)
else:
    source_text = form.cleaned_data["text"]
```

以降は既存処理と同じ。

```python
anonymized_text, restore_map, metadata = anonymize_text(source_text, template_type=template_type)
prompt_payload = build_prompt_payload(...)
```

実際の `anonymize_text()` の戻り値形式は既存実装に合わせること。

### 8.2 保存メタデータ

`RestoreMetadata.prompt_json.metadata` に以下を追加する。

```json
{
  "input_mode": "structured",
  "structured_input": {
    "chief_complaint": "...",
    "present_history": "..."
  }
}
```

ただし、DMZ に出す `prompt_json` に匿名化前の個人情報を含む `structured_input` を入れてはいけない。

重要：`structured_input` は匿名化前データであり、CloseSide 内部保存専用とする。

そのため実装方針は以下のいずれかとする。

#### 推奨方針

- `RestoreMetadata` に保存する内部メタデータには `input_mode` のみ保存する
- `structured_input` の生データは保存しない
- 必要であれば、匿名化後の構造化データのみ `prompt_json.metadata.structured_input_labels` として保存する

#### 保存する場合の制約

`structured_input` を保存する場合は、絶対に DMZ 出力 JSON へ含めないこと。
CloseSide DB 内のみで保持すること。

### 8.3 DMZ JSON への追加項目

DMZ に出力するプロンプト JSON には、以下のみ追加してよい。

```json
{
  "metadata": {
    "input_mode": "structured"
  }
}
```

匿名化前の各項目値は含めない。

---

## 9. UI 実装詳細

### 9.1 HTML の基本構造

```html
<div class="panel">
  <div class="panel-header">
    <h3 class="panel-title">入力方式</h3>
  </div>
  <div class="panel-body">
    <label>
      <input type="radio" name="input_mode" value="structured">
      テンプレート項目入力
    </label>
    <label>
      <input type="radio" name="input_mode" value="free" checked>
      フリー入力
    </label>
  </div>
</div>

<div id="structured-input-panel" class="panel" hidden>
  <div class="panel-header">
    <h3 class="panel-title">テンプレート項目入力</h3>
  </div>
  <div class="panel-body" id="structured-input-fields"></div>
</div>

<div id="free-input-panel" class="panel">
  <div class="panel-header">
    <h3 class="panel-title">フリー入力</h3>
  </div>
  <div class="panel-body">
    <textarea name="text"></textarea>
  </div>
</div>
```

### 9.2 JavaScript

- `input_mode` の radio 変更時に表示を切り替える
- 文書種別 select の変更時に `structured-input-fields` を再描画する
- field schema は `json_script` などで安全に埋め込む

例：

```django
{{ template_input_schemas|json_script:"template-input-schemas" }}
```

### 9.3 CSS

既存の `.panel`, `.panel-header`, `.panel-body`, `textarea`, `input`, `select` を利用する。
新規 CSS は最小限にする。

必要に応じて以下を追加する。

```css
.structured-field {
  margin-bottom: 14px;
}

.required-mark {
  color: var(--danger);
  font-weight: 800;
}
```

---

## 10. モデル変更方針

### 10.1 原則

最小実装ではモデル変更は不要。

理由：

- 最終的に匿名化処理へ渡すのは本文文字列である
- 既存の `RestoreMetadata.prompt_json` に `input_mode` を含められる
- 既存フローを壊さず実装できる

### 10.2 将来拡張

将来的に入力方式や入力項目を履歴検索したい場合は、以下のフィールド追加を検討する。

```python
input_mode = models.CharField(max_length=20, default="free")
structured_input_summary = models.JSONField(default=dict, blank=True)
```

ただし、`structured_input_summary` に匿名化前データを保存する場合は個人情報を含むため、DMZ 出力対象外であることを厳守する。

---

## 11. テンプレート管理との関係

現行では、テンプレート正本は以下に配置されている。

```text
webapp/anonymizer_app/prompt_templates/*.txt
```

また、DB の `Template` は txt ファイルを同期したキャッシュである。

今回の入力項目 schema は、プロンプトテンプレート本文から毎回自動抽出するのではなく、まずは `template_input_schemas.py` で明示定義する。

理由：

- プロンプト本文の表記ゆれに影響されにくい
- Codex による実装修正が単純になる
- 医療文書ごとの required 設定を明示できる

将来的には、テンプレート管理画面から入力項目 schema も編集できるようにしてよい。

---

## 12. セキュリティ・個人情報の扱い

### 12.1 基本方針

テンプレート項目入力で入力される各項目は、匿名化前データである。
そのため、取り扱いは従来のフリー入力本文と同じく CloseSide 内に限定する。

### 12.2 禁止事項

- 匿名化前の `structured_input` を OpenSide に渡さない
- 匿名化前の `structured_input` を DMZ JSON に含めない
- OpenSide のログに匿名化前データを保存しない

### 12.3 DMZ に渡してよいもの

- 匿名化後本文
- 匿名化後本文を埋め込んだ `prompt_text`
- `input_mode` など個人情報を含まないメタデータ

---

## 13. テスト観点

### 13.1 フリー入力

- `input_mode=free` で従来どおり匿名化できる
- 既存の本文欄の内容が `anonymize_text()` に渡る
- 既存の DMZ JSON 構造が壊れない
- 既存の復元処理が動作する

### 13.2 テンプレート項目入力

- `input_mode=structured` で項目欄が表示される
- 文書種別ごとに正しい入力欄が表示される
- 必須項目が空の場合にエラーになる
- 任意項目が空の場合は本文生成時に省略される
- 入力された項目が `【項目名】\n内容` 形式で本文化される
- 生成本文が `anonymize_text()` に渡る
- 匿名化後本文に見出し構造が残る
- `restore_map` が従来どおり作られる

### 13.3 DMZ・復元

- DMZ 出力 JSON に匿名化前の `structured_input` が含まれない
- OpenSide で `prompt_text` が表示される
- OpenSide 返却 JSON を CloseSide で取り込める
- `restore_map` により復元できる

### 13.4 後方互換性

- 既存の手動プロンプト作成画面に影響しない
- 既存テンプレート一覧・編集画面に影響しない
- 既存履歴画面に影響しない
- JavaScript 無効時でも `free` 入力は動作する

---

## 14. 実装タスク一覧

### 14.1 新規ファイル

- `webapp/anonymizer_app/template_input_schemas.py`
- `webapp/anonymizer_app/structured_input.py`

### 14.2 修正ファイル候補

- `webapp/anonymizer_app/forms.py`
  - `input_mode` を追加
  - 必要に応じて structured 入力用の受け口を追加

- `webapp/close_side/views.py`
  - POST 時に `input_mode` を判定
  - structured 入力を収集・検証
  - structured 入力から匿名化前本文を生成
  - 生成本文を既存匿名化処理に渡す

- `webapp/anonymizer_app/templates/anonymizer_app/index.html`
  - 入力方式 radio を追加
  - structured 入力欄を追加
  - free 入力欄との表示切り替えを追加

実際の匿名化画面テンプレート名が異なる場合は、既存 URL `/close/anonymize/` で利用されているテンプレートを修正する。

### 14.3 任意修正

- `OperationLog` の詳細 JSON に `input_mode` を記録する
- 匿名化結果画面に「入力方式」を表示する
- 履歴画面に「入力方式」を表示する

---

## 15. 受け入れ条件

以下を満たせば完了とする。

1. `/close/anonymize/` で入力方式を選択できる
2. `free` を選択した場合、従来どおり自由入力本文を匿名化できる
3. `structured` を選択した場合、文書種別ごとの項目入力欄が表示される
4. `structured` の必須項目が空欄の場合、匿名化前にエラー表示される
5. `structured` の入力内容が見出し付き本文に変換される
6. 変換後本文が既存の匿名化処理に渡る
7. DMZ JSON に匿名化前の構造化入力値が含まれない
8. OpenSide への受け渡し、返却、CloseSide での復元が従来どおり動く
9. 既存のフリー入力運用が壊れない

---

## 16. Codex 向け実装指示

次の方針で修正すること。

1. 既存の匿名化・DMZ・復元フローは変更しない。
2. `/close/anonymize/` の入力前処理として `input_mode` を追加する。
3. `input_mode=free` の場合は従来処理を維持する。
4. `input_mode=structured` の場合のみ、テンプレート項目入力を本文化してから既存匿名化処理に渡す。
5. 匿名化前の structured 入力値を DMZ JSON に含めない。
6. UI は既存の `.panel` 系デザインに合わせる。
7. モデル変更は原則行わず、必要な場合のみ最小限にする。
8. 可能であれば単体テストまたは Django TestCase を追加する。

---

## 17. 補足：実装例の疑似コード

```python
def collect_structured_input(post_data):
    result = {}
    for key, value in post_data.items():
        if key.startswith("structured__"):
            field_key = key.replace("structured__", "", 1)
            result[field_key] = value.strip()
    return result


def validate_structured_input(template_type, structured_input):
    fields = get_template_input_schema(template_type)
    errors = []
    for field in fields:
        if field.get("required") and not structured_input.get(field["key"], "").strip():
            errors.append(f"{field['label']} は必須項目です。")
    return errors


def build_source_text_from_structured_input(template_type, structured_input):
    fields = get_template_input_schema(template_type)
    blocks = []
    for field in fields:
        value = structured_input.get(field["key"], "").strip()
        if not value:
            continue
        blocks.append(f"【{field['label']}】\n{value}")
    return "\n\n".join(blocks)
```

---

## 18. 今回の仕様の要点

今回の変更は「匿名化前本文をどう作るか」の選択肢を増やすものであり、匿名化後のプロンプト生成、DMZ 連携、OpenSide 表示、返却、復元の流れは変えない。

- フリー入力：従来どおり
- テンプレート項目入力：項目別入力 → 見出し付き本文生成 → 既存匿名化処理

この設計により、既存運用を維持しながら、プロンプトの項目に沿った抜け漏れの少ない匿名化前データ作成が可能になる。

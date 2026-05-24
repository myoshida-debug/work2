from django import forms

from .models import Patient
from .template_input_schemas import get_template_input_schema


TEMPLATE_CHOICES = [
    ('入院時サマリー', '入院時サマリー'),
    ('精神科入院時サマリー', '精神科入院時サマリー'),
    ('精神科退院時サマリー（医師用）', '精神科退院時サマリー（医師用）'),
    ('看護入院時サマリー', '看護入院時サマリー'),
    ('看護中間サマリー', '看護中間サマリー'),
    ('看護退院時サマリー', '看護退院時サマリー'),
    ('OT評価サマリー', 'OT評価サマリー'),
    ('PSW退院支援サマリー', 'PSW退院支援サマリー'),
    ('精神科訪問看護サマリー', '精神科訪問看護サマリー'),
    ('退院時サマリー', '退院時サマリー'),
    ('中間サマリー', '中間サマリー'),
    ('インシデントレポート', 'インシデントレポート'),
    ('委員会議事録', '委員会議事録'),
    ('看護計画', '看護計画'),
]

INPUT_MODE_CHOICES = [
    ('structured', 'テンプレート項目入力'),
    ('free', 'フリー入力'),
    ('voice', '録音・文字起こし入力'),
]


class AnonymizeForm(forms.Form):
    template = forms.ChoiceField(label='書類テンプレート')
    input_mode = forms.ChoiceField(
        label='入力方式',
        choices=INPUT_MODE_CHOICES,
        initial='free',
        widget=forms.RadioSelect,
    )
    text = forms.CharField(
        label='入力テキスト',
        widget=forms.Textarea(attrs={'rows': 8}),
        required=False,
    )
    transcript_text = forms.CharField(
        label='文字起こし結果',
        widget=forms.Textarea(attrs={'rows': 8}),
        required=False,
    )
    transcript_source = forms.CharField(required=False, widget=forms.HiddenInput, initial='manual_input')
    structured_input = forms.JSONField(required=False, widget=forms.HiddenInput)
    reviewer = forms.CharField(label='レビュワー', required=False)
    patient_id = forms.CharField(
        label='患者ID',
        required=False,
        widget=forms.TextInput(attrs={'autocomplete': 'off', 'placeholder': '患者ID'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # txt files are the canonical template source; DB is refreshed as a cache.
        try:
            from .prompt_template_store import list_template_sources, sync_templates_to_db

            sync_templates_to_db()
            sources = list_template_sources()
            choices = [(source.name, source.name) for source in sources] or TEMPLATE_CHOICES
        except Exception:
            choices = TEMPLATE_CHOICES
        self.fields['template'].choices = choices


class PatientForm(forms.ModelForm):
    birth_date = forms.DateField(
        label='生年月日',
        required=False,
        input_formats=['%Y-%m-%d', '%Y/%m/%d', '%Y年%m月%d日'],
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    class Meta:
        model = Patient
        fields = [
            'patient_id',
            'surname',
            'given_name',
            'kana_surname',
            'kana_given_name',
            'birth_date',
            'sex',
            'primary_diagnosis',
        ]
    widgets = {
        'patient_id': forms.TextInput(attrs={'autocomplete': 'off'}),
        'surname': forms.TextInput(attrs={'autocomplete': 'off'}),
        'given_name': forms.TextInput(attrs={'autocomplete': 'off'}),
        'kana_surname': forms.TextInput(attrs={'autocomplete': 'off'}),
        'kana_given_name': forms.TextInput(attrs={'autocomplete': 'off'}),
        'sex': forms.Select(),
        'primary_diagnosis': forms.Textarea(attrs={'rows': 3}),
    }


class PatientSearchForm(forms.Form):
    patient_id = forms.CharField(label='ID', required=False, widget=forms.TextInput(attrs={'autocomplete': 'off'}))
    kana = forms.CharField(label='ふりかな', required=False, widget=forms.TextInput(attrs={'autocomplete': 'off'}))
    sex = forms.ChoiceField(label='性別', required=False, choices=[('', 'すべて')] + Patient.SEX_CHOICES)
    birth_date = forms.DateField(
        label='生年月日',
        required=False,
        input_formats=['%Y-%m-%d', '%Y/%m/%d', '%Y年%m月%d日'],
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    primary_diagnosis = forms.CharField(
        label='主病名',
        required=False,
        widget=forms.TextInput(attrs={'autocomplete': 'off'}),
    )
    sort = forms.ChoiceField(
        label='ソート',
        required=False,
        choices=[
            ('patient_id', 'ID'),
            ('kana', 'ふりかな'),
            ('sex', '性別'),
            ('birth_date', '生年月日'),
        ],
    )


class PatientImportForm(forms.Form):
    csv_file = forms.FileField(label='CSVファイル', widget=forms.FileInput(attrs={'accept': '.csv,text/csv'}))


class DMZImportForm(forms.Form):
    filename = forms.CharField(label='取り込むファイル名', required=True, help_text='例: prompt_20260518_0830.json')
    # テスト用：ローカルDMZフォルダーから読み込み


class DMZListForm(forms.Form):
    # テスト用：ローカルDMZフォルダーを使用するため入力不要
    pass


class DMZExportForm(forms.Form):
    source_id = forms.CharField(label='送るデータの source_id', required=True)
    # テスト用：ローカルDMZフォルダーへ書き込み


class ChatGPTResultForm(forms.Form):
    result_text = forms.CharField(
        label='ChatGPT 生成結果',
        widget=forms.Textarea(attrs={'rows': 14}),
        required=True,
    )
    reviewer = forms.CharField(label='レビュワー', required=False)


class DMZResultImportForm(forms.Form):
    filename = forms.CharField(label='取り込む返却ファイル名', required=True)


class PromptForm(forms.Form):
    name = forms.CharField(label='プロンプト名', max_length=255)
    content = forms.CharField(label='プロンプト内容', widget=forms.Textarea(attrs={'rows':8}))


class TemplateForm(forms.Form):
    template_type = forms.ChoiceField(choices=TEMPLATE_CHOICES, label='テンプレート種別')
    name = forms.CharField(label='テンプレート名', max_length=255)
    description = forms.CharField(
        label='説明',
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
    )
    basic_content = forms.CharField(
        label='基本テンプレート',
        widget=forms.Textarea(attrs={'rows':16}),
        required=False,
    )
    additional_content = forms.CharField(
        label='追加部分',
        widget=forms.Textarea(attrs={'rows':8}),
        required=False,
    )


class TemplateInputDefaultsForm(forms.Form):
    def __init__(self, *args, template_type: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.template_type = template_type
        for field in get_template_input_schema(template_type):
            key = str(field['key'])
            label = str(field['label'])
            self.fields[f'default__{key}'] = forms.CharField(
                label=label,
                required=False,
                widget=forms.Textarea(attrs={'rows': 3, 'style': 'min-height: 120px; width: 100%;'}),
            )
            self.fields[f'required__{key}'] = forms.ChoiceField(
                label=f'{label}の必須設定',
                required=False,
                choices=[
                    ('', '既定'),
                    ('true', '必須'),
                    ('false', '任意'),
                ],
                widget=forms.Select(attrs={'style': 'width: 160px;'}),
            )

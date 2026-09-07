from django import forms

from .models import Patient, PatientLinkedPerson, Staff, Template
from .template_input_schemas import get_template_input_schema
from .prompt_template_store import list_template_sources, sync_templates_to_db


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


def _is_admin_user(user) -> bool:
    return bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False))


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
    text_file = forms.FileField(
        label='ファイル',
        required=False,
        widget=forms.FileInput(attrs={
            'accept': '.txt,.md,.csv,.log,.json,.xlsx,.docx,.pdf,text/plain,application/json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/pdf',
        }),
    )
    text_file_snapshot = forms.CharField(required=False, widget=forms.HiddenInput())
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
            sync_templates_to_db()
            source_filenames = {source.source_filename for source in list_template_sources()}
            templates = Template.objects.filter(
                is_active=True,
                source_filename__in=source_filenames,
            ).order_by('sort_order', 'template_type', 'name', 'id')
            choices = [(template.name, template.name) for template in templates]
            if not choices:
                choices = [('', '有効なテンプレートがありません')]
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
            'is_admin_only',
        ]
        labels = {
            'patient_id': '患者ID',
            'surname': '姓',
            'given_name': '名',
            'kana_surname': 'ふりかな姓',
            'kana_given_name': 'ふりかな名',
            'sex': '性別',
            'primary_diagnosis': '主病名',
            'is_admin_only': '管理者のみ閲覧可',
        }
        widgets = {
            'patient_id': forms.TextInput(attrs={'autocomplete': 'off'}),
            'surname': forms.TextInput(attrs={'autocomplete': 'off'}),
            'given_name': forms.TextInput(attrs={'autocomplete': 'off'}),
            'kana_surname': forms.TextInput(attrs={'autocomplete': 'off'}),
            'kana_given_name': forms.TextInput(attrs={'autocomplete': 'off'}),
            'sex': forms.Select(),
            'primary_diagnosis': forms.Textarea(attrs={'rows': 3}),
            'is_admin_only': forms.CheckboxInput(),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if not _is_admin_user(user):
            self.fields.pop('is_admin_only', None)


class StaffForm(forms.ModelForm):
    class Meta:
        model = Staff
        fields = [
            'staff_id',
            'surname',
            'given_name',
            'kana_surname',
            'kana_given_name',
            'occupation_label',
            'position_label',
            'is_active',
        ]
        labels = {
            'staff_id': '職員ID',
            'surname': '姓',
            'given_name': '名',
            'kana_surname': 'ふりかな姓',
            'kana_given_name': 'ふりかな名',
            'occupation_label': '職種',
            'position_label': '役職',
            'is_active': '有効',
        }
        widgets = {
            'staff_id': forms.TextInput(attrs={'autocomplete': 'off'}),
            'surname': forms.TextInput(attrs={'autocomplete': 'off'}),
            'given_name': forms.TextInput(attrs={'autocomplete': 'off'}),
            'kana_surname': forms.TextInput(attrs={'autocomplete': 'off'}),
            'kana_given_name': forms.TextInput(attrs={'autocomplete': 'off'}),
            'occupation_label': forms.TextInput(attrs={'autocomplete': 'off', 'placeholder': '看護師 / 医師 / 相談員'}),
            'position_label': forms.TextInput(attrs={'autocomplete': 'off', 'placeholder': '主任 / 部長 / 係長'}),
        }


class PatientLinkedPersonFormMixin:
    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_patient_id(self):
        patient_id = str(self.cleaned_data.get('patient_id') or '').strip()
        if not patient_id:
            raise forms.ValidationError('患者IDを入力してください。')
        patient_queryset = Patient.objects.all() if _is_admin_user(self.user) else Patient.objects.filter(is_admin_only=False)
        if not patient_queryset.filter(patient_id=patient_id).exists():
            raise forms.ValidationError(f'患者ID {patient_id} が見つかりません。')
        return patient_id


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


class StaffSearchForm(forms.Form):
    staff_id = forms.CharField(label='ID', required=False, widget=forms.TextInput(attrs={'autocomplete': 'off'}))
    kana = forms.CharField(label='ふりかな', required=False, widget=forms.TextInput(attrs={'autocomplete': 'off'}))
    occupation_label = forms.CharField(label='職種', required=False, widget=forms.TextInput(attrs={'autocomplete': 'off'}))
    position_label = forms.CharField(label='役職', required=False, widget=forms.TextInput(attrs={'autocomplete': 'off'}))
    is_active = forms.ChoiceField(
        label='状態',
        required=False,
        choices=[('', 'すべて'), ('1', '有効'), ('0', '無効')],
    )
    sort = forms.ChoiceField(
        label='ソート',
        required=False,
        choices=[
            ('staff_id', 'ID'),
            ('kana', 'ふりかな'),
            ('occupation_label', '職種'),
            ('position_label', '役職'),
            ('is_active', '状態'),
            ('updated_at', '更新日時'),
        ],
    )


class PatientImportForm(forms.Form):
    csv_file = forms.FileField(label='CSVファイル', widget=forms.FileInput(attrs={'accept': '.csv,text/csv'}))


class StaffImportForm(forms.Form):
    csv_file = forms.FileField(label='CSVファイル', widget=forms.FileInput(attrs={'accept': '.csv,text/csv'}))


class PatientLinkedPersonForm(PatientLinkedPersonFormMixin, forms.ModelForm):
    class Meta:
        model = PatientLinkedPerson
        fields = [
            'patient_id',
            'branch_no',
            'relation_kind',
            'surname',
            'given_name',
            'kana_surname',
            'kana_given_name',
            'relationship_label',
            'is_active',
        ]
        labels = {
            'patient_id': '患者ID',
            'branch_no': '枝番',
            'relation_kind': '種別',
            'surname': '姓',
            'given_name': '名',
            'kana_surname': 'ふりかな姓',
            'kana_given_name': 'ふりかな名',
            'relationship_label': '属性',
            'is_active': '有効',
        }
        widgets = {
            'patient_id': forms.TextInput(attrs={'autocomplete': 'off', 'placeholder': '患者ID'}),
            'branch_no': forms.NumberInput(attrs={'min': 1, 'autocomplete': 'off', 'placeholder': '1'}),
            'relation_kind': forms.Select(attrs={'autocomplete': 'off'}),
            'surname': forms.TextInput(attrs={'autocomplete': 'off'}),
            'given_name': forms.TextInput(attrs={'autocomplete': 'off'}),
            'kana_surname': forms.TextInput(attrs={'autocomplete': 'off'}),
            'kana_given_name': forms.TextInput(attrs={'autocomplete': 'off'}),
            'relationship_label': forms.TextInput(attrs={'autocomplete': 'off', 'placeholder': '父 / 母 / 夫 / 妻 / 子 / 後見人 / 保佐人 / 補助人'}),
        }


class PatientLinkedPersonSearchForm(forms.Form):
    linked_person_code = forms.CharField(
        label='個別コード',
        required=False,
        widget=forms.TextInput(attrs={'autocomplete': 'off', 'placeholder': 'LP00000001'}),
    )
    patient_id = forms.CharField(label='患者ID', required=False, widget=forms.TextInput(attrs={'autocomplete': 'off'}))
    branch_no = forms.IntegerField(label='枝番', required=False, min_value=1, widget=forms.NumberInput(attrs={'autocomplete': 'off', 'min': '1'}))
    relation_kind = forms.ChoiceField(
        label='種別',
        required=False,
        choices=[('', 'すべて')] + list(PatientLinkedPerson.RELATION_KIND_CHOICES),
    )
    kana = forms.CharField(label='ふりかな', required=False, widget=forms.TextInput(attrs={'autocomplete': 'off'}))
    relationship_label = forms.CharField(label='属性', required=False, widget=forms.TextInput(attrs={'autocomplete': 'off'}))
    is_active = forms.ChoiceField(
        label='状態',
        required=False,
        choices=[('', 'すべて'), ('1', '有効'), ('0', '無効')],
    )
    sort = forms.ChoiceField(
        label='ソート',
        required=False,
        choices=[
            ('linked_person_code', '個別コード'),
            ('patient_id', '患者ID'),
            ('branch_no', '枝番'),
            ('relation_kind', '種別'),
            ('kana', 'ふりかな'),
            ('relationship_label', '属性'),
            ('is_active', '状態'),
            ('updated_at', '更新日時'),
        ],
    )


class PatientLinkedPersonImportForm(forms.Form):
    csv_file = forms.FileField(label='CSVファイル', widget=forms.FileInput(attrs={'accept': '.csv,text/csv'}))


class FamilyForm(PatientLinkedPersonForm):
    pass


class FamilySearchForm(PatientLinkedPersonSearchForm):
    pass


class FamilyImportForm(PatientLinkedPersonImportForm):
    pass


class GuardianForm(PatientLinkedPersonForm):
    pass


class GuardianSearchForm(PatientLinkedPersonSearchForm):
    pass


class GuardianImportForm(PatientLinkedPersonImportForm):
    pass


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

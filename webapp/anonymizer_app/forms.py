from django import forms


TEMPLATE_CHOICES = [
    ('入院時サマリー', '入院時サマリー'),
    ('退院時サマリー', '退院時サマリー'),
    ('中間サマリー', '中間サマリー'),
    ('インシデントレポート', 'インシデントレポート'),
    ('委員会議事録', '委員会議事録'),
    ('看護計画', '看護計画'),
]


class AnonymizeForm(forms.Form):
    template = forms.ChoiceField(label='書類テンプレート')
    text = forms.CharField(label='入力テキスト', widget=forms.Textarea(attrs={'rows': 8}), required=True)
    reviewer = forms.CharField(label='レビュワー', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Load available templates from DB, fallback to TEMPLATE_CHOICES
        try:
            from .models import Template
            templates = Template.objects.all().values_list('name', flat=True).distinct()
            if templates:
                choices = [(name, name) for name in templates]
            else:
                choices = TEMPLATE_CHOICES
        except Exception:
            choices = TEMPLATE_CHOICES
        self.fields['template'].choices = choices


class DMZImportForm(forms.Form):
    host = forms.CharField(label='ホスト名 / IP', required=True)
    port = forms.IntegerField(label='ポート', required=False, initial=22)
    username = forms.CharField(label='ユーザー名', required=True)
    password = forms.CharField(label='パスワード（省略可）', required=False, widget=forms.PasswordInput(render_value=False))
    remote_path = forms.CharField(label='リモートファイルパス', required=True)
    target_filename = forms.CharField(label='保存時のファイル名（省略可）', required=False)
    # 将来的に鍵認証対応を追加できます


class DMZExportForm(forms.Form):
    host = forms.CharField(label='ホスト名 / IP', required=True)
    port = forms.IntegerField(label='ポート', required=False, initial=22)
    username = forms.CharField(label='ユーザー名', required=True)
    password = forms.CharField(label='パスワード（省略可）', required=False, widget=forms.PasswordInput(render_value=False))
    remote_path = forms.CharField(label='保存するリモートパス（例: /dmz/prompt.json）', required=True)
    source_id = forms.CharField(label='送るデータの source_id（省略可）', required=False)
    # source_idが指定されない場合は生のテキストを手動で貼る運用にする


class PromptForm(forms.Form):
    name = forms.CharField(label='プロンプト名', max_length=255)
    content = forms.CharField(label='プロンプト内容', widget=forms.Textarea(attrs={'rows':8}))


class TemplateForm(forms.Form):
    template_type = forms.ChoiceField(choices=TEMPLATE_CHOICES, label='テンプレート種別')
    name = forms.CharField(label='テンプレート名', max_length=255)
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

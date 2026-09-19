from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import AIProfile, ModelSetting


class StaffLimitForm(forms.ModelForm):
    class Meta:
        model = AIProfile
        fields = (
            'enabled', 'daily_request_limit', 'monthly_cost_limit_jpy',
            'max_input_chars', 'max_output_tokens', 'allowed_model_level',
        )
        labels = {
            'enabled': 'AIサービスの利用を許可する',
            'daily_request_limit': '1日のリクエスト上限（回）',
            'monthly_cost_limit_jpy': '月額利用上限（円）',
            'max_input_chars': '1回の入力文字数上限',
            'max_output_tokens': '1回の出力トークン上限',
            'allowed_model_level': '利用可能なモデルの権限レベル上限',
        }
        help_texts = {
            'enabled': '無効にするとAIへの送信と社内AIへのログインを停止します。',
            'daily_request_limit': '成功したリクエストを集計します。0にすると送信できません。',
            'monthly_cost_limit_jpy': '成功したリクエストの推定料金がこの額に達すると送信を停止します。0円で送信停止。',
            'allowed_model_level': 'この値以下の権限レベルを持つ有効なモデルを利用できます。',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('daily_request_limit', 'max_input_chars', 'max_output_tokens', 'allowed_model_level'):
            minimum = 1 if name in ('max_input_chars', 'max_output_tokens') else 0
            self.fields[name].min_value = minimum
            self.fields[name].max_value = 2147483647
            self.fields[name].widget.attrs.update(min=minimum, max=2147483647)
        self.fields['monthly_cost_limit_jpy'].min_value = 0
        self.fields['monthly_cost_limit_jpy'].widget.attrs['min'] = 0

    def clean(self):
        data = super().clean()
        for name in self.Meta.fields:
            if name == 'enabled' or name not in data:
                continue
            minimum = 1 if name in ('max_input_chars', 'max_output_tokens') else 0
            if data[name] < minimum:
                self.add_error(name, f'{minimum}以上の値を入力してください。')
            elif name != 'monthly_cost_limit_jpy' and data[name] > 2147483647:
                self.add_error(name, '2147483647以下の値を入力してください。')
        return data


class StaffForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ('username', 'last_name', 'first_name', 'email', 'is_active')
        labels = {'username': '職員ID', 'last_name': '姓', 'first_name': '名',
                  'email': 'メールアドレス', 'is_active': 'アカウントを有効にする'}
        help_texts = {'is_active': '無効にするとログインできなくなります。利用履歴は保持されます。'}


class StaffCreateForm(UserCreationForm):
    class Meta(StaffForm.Meta):
        pass


class LogSearchForm(forms.Form):
    kind = forms.ChoiceField(label='ログ種別', choices=(('usage', 'AI利用ログ'), ('audit', '管理操作ログ')))
    start = forms.DateField(label='開始日', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    end = forms.DateField(label='終了日', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    staff = forms.CharField(label='職員ID・氏名', required=False, max_length=150)
    keyword = forms.CharField(label='キーワード', required=False, max_length=150)

    def __init__(self, *args, **kwargs):
        from .models import UsageLog
        super().__init__(*args, **kwargs)
        if self.data.get('kind', 'usage') == 'usage':
            self.fields['status'] = forms.ChoiceField(
                label='結果', required=False, choices=[('', 'すべて'), *UsageLog.STATUS_CHOICES])
            self.fields['keyword'].help_text = 'リクエストID（完全一致）、モデル名、エラーコードを検索します。'
        else:
            self.fields['keyword'].help_text = '操作名、対象種別、対象IDを検索します。'

    def clean(self):
        from datetime import date
        data = super().clean()
        start, end = data.get('start'), data.get('end')
        if start and end and start > end:
            self.add_error('end', '終了日は開始日以降を指定してください。')
        if end == date.max:
            self.add_error('end', '終了日は9999年12月30日以前を指定してください。')
        return data


class AIModelForm(forms.ModelForm):
    class Meta:
        model = ModelSetting
        fields = ('model_code', 'display_name', 'enabled', 'permission_level',
                  'input_price_per_million', 'output_price_per_million')
        labels = {'model_code': 'モデルID', 'display_name': '表示名', 'enabled': 'このモデルを利用可能にする',
                  'permission_level': '必要な権限レベル', 'input_price_per_million': '入力単価（USD / 100万トークン）',
                  'output_price_per_million': '出力単価（USD / 100万トークン）'}
        help_texts = {'model_code': 'APIに送信するモデルIDを入力してください。',
                      'permission_level': '職員のモデル権限レベルがこの値以上の場合に利用できます。'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['model_code'].disabled = True
            self.fields['model_code'].help_text = '登録済みのIDです。別のモデルは新規登録してください。'
        for name in ('permission_level', 'input_price_per_million', 'output_price_per_million'):
            self.fields[name].widget.attrs['min'] = 0

    def clean(self):
        data = super().clean()
        for name in ('permission_level', 'input_price_per_million', 'output_price_per_million'):
            if data.get(name) is not None and data[name] < 0:
                self.add_error(name, '0以上の値を入力してください。')
        return data

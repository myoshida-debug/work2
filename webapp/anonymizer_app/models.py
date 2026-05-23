from django.conf import settings
from django.utils import timezone
from django.db import models


class RestoreMetadata(models.Model):
    STATUS_CHOICES = [
        ('draft', '作成済み'),
        ('sent_to_dmz', 'DMZ送信済み'),
        ('imported_to_open', 'OpenSide取込済み'),
        ('returned_to_dmz', '返却DMZ送信済み'),
        ('imported_to_close', 'CloseSide取込済み'),
    ]

    source_id = models.CharField(max_length=255, unique=True)
    template_type = models.CharField(max_length=255)
    restore_map = models.JSONField()
    prompt_json = models.JSONField(null=True, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.source_id} ({self.template_type})'


class RestoredResult(models.Model):
    STATUS_CHOICES = [
        ('imported', '取込済み'),
        ('deleted', '削除済み'),
    ]

    source_id = models.CharField(max_length=255, db_index=True)
    result_id = models.CharField(max_length=255, blank=True, default='')
    template_type = models.CharField(max_length=255, blank=True, default='')
    result_text = models.TextField()
    restored_text = models.TextField()
    result_json = models.JSONField(null=True, blank=True)
    imported_filename = models.CharField(max_length=255, blank=True, default='')
    reviewer = models.CharField(max_length=255, blank=True, default='')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='imported')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.result_id or self.source_id} ({self.template_type})'


class Prompt(models.Model):
    STATUS_CHOICES = [
        ('draft', '作成済み'),
        ('sent_to_dmz', 'DMZ送信済み'),
        ('imported_to_open', 'OpenSide取込済み'),
    ]

    name = models.CharField(max_length=255)
    content = models.TextField()
    source_input_data = models.JSONField(blank=True, default=dict)
    source_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


# テンプレート用の定義（フォームと合わせてください）
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


class Template(models.Model):
    template_type = models.CharField(max_length=255, choices=TEMPLATE_CHOICES)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    source_filename = models.CharField(max_length=255, blank=True, default='')
    content = models.TextField()
    basic_content = models.TextField(blank=True, default='')
    additional_content = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.template_type} - {self.name}"

    @property
    def combined_content(self):
        if self.additional_content:
            return f"{self.basic_content}\n\n{self.additional_content}"
        return self.basic_content or self.content


class TemplateInputDefault(models.Model):
    template_type = models.CharField(max_length=255, choices=TEMPLATE_CHOICES)
    field_key = models.CharField(max_length=255)
    default_text = models.TextField(blank=True, default='')
    required_override = models.BooleanField(null=True, blank=True, default=None)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['template_type', 'field_key'], name='unique_template_input_default'),
        ]
        ordering = ['template_type', 'field_key']

    def __str__(self):
        return f'{self.template_type}:{self.field_key}'


FIELD_INPUT_TYPE_CHOICES = [
    ('textarea', 'テキスト'),
    ('date', '日付'),
    ('checkbox_group', 'チェックボックス'),
]


class TemplateInputField(models.Model):
    template_type = models.CharField(max_length=255, choices=TEMPLATE_CHOICES)
    field_key = models.CharField(max_length=255)
    label = models.CharField(max_length=255, blank=True, default='')
    input_type = models.CharField(max_length=32, choices=FIELD_INPUT_TYPE_CHOICES, default='textarea')
    section_title = models.CharField(max_length=255, blank=True, default='')
    required = models.BooleanField(default=False)
    allow_other = models.BooleanField(default=True)
    other_label = models.CharField(max_length=255, blank=True, default='その他')
    other_placeholder = models.CharField(max_length=255, blank=True, default='自由入力')
    help_text = models.TextField(blank=True, default='')
    textarea_rows = models.PositiveIntegerField(default=3)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['template_type', 'field_key'], name='unique_template_input_field'),
        ]
        ordering = ['template_type', 'sort_order', 'field_key']

    def __str__(self):
        return f'{self.template_type}:{self.field_key}'


class TemplateInputCheckboxGroup(models.Model):
    template_type = models.CharField(max_length=255, choices=TEMPLATE_CHOICES)
    field_key = models.CharField(max_length=255)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['template_type', 'field_key'], name='unique_template_input_checkbox_group'),
        ]
        ordering = ['template_type', 'field_key']

    def __str__(self):
        return f'{self.template_type}:{self.field_key}'


class TemplateInputCheckboxOption(models.Model):
    group = models.ForeignKey(TemplateInputCheckboxGroup, related_name='options', on_delete=models.CASCADE)
    text = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['group', 'text'], name='unique_template_input_checkbox_option'),
        ]
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f'{self.group.template_type}:{self.group.field_key}:{self.text}'


class AnonymizationRule(models.Model):
    """Store editable anonymization rule text for admin editing and runtime display."""
    name = models.CharField(max_length=255, default='default')
    content = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class OperationLog(models.Model):
    RESULT_CHOICES = [
        ('success', '成功'),
        ('failure', '失敗'),
    ]

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    actor_username = models.CharField(max_length=150, blank=True, default='')
    action = models.CharField(max_length=80)
    target_type = models.CharField(max_length=80, blank=True, default='')
    target_id = models.CharField(max_length=255, blank=True, default='')
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    import_source_ip = models.GenericIPAddressField(null=True, blank=True)
    result = models.CharField(max_length=16, choices=RESULT_CHOICES, default='success')
    error_message = models.TextField(blank=True, default='')
    details = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f'{self.created_at:%Y-%m-%d %H:%M:%S} {self.action} {self.target_id} {self.result}'

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

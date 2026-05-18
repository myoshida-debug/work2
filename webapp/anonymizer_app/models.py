from django.db import models
from django.utils import timezone


class RestoreMetadata(models.Model):
    source_id = models.CharField(max_length=255, unique=True)
    template_type = models.CharField(max_length=255)
    restore_map = models.JSONField()
    prompt_json = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.source_id} ({self.template_type})'


class Prompt(models.Model):
    name = models.CharField(max_length=255)
    content = models.TextField()
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
    content = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.template_type} - {self.name}"

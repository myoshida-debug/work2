from django.conf import settings
from django.db import models
from django.utils import timezone


class AIProfile(models.Model):
    ROLE_CHOICES = [('USER', '一般職員'), ('ADMIN', '管理者'), ('SUPER_ADMIN', '最高管理者')]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='USER')
    enabled = models.BooleanField(default=True)
    daily_request_limit = models.PositiveIntegerField(default=50)
    monthly_cost_limit_jpy = models.DecimalField(max_digits=12, decimal_places=2, default=1000)
    max_input_chars = models.PositiveIntegerField(default=20000)
    max_output_tokens = models.PositiveIntegerField(default=2000)
    allowed_model_level = models.PositiveIntegerField(default=1)
    failed_login_count = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)


class ModelSetting(models.Model):
    model_code = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=100)
    permission_level = models.PositiveIntegerField(default=1)
    input_price_per_million = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    output_price_per_million = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    enabled = models.BooleanField(default=True)


class UsageLog(models.Model):
    STATUS_CHOICES = [('SUCCESS', '成功'), ('FAILED', '失敗'), ('REJECTED_LIMIT', '制限拒否'), ('TIMEOUT', 'タイムアウト')]
    request_id = models.UUIDField(unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='ai_usage_logs')
    model = models.ForeignKey(ModelSetting, null=True, on_delete=models.SET_NULL)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=14, decimal_places=6, default=0)
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, default=160)
    cost_jpy = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    response_time_ms = models.PositiveIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=50, blank=True)
    target_id = models.CharField(max_length=100, blank=True)
    before_value = models.JSONField(null=True, blank=True)
    after_value = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)


class Department(models.Model):
    department_code = models.CharField(max_length=20, unique=True)
    department_name = models.CharField(max_length=100)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)


class ChatSession(models.Model):
    session_uuid = models.UUIDField(default=__import__('uuid').uuid4, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    title = models.CharField(max_length=200, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)


class ChatMessage(models.Model):
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20)
    content = models.TextField(null=True, blank=True)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)


class SystemSetting(models.Model):
    setting_key = models.CharField(max_length=100, unique=True)
    setting_value = models.TextField()
    value_type = models.CharField(max_length=20)
    description = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class SecurityEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    event_type = models.CharField(max_length=100, db_index=True)
    severity = models.CharField(max_length=20)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)


class Notification(models.Model):
    notification_type = models.CharField(max_length=50)
    title = models.CharField(max_length=200)
    message = models.TextField()
    severity = models.CharField(max_length=20)
    read_flag = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

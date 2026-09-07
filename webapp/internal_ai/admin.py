from django.contrib import admin
from .models import AIProfile, AuditLog, ChatMessage, ChatSession, Department, ModelSetting, Notification, SecurityEvent, SystemSetting, UsageLog

admin.site.register(AIProfile)
admin.site.register(ModelSetting)
admin.site.register(UsageLog)
admin.site.register(AuditLog)
admin.site.register([Department, ChatSession, ChatMessage, SystemSetting, SecurityEvent, Notification])

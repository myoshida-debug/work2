import time
import uuid
import logging
from datetime import timedelta
from decimal import Decimal, ROUND_UP
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Count
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.conf import settings as django_settings
from django.views.decorators.http import require_POST
from .models import AIProfile, AuditLog, ModelSetting, UsageLog

logger = logging.getLogger(__name__)


def profile(user):
    p, _ = AIProfile.objects.get_or_create(user=user, defaults={'role': 'ADMIN' if user.is_staff else 'USER'})
    return p


def login_view(request):
    if request.user.is_authenticated:
        return redirect('internal_ai:chat')
    error = ''
    if request.method == 'POST':
        username = request.POST.get('username', '')[:150]
        user = __import__('django.contrib.auth', fromlist=['get_user_model']).get_user_model().objects.filter(username=username).first()
        p = profile(user) if user else None
        locked = p and p.locked_until and p.locked_until > timezone.now()
        user = authenticate(request, username=username, password=request.POST.get('password', '')) if not locked else None
        if user and user.is_active and p.enabled:
            p.failed_login_count = 0; p.locked_until = None; p.save(update_fields=['failed_login_count', 'locked_until']); login(request, user)
            return redirect('internal_ai:chat')
        if p:
            p.failed_login_count += 1
            if p.failed_login_count >= 5: p.locked_until = timezone.now() + timedelta(minutes=15)
            p.save(update_fields=['failed_login_count', 'locked_until'])
        error = '職員IDまたはパスワードが正しくありません。'
    return render(request, 'internal_ai/login.html', {'error': error})


def logout_view(request):
    logout(request); return redirect('internal_ai:login')


def cost(input_tokens, output_tokens, model):
    usd = (Decimal(input_tokens) * model.input_price_per_million + Decimal(output_tokens) * model.output_price_per_million) / Decimal(1000000)
    return usd, (usd * Decimal(str(getattr(django_settings, 'AI_USD_JPY_RATE', 160)))).quantize(Decimal('0.01'), rounding=ROUND_UP)


@login_required
def chat(request):
    p = profile(request.user)
    models = ModelSetting.objects.filter(enabled=True, permission_level__lte=p.allowed_model_level)
    return render(request, 'internal_ai/chat.html', {'profile': p, 'models': models})


@login_required
@require_POST
def chat_api(request):
    p = profile(request.user); message = request.POST.get('message', '')
    if not p.enabled: return JsonResponse({'error': '現在AIサービスを利用できません。'}, status=403)
    if len(message) > p.max_input_chars: return JsonResponse({'error': '入力文字数が上限を超えています。'}, status=413)
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if UsageLog.objects.filter(user=request.user, status='SUCCESS', created_at__gte=today_start).count() >= p.daily_request_limit:
        return JsonResponse({'error': '本日のAI利用上限に達しました。'}, status=403)
    current_cost = UsageLog.objects.filter(user=request.user, status='SUCCESS', created_at__gte=month_start).aggregate(v=Sum('cost_jpy'))['v'] or Decimal('0')
    if current_cost >= p.monthly_cost_limit_jpy:
        return JsonResponse({'error': '今月のAI利用上限に達しました。'}, status=403)
    company_cost = UsageLog.objects.filter(status='SUCCESS', created_at__gte=month_start).aggregate(v=Sum('cost_jpy'))['v'] or Decimal('0')
    company_limit = Decimal(str(getattr(django_settings, 'AI_COMPANY_INTERNAL_STOP_JPY', 29000)))
    if company_cost >= company_limit:
        return JsonResponse({'error': '会社全体のAI利用上限に達しているため送信できません。'}, status=403)
    requested_model = request.POST.get('model', '')
    model = ModelSetting.objects.filter(model_code=requested_model, enabled=True,
                                        permission_level__lte=p.allowed_model_level).first()
    if not model:
        model = ModelSetting.objects.filter(enabled=True, permission_level__lte=p.allowed_model_level).first()
    if not model: return JsonResponse({'error': '利用可能なAIモデルがありません。'}, status=503)
    start = time.monotonic(); request_id = uuid.uuid4()
    try:
        from openai import OpenAI
        from django.conf import settings
        key = getattr(settings, 'OPENAI_API_KEY', '')
        if not key: raise RuntimeError('OPENAI_API_KEY is not configured')
        response = OpenAI(api_key=key, timeout=60).responses.create(model=model.model_code, input=message, max_output_tokens=p.max_output_tokens)
        usage = response.usage; inputs = int(getattr(usage, 'input_tokens', 0) or 0); outputs = int(getattr(usage, 'output_tokens', 0) or 0)
        usd, jpy = cost(inputs, outputs, model)
        UsageLog.objects.create(request_id=request_id, user=request.user, model=model, input_tokens=inputs, output_tokens=outputs, cost_usd=usd, exchange_rate=getattr(django_settings, 'AI_USD_JPY_RATE', 160), cost_jpy=jpy, status='SUCCESS', response_time_ms=int((time.monotonic()-start)*1000))
        return JsonResponse({'answer': response.output_text, 'cost_jpy': str(jpy)})
    except Exception as exc:
        logger.exception('Internal AI request failed: %s', type(exc).__name__)
        UsageLog.objects.create(request_id=request_id, user=request.user, model=model, status='FAILED', error_code=type(exc).__name__, response_time_ms=int((time.monotonic()-start)*1000))
        return JsonResponse({'error': 'AIサービスで一時的な問題が発生しました。'}, status=502)


@login_required
def usage(request):
    p = profile(request.user); logs = UsageLog.objects.filter(user=request.user, status='SUCCESS', created_at__month=timezone.now().month)
    total = logs.aggregate(value=Sum('cost_jpy'))['value'] or Decimal('0')
    return render(request, 'internal_ai/usage.html', {'profile': p, 'count': logs.count(), 'total': total, 'remaining': max(Decimal('0'), p.monthly_cost_limit_jpy-total)})


def is_admin(user): return user.is_authenticated and (user.is_staff or profile(user).role in ('ADMIN', 'SUPER_ADMIN'))


@user_passes_test(is_admin)
def dashboard(request):
    total = UsageLog.objects.filter(status='SUCCESS', created_at__month=timezone.now().month).aggregate(value=Sum('cost_jpy'))['value'] or Decimal('0')
    return render(request, 'internal_ai/dashboard.html', {'total': total, 'user_count': UsageLog.objects.values('user').distinct().count()})

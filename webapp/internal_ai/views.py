import time
import uuid
import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_UP
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDate
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from .chat_files import FORMATS, prepare_input, export_answer
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.views.decorators.http import require_http_methods
from .forms import StaffCreateForm, StaffForm, StaffLimitForm
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
    return render(request, 'internal_ai/chat.html', {'profile': p, 'models': models, 'can_admin': is_admin(request.user)})


@login_required
@require_POST
def chat_api(request):
    p = profile(request.user); message = request.POST.get('message', '')
    if not p.enabled: return JsonResponse({'error': '現在AIサービスを利用できません。'}, status=403)
    answer_type = request.POST.get('answer_type', 'text')
    if answer_type not in ('text', 'image'):
        return JsonResponse({'error': '回答の種類が不正です。'}, status=400)
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
    try:
        ai_input, message = prepare_input(message, request.FILES.getlist('files'), p.max_input_chars)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    start = time.monotonic(); request_id = uuid.uuid4()
    try:
        from openai import OpenAI
        from django.conf import settings
        key = getattr(settings, 'OPENAI_API_KEY', '')
        if not key: raise RuntimeError('OPENAI_API_KEY is not configured')
        options = {}
        if answer_type == 'image':
            options = {
                'tools': [{'type': 'image_generation', 'model': 'gpt-image-1',
                           'size': '1024x1024', 'quality': 'medium', 'output_format': 'png'}],
                'tool_choice': {'type': 'image_generation'},
                'parallel_tool_calls': False,
            }
        response = OpenAI(api_key=key, timeout=180 if answer_type == 'image' else 60,
                          max_retries=0).responses.create(
            model=model.model_code, input=ai_input, max_output_tokens=p.max_output_tokens, **options)
        generated_images = []
        if answer_type == 'image':
            from .chat_files import validate_generated_image
            for item in response.output:
                if item.type == 'image_generation_call' and getattr(item, 'result', None):
                    validate_generated_image(item.result)
                    generated_images.append(item.result)
        answer = response.output_text or ('画像を生成しました。' if generated_images else '')
        if answer_type == 'image' and not generated_images:
            answer = answer or '画像を生成できませんでした。質問内容を変更して再度お試しください。'

        usage = response.usage; inputs = int(getattr(usage, 'input_tokens', 0) or 0); outputs = int(getattr(usage, 'output_tokens', 0) or 0)
        usd, jpy = cost(inputs, outputs, model)
        if generated_images:
            # Responses usage excludes the image tool's separately billed work.
            # Account for it with a configurable internal estimate, marked in the UI.
            usd += Decimal(str(getattr(settings, 'AI_IMAGE_ESTIMATED_USD', '0.20'))) * len(generated_images)
            jpy = (usd * Decimal(str(getattr(settings, 'AI_USD_JPY_RATE', 160)))).quantize(Decimal('0.01'), rounding=ROUND_UP)
        UsageLog.objects.create(request_id=request_id, user=request.user, model=model, prompt_text=message, response_text=answer, generated_images=generated_images, image_cost_estimated=bool(generated_images), input_tokens=inputs, output_tokens=outputs, cost_usd=usd, exchange_rate=getattr(django_settings, 'AI_USD_JPY_RATE', 160), cost_jpy=jpy, status='SUCCESS', response_time_ms=int((time.monotonic()-start)*1000))
        return JsonResponse({'answer': answer, 'cost_jpy': str(jpy),
                             'image_cost_estimated': bool(generated_images),
                             'images': [{fmt: reverse('internal_ai:generated_image', args=[request_id, index, fmt])
                                         for fmt in ('png', 'jpeg')} for index in range(len(generated_images))],
                             'downloads': {fmt: reverse('internal_ai:chat_download', args=[request_id, fmt]) for fmt in FORMATS}})
    except Exception as exc:
        logger.exception('Internal AI request failed: %s', type(exc).__name__)
        UsageLog.objects.create(request_id=request_id, user=request.user, model=model, prompt_text=message, status='FAILED', error_code=type(exc).__name__, response_time_ms=int((time.monotonic()-start)*1000))
        return JsonResponse({'error': 'AIサービスで一時的な問題が発生しました。'}, status=502)


@login_required
def usage(request):
    p = profile(request.user); logs = UsageLog.objects.filter(user=request.user, status='SUCCESS', created_at__month=timezone.now().month)
    total = logs.aggregate(value=Sum('cost_jpy'))['value'] or Decimal('0')
    return render(request, 'internal_ai/usage.html', {'profile': p, 'count': logs.count(), 'total': total, 'remaining': max(Decimal('0'), p.monthly_cost_limit_jpy-total)})


def is_admin(user):
    return user.is_authenticated and user.is_active and (
        user.is_staff or AIProfile.objects.filter(
            user=user, enabled=True, role__in=('ADMIN', 'SUPER_ADMIN')
        ).exists()
    )


@login_required(login_url='internal_ai:login')
def dashboard(request):
    if not is_admin(request.user):
        raise PermissionDenied
    month = request.GET.get('month', timezone.localdate().strftime('%Y-%m'))
    error = ''
    try:
        start = datetime.strptime(month, '%Y-%m').replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)
    except (ValueError, OverflowError):
        error = '対象月を正しく指定してください。今月の利用状況を表示しています。'
        start = datetime.combine(timezone.localdate().replace(day=1), datetime.min.time())
        end = (start + timedelta(days=32)).replace(day=1)
    month = start.strftime('%Y-%m')
    logs = UsageLog.objects.filter(
        created_at__gte=timezone.make_aware(start), created_at__lt=timezone.make_aware(end)
    )
    success = Q(status='SUCCESS')
    totals = logs.aggregate(
        total=Sum('cost_jpy', filter=success), count=Count('id'),
        success_count=Count('id', filter=success), user_count=Count('user', distinct=True),
        input_tokens=Sum('input_tokens'), output_tokens=Sum('output_tokens'),
    )
    totals['total'] = totals['total'] or Decimal('0')
    totals['success_rate'] = round(100 * totals['success_count'] / totals['count'], 1) if totals['count'] else None
    totals['failed_count'] = totals['count'] - totals['success_count']
    limit = Decimal(str(getattr(django_settings, 'AI_COMPANY_INTERNAL_STOP_JPY', 29000)))
    user_summary = logs.values('user__username', 'user__first_name', 'user__last_name').annotate(
        count=Count('id'), total=Sum('cost_jpy', filter=success),
        failed=Count('id', filter=~success),
    ).order_by('-total', 'user__username')
    model_summary = logs.values('model__display_name').annotate(
        count=Count('id'), total=Sum('cost_jpy', filter=success),
    ).order_by('-count', 'model__display_name')
    daily_counts = dict(logs.annotate(day=TruncDate('created_at')).values('day').annotate(count=Count('id')).values_list('day', 'count'))
    daily = [{'date': start.date() + timedelta(days=i), 'count': daily_counts.get(start.date() + timedelta(days=i), 0)} for i in range((end-start).days)]
    maximum = max((day['count'] for day in daily), default=0) or 1
    for day in daily:
        day['height'] = round(day['count'] / maximum * 100)
    query = request.GET.get('q', '').strip()[:150]
    status = request.GET.get('status', '')
    if status not in dict(UsageLog.STATUS_CHOICES):
        status = ''
    history = logs.select_related('user', 'model').order_by('-created_at', '-id')
    if query:
        history = history.filter(Q(user__username__icontains=query) | Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query))
    if status:
        history = history.filter(status=status)
    params = request.GET.copy()
    params.pop('page', None)
    params['month'] = month
    return render(request, 'internal_ai/dashboard.html', {
        **totals, 'month': month, 'error': error, 'limit': limit,
        'remaining': max(Decimal('0'), limit-totals['total']),
        'budget_percent': min(100, max(0, totals['total'] / limit * 100)) if limit > 0 else 0,
        'over_budget': totals['total'] >= limit,
        'user_summary': user_summary, 'model_summary': model_summary, 'daily': daily,
        'page_obj': Paginator(history, 25).get_page(request.GET.get('page')),
        'query': query, 'status': status, 'statuses': UsageLog.STATUS_CHOICES,
        'pagination_query': params.urlencode(),
    })


@login_required(login_url='internal_ai:login')
@require_http_methods(['GET'])
def staff_limits(request):
    if not is_admin(request.user):
        raise PermissionDenied
    query = request.GET.get('q', '').strip()[:150]
    users = get_user_model().objects.select_related('ai_profile').order_by('username', 'pk')
    if query:
        users = users.filter(Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query))
    page = Paginator(users, 25).get_page(request.GET.get('page'))
    for user in page:
        user.limit_profile = getattr(user, 'ai_profile', None) or AIProfile(user=user)
    return render(request, 'internal_ai/staff_limits.html', {'page_obj': page, 'query': query})


@login_required(login_url='internal_ai:login')
@require_http_methods(['GET', 'POST'])
def staff_limit_edit(request, user_id):
    if not is_admin(request.user):
        raise PermissionDenied
    with transaction.atomic():
        users = get_user_model().objects
        if request.method == 'POST':
            users = users.select_for_update()
        staff = get_object_or_404(users, pk=user_id)
        current = AIProfile.objects.filter(user=staff).first()
        instance = current or AIProfile(user=staff, role='ADMIN' if staff.is_staff else 'USER')
        before = {name: str(getattr(instance, name)) if name == 'monthly_cost_limit_jpy' else getattr(instance, name) for name in StaffLimitForm.Meta.fields}
        form = StaffLimitForm(request.POST if request.method == 'POST' else None, instance=instance)
        if request.method == 'POST' and form.is_valid():
            if staff.pk == request.user.pk and not form.cleaned_data['enabled']:
                form.add_error('enabled', '自分自身の利用停止は別の管理者に依頼してください。')
            else:
                saved = form.save()
                after = {name: str(getattr(saved, name)) if name == 'monthly_cost_limit_jpy' else getattr(saved, name) for name in StaffLimitForm.Meta.fields}
                AuditLog.objects.create(
                    actor=request.user, action='UPDATE_STAFF_LIMITS', target_type='AIProfile',
                    target_id=str(saved.pk), before_value=before, after_value=after,
                )
                messages.success(request, f'職員「{staff.username}」の制限設定を保存しました。')
                return redirect('internal_ai:staff_limit_edit', user_id=staff.pk)
    return render(request, 'internal_ai/staff_limit_edit.html', {
        'staff': staff, 'form': form, 'models': ModelSetting.objects.filter(enabled=True).order_by('permission_level', 'display_name'),
    })


@login_required(login_url='internal_ai:login')
@require_http_methods(['GET'])
def staff_management(request):
    if not is_admin(request.user):
        raise PermissionDenied
    query = request.GET.get('q', '').strip()[:150]
    status = request.GET.get('status', '')
    users = get_user_model().objects.select_related('ai_profile').order_by('username', 'pk')
    if query:
        users = users.filter(Q(username__icontains=query) | Q(first_name__icontains=query) |
                             Q(last_name__icontains=query) | Q(email__icontains=query))
    if status in ('active', 'inactive'):
        users = users.filter(is_active=status == 'active')
    else:
        status = ''
    page = Paginator(users, 25).get_page(request.GET.get('page'))
    for staff in page:
        staff.management_profile = getattr(staff, 'ai_profile', None) or AIProfile(user=staff)
        staff.can_edit = request.user.is_superuser or not (
            staff.is_staff or staff.is_superuser or
            staff.management_profile.role in ('ADMIN', 'SUPER_ADMIN')
        )
    return render(request, 'internal_ai/staff_management.html', {
        'page_obj': page, 'query': query, 'status': status,
    })


@login_required(login_url='internal_ai:login')
@require_http_methods(['GET', 'POST'])
def staff_edit(request, user_id=None):
    if not is_admin(request.user):
        raise PermissionDenied
    creating = user_id is None
    with transaction.atomic():
        users = get_user_model().objects
        if request.method == 'POST':
            users = users.select_for_update()
        staff = get_user_model()() if creating else get_object_or_404(users, pk=user_id)
        if not creating and not request.user.is_superuser and (
            staff.is_staff or staff.is_superuser or
            AIProfile.objects.filter(user=staff, role__in=('ADMIN', 'SUPER_ADMIN')).exists()
        ):
            raise PermissionDenied
        before = None if creating else {name: getattr(staff, name) for name in StaffForm.Meta.fields}
        form_class = StaffCreateForm if creating else StaffForm
        form = form_class(request.POST if request.method == 'POST' else None, instance=staff)
        if request.method == 'POST' and form.is_valid():
            if not creating and staff.pk == request.user.pk and not form.cleaned_data['is_active']:
                form.add_error('is_active', '自分自身のアカウントは無効にできません。')
            else:
                saved = form.save()
                if creating:
                    AIProfile.objects.create(user=saved)
                AuditLog.objects.create(
                    actor=request.user, action='CREATE_STAFF' if creating else 'UPDATE_STAFF',
                    target_type='User', target_id=str(saved.pk), before_value=before,
                    after_value={name: getattr(saved, name) for name in StaffForm.Meta.fields},
                )
                messages.success(request, f'職員「{saved.username}」を保存しました。')
                return redirect('internal_ai:staff_edit', user_id=saved.pk)
    return render(request, 'internal_ai/staff_edit.html', {'form': form, 'staff': staff, 'creating': creating})


@login_required(login_url='internal_ai:login')
@require_http_methods(['GET'])
def log_search(request):
    from .forms import LogSearchForm
    params = request.GET.copy()
    params.setdefault('kind', 'usage')
    if 'start' not in params and 'end' not in params:
        today = timezone.localdate()
        params['start'] = (today - timedelta(days=29)).isoformat()
        params['end'] = today.isoformat()
    if not is_admin(request.user):
        raise PermissionDenied
    form = LogSearchForm(params)
    kind = 'audit' if params.get('kind') == 'audit' else 'usage'
    model = AuditLog if kind == 'audit' else UsageLog
    logs = model.objects.none()
    if form.is_valid():
        data = form.cleaned_data
        relation = 'actor' if kind == 'audit' else 'user'
        logs = model.objects.select_related(relation)
        if kind == 'usage':
            logs = logs.select_related('model')
        if data['start']:
            logs = logs.filter(created_at__gte=timezone.make_aware(datetime.combine(data['start'], datetime.min.time())))
        if data['end']:
            logs = logs.filter(created_at__lt=timezone.make_aware(datetime.combine(data['end'] + timedelta(days=1), datetime.min.time())))
        if data['staff']:
            logs = logs.filter(
                Q(**{f'{relation}__username__icontains': data['staff']}) |
                Q(**{f'{relation}__first_name__icontains': data['staff']}) |
                Q(**{f'{relation}__last_name__icontains': data['staff']})
            )
        keyword = data['keyword']
        if kind == 'usage':
            if data['status']:
                logs = logs.filter(status=data['status'])
            if keyword:
                match = Q(model__display_name__icontains=keyword) | Q(model__model_code__icontains=keyword) | Q(error_code__icontains=keyword)
                try:
                    match |= Q(request_id=uuid.UUID(keyword))
                except ValueError:
                    pass
                logs = logs.filter(match)
        elif keyword:
            logs = logs.filter(Q(action__icontains=keyword) | Q(target_type__icontains=keyword) | Q(target_id__icontains=keyword))
    page = Paginator(logs.order_by('-created_at', '-pk'), 25).get_page(params.get('page'))
    params.pop('page', None)
    return render(request, 'internal_ai/log_search.html', {
        'form': form, 'kind': kind, 'page_obj': page, 'pagination_query': params.urlencode(),
    })


@login_required(login_url='internal_ai:login')
@require_http_methods(['GET'])
def admin_home(request):
    if not is_admin(request.user):
        raise PermissionDenied
    return render(request, 'internal_ai/admin_home.html')


@login_required(login_url='internal_ai:login')
@require_http_methods(['GET'])
def ai_settings(request):
    if not is_admin(request.user):
        raise PermissionDenied
    return render(request, 'internal_ai/ai_settings.html', {
        'models': ModelSetting.objects.order_by('permission_level', 'model_code'),
    })


@login_required(login_url='internal_ai:login')
@require_http_methods(['GET', 'POST'])
def ai_model_edit(request, model_id=None):
    from .forms import AIModelForm
    if not is_admin(request.user):
        raise PermissionDenied
    with transaction.atomic():
        models = ModelSetting.objects.select_for_update() if request.method == 'POST' else ModelSetting.objects
        model = get_object_or_404(models, pk=model_id) if model_id is not None else ModelSetting()
        before = {name: str(getattr(model, name)) for name in AIModelForm.Meta.fields} if model.pk else None
        form = AIModelForm(request.POST if request.method == 'POST' else None, instance=model)
        if request.method == 'POST' and form.is_valid():
            saved = form.save()
            AuditLog.objects.create(
                actor=request.user, action='UPDATE_AI_MODEL' if model_id is not None else 'CREATE_AI_MODEL',
                target_type='ModelSetting', target_id=str(saved.pk), before_value=before,
                after_value={name: str(getattr(saved, name)) for name in AIModelForm.Meta.fields},
            )
            messages.success(request, 'AIモデルの設定を保存しました。')
            return redirect('internal_ai:ai_model_edit', model_id=saved.pk)
    return render(request, 'internal_ai/ai_model_edit.html', {'form': form, 'creating': model_id is None})


@login_required
@require_http_methods(['GET'])
def chat_download(request, request_id, format):
    if not profile(request.user).enabled:
        raise PermissionDenied
    log = get_object_or_404(UsageLog, request_id=request_id, user=request.user, status='SUCCESS')
    if format not in FORMATS:
        return JsonResponse({'error': '対応していない出力形式です。'}, status=400)
    preview = request.GET.get('preview') == '1'
    page_count = None
    if preview and format not in ('pdf', 'png', 'jpeg'):
        return JsonResponse({'error': 'プレビューはPDF・PNG・JPEGに対応しています。'}, status=400)
    if preview and format in ('png', 'jpeg'):
        import pymupdf
        try:
            page_number = int(request.GET.get('page', '1'))
        except ValueError:
            return JsonResponse({'error': 'ページ番号が不正です。'}, status=400)
        with pymupdf.open(stream=export_answer(log.response_text, 'pdf'), filetype='pdf') as pdf:
            page_count = len(pdf)
            if not 1 <= page_number <= page_count:
                return JsonResponse({'error': 'ページが見つかりません。'}, status=404)
            data = pdf[page_number - 1].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).tobytes(format)
    else:
        data = export_answer(log.response_text, format)
    zipped = format in ('jpeg', 'png') and data.startswith(b'PK')
    extension = 'zip' if zipped else format
    response = HttpResponse(data, content_type='application/zip' if zipped else FORMATS[format])
    disposition = 'inline' if preview else 'attachment'
    response['Content-Disposition'] = f'{disposition}; filename="answer-{request_id}.{extension}"'
    if page_count is not None:
        response['X-Page-Count'] = str(page_count)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@login_required
@require_http_methods(['GET'])
def generated_image(request, request_id, index, format):
    if not profile(request.user).enabled:
        raise PermissionDenied
    log = get_object_or_404(UsageLog, request_id=request_id, user=request.user, status='SUCCESS')
    if format not in ('png', 'jpeg') or index >= len(log.generated_images):
        from django.http import Http404
        raise Http404
    import base64
    from io import BytesIO
    from PIL import Image
    data = base64.b64decode(log.generated_images[index], validate=True)
    if format == 'jpeg':
        with Image.open(BytesIO(data)) as image:
            background = Image.new('RGB', image.size, 'white')
            rgba = image.convert('RGBA')
            background.paste(rgba, mask=rgba.getchannel('A'))
            output = BytesIO()
            background.save(output, format='JPEG', quality=95)
            data = output.getvalue()
    response = HttpResponse(data, content_type=FORMATS[format])
    disposition = 'attachment' if request.GET.get('download') == '1' else 'inline'
    response['Content-Disposition'] = f'{disposition}; filename="generated-{request_id}-{index + 1}.{format}"'
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response

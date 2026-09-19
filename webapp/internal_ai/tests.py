from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AIProfile, ModelSetting, UsageLog


class DashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_user('admin', is_staff=True)
        cls.employee = get_user_model().objects.create_user('employee', last_name='確認職員')
        cls.model = ModelSetting.objects.create(model_code='test', display_name='テストモデル')
        cls.url = reverse('internal_ai:dashboard')

    def log(self, date, status='SUCCESS', amount='12.50', user=None):
        return UsageLog.objects.create(
            request_id=uuid4(), user=user or self.employee, model=self.model,
            created_at=timezone.make_aware(datetime.fromisoformat(date)),
            status=status, cost_jpy=Decimal(amount), input_tokens=10, output_tokens=5,
        )

    def test_access_control(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse('internal_ai:login') + '?next=' + self.url)
        self.client.force_login(self.employee)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        p = AIProfile.objects.create(user=self.employee, role='ADMIN')
        self.assertEqual(self.client.get(self.url).status_code, 200)
        p.enabled = False
        p.save()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        p.enabled = True
        p.role = 'SUPER_ADMIN'
        p.save()
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_month_boundaries_and_aggregates(self):
        self.client.force_login(self.admin)
        self.log('2025-09-01T00:00:00', amount='999')
        self.log('2026-08-31T23:59:59', amount='999')
        self.log('2026-09-01T00:00:00')
        self.log('2026-09-30T23:59:59')
        self.log('2026-09-02T10:00:00', 'FAILED', '0')
        self.log('2026-10-01T00:00:00', amount='999')
        response = self.client.get(self.url, {'month': '2026-09'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total'], Decimal('25'))
        self.assertEqual(response.context['count'], 3)
        self.assertEqual(response.context['user_count'], 1)
        self.assertEqual(response.context['success_rate'], 66.7)
        self.assertEqual(response.context['daily'][0]['count'], 1)
        self.assertEqual(response.context['daily'][-1]['count'], 1)
        self.assertContains(response, 'テストモデル')
        self.assertEqual(response.context['user_summary'][0]['failed'], 1)

    def test_filter_and_pagination_keep_month_summary(self):
        self.client.force_login(self.admin)
        for _ in range(26):
            self.log('2026-09-02T10:00:00', 'FAILED', '0')
        self.log('2026-09-03T10:00:00', user=self.admin)
        response = self.client.get(self.url, {'month': '2026-09', 'q': '確認職員', 'status': 'FAILED', 'page': '2'})
        self.assertEqual(len(response.context['page_obj']), 1)
        self.assertEqual(response.context['page_obj'].paginator.count, 26)
        self.assertEqual(response.context['count'], 27)
        self.assertContains(response, 'status=FAILED')
        response = self.client.get(self.url, {'month': '2026-09', 'q': 'missing'})
        self.assertContains(response, '条件に一致する利用履歴はありません。')

    def test_invalid_parameters_and_empty_month(self):
        self.client.force_login(self.admin)
        for month in ('invalid', '9999-12', ''):
            response = self.client.get(self.url, {'month': month, 'page': 'bad', 'status': 'bad'})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['error'])
        response = self.client.get(self.url, {'month': '2024-02'})
        self.assertEqual(len(response.context['daily']), 29)
        self.assertEqual(response.context['total'], 0)
        self.assertIsNone(response.context['success_rate'])
        self.assertContains(response, '対象月の利用記録はありません。')

    def test_chat_navigation_is_admin_only(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('internal_ai:chat')), reverse('internal_ai:admin_home'))
        self.client.force_login(self.employee)
        self.assertNotContains(self.client.get(reverse('internal_ai:chat')), reverse('internal_ai:admin_home'))


class StaffLimitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_user('limit-admin', is_staff=True)
        cls.staff = get_user_model().objects.create_user('limit-staff', last_name='制限職員')
        cls.url = reverse('internal_ai:staff_limit_edit', args=[cls.staff.pk])
        cls.data = {'enabled': 'on', 'daily_request_limit': '10', 'monthly_cost_limit_jpy': '500.50',
                    'max_input_chars': '3000', 'max_output_tokens': '1000', 'allowed_model_level': '2'}

    def test_permissions_and_csrf(self):
        from django.test import Client
        listing = reverse('internal_ai:staff_limits')
        for url in (listing, self.url):
            self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(listing).status_code, 403)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.data).status_code, 403)
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.admin)
        self.assertEqual(secure.post(self.url, self.data).status_code, 403)

    def test_get_does_not_create_profile_and_search(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(self.url), '制限職員')
        response = self.client.get(reverse('internal_ai:staff_limits'), {'q': '制限職員'})
        self.assertEqual(response.context['page_obj'].paginator.count, 1)
        self.assertContains(response, self.url)
        self.assertFalse(AIProfile.objects.filter(user=self.staff).exists())
        self.assertEqual(self.client.get(reverse('internal_ai:staff_limit_edit', args=[999999])).status_code, 404)

    def test_save_audit_and_cannot_change_role(self):
        from .models import AuditLog
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(self.url, {**self.data, 'role': 'SUPER_ADMIN'}), self.url)
        p = AIProfile.objects.get(user=self.staff)
        self.assertEqual(p.role, 'USER')
        self.assertEqual(p.daily_request_limit, 10)
        self.assertEqual(p.monthly_cost_limit_jpy, Decimal('500.50'))
        event = AuditLog.objects.get()
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.before_value['daily_request_limit'], 50)
        self.assertEqual(event.after_value['daily_request_limit'], 10)
        self.assertEqual(event.target_id, str(p.pk))
        response = self.client.post(self.url, {**self.data, 'daily_request_limit': '0'}, follow=True)
        self.assertContains(response, '制限設定を保存しました')
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(reverse('internal_ai:chat_api'), {'message': 'test'}).status_code, 403)

    def test_invalid_values_do_not_save(self):
        from .models import AuditLog
        self.client.force_login(self.admin)
        for field, value in [('daily_request_limit', '-1'), ('monthly_cost_limit_jpy', '-1'),
                             ('monthly_cost_limit_jpy', '1.001'), ('max_input_chars', '0'),
                             ('max_output_tokens', '0'), ('allowed_model_level', '-1'),
                             ('daily_request_limit', '2147483648'), ('max_input_chars', 'invalid')]:
            with self.subTest(field=field, value=value):
                response = self.client.post(self.url, {**self.data, field: value})
                self.assertContains(response, '設定は保存されていません')
                self.assertFalse(AIProfile.objects.filter(user=self.staff).exists())
        self.assertFalse(AuditLog.objects.exists())

    def test_disable_and_self_disable_guard(self):
        self.client.force_login(self.admin)
        data = {key: value for key, value in self.data.items() if key != 'enabled'}
        self.client.post(self.url, data)
        self.assertFalse(AIProfile.objects.get(user=self.staff).enabled)
        own_url = reverse('internal_ai:staff_limit_edit', args=[self.admin.pk])
        self.assertContains(self.client.post(own_url, data), '自分自身の利用停止は別の管理者に依頼してください')
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(reverse('internal_ai:chat_api'), {'message': 'test'}).status_code, 403)


class StaffManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_user('manager', is_staff=True)
        cls.staff = get_user_model().objects.create_user('member', last_name='対象', email='member@example.com')
        cls.list_url = reverse('internal_ai:staff_management')
        cls.create_url = reverse('internal_ai:staff_create')
        cls.edit_url = reverse('internal_ai:staff_edit', args=[cls.staff.pk])
        cls.data = {'username': 'new-member', 'last_name': '新規', 'first_name': '職員',
                    'email': 'new@example.com', 'is_active': 'on',
                    'password1': 'Strong-Staff-Password-394!', 'password2': 'Strong-Staff-Password-394!'}

    def test_permissions_and_csrf(self):
        from django.test import Client
        for url in (self.list_url, self.create_url, self.edit_url):
            self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.staff)
        for url in (self.list_url, self.create_url, self.edit_url):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(self.create_url, self.data).status_code, 403)
        self.assertEqual(self.client.post(self.edit_url, self.data).status_code, 403)
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.admin)
        self.assertEqual(secure.post(self.create_url, self.data).status_code, 403)

    def test_create_with_password_default_limits_and_audit(self):
        from .models import AuditLog
        self.client.force_login(self.admin)
        response = self.client.post(self.create_url, {**self.data, 'is_staff': 'on', 'is_superuser': 'on', 'role': 'ADMIN'})
        user = get_user_model().objects.get(username='new-member')
        self.assertRedirects(response, reverse('internal_ai:staff_edit', args=[user.pk]))
        self.assertTrue(user.check_password(self.data['password1']))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.ai_profile.role, 'USER')
        event = AuditLog.objects.get(action='CREATE_STAFF')
        self.assertEqual(event.actor, self.admin)
        self.assertNotIn('password', str(event.after_value))
        self.client.logout()
        self.assertRedirects(self.client.post(reverse('internal_ai:login'), {
            'username': user.username, 'password': self.data['password1'],
        }), reverse('internal_ai:chat'))

    def test_invalid_registration(self):
        self.client.force_login(self.admin)
        for patch in ({'username': 'member'}, {'password2': 'mismatch'}, {'email': 'bad'}, {'username': ''}):
            with self.subTest(patch=patch):
                self.assertContains(self.client.post(self.create_url, {**self.data, **patch}), '保存されていません')
        self.assertEqual(get_user_model().objects.count(), 2)

    def test_edit_preserves_limits_password_and_deactivates_session(self):
        from .models import AuditLog
        AIProfile.objects.create(user=self.staff, daily_request_limit=7)
        self.staff.set_password('Original-Password-123!')
        self.staff.save()
        self.client.force_login(self.admin)
        data = {'username': 'member', 'last_name': '更新', 'first_name': '職員', 'email': 'updated@example.com'}
        self.assertRedirects(self.client.post(self.edit_url, data), self.edit_url)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_active)
        self.assertEqual(self.staff.last_name, '更新')
        self.assertTrue(self.staff.check_password('Original-Password-123!'))
        self.assertEqual(self.staff.ai_profile.daily_request_limit, 7)
        event = AuditLog.objects.get(action='UPDATE_STAFF')
        self.assertTrue(event.before_value['is_active'])
        self.assertFalse(event.after_value['is_active'])
        self.client.logout()
        self.assertFalse(self.client.login(username='member', password='Original-Password-123!'))
        self.client.force_login(self.admin)
        self.client.post(self.edit_url, {**data, 'is_active': 'on'})
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)

    def test_protected_accounts_and_self_deactivation(self):
        self.client.force_login(self.admin)
        own = reverse('internal_ai:staff_edit', args=[self.admin.pk])
        self.assertEqual(self.client.post(own, {'username': 'manager'}).status_code, 403)
        self.admin.is_superuser = True
        self.admin.save()
        self.assertContains(self.client.post(own, {'username': 'manager'}), '自分自身のアカウントは無効にできません')
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_search_status_pagination_and_missing_user(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(self.list_url, {'q': 'member@example.com'}), '対象')
        self.assertEqual(self.client.get(self.list_url, {'status': 'inactive'}).context['page_obj'].paginator.count, 0)
        for i in range(26):
            get_user_model().objects.create_user(f'search-{i}')
        response = self.client.get(self.list_url, {'q': 'search-', 'status': 'active', 'page': '2'})
        self.assertEqual(len(response.context['page_obj']), 1)
        self.assertContains(response, 'status=active')
        self.assertEqual(self.client.get(reverse('internal_ai:staff_edit', args=[999999])).status_code, 404)

    def test_audit_failure_rolls_back_creation(self):
        from unittest.mock import patch
        self.client.force_login(self.admin)
        with patch('internal_ai.views.AuditLog.objects.create', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.client.post(self.create_url, self.data)
        self.assertFalse(get_user_model().objects.filter(username='new-member').exists())


class LogSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_user('log-admin', is_staff=True)
        cls.staff = get_user_model().objects.create_user('log-staff', last_name='検索職員')
        cls.model = ModelSetting.objects.create(model_code='log-model', display_name='検索モデル')
        cls.url = reverse('internal_ai:log_search')

    def usage(self, date='2026-09-08T12:00:00', **kwargs):
        return UsageLog.objects.create(request_id=uuid4(), user=self.staff, model=self.model,
            created_at=timezone.make_aware(datetime.fromisoformat(date)), status=kwargs.pop('status', 'SUCCESS'), **kwargs)

    def test_access_and_methods(self):
        self.assertRedirects(self.client.get(self.url), reverse('internal_ai:login') + '?next=' + self.url)
        self.client.force_login(self.staff)
        for kind in ('usage', 'audit'):
            self.assertEqual(self.client.get(self.url, {'kind': kind}).status_code, 403)
        AIProfile.objects.create(user=self.staff, role='ADMIN')
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_inclusive_japan_dates_and_combined_filters(self):
        self.client.force_login(self.admin)
        self.usage('2026-09-07T23:59:59')
        first = self.usage('2026-09-08T00:00:00', status='FAILED', error_code='TestError')
        last = self.usage('2026-09-08T23:59:59', status='FAILED', error_code='TestError')
        self.usage('2026-09-09T00:00:00')
        self.usage()
        response = self.client.get(self.url, {'kind': 'usage', 'start': '2026-09-08', 'end': '2026-09-08',
            'staff': '検索職員', 'status': 'FAILED', 'keyword': 'TestError'})
        self.assertEqual(list(response.context['page_obj']), [last, first])
        self.assertContains(response, 'TestError')
        self.assertContains(response, str(first.request_id))

    def test_uuid_model_search_and_open_dates(self):
        self.client.force_login(self.admin)
        log = self.usage()
        for keyword in (str(log.request_id), '検索モデル', 'log-model'):
            response = self.client.get(self.url, {'start': '', 'end': '', 'keyword': keyword})
            self.assertEqual(response.context['page_obj'].paginator.count, 1)
        response = self.client.get(self.url, {'start': '', 'end': '', 'keyword': 'no-such-id'})
        self.assertContains(response, '条件に一致するログはありません。')

    def test_audit_filters_details_and_escaping(self):
        from .models import AuditLog
        self.client.force_login(self.admin)
        event = AuditLog.objects.create(actor=self.admin, action='UPDATE_STAFF_LIMITS', target_type='AIProfile', target_id='123',
            before_value={'enabled': True}, after_value={'note': '<script>alert(1)</script>'})
        for keyword in ('UPDATE_STAFF', 'AIProfile', '123'):
            response = self.client.get(self.url, {'kind': 'audit', 'staff': 'log-admin', 'keyword': keyword})
            self.assertEqual(list(response.context['page_obj']), [event])
            self.assertContains(response, '変更前後を表示')
            self.assertContains(response, '&lt;script&gt;')
            self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertEqual(self.client.get(self.url, {'kind': 'audit', 'staff': 'missing'}).context['page_obj'].paginator.count, 0)

    def test_invalid_conditions_do_not_query_all_logs(self):
        self.client.force_login(self.admin)
        self.usage()
        for params in ({'start': 'bad'}, {'start': '2026-10-01', 'end': '2026-09-01'},
                       {'end': '9999-12-31'}, {'kind': 'unknown'}, {'status': 'unknown'}):
            with self.subTest(params=params):
                response = self.client.get(self.url, params)
                self.assertContains(response, '検索は実行されていません')
                self.assertEqual(response.context['page_obj'].paginator.count, 0)

    def test_defaults_and_pagination(self):
        self.client.force_login(self.admin)
        today = timezone.localdate()
        self.usage((today - timezone.timedelta(days=30)).isoformat() + 'T23:59:59')
        for _ in range(26):
            self.usage(today.isoformat() + 'T00:00:00', status='FAILED')
        response = self.client.get(self.url, {'status': 'FAILED', 'staff': 'log-staff', 'page': '2'})
        self.assertEqual(response.context['page_obj'].paginator.count, 26)
        self.assertEqual(len(response.context['page_obj']), 1)
        self.assertContains(response, 'status=FAILED')
        self.assertContains(response, 'staff=log-staff')
        self.assertIn('start=', response.context['pagination_query'])
        self.assertEqual(self.client.get(self.url, {'page': 'bad'}).status_code, 200)


class UsageContentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user('content-staff')
        cls.admin = get_user_model().objects.create_user('content-admin', is_staff=True)
        cls.model = ModelSetting.objects.create(model_code='content-test', display_name='本文テスト')
        cls.url = reverse('internal_ai:log_search')

    def test_success_saves_exact_question_and_answer(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        question = '質問です。\n<script>alert(1)</script>'
        answer = '回答です。\n<strong>本文</strong>'
        self.client.force_login(self.staff)
        with self.settings(OPENAI_API_KEY='test-key'), patch('openai.OpenAI') as client:
            client.return_value.responses.create.return_value = SimpleNamespace(
                output_text=answer, usage=SimpleNamespace(input_tokens=10, output_tokens=20))
            response = self.client.post(reverse('internal_ai:chat_api'), {'message': question, 'model': self.model.model_code})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['answer'], answer)
        log = UsageLog.objects.get(user=self.staff)
        self.assertEqual(log.prompt_text, question)
        self.assertEqual(log.response_text, answer)
        self.assertEqual(log.status, 'SUCCESS')
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertContains(response, '質問・回答の詳細を表示')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertContains(response, '&lt;strong&gt;本文&lt;/strong&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')

    def test_failure_keeps_question_without_fabricating_answer(self):
        from unittest.mock import patch
        self.client.force_login(self.staff)
        with self.settings(OPENAI_API_KEY='test-key'), patch('openai.OpenAI') as client, patch('internal_ai.views.logger.exception'):
            client.return_value.responses.create.side_effect = RuntimeError('test')
            response = self.client.post(reverse('internal_ai:chat_api'), {'message': '失敗した質問', 'model': self.model.model_code})
        self.assertEqual(response.status_code, 502)
        log = UsageLog.objects.get(user=self.staff)
        self.assertEqual(log.prompt_text, '失敗した質問')
        self.assertIsNone(log.response_text)
        self.assertEqual(log.status, 'FAILED')

    def test_legacy_log_has_no_content(self):
        log = UsageLog.objects.create(request_id=uuid4(), user=self.staff, model=self.model, status='SUCCESS')
        self.assertIsNone(log.prompt_text)
        self.assertIsNone(log.response_text)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(self.url), '本文の記録なし')


class AdminNavigationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_user('nav-admin', is_staff=True)
        cls.staff = get_user_model().objects.create_user('nav-staff')
        cls.model = ModelSetting.objects.create(model_code='nav-model', display_name='ナビモデル')
        cls.data = {'model_code': 'new-model', 'display_name': '新モデル', 'enabled': 'on',
                    'permission_level': '2', 'input_price_per_million': '0.25', 'output_price_per_million': '1.5'}

    def test_navigation_on_every_admin_page(self):
        self.client.force_login(self.admin)
        destinations = ['dashboard', 'staff_management', 'staff_limits', 'ai_settings', 'log_search']
        for name in ['admin_home', *destinations, 'ai_model_create', 'staff_create']:
            response = self.client.get(reverse('internal_ai:' + name))
            self.assertEqual(response.status_code, 200)
            for destination in destinations:
                self.assertContains(response, reverse('internal_ai:' + destination))
            if name != 'admin_home':
                self.assertContains(response, 'aria-current="page"')

    def test_permissions(self):
        for name in ('admin_home', 'ai_settings', 'ai_model_create'):
            self.assertEqual(self.client.get(reverse('internal_ai:' + name)).status_code, 302)
        self.client.force_login(self.staff)
        for name in ('admin_home', 'ai_settings', 'ai_model_create'):
            self.assertEqual(self.client.get(reverse('internal_ai:' + name)).status_code, 403)
        self.assertEqual(self.client.post(reverse('internal_ai:ai_model_create'), self.data).status_code, 403)
        self.assertEqual(self.client.post(reverse('internal_ai:ai_model_edit', args=[self.model.pk]), self.data).status_code, 403)

    def test_model_save_validation_and_effect(self):
        from .models import AuditLog
        self.client.force_login(self.admin)
        response = self.client.post(reverse('internal_ai:ai_model_create'), self.data)
        model = ModelSetting.objects.get(model_code='new-model')
        edit = reverse('internal_ai:ai_model_edit', args=[model.pk])
        self.assertRedirects(response, edit)
        self.assertEqual(model.input_price_per_million, Decimal('0.25'))
        self.assertTrue(AuditLog.objects.filter(action='CREATE_AI_MODEL', target_id=str(model.pk)).exists())
        self.assertContains(self.client.post(edit, {**self.data, 'output_price_per_million': '-1'}), '保存されていません')
        self.assertContains(self.client.post(reverse('internal_ai:ai_model_create'), self.data), '保存されていません')
        self.client.post(edit, {**self.data, 'model_code': 'tampered', 'enabled': '', 'permission_level': '1'})
        model.refresh_from_db()
        self.assertEqual(model.model_code, 'new-model')
        self.assertFalse(model.enabled)
        self.client.force_login(self.staff)
        self.assertNotContains(self.client.get(reverse('internal_ai:chat')), '新モデル')

    def test_csrf_and_missing_model(self):
        from django.test import Client
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.admin)
        self.assertEqual(secure.post(reverse('internal_ai:ai_model_create'), self.data).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('internal_ai:ai_model_edit', args=[999999])).status_code, 404)

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse


class PasswordChangeTests(TestCase):
    namespaces = ('close_side', 'open_side', 'internal_ai')

    def setUp(self):
        self.user = get_user_model().objects.create_user('employee', password='Original-pass-123!')

    def test_requires_login(self):
        for namespace in self.namespaces:
            for name in ('password_change', 'password_change_done'):
                url = reverse(f'{namespace}:{name}')
                self.assertRedirects(self.client.get(url), reverse(f'{namespace}:login') + '?next=' + url)

    def test_change_preserves_session_and_updates_password(self):
        for namespace in self.namespaces:
            with self.subTest(namespace=namespace):
                self.user.set_password('Original-pass-123!')
                self.user.save()
                self.client.force_login(self.user)
                url = reverse(f'{namespace}:password_change')
                response = self.client.get(url)
                self.assertContains(response, '現在のパスワード')
                self.assertContains(response, 'csrfmiddlewaretoken')
                response = self.client.post(url, {
                    'old_password': 'Original-pass-123!',
                    'new_password1': 'Updated-pass-456!',
                    'new_password2': 'Updated-pass-456!',
                }, follow=True)
                self.assertContains(response, 'パスワードを変更しました')
                self.user.refresh_from_db()
                self.assertTrue(self.user.check_password('Updated-pass-456!'))
                self.assertFalse(self.user.check_password('Original-pass-123!'))
                self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)
                self.assertEqual(self.client.get(url).status_code, 200)

    @override_settings(AUTH_PASSWORD_VALIDATORS=[{
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 12},
    }])
    def test_invalid_passwords_do_not_change_credentials(self):
        self.client.force_login(self.user)
        for namespace in self.namespaces:
            for old, first, second, field in (
                ('wrong', 'Updated-pass-456!', 'Updated-pass-456!', 'old_password'),
                ('Original-pass-123!', 'Updated-pass-456!', 'different', 'new_password2'),
                ('Original-pass-123!', 'short', 'short', 'new_password2'),
            ):
                response = self.client.post(reverse(f'{namespace}:password_change'), {
                    'old_password': old, 'new_password1': first, 'new_password2': second,
                })
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context['form'].errors)
                self.user.refresh_from_db()
                self.assertTrue(self.user.check_password('Original-pass-123!'))

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for namespace in self.namespaces:
            self.assertEqual(client.post(reverse(f'{namespace}:password_change'), {
                'old_password': 'Original-pass-123!',
                'new_password1': 'Updated-pass-456!', 'new_password2': 'Updated-pass-456!',
            }).status_code, 403)

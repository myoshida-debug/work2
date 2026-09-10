from django.contrib.auth.views import PasswordChangeDoneView, PasswordChangeView, redirect_to_login
from django.urls import reverse


class AccountContextMixin:
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), self.get_login_url())
        return super().dispatch(request, *args, **kwargs)

    def get_login_url(self):
        return reverse(f'{self.request.resolver_match.namespace}:login')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        namespace = self.request.resolver_match.namespace
        context['account_base'] = (
            'internal_ai/base.html' if namespace == 'internal_ai'
            else 'anonymizer_app/base.html'
        )
        context['return_url'] = reverse(
            f'{namespace}:chat' if namespace == 'internal_ai' else f'{namespace}:menu'
        )
        return context


class AccountPasswordChangeView(AccountContextMixin, PasswordChangeView):
    template_name = 'anonymizer_app/password_change.html'

    def get_success_url(self):
        return reverse(f'{self.request.resolver_match.namespace}:password_change_done')


class AccountPasswordChangeDoneView(AccountContextMixin, PasswordChangeDoneView):
    template_name = 'anonymizer_app/password_change_done.html'

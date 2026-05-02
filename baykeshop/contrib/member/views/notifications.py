from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from baykeshop.contrib.common.mixins import BaykeLoginRequiredMixin
from baykeshop.contrib.member.services.notification_service import NotificationService


class BaykeShopNotificationsView(BaykeLoginRequiredMixin, TemplateView):
    """消息中心"""
    template_name = 'baykeshop/member/notifications.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = int(self.request.GET.get('page', 1))
        result = NotificationService.get_user_notifications(self.request.user, page=page)
        context['title'] = _('消息中心')
        context['notifications'] = result['notifications']
        context['page'] = result['page']
        context['total_pages'] = result['total_pages']
        context['page_range'] = range(1, result['total_pages'] + 1)
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        if action == 'mark_read':
            notif_id = request.POST.get('id')
            if notif_id:
                NotificationService.mark_read(int(notif_id), request.user)
        elif action == 'mark_all_read':
            NotificationService.mark_all_read(request.user)
        return JsonResponse({'success': True})

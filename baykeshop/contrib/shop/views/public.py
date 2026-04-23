from django.views.generic import TemplateView
from django.utils.translation import gettext_lazy as _

from baykeshop.contrib.shop.services.public_service import PublicService


class BaykeShopIndexView(TemplateView):
    template_name = 'baykeshop/index.html'

    def get_floors(self):
        """ 获取楼层 """
        return PublicService.get_index_floors()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['floors'] = self.get_floors()
        context['title'] = _('首页')
        return context
        
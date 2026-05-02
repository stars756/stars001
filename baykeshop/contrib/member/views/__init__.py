from .actions import CommentActionView, OrderStatusActionView
from .auth import (
                   BaykePasswordResetCompleteView,
                   BaykePasswordResetConfirmView,
                   BaykePasswordResetDoneView,
                   BaykePasswordResetView,
                   BaykeShopUserLoginView,
                   BaykeShopUserLogoutView,
                   BaykeShopUserRegisterView,
                   EmailVerificationView,
                   IPVerificationView,
                   ResendVerificationEmailView,
                   SendSMSVerificationView,
)
from .favorites import BaykeShopFavoritesView
from .notifications import BaykeShopNotificationsView
from .orders import BaykeShopOrdersDetailView, BaykeShopOrdersListView
from .profile import (
                   BaykeShopUserAddressCreateView,
                   BaykeShopUserAddressDeleteView,
                   BaykeShopUserAddressListView,
                   BaykeShopUserAddressUpdateView,
                   BaykeShopUserPasswordView,
                   BaykeShopUserProfileUpdateView,
                   BaykeShopUserProfileView,
)

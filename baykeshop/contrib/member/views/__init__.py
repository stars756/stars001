from .auth import (
    BaykeShopUserLoginView,
    BaykeShopUserLogoutView,
    BaykeShopUserRegisterView,
    BaykePasswordResetView,
    BaykePasswordResetDoneView,
    BaykePasswordResetConfirmView,
    BaykePasswordResetCompleteView,
    EmailVerificationView,
    ResendVerificationEmailView,
    IPVerificationView,
    SendSMSVerificationView,
)
from .orders import BaykeShopOrdersListView, BaykeShopOrdersDetailView
from .actions import OrderStatusActionView, CommentActionView
from .profile import (
    BaykeShopUserProfileView,
    BaykeShopUserPasswordView,
    BaykeShopUserAddressListView,
    BaykeShopUserAddressCreateView,
    BaykeShopUserAddressUpdateView,
    BaykeShopUserAddressDeleteView,
    BaykeShopUserProfileUpdateView,
)


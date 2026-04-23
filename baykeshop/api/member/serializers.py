from django.contrib.auth import get_user_model
from rest_framework import serializers


from baykeshop.contrib.member.models import BaykeShopUser, BaykeShopUserAddress
from baykeshop.db import validators

User = get_user_model()


class BaykeShopUserAddressSerializer(serializers.ModelSerializer):
    """用户地址序列化器"""

    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = BaykeShopUserAddress
        fields = ('id', 'user', 'name', 'phone', 'province', 'city', 'district',
                  'address', 'email', 'is_default', 'created_time', 'updated_time')
        read_only_fields = ('id', 'created_time', 'updated_time')

    def validate_phone(self, value):
        validators.validate_phone(value)
        return value


class BaykeShopUserSerializer(serializers.ModelSerializer):
    """用户信息序列化器"""

    address_count = serializers.SerializerMethodField()
    default_address = serializers.SerializerMethodField()

    class Meta:
        model = BaykeShopUser
        fields = ('id', 'user', 'nickname', 'gender', 'birthday', 'email',
                  'qq', 'wechat', 'description', 'avatar',
                  'is_email_verified', 'address_count', 'default_address')
        read_only_fields = ('id', 'user')

    def get_address_count(self, obj):
        return obj.user.baykeshopuseraddress_set.count()

    def get_default_address(self, obj):
        default = obj.user.baykeshopuseraddress_set.filter(is_default=True).first()
        if default:
            return BaykeShopUserAddressSerializer(default).data
        return None


class BaykeShopEmailVerifySerializer(serializers.Serializer):
    """邮箱验证序列化器"""

    token = serializers.CharField(write_only=True, required=True)
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        fields = ('token', 'user')


class BaykeShopSMSVerifySerializer(serializers.Serializer):
    """短信验证码序列化器"""

    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    operation_type = serializers.CharField(
        max_length=50,
        required=False,
        default='general',
        allow_blank=True
    )

    class Meta:
        fields = ('user', 'operation_type',)


class BaykeShopProfileUpdateSerializer(serializers.Serializer):
    """
    个人资料更新序列化器
    """

    nickname = serializers.CharField(max_length=100, required=False, allow_blank=True)
    gender = serializers.ChoiceField(
        choices=[('', ''), ('male', '男'), ('female', '女')],
        required=False
    )
    birthday = serializers.DateField(required=False, allow_null=True)
    qq = serializers.CharField(max_length=20, required=False, allow_blank=True)
    wechat = serializers.CharField(max_length=50, required=False, allow_blank=True)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    email = serializers.EmailField(required=False)
    mobile = serializers.CharField(max_length=20, required=False)
    avatar = serializers.ImageField(required=False, allow_null=True)
    sms_code = serializers.CharField(max_length=6, required=True, write_only=True)

    class Meta:
        fields = ('nickname', 'gender', 'birthday', 'qq', 'wechat', 'description',
                  'email', 'mobile', 'avatar', 'sms_code')

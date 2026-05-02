DEFAULTS = {
    # 站点基本设置
    'SITE_ID': 1,
    'SITE_TITLE': 'BaykeShop',
    'SITE_HEADER': 'baykeShop开源商城系统',
    'INDEX_TITLE': '欢迎使用BaykeShop商城系统',
    'DESCRIPTION': '基于Django构建的开源商城系统',
    'KEYWORDS': 'baykeShop,商城系统,Django商城系统,Django商城',
    'COPYRIGHT': 'BaykeShop © 2024 All rights reserved.',
    'ICP': '陕ICP备19000001号',

    # 邮箱基本配置
    'EMAIL_HOST': 'smtp.qq.com',
    'EMAIL_HOST_USER': '',
    'EMAIL_HOST_PASSWORD': '',
    'EMAIL_PORT': 465,
    'EMAIL_USE_SSL': True,
    'EMAIL_USE_TLS': False,
    'EMAIL_BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
    'DEFAULT_FROM_EMAIL': '',
    'EMAIL_SUBJECT_PREFIX': '[baykeShop]',

    # 支付宝配置（必须在 .env 或管理后台中设置）
    'ALIPAY_APPID': '',
    'ALIPAY_PRIVATE_KEY': '',
    'ALIPAY_PUBLIC_KEY': '',

    # 手机号验证规则
    'REGEX_PHONE' : r'^1[3-9]\d{9}$',
    # 上传图片大小
    'MAX_IMAGE_SIZE': 2 * 1024 * 1024,
    # 自定义菜单开关
    'USE_MENU': False,

    # ============================================================
    # 安全验证相关配置（重构后统一收敛，消灭硬编码）
    # ============================================================
    # SMS验证码
    'SMS_CODE_LENGTH': 6,                        # 验证码长度
    'SMS_CODE_EXPIRE_SECONDS': 300,              # 验证码过期时间（5分钟）
    'SMS_RATE_LIMIT_MINUTE': 1,                  # 每分钟限发次数
    'SMS_RATE_LIMIT_HOUR': 5,                    # 每小时限发次数
    'SMS_RATE_MINUTE_WINDOW': 60,                # 1分钟限流窗口（秒）
    'SMS_RATE_HOUR_WINDOW': 3600,               # 1小时限流窗口（秒）

    # 邮箱验证
    'EMAIL_VERIFY_TOKEN_EXPIRE_SECONDS': 86400,  # 邮箱验证token有效期（24小时）
    'EMAIL_VERIFY_COOLDOWN_SECONDS': 60,         # 邮箱验证冷却时间（秒）
    'EMAIL_RESEND_COOLDOWN_SECONDS': 300,        # 重发冷却时间（5分钟）

    # 缓存键前缀
    'CACHE_PREFIX_SMS_VERIFY': 'sms_verify',           # SMS验证码缓存键前缀
    'CACHE_PREFIX_SMS_RATE_MINUTE': 'sms_rate_minute', # SMS频率限制（分钟）前缀
    'CACHE_PREFIX_SMS_RATE_HOUR': 'sms_rate_hour',     # SMS频率限制（小时）前缀
    'CACHE_PREFIX_EMAIL_VERIFY_LIMIT': 'email_verify_limit',  # 邮箱验证频率限制前缀
    'CACHE_PREFIX_EMAIL_RESEND_LIMIT': 'email_resend_limit',  # 重发频率限制前缀

    # 验证码安全
    'MAX_VERIFICATION_ATTEMPTS': 5,                    # 验证码最大尝试次数
    'VERIFICATION_LOCKOUT_SECONDS': 1800,              # 锁定时间（30分钟）
}

IMPORT_STRINGS = [
    'EMAIL_BACKEND'
]

REMOVED_SETTINGS = []
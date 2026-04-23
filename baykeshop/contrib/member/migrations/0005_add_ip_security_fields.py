# Generated for account security system - 2026-03-14

from django.conf import settings
import django.contrib.sites.managers
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('member', '0004_baykeshopuser_email_verification_token_and_more'),
    ]

    operations = [
        # 添加IP安全相关字段到 BaykeShopUser 模型
        migrations.AddField(
            model_name='baykeshopuser',
            name='trusted_ips',
            field=models.TextField(default='[]', verbose_name='可信IP列表'),
        ),
        migrations.AddField(
            model_name='baykeshopuser',
            name='ip_verify_token',
            field=models.CharField(blank=True, max_length=64, null=True, verbose_name='IP验证令牌'),
        ),
        migrations.AddField(
            model_name='baykeshopuser',
            name='ip_verify_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='IP验证令牌生成时间'),
        ),
        migrations.AddField(
            model_name='baykeshopuser',
            name='ip_verify_target',
            field=models.GenericIPAddressField(blank=True, null=True, verbose_name='待验证的IP地址'),
        ),

        # 创建 SecurityLog 安全操作日志模型
        migrations.CreateModel(
            name='SecurityLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_time', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_time', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('is_delete', models.BooleanField(default=False, editable=False, verbose_name='是否删除')),
                ('ip_address', models.GenericIPAddressField(verbose_name='IP地址')),
                ('action_type', models.CharField(
                    choices=[
                        ('LOGIN', '登录'),
                        ('IP_VERIFY', 'IP验证'),
                        ('REGISTER', '注册'),
                        ('BIND_CARD', '绑卡'),
                        ('PAYMENT', '支付'),
                        ('WITHDRAW', '提现'),
                        ('CHANGE_PASSWORD', '修改密码'),
                        ('CHANGE_EMAIL', '修改邮箱'),
                        ('CHANGE_MOBILE', '修改手机'),
                        ('IP_UNTRUSTED_ACCESS', '不可信IP访问'),
                    ],
                    max_length=50,
                    verbose_name='操作类型'
                )),
                ('action_detail', models.TextField(verbose_name='操作详情')),
                ('status', models.CharField(
                    choices=[('success', '成功'), ('failed', '失败')],
                    max_length=20,
                    verbose_name='状态'
                )),
                ('site', models.ForeignKey(
                    blank=True,
                    editable=False,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    to='sites.site',
                    verbose_name='站点'
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='用户'
                )),
            ],
            options={
                'verbose_name': '安全日志',
                'verbose_name_plural': '安全日志',
                'ordering': ['-created_time'],
                'indexes': [
                    models.Index(fields=['user', '-created_time'], name='user_time_idx'),
                    models.Index(fields=['ip_address', '-created_time'], name='ip_time_idx'),
                ],
            },
            managers=[
                ('objects', django.db.models.manager.Manager()),
                ('current_site', django.contrib.sites.managers.CurrentSiteManager()),
            ],
        ),
    ]

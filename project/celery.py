# ============================================================
# Celery 应用配置
# ============================================================
import os
from celery import Celery

# 从 Django settings 中读取配置
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')

app = Celery('project')

# 从 settings.py 中以 CELERY_ 为前缀的配置项作为 Celery 配置
app.config_from_object('django.conf:settings', namespace='CELERY')

# 自动发现各 app 下的 tasks.py
app.autodiscover_tasks()

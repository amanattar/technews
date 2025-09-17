import os
from celery import Celery

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'technews_project.settings')

app = Celery('technews_project')

# Configure Celery using settings from Django settings.py
app.config_from_object('django.conf:settings', namespace='CELERY')

# Autodiscover tasks
app.autodiscover_tasks()

# Simple debug task
@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
    return 'Debug task completed successfully'

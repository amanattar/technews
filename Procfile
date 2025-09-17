release: python manage.py migrate && python manage.py migrate django_celery_beat
web: gunicorn technews_project.wsgi:application --bind 0.0.0.0:$PORT
worker: C_FORCE_ROOT=1 celery -A technews_project worker --loglevel=info --concurrency=4
beat: C_FORCE_ROOT=1 celery -A technews_project beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler

release: python manage.py migrate && python manage.py migrate django_celery_beat && python manage.py migrate django_celery_results
web: gunicorn technews_project.wsgi:application --bind 0.0.0.0:$PORT --timeout 120
worker: python -m celery -A technews_project worker --loglevel=debug --pool=solo
beat: python -m celery -A technews_project beat --loglevel=debug

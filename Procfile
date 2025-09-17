web: gunicorn technews_project.wsgi:application --bind 0.0.0.0:$PORT
worker: celery -A technews_project worker --loglevel=info
beat: celery -A technews_project beat --loglevel=info
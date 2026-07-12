web: gunicorn config.wsgi:application --workers 2 --timeout 120 --bind 0.0.0.0:$PORT --log-level info
worker: celery -A config worker --loglevel=info --concurrency=2

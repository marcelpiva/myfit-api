web: uvicorn src.main:app --host 0.0.0.0 --port $PORT
worker: celery -A src.core.celery_app worker -B -l info --concurrency=2

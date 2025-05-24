from celery import Celery
from config import get_settings
import multiprocessing
import os

# Set environment variables for CUDA
os.environ['CUDA_VISIBLE_DEVICES'] = ''  # Disable CUDA
os.environ['TORCH_MULTIPROCESSING_START_METHOD'] = 'spawn'

# Set multiprocessing start method
multiprocessing.set_start_method('spawn', force=True)

settings = get_settings()

# Create Celery instance
celery_app = Celery(
    'receipt_processor',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Europe/Warsaw',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour timeout
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks
    worker_prefetch_multiplier=1,  # Process one task at a time
    broker_connection_retry_on_startup=True,  # Add this to fix the warning
    worker_pool_restarts=True,  # Enable worker pool restarts
    worker_pool='prefork'  # Use prefork pool
)

# Import tasks module to register tasks
celery_app.autodiscover_tasks(['tasks'], force=True)

# Import and register the process_receipt task
from tasks import process_receipt_task
celery_app.tasks.register(process_receipt_task) 
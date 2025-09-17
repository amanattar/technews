from django.core.management.base import BaseCommand
from django.conf import settings
from news_aggregator.models import Source, Tag
from django_celery_beat.models import PeriodicTask, IntervalSchedule
import json


class Command(BaseCommand):
    help = 'Setup initial RSS sources and Celery periodic tasks for TechNews Aggregator'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset all sources and tasks (WARNING: This will delete existing data)',
        )
        parser.add_argument(
            '--sources-only',
            action='store_true',
            help='Only setup sources, skip Celery tasks',
        )
        parser.add_argument(
            '--tasks-only',
            action='store_true',
            help='Only setup Celery tasks, skip sources',
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Setting up TechNews Aggregator...'))
        
        if options['reset']:
            self.reset_data()
        
        if not options['tasks_only']:
            self.setup_sources()
            self.setup_tags()
        
        if not options['sources_only']:
            self.setup_celery_tasks()
        
        self.stdout.write(self.style.SUCCESS('Setup completed successfully!'))
    
    def reset_data(self):
        self.stdout.write(self.style.WARNING('Resetting existing data...'))
        
        # Delete periodic tasks
        PeriodicTask.objects.filter(
            name__startswith='technews_'
        ).delete()
        
        # Delete sources (this will cascade to articles)
        Source.objects.all().delete()
        
        # Delete tags
        Tag.objects.all().delete()
        
        self.stdout.write(self.style.SUCCESS('Reset completed'))
    
    def setup_sources(self):
        self.stdout.write('Setting up RSS sources...')
        
        # RSS Feed sources from settings
        rss_feeds = getattr(settings, 'RSS_FEEDS', {})
        
        # Add default sources if none configured
        if not rss_feeds:
            rss_feeds = {
                'techcrunch': 'https://techcrunch.com/feed/',
                'theverge': 'https://www.theverge.com/rss/index.xml',
                'android_authority': 'https://www.androidauthority.com/feed/',
                'gsmarena': 'https://www.gsmarena.com/rss-news-reviews.php3',
                'macrumors': 'https://www.macrumors.com/macrumors.xml',
            }
        
        for name, url in rss_feeds.items():
            source, created = Source.objects.get_or_create(
                name=name.replace('_', ' ').title(),
                defaults={
                    'url': url,
                    'source_type': 'rss',
                    'is_active': True,
                    'scrape_frequency': 10,
                    'priority_weight': 1.0
                }
            )
            
            if created:
                self.stdout.write(f'  ✓ Created RSS source: {source.name}')
            else:
                self.stdout.write(f'  - RSS source already exists: {source.name}')
        
        
        self.stdout.write(self.style.SUCCESS('Sources setup completed'))
    
    def setup_tags(self):
        self.stdout.write('Setting up default tags...')
        
        default_tags = [
            ('Apple', '#007AFF', 'Apple products and news'),
            ('Samsung', '#1428A0', 'Samsung devices and announcements'),
            ('Google', '#4285F4', 'Google products and services'),
            ('OnePlus', '#EB0028', 'OnePlus devices and updates'),
            ('Xiaomi', '#FF6900', 'Xiaomi products and news'),
            ('Android', '#3DDC84', 'Android OS and ecosystem'),
            ('iOS', '#007AFF', 'iOS updates and features'),
            ('Breaking', '#DC3545', 'Breaking news and urgent updates'),
            ('Rumor', '#FFC107', 'Rumors and speculation'),
            ('Launch', '#28A745', 'Product launches and announcements'),
            ('Review', '#6F42C1', 'Product reviews and analysis'),
            ('India', '#FF9500', 'India-specific tech news'),
            ('AI', '#6F42C1', 'Artificial Intelligence and ML'),
            ('Gaming', '#17A2B8', 'Gaming news and hardware'),
            ('Security', '#DC3545', 'Cybersecurity and privacy'),
        ]
        
        for name, color, description in default_tags:
            tag, created = Tag.objects.get_or_create(
                name=name,
                defaults={
                    'color': color,
                    'description': description
                }
            )
            
            if created:
                self.stdout.write(f'  ✓ Created tag: {tag.name}')
            else:
                self.stdout.write(f'  - Tag already exists: {tag.name}')
        
        self.stdout.write(self.style.SUCCESS('Tags setup completed'))
    
    def setup_celery_tasks(self):
        self.stdout.write('Setting up Celery periodic tasks...')
        
        # Create interval schedules
        schedule_10min, _ = IntervalSchedule.objects.get_or_create(
            every=10,
            period=IntervalSchedule.MINUTES,
        )
        
        schedule_30min, _ = IntervalSchedule.objects.get_or_create(
            every=30,
            period=IntervalSchedule.MINUTES,
        )
        
        schedule_1hour, _ = IntervalSchedule.objects.get_or_create(
            every=1,
            period=IntervalSchedule.HOURS,
        )
        
        schedule_6hours, _ = IntervalSchedule.objects.get_or_create(
            every=6,
            period=IntervalSchedule.HOURS,
        )
        
        schedule_daily, _ = IntervalSchedule.objects.get_or_create(
            every=24,
            period=IntervalSchedule.HOURS,
        )
        
        # Define periodic tasks
        tasks = [
            {
                'name': 'technews_scrape_rss_feeds',
                'task': 'news_aggregator.tasks.scrape_rss_feeds',
                'schedule': schedule_10min,
                'description': 'Scrape all RSS feeds every 10 minutes'
            },
            {
                'name': 'technews_update_priorities',
                'task': 'news_aggregator.tasks.update_article_priorities',
                'schedule': schedule_30min,
                'description': 'Update article priority scores every 30 minutes'
            },
            {
                'name': 'technews_detect_trending',
                'task': 'news_aggregator.tasks.detect_and_update_trending',
                'schedule': schedule_1hour,
                'description': 'Detect trending topics every hour'
            },
            {
                'name': 'technews_health_check',
                'task': 'news_aggregator.tasks.health_check_sources',
                'schedule': schedule_6hours,
                'description': 'Check source health every 6 hours'
            },
            {
                'name': 'technews_cleanup',
                'task': 'news_aggregator.tasks.cleanup_old_data',
                'schedule': schedule_daily,
                'description': 'Clean up old data daily'
            }
        ]
        
        for task_config in tasks:
            task, created = PeriodicTask.objects.get_or_create(
                name=task_config['name'],
                defaults={
                    'task': task_config['task'],
                    'interval': task_config['schedule'],
                    'enabled': True,
                    'description': task_config['description']
                }
            )
            
            if created:
                self.stdout.write(f'  ✓ Created task: {task.name}')
            else:
                # Update existing task
                task.task = task_config['task']
                task.interval = task_config['schedule']
                task.enabled = True
                task.save()
                self.stdout.write(f'  - Updated task: {task.name}')
        
        self.stdout.write(self.style.SUCCESS('Celery tasks setup completed'))
        
        # Provide instructions
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('NEXT STEPS:'))
        self.stdout.write('\n1. Start Redis server:')
        self.stdout.write('   redis-server')
        self.stdout.write('\n2. Start Celery worker:')
        self.stdout.write('   conda activate technews')
        self.stdout.write('   celery -A technews_project worker --loglevel=info')
        self.stdout.write('\n3. Start Celery beat scheduler:')
        self.stdout.write('   conda activate technews')
        self.stdout.write('   celery -A technews_project beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler')
        self.stdout.write('\n4. Start Django development server:')
        self.stdout.write('   conda activate technews')
        self.stdout.write('   python manage.py runserver')
        self.stdout.write('\n5. Access the application:')
        self.stdout.write('   Dashboard: http://127.0.0.1:8000/')
        self.stdout.write('   Admin: http://127.0.0.1:8000/admin/')
        self.stdout.write('   API: http://127.0.0.1:8000/api/')
        self.stdout.write('='*60)
from django.core.management.base import BaseCommand
from news_aggregator.models import Article
from news_aggregator.utils import calculate_priority_label


class Command(BaseCommand):
    help = 'Update existing articles with priority labels based on new keyword system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit the number of articles to update (for testing)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )
        
        # Get articles to update
        articles_queryset = Article.objects.filter(is_processed=True)
        if limit:
            articles_queryset = articles_queryset[:limit]
        
        total_articles = articles_queryset.count()
        self.stdout.write(f'Processing {total_articles} articles...')
        
        updated_count = 0
        priority_counts = {'high': 0, 'medium': 0, 'low': 0, 'minimal': 0}
        
        for i, article in enumerate(articles_queryset.iterator(), 1):
            try:
                # Calculate new priority label
                priority_label, keyword_matches = calculate_priority_label(
                    article.title,
                    article.description,
                    article.content or ''
                )
                
                # Check if update is needed
                needs_update = (
                    article.priority_label != priority_label or
                    article.keyword_matches != keyword_matches
                )
                
                if needs_update:
                    if not dry_run:
                        article.priority_label = priority_label
                        article.keyword_matches = keyword_matches
                        article.save(update_fields=['priority_label', 'keyword_matches'])
                    
                    updated_count += 1
                    if dry_run:
                        self.stdout.write(
                            f'Would update article {article.id}: '
                            f'{article.priority_label} -> {priority_label}'
                        )
                
                priority_counts[priority_label] += 1
                
                # Progress indicator
                if i % 100 == 0:
                    self.stdout.write(f'Processed {i}/{total_articles} articles...')
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error processing article {article.id}: {str(e)}')
                )
                continue
        
        # Summary
        action = 'Would update' if dry_run else 'Updated'
        self.stdout.write(
            self.style.SUCCESS(f'{action} {updated_count} articles')
        )
        
        self.stdout.write('\nPriority distribution:')
        for priority, count in priority_counts.items():
            percentage = (count / total_articles) * 100 if total_articles > 0 else 0
            self.stdout.write(f'  {priority.capitalize()}: {count} ({percentage:.1f}%)')
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('\nRun without --dry-run to apply changes')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('\nPriority labels updated successfully!')
            )
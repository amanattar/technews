from django.core.management.base import BaseCommand
from news_aggregator.models import Article
from news_aggregator.utils import generate_article_summary


class Command(BaseCommand):
    help = 'Generate summaries for articles that do not have summaries yet'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--article-id',
            type=int,
            help='Generate summary for specific article ID',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Maximum number of articles to process (default: 10)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Regenerate summaries even if they already exist',
        )
    
    def handle(self, *args, **options):
        if options['article_id']:
            # Process specific article
            try:
                article = Article.objects.get(id=options['article_id'])
                self.process_article(article, options['force'])
            except Article.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Article with ID {options["article_id"]} not found')
                )
                return
        else:
            # Process articles without summaries
            if options['force']:
                queryset = Article.objects.all()
                self.stdout.write('Processing all articles (forcing regeneration)...')
            else:
                queryset = Article.objects.filter(summary='')
                self.stdout.write('Processing articles without summaries...')
            
            articles = queryset[:options['limit']]
            
            if not articles:
                self.stdout.write(
                    self.style.SUCCESS('No articles found that need summary generation')
                )
                return
            
            self.stdout.write(f'Found {articles.count()} articles to process')
            
            for i, article in enumerate(articles, 1):
                self.stdout.write(f'Processing article {i}/{articles.count()}: {article.title[:80]}...')
                self.process_article(article, options['force'])
        
        self.stdout.write(self.style.SUCCESS('Summary generation completed!'))
    
    def process_article(self, article, force=False):
        """Process a single article to generate summary"""
        if article.summary and not force:
            self.stdout.write(f'  - Article already has summary, skipping (use --force to regenerate)')
            return
        
        try:
            # Generate summary
            summary = generate_article_summary(
                title=article.title,
                content=article.content,
                description=article.description
            )
            
            # Save to database
            article.summary = summary
            article.save(update_fields=['summary'])
            
            summary_preview = summary[:100] + '...' if len(summary) > 100 else summary
            self.stdout.write(f'  ✓ Generated summary: {summary_preview}')
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  ✗ Failed to generate summary: {str(e)}')
            )
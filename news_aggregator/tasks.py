from celery import shared_task
from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone
from datetime import timedelta
import time

from .scrapers import scrape_all_sources, scrape_single_source
from .models import Source, Article, ScrapingLog
from .utils import calculate_priority_score, calculate_priority_label, calculate_recency_bonus, detect_trending_topics, generate_article_summary

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3)
def scrape_rss_feeds(self):
    """Scheduled task to scrape all RSS feeds"""
    try:
        logger.info("Starting RSS feed scraping task")
        start_time = time.time()
        
        scrape_all_sources()
        
        duration = time.time() - start_time
        logger.info(f"RSS scraping completed in {duration:.2f} seconds")
        
        return {
            'status': 'success',
            'duration': duration,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as exc:
        logger.error(f"RSS scraping failed: {str(exc)}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True)
def scrape_single_rss_source(self, source_id):
    """Scrape a single RSS source"""
    try:
        logger.info(f"Scraping single source: {source_id}")
        
        articles_found, articles_new, articles_updated = scrape_single_source(source_id)
        
        return {
            'status': 'success',
            'source_id': source_id,
            'articles_found': articles_found,
            'articles_new': articles_new,
            'articles_updated': articles_updated,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Single source scraping failed for {source_id}: {str(exc)}")
        return {
            'status': 'error',
            'source_id': source_id,
            'error': str(exc),
            'timestamp': timezone.now().isoformat()
        }


@shared_task
def update_article_priorities():
    """Recalculate priority labels and scores for recent articles"""
    try:
        logger.info("Starting priority update task")
        
        # Update articles from last 24 hours
        cutoff_time = timezone.now() - timedelta(hours=24)
        recent_articles = Article.objects.filter(
            scraped_date__gte=cutoff_time,
            is_processed=True
        )
        
        updated_count = 0
        current_time = timezone.now()
        
        for article in recent_articles:
            try:
                # Recalculate priority label and score
                priority_label, keyword_matches = calculate_priority_label(
                    article.title,
                    article.description,
                    article.content
                )
                
                # Also calculate legacy numeric score for backward compatibility
                priority_score, _ = calculate_priority_score(
                    article.title,
                    article.description,
                    article.content
                )
                
                # Add recency bonus to numeric score
                recency_bonus = calculate_recency_bonus(article.published_date, current_time)
                final_priority_score = priority_score + recency_bonus
                
                # Update if priority changed or score changed significantly
                should_update = (
                    article.priority_label != priority_label or
                    abs(article.priority_score - final_priority_score) > 0.5
                )
                
                if should_update:
                    article.priority_label = priority_label
                    article.priority_score = final_priority_score
                    article.keyword_matches = keyword_matches
                    article.save(update_fields=['priority_label', 'priority_score', 'keyword_matches'])
                    updated_count += 1
                    
            except Exception as e:
                logger.error(f"Error updating priority for article {article.id}: {str(e)}")
                continue
        
        logger.info(f"Updated priority labels/scores for {updated_count} articles")
        
        return {
            'status': 'success',
            'articles_updated': updated_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Priority update task failed: {str(exc)}")
        return {
            'status': 'error',
            'error': str(exc),
            'timestamp': timezone.now().isoformat()
        }


@shared_task
def detect_and_update_trending():
    """Detect trending topics and update article trending flags"""
    try:
        logger.info("Starting trending detection task")
        
        # Get articles from last 6 hours for trending detection
        recent_articles = Article.objects.filter(
            published_date__gte=timezone.now() - timedelta(hours=6)
        )
        
        # Detect trending topics
        trending_topics = detect_trending_topics(recent_articles, time_window_hours=6)
        
        # Reset all trending flags
        Article.objects.filter(is_trending=True).update(is_trending=False)
        
        # Mark articles with trending keywords as trending
        trending_count = 0
        for topic in trending_topics:
            keyword = topic['keyword']
            articles_with_keyword = recent_articles.filter(
                keyword_matches__has_key=keyword
            )
            
            updated = articles_with_keyword.update(is_trending=True)
            trending_count += updated
        
        logger.info(f"Marked {trending_count} articles as trending based on {len(trending_topics)} topics")
        
        return {
            'status': 'success',
            'trending_articles': trending_count,
            'trending_topics': len(trending_topics),
            'topics': [topic['keyword'] for topic in trending_topics[:10]],
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Trending detection task failed: {str(exc)}")
        return {
            'status': 'error',
            'error': str(exc),
            'timestamp': timezone.now().isoformat()
        }


@shared_task
def cleanup_old_data():
    """Clean up old articles and logs to manage database size"""
    try:
        logger.info("Starting data cleanup task")
        
        # Delete articles older than 30 days that aren't featured or bookmarked
        cutoff_date = timezone.now() - timedelta(days=30)
        
        old_articles = Article.objects.filter(
            published_date__lt=cutoff_date,
            is_featured=False,
            is_bookmarked=False
        )
        
        articles_count = old_articles.count()
        old_articles.delete()
        
        # Delete scraping logs older than 7 days
        log_cutoff = timezone.now() - timedelta(days=7)
        old_logs = ScrapingLog.objects.filter(scrape_date__lt=log_cutoff)
        logs_count = old_logs.count()
        old_logs.delete()
        
        logger.info(f"Cleaned up {articles_count} old articles and {logs_count} old logs")
        
        return {
            'status': 'success',
            'articles_deleted': articles_count,
            'logs_deleted': logs_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Cleanup task failed: {str(exc)}")
        return {
            'status': 'error',
            'error': str(exc),
            'timestamp': timezone.now().isoformat()
        }


@shared_task
def health_check_sources():
    """Check health status of all sources"""
    try:
        logger.info("Starting source health check")
        
        sources = Source.objects.filter(is_active=True)
        unhealthy_sources = []
        
        for source in sources:
            # Check if source hasn't been scraped recently
            if source.last_scraped:
                time_since_scrape = timezone.now() - source.last_scraped
                expected_interval = timedelta(minutes=source.scrape_frequency * 3)  # 3x buffer
                
                if time_since_scrape > expected_interval:
                    unhealthy_sources.append({
                        'id': source.id,
                        'name': source.name,
                        'issue': f'No scraping for {time_since_scrape}',
                        'last_scraped': source.last_scraped.isoformat()
                    })
            
            # Check recent error rate
            recent_logs = source.logs.filter(
                scrape_date__gte=timezone.now() - timedelta(hours=24)
            )
            
            if recent_logs.exists():
                error_rate = recent_logs.filter(success=False).count() / recent_logs.count()
                
                if error_rate > 0.5:  # More than 50% failures
                    unhealthy_sources.append({
                        'id': source.id,
                        'name': source.name,
                        'issue': f'High error rate: {error_rate:.1%}',
                        'error_rate': error_rate
                    })
        
        logger.info(f"Health check completed. Found {len(unhealthy_sources)} unhealthy sources")
        
        return {
            'status': 'success',
            'total_sources': sources.count(),
            'unhealthy_sources': len(unhealthy_sources),
            'issues': unhealthy_sources,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Health check task failed: {str(exc)}")
        return {
            'status': 'error',
            'error': str(exc),
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True)
def generate_article_summary_task(self, article_id):
    """Generate AI summary for a specific article"""
    try:
        logger.info(f"Starting summary generation for article: {article_id}")
        
        # Get the article
        article = Article.objects.get(id=article_id)
        
        # Generate summary
        summary = generate_article_summary(
            title=article.title,
            content=article.content,
            description=article.description
        )
        
        # Update article with summary
        article.summary = summary
        article.save(update_fields=['summary'])
        
        logger.info(f"Summary generated for article: {article_id}")
        
        return {
            'status': 'success',
            'article_id': article_id,
            'title': article.title[:100],
            'summary_length': len(summary),
            'timestamp': timezone.now().isoformat()
        }
        
    except Article.DoesNotExist:
        logger.error(f"Article not found: {article_id}")
        return {
            'status': 'error',
            'article_id': article_id,
            'error': 'Article not found',
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Summary generation failed for article {article_id}: {str(exc)}")
        return {
            'status': 'error',
            'article_id': article_id,
            'error': str(exc),
            'timestamp': timezone.now().isoformat()
        }
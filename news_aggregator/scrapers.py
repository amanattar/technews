import feedparser
import requests
from datetime import datetime, timezone
from django.conf import settings
from django.utils import timezone as django_timezone
from django.utils.dateparse import parse_datetime
from bs4 import BeautifulSoup
import re
import logging
from typing import Dict, List, Tuple, Optional
import time
import json
from urllib.parse import urlparse, parse_qs

from .models import Source, Article, ScrapingLog, Tag
from .utils import calculate_priority_score, calculate_priority_label, extract_keywords

logger = logging.getLogger(__name__)


class RSSFeedScraper:
    """Main RSS feed scraper for news articles"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def scrape_source(self, source: Source) -> Tuple[int, int, int]:
        """
        Scrape a single RSS source
        Returns: (articles_found, articles_new, articles_updated)
        """
        start_time = time.time()
        articles_found = 0
        articles_new = 0
        articles_updated = 0
        error_message = ""
        
        try:
            logger.info(f"Starting scrape for source: {source.name}")
            
            # Try to parse RSS feed with retry mechanism for 403 errors
            feed = None
            retries = 3
            for attempt in range(retries):
                try:
                    feed = feedparser.parse(source.url, request_headers=self.session.headers)
                    if not (hasattr(feed, 'bozo') and feed.bozo and 
                           '403' in str(getattr(feed, 'bozo_exception', ''))):
                        break  # Success or non-403 error
                    elif attempt < retries - 1:
                        logger.warning(f"Attempt {attempt + 1} failed with 403 for {source.name}, retrying...")
                        time.sleep(2 ** attempt)  # Exponential backoff
                except Exception as e:
                    if '403' not in str(e) or attempt >= retries - 1:
                        raise  # Re-raise if not 403 or last attempt
                    logger.warning(f"Attempt {attempt + 1} failed with 403 for {source.name}, retrying...")
                    time.sleep(2 ** attempt)  # Exponential backoff
            
            if hasattr(feed, 'bozo') and feed.bozo:
                logger.warning(f"RSS feed parsing warning for {source.name}: {feed.bozo_exception}")
            
            if not feed or not hasattr(feed, 'entries'):
                raise Exception(f"Failed to parse RSS feed for {source.name}")
            
            articles_found = len(feed.entries)
            
            for entry in feed.entries:
                try:
                    article_data = self._extract_article_data(entry, source)
                    if article_data:
                        created = self._save_article(article_data, source)
                        if created:
                            articles_new += 1
                        else:
                            articles_updated += 1
                            
                except Exception as e:
                    logger.error(f"Error processing entry from {source.name}: {str(e)}")
                    continue
            
            # Update source last_scraped time
            source.last_scraped = django_timezone.now()
            source.save(update_fields=['last_scraped'])
            
            success = True
            
        except Exception as e:
            error_message = str(e)
            success = False
            logger.error(f"Error scraping {source.name}: {error_message}")
        
        # Log the scraping activity
        duration = time.time() - start_time
        ScrapingLog.objects.create(
            source=source,
            articles_found=articles_found,
            articles_new=articles_new,
            articles_updated=articles_updated,
            success=success,
            error_message=error_message,
            duration_seconds=duration
        )
        
        logger.info(f"Completed scrape for {source.name}: {articles_new} new, {articles_updated} updated")
        return articles_found, articles_new, articles_updated
    
    def _extract_article_data(self, entry, source: Source) -> Optional[Dict]:
        """Extract article data from RSS entry"""
        try:
            # Required fields
            title = entry.get('title', '').strip()
            link = entry.get('link', '').strip()
            
            if not title or not link:
                return None
            
            # Optional fields with fallbacks
            description = self._get_description(entry)
            content = self._get_content(entry)
            author = self._get_author(entry)
            published_date = self._get_published_date(entry)
            
            return {
                'title': title,
                'url': link,
                'description': description,
                'content': content,
                'author': author,
                'published_date': published_date,
            }
            
        except Exception as e:
            logger.error(f"Error extracting article data: {str(e)}")
            return None
    
    def _get_description(self, entry) -> str:
        """Extract description from various RSS fields"""
        description = ""
        
        # Try different description fields
        for field in ['summary', 'description', 'subtitle']:
            if hasattr(entry, field) and entry[field]:
                description = entry[field]
                break
        
        # Clean HTML if present
        if description:
            description = self._clean_html(description)
        
        return description[:1000]  # Limit length
    
    def _get_content(self, entry) -> str:
        """Extract full content from RSS entry"""
        content = ""
        
        # Try content fields
        if hasattr(entry, 'content') and entry.content:
            if isinstance(entry.content, list) and entry.content:
                content = entry.content[0].get('value', '')
            else:
                content = str(entry.content)
        elif hasattr(entry, 'summary_detail') and entry.summary_detail:
            content = entry.summary_detail.get('value', '')
        
        # Clean HTML
        if content:
            content = self._clean_html(content)
        
        return content[:5000]  # Limit length
    
    def _get_author(self, entry) -> str:
        """Extract author information"""
        author = ""
        
        if hasattr(entry, 'author') and entry.author:
            author = entry.author
        elif hasattr(entry, 'authors') and entry.authors:
            if isinstance(entry.authors, list) and entry.authors:
                author = entry.authors[0].get('name', '')
            else:
                author = str(entry.authors)
        elif hasattr(entry, 'dc_creator'):
            author = entry.dc_creator
        
        return author[:200]  # Limit length
    
    def _get_published_date(self, entry) -> datetime:
        """Extract and parse published date"""
        published_date = django_timezone.now()  # Default to now
        
        # Try different date fields
        date_fields = ['published', 'updated', 'created', 'pubDate']
        
        for field in date_fields:
            if hasattr(entry, field) and getattr(entry, field):
                date_str = getattr(entry, field)
                try:
                    # feedparser provides parsed time tuples
                    if hasattr(entry, f'{field}_parsed') and getattr(entry, f'{field}_parsed'):
                        time_tuple = getattr(entry, f'{field}_parsed')
                        if time_tuple:
                            published_date = datetime(*time_tuple[:6], tzinfo=timezone.utc)
                            break
                    # Try parsing string date
                    elif isinstance(date_str, str):
                        parsed_date = parse_datetime(date_str)
                        if parsed_date:
                            published_date = parsed_date
                            break
                except Exception as e:
                    logger.warning(f"Error parsing date {date_str}: {e}")
                    continue
        
        return published_date
    
    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and clean text"""
        if not text:
            return ""
        
        # Remove HTML tags
        soup = BeautifulSoup(text, 'html.parser')
        text = soup.get_text()
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def _save_article(self, article_data: Dict, source: Source) -> bool:
        """Save article to database, return True if created, False if updated"""
        try:
            article, created = Article.objects.get_or_create(
                url=article_data['url'],
                defaults={
                    'title': article_data['title'],
                    'description': article_data['description'],
                    'content': article_data['content'],
                    'author': article_data['author'],
                    'source': source,
                    'published_date': article_data['published_date'],
                }
            )
            
            if not created:
                # Update existing article if content changed
                updated = False
                for field in ['title', 'description', 'content', 'author']:
                    if getattr(article, field) != article_data[field]:
                        setattr(article, field, article_data[field])
                        updated = True
                
                if updated:
                    article.save()
            
            # Calculate priority label and score
            if created or not article.is_processed:
                # Use new priority label system
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
                
                article.priority_label = priority_label
                article.priority_score = priority_score
                article.keyword_matches = keyword_matches
                article.is_processed = True
                article.save(update_fields=['priority_label', 'priority_score', 'keyword_matches', 'is_processed'])
                
                # Auto-assign tags based on keywords
                self._auto_assign_tags(article)
            
            return created
            
        except Exception as e:
            logger.error(f"Error saving article {article_data['url']}: {str(e)}")
            return False
    
    def _auto_assign_tags(self, article: Article):
        """Automatically assign tags based on content"""
        try:
            # Tag mapping based on keywords
            tag_keywords = {
                'Apple': ['iphone', 'ipad', 'mac', 'apple', 'ios', 'macos', 'airpods'],
                'Samsung': ['samsung', 'galaxy', 'note'],
                'Google': ['google', 'pixel', 'android', 'chrome'],
                'OnePlus': ['oneplus', 'oxygen'],
                'Xiaomi': ['xiaomi', 'mi', 'redmi'],
                'Rumor': ['rumor', 'leaked', 'leak', 'speculation'],
                'Breaking': ['breaking', 'urgent', 'exclusive'],
                'India': ['india', 'indian'],
                'Launch': ['launch', 'announced', 'release', 'unveil'],
            }
            
            text_to_check = f"{article.title} {article.description}".lower()
            
            for tag_name, keywords in tag_keywords.items():
                if any(keyword in text_to_check for keyword in keywords):
                    tag, created = Tag.objects.get_or_create(
                        name=tag_name,
                        defaults={'description': f'Auto-generated tag for {tag_name}'}
                    )
                    article.tags.add(tag)
            
        except Exception as e:
            logger.error(f"Error auto-assigning tags for article {article.id}: {str(e)}")


def scrape_all_sources():
    """Scrape all active RSS sources"""
    rss_scraper = RSSFeedScraper()
    
    # Scrape RSS sources
    rss_sources = Source.objects.filter(is_active=True, source_type='rss')
    for source in rss_sources:
        try:
            rss_scraper.scrape_source(source)
        except Exception as e:
            logger.error(f"Failed to scrape RSS source {source.name}: {str(e)}")
    
    logger.info("Completed scraping all sources")


def scrape_single_source(source_id: int):
    """Scrape a single source by ID"""
    try:
        source = Source.objects.get(id=source_id, is_active=True)
        
        if source.source_type == 'rss':
            scraper = RSSFeedScraper()
            return scraper.scrape_source(source)
        
    except Source.DoesNotExist:
        logger.error(f"Source with ID {source_id} not found or inactive")
        return 0, 0, 0
    except Exception as e:
        logger.error(f"Error scraping source {source_id}: {str(e)}")
        return 0, 0, 0

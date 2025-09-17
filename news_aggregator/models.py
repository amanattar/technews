from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
import json


class Source(models.Model):
    """RSS feed sources for news aggregation"""
    SOURCE_TYPES = [
        ('rss', 'RSS Feed'),
        ('manual', 'Manual Entry'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    url = models.URLField()
    source_type = models.CharField(max_length=10, choices=SOURCE_TYPES, default='rss')
    is_active = models.BooleanField(default=True)
    last_scraped = models.DateTimeField(null=True, blank=True)
    scrape_frequency = models.IntegerField(default=10)  # minutes
    priority_weight = models.FloatField(default=1.0)  # source credibility multiplier
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']


class Tag(models.Model):
    """Tags for categorizing articles"""
    name = models.CharField(max_length=50, unique=True)
    color = models.CharField(max_length=7, default='#007bff')  # hex color
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']


class Article(models.Model):
    """Main article model for storing scraped news"""
    title = models.TextField()
    url = models.URLField(unique=True)
    description = models.TextField(blank=True)
    content = models.TextField(blank=True)
    summary = models.TextField(blank=True)  # AI-generated summary
    author = models.CharField(max_length=200, blank=True)
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name='articles')
    tags = models.ManyToManyField(Tag, blank=True, related_name='articles')
    
    # Dates
    published_date = models.DateTimeField()
    scraped_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    
    # Priority and scoring
    priority_score = models.FloatField(default=0.0)  # Kept for backward compatibility
    priority_label = models.CharField(
        max_length=20, 
        choices=[
            ('high', 'High Priority'),
            ('medium', 'Medium Priority'),
            ('low', 'Low Priority'),
            ('minimal', 'Minimal Priority'),
        ],
        default='minimal'
    )
    keyword_matches = models.JSONField(default=dict)  # stores matched keywords and priorities
    is_breaking = models.BooleanField(default=False)
    is_trending = models.BooleanField(default=False)
    
    # Status
    is_processed = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)
    
    # User interactions
    views_count = models.PositiveIntegerField(default=0)
    is_bookmarked = models.BooleanField(default=False)
    
    def __str__(self):
        return self.title[:100]
    
    def get_keyword_score(self):
        """Calculate total keyword score from matched keywords (legacy method)"""
        if not self.keyword_matches:
            return 0.0
        # Convert priority labels to scores for backward compatibility
        priority_to_score = {'high': 5.0, 'medium': 3.0, 'low': 1.0, 'minimal': 0.5}
        total = 0.0
        for keyword, priority in self.keyword_matches.items():
            if isinstance(priority, str):  # New priority label format
                total += priority_to_score.get(priority, 0.5)
            else:  # Old numeric format
                total += float(priority)
        return total
    
    def get_priority_display_info(self):
        """Get priority display information including color and icon"""
        priority_info = {
            'high': {'color': 'danger', 'icon': 'fas fa-exclamation-triangle', 'label': 'High Priority'},
            'medium': {'color': 'warning', 'icon': 'fas fa-star', 'label': 'Medium Priority'},
            'low': {'color': 'info', 'icon': 'fas fa-info-circle', 'label': 'Low Priority'},
            'minimal': {'color': 'secondary', 'icon': 'fas fa-circle', 'label': 'Minimal Priority'},
        }
        return priority_info.get(self.priority_label, priority_info['minimal'])
    
    def get_final_score(self):
        """Calculate final priority score including source weight (legacy method)"""
        base_score = self.priority_score
        source_weight = self.source.priority_weight if self.source else 1.0
        return base_score * source_weight
    
    class Meta:
        ordering = ['-priority_score', '-published_date']  # Keep existing ordering for compatibility
        indexes = [
            models.Index(fields=['-priority_score', '-published_date']),
            models.Index(fields=['-scraped_date']),
            models.Index(fields=['source', '-published_date']),
            models.Index(fields=['priority_label', '-published_date']),  # New index for label-based queries
        ]


class ScrapingLog(models.Model):
    """Log scraping activities and errors"""
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name='logs')
    scrape_date = models.DateTimeField(auto_now_add=True)
    articles_found = models.PositiveIntegerField(default=0)
    articles_new = models.PositiveIntegerField(default=0)
    articles_updated = models.PositiveIntegerField(default=0)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    duration_seconds = models.FloatField(default=0.0)
    
    def __str__(self):
        status = "Success" if self.success else "Failed"
        return f"{self.source.name} - {self.scrape_date.strftime('%Y-%m-%d %H:%M')} - {status}"
    
    class Meta:
        ordering = ['-scrape_date']


class UserPreference(models.Model):
    """User preferences for news filtering and prioritization"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='news_preferences')
    preferred_sources = models.ManyToManyField(Source, blank=True)
    preferred_tags = models.ManyToManyField(Tag, blank=True)
    custom_keywords = models.JSONField(default=dict)  # custom keyword scores
    email_notifications = models.BooleanField(default=False)
    daily_digest = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} preferences"


class ExportHistory(models.Model):
    """Track CSV exports for analytics"""
    EXPORT_FORMATS = [
        ('csv', 'CSV'),
        ('json', 'JSON'),
        ('xml', 'XML'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    export_date = models.DateTimeField(auto_now_add=True)
    format_type = models.CharField(max_length=10, choices=EXPORT_FORMATS, default='csv')
    filters_applied = models.JSONField(default=dict)
    articles_count = models.PositiveIntegerField(default=0)
    file_size_bytes = models.PositiveIntegerField(default=0)
    
    def __str__(self):
        return f"Export {self.export_date.strftime('%Y-%m-%d %H:%M')} - {self.articles_count} articles"
    
    class Meta:
        ordering = ['-export_date']
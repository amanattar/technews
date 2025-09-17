from rest_framework import serializers
from .models import Article, Source, Tag, ScrapingLog, ExportHistory


class TagSerializer(serializers.ModelSerializer):
    articles_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Tag
        fields = ['id', 'name', 'color', 'description', 'articles_count', 'created_at']
    
    def get_articles_count(self, obj):
        return obj.articles.count()


class SourceSerializer(serializers.ModelSerializer):
    articles_count = serializers.SerializerMethodField()
    health_status = serializers.SerializerMethodField()
    
    class Meta:
        model = Source
        fields = ['id', 'name', 'url', 'source_type', 'is_active', 'last_scraped', 
                 'scrape_frequency', 'priority_weight', 'articles_count', 'health_status']
    
    def get_articles_count(self, obj):
        return obj.articles.count()
    
    def get_health_status(self, obj):
        from .utils import get_source_health_status
        return get_source_health_status(obj)


class ArticleListSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source='source.name', read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    final_score = serializers.SerializerMethodField()
    priority_display = serializers.SerializerMethodField()
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = Article
        fields = ['id', 'title', 'url', 'description', 'summary', 'author', 'source_name', 
                 'tags', 'published_date', 'scraped_date', 'priority_score', 'priority_label',
                 'priority_display', 'final_score', 'is_breaking', 'is_trending', 'is_featured', 
                 'views_count', 'time_ago']
    
    def get_final_score(self, obj):
        return obj.get_final_score()
    
    def get_priority_display(self, obj):
        return obj.get_priority_display_info()
    
    def get_time_ago(self, obj):
        from django.utils import timezone
        from datetime import datetime, timedelta
        
        now = timezone.now()
        diff = now - obj.published_date
        
        if diff.days > 0:
            return f"{diff.days} days ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hours ago"
        else:
            minutes = diff.seconds // 60
            return f"{minutes} minutes ago"


class ArticleDetailSerializer(serializers.ModelSerializer):
    source = SourceSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    final_score = serializers.SerializerMethodField()
    priority_display = serializers.SerializerMethodField()
    keyword_score = serializers.SerializerMethodField()
    
    class Meta:
        model = Article
        fields = ['id', 'title', 'url', 'description', 'content', 'summary', 'author', 
                 'source', 'tags', 'published_date', 'scraped_date', 'updated_date',
                 'priority_score', 'priority_label', 'priority_display', 'final_score', 
                 'keyword_score', 'keyword_matches', 'is_breaking', 'is_trending', 
                 'is_featured', 'is_processed', 'is_archived', 'is_bookmarked', 'views_count']
    
    def get_final_score(self, obj):
        return obj.get_final_score()
    
    def get_priority_display(self, obj):
        return obj.get_priority_display_info()
    
    def get_keyword_score(self, obj):
        return obj.get_keyword_score()


class ScrapingLogSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source='source.name', read_only=True)
    
    class Meta:
        model = ScrapingLog
        fields = ['id', 'source_name', 'scrape_date', 'articles_found', 'articles_new',
                 'articles_updated', 'success', 'error_message', 'duration_seconds']


class ExportHistorySerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    file_size_kb = serializers.SerializerMethodField()
    
    class Meta:
        model = ExportHistory
        fields = ['id', 'username', 'export_date', 'format_type', 'filters_applied',
                 'articles_count', 'file_size_bytes', 'file_size_kb']
    
    def get_file_size_kb(self, obj):
        return round(obj.file_size_bytes / 1024, 2)


class StatsSerializer(serializers.Serializer):
    total_articles = serializers.IntegerField()
    articles_today = serializers.IntegerField()
    articles_this_week = serializers.IntegerField()
    breaking_news_count = serializers.IntegerField()
    trending_articles_count = serializers.IntegerField()
    active_sources_count = serializers.IntegerField()
    top_sources = serializers.ListField()
    trending_topics = serializers.ListField()
    recent_activity = serializers.ListField()


class FilterOptionsSerializer(serializers.Serializer):
    sources = SourceSerializer(many=True)
    tags = TagSerializer(many=True)
    time_ranges = serializers.ListField()
    sort_options = serializers.ListField()


class BulkActionSerializer(serializers.Serializer):
    article_ids = serializers.ListField(child=serializers.IntegerField())
    action = serializers.ChoiceField(choices=['bookmark', 'unbookmark', 'feature', 'unfeature', 'archive', 'delete'])
    
    def validate_article_ids(self, value):
        if not value:
            raise serializers.ValidationError("At least one article ID is required")
        if len(value) > 100:
            raise serializers.ValidationError("Maximum 100 articles can be processed at once")
        return value


class ExportRequestSerializer(serializers.Serializer):
    format = serializers.ChoiceField(choices=['csv', 'json', 'xml'], default='csv')
    time_range = serializers.ChoiceField(
        choices=['1hour', '24hours', '1week', '1month', 'all'], 
        default='24hours'
    )
    sources = serializers.ListField(child=serializers.IntegerField(), required=False)
    tags = serializers.ListField(child=serializers.IntegerField(), required=False)
    min_priority_score = serializers.FloatField(required=False, min_value=0)
    include_content = serializers.BooleanField(default=False)
    only_breaking = serializers.BooleanField(default=False)
    only_trending = serializers.BooleanField(default=False)
    only_featured = serializers.BooleanField(default=False)
    article_ids = serializers.ListField(child=serializers.IntegerField(), required=False)


class SourceValidationSerializer(serializers.Serializer):
    url = serializers.URLField()
    
    def validate_url(self, value):
        from .utils import validate_rss_url
        
        is_valid, message = validate_rss_url(value)
        if not is_valid:
            raise serializers.ValidationError(message)
        return value


class ManualArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = ['title', 'url', 'description', 'content', 'author', 'source', 'published_date']
    
    def validate_url(self, value):
        # Check if article already exists
        if Article.objects.filter(url=value).exists():
            raise serializers.ValidationError("Article with this URL already exists")
        return value
    
    def create(self, validated_data):
        from .utils import calculate_priority_label, calculate_priority_score
        
        # Create article
        article = Article.objects.create(**validated_data)
        
        # Calculate priority label and score
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
        
        return article
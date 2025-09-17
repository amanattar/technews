from django.contrib import admin
from django.utils.html import format_html
from .models import Source, Tag, Article, ScrapingLog, UserPreference, ExportHistory

@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ['name', 'source_type', 'is_active', 'last_scraped', 'scrape_frequency', 'priority_weight']
    list_filter = ['source_type', 'is_active', 'created_at']
    search_fields = ['name', 'url']
    list_editable = ['is_active', 'scrape_frequency', 'priority_weight']
    readonly_fields = ['last_scraped', 'created_at', 'updated_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('articles')


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'color_preview', 'articles_count', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at']
    
    def color_preview(self, obj):
        return format_html(
            '<span style="background-color: {}; padding: 2px 8px; border-radius: 3px; color: white;">{}</span>',
            obj.color, obj.color
        )
    color_preview.short_description = 'Color'
    
    def articles_count(self, obj):
        return obj.articles.count()
    articles_count.short_description = 'Articles'


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ['title_preview', 'source', 'priority_score', 'published_date', 'is_breaking', 'is_featured']
    list_filter = ['source', 'is_breaking', 'is_trending', 'is_featured', 'is_processed', 'published_date', 'tags']
    search_fields = ['title', 'description', 'author']
    list_editable = ['is_breaking', 'is_featured']
    readonly_fields = ['scraped_date', 'updated_date', 'views_count', 'keyword_matches', 'get_final_score']
    filter_horizontal = ['tags']
    date_hierarchy = 'published_date'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'url', 'description', 'content', 'author', 'source')
        }),
        ('Dates', {
            'fields': ('published_date', 'scraped_date', 'updated_date'),
            'classes': ('collapse',)
        }),
        ('Priority & Scoring', {
            'fields': ('priority_score', 'keyword_matches', 'get_final_score'),
        }),
        ('Status & Flags', {
            'fields': ('is_breaking', 'is_trending', 'is_featured', 'is_processed', 'is_archived', 'is_bookmarked'),
        }),
        ('Categorization', {
            'fields': ('tags',),
        }),
        ('Analytics', {
            'fields': ('views_count',),
            'classes': ('collapse',)
        })
    )
    
    def title_preview(self, obj):
        return obj.title[:80] + '...' if len(obj.title) > 80 else obj.title
    title_preview.short_description = 'Title'
    
    def get_final_score(self, obj):
        return f"{obj.get_final_score():.2f}"
    get_final_score.short_description = 'Final Score'

@admin.register(ScrapingLog)
class ScrapingLogAdmin(admin.ModelAdmin):
    list_display = ['source', 'scrape_date', 'success', 'articles_new', 'articles_found', 'duration_seconds']
    list_filter = ['success', 'source', 'scrape_date']
    readonly_fields = ['scrape_date', 'duration_seconds']
    date_hierarchy = 'scrape_date'
    
    def has_add_permission(self, request):
        return False  # Logs are created automatically


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user', 'email_notifications', 'daily_digest', 'created_at']
    list_filter = ['email_notifications', 'daily_digest', 'created_at']
    filter_horizontal = ['preferred_sources', 'preferred_tags']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ExportHistory)
class ExportHistoryAdmin(admin.ModelAdmin):
    list_display = ['export_date', 'user', 'format_type', 'articles_count', 'file_size_kb']
    list_filter = ['format_type', 'export_date', 'user']
    readonly_fields = ['export_date', 'file_size_bytes']
    date_hierarchy = 'export_date'
    
    def file_size_kb(self, obj):
        return f"{obj.file_size_bytes / 1024:.1f} KB"
    file_size_kb.short_description = 'File Size'
    
    def has_add_permission(self, request):
        return False  # Export history is created automatically

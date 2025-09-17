from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db.models import Q, Count, Avg
from django.http import HttpResponse, Http404
from django.shortcuts import render
from django.views.generic import TemplateView
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.core.management import call_command
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from datetime import timedelta, datetime
import csv
import json
import xml.etree.ElementTree as ET
import io
import logging
import tempfile
import os

from .models import Article, Source, Tag, ScrapingLog, ExportHistory
from .serializers import (
    ArticleListSerializer, ArticleDetailSerializer, SourceSerializer, TagSerializer,
    ScrapingLogSerializer, ExportHistorySerializer,
    StatsSerializer, FilterOptionsSerializer, BulkActionSerializer,
    ExportRequestSerializer, SourceValidationSerializer, ManualArticleSerializer
)
from .tasks import scrape_single_rss_source, scrape_rss_feeds, generate_article_summary_task
from .utils import format_article_for_export, sanitize_filename

logger = logging.getLogger(__name__)


# Template Views
class DashboardView(TemplateView):
    template_name = 'news_aggregator/dashboard.html'


class ArticleListView(TemplateView):
    template_name = 'news_aggregator/article_list.html'


class ArticleDetailView(TemplateView):
    template_name = 'news_aggregator/article_detail.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        article_id = kwargs.get('pk')
        try:
            from .models import Article
            article = Article.objects.select_related('source').prefetch_related('tags').get(id=article_id)
            # Increment view count
            article.views_count += 1
            article.save(update_fields=['views_count'])
            context['article'] = article
        except Article.DoesNotExist:
            context['article'] = None
        return context


class SourceListView(TemplateView):
    template_name = 'news_aggregator/source_list.html'


class ScriptGeneratorView(TemplateView):
    template_name = 'news_aggregator/script_generator.html'


# API Views
class ArticleFilter:
    """Custom filter class for articles"""
    
    @staticmethod
    def filter_by_time_range(queryset, time_range):
        now = timezone.now()
        
        time_ranges = {
            '1hour': now - timedelta(hours=1),
            '24hours': now - timedelta(hours=24),
            '1week': now - timedelta(weeks=1),
            '1month': now - timedelta(days=30),
        }
        
        if time_range in time_ranges:
            return queryset.filter(published_date__gte=time_ranges[time_range])
        return queryset
    
    @staticmethod
    def filter_by_sources(queryset, source_ids):
        if source_ids:
            return queryset.filter(source__id__in=source_ids)
        return queryset
    
    @staticmethod
    def filter_by_tags(queryset, tag_ids):
        if tag_ids:
            return queryset.filter(tags__id__in=tag_ids).distinct()
        return queryset


class ArticleViewSet(viewsets.ModelViewSet):
    """ViewSet for managing articles"""
    
    queryset = Article.objects.select_related('source').prefetch_related('tags')
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description', 'content', 'author']
    ordering_fields = ['published_date', 'priority_score', 'scraped_date', 'views_count']
    ordering = ['-priority_score', '-published_date']
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ArticleDetailSerializer
        elif self.action == 'create':
            return ManualArticleSerializer
        return ArticleListSerializer
    
    def get_queryset(self):
        queryset = self.queryset
        
        # Apply custom filters
        time_range = self.request.query_params.get('time_range')
        if time_range:
            queryset = ArticleFilter.filter_by_time_range(queryset, time_range)
        
        source_ids = self.request.query_params.getlist('sources')
        if source_ids:
            try:
                source_ids = [int(sid) for sid in source_ids]
                queryset = ArticleFilter.filter_by_sources(queryset, source_ids)
            except ValueError:
                pass
        
        tag_ids = self.request.query_params.getlist('tags')
        if tag_ids:
            try:
                tag_ids = [int(tid) for tid in tag_ids]
                queryset = ArticleFilter.filter_by_tags(queryset, tag_ids)
            except ValueError:
                pass
        
        # Filter by flags
        if self.request.query_params.get('breaking') == 'true':
            queryset = queryset.filter(is_breaking=True)
        
        if self.request.query_params.get('trending') == 'true':
            queryset = queryset.filter(is_trending=True)
        
        if self.request.query_params.get('featured') == 'true':
            queryset = queryset.filter(is_featured=True)
        
        # Filter by minimum priority score
        min_score = self.request.query_params.get('min_score')
        if min_score:
            try:
                queryset = queryset.filter(priority_score__gte=float(min_score))
            except ValueError:
                pass
        
        return queryset.filter(is_archived=False)  # Exclude archived by default
    
    def retrieve(self, request, *args, **kwargs):
        """Get single article and increment view count"""
        article = self.get_object()
        article.views_count += 1
        article.save(update_fields=['views_count'])
        
        serializer = self.get_serializer(article)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def generate_script(self, request):
        """Generate a tech news script from uploaded CSV file"""
        try:
            # Check if file was uploaded
            if 'csv_file' not in request.FILES:
                return Response({'success': False, 'error': 'No CSV file uploaded'}, status=400)
            
            csv_file = request.FILES['csv_file']
            
            # Validate file type
            if not csv_file.name.endswith('.csv'):
                return Response({'success': False, 'error': 'File must be a CSV'}, status=400)
            
            # Create a temporary file
            with tempfile.NamedTemporaryFile(mode='w+b', suffix='.csv', delete=False) as temp_csv:
                for chunk in csv_file.chunks():
                    temp_csv.write(chunk)
                temp_csv_path = temp_csv.name
            
            # Generate output file name
            output_file_name = request.data.get('output_file', 'tech_news_script.txt')
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_output:
                temp_output_path = temp_output.name
            
            try:
                # Call the management command
                call_command('generate_script', temp_csv_path, '--output', temp_output_path)
                
                # Read the generated script
                with open(temp_output_path, 'r', encoding='utf-8') as f:
                    script_content = f.read()
                
                # Return the script content
                return Response({
                    'success': True,
                    'script': script_content
                })
            except Exception as e:
                return Response({'success': False, 'error': str(e)}, status=500)
            finally:
                # Clean up temporary files
                try:
                    os.unlink(temp_csv_path)
                    os.unlink(temp_output_path)
                except:
                    pass
        except Exception as e:
            return Response({'success': False, 'error': str(e)}, status=500)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get dashboard statistics"""
        now = timezone.now()
        
        # Basic counts
        total_articles = Article.objects.count()
        articles_today = Article.objects.filter(published_date__date=now.date()).count()
        articles_this_week = Article.objects.filter(
            published_date__gte=now - timedelta(days=7)
        ).count()
        
        breaking_news_count = Article.objects.filter(
            is_breaking=True,
            published_date__gte=now - timedelta(hours=24)
        ).count()
        
        trending_articles_count = Article.objects.filter(is_trending=True).count()
        active_sources_count = Source.objects.filter(is_active=True).count()
        
        # Top sources by article count
        top_sources = list(Source.objects.annotate(
            article_count=Count('articles')
        ).order_by('-article_count')[:5].values('name', 'article_count'))
        
        # Trending topics (most common keywords in recent articles)
        from .utils import detect_trending_topics
        recent_articles = Article.objects.filter(
            published_date__gte=now - timedelta(hours=24)
        )
        trending_topics_data = detect_trending_topics(recent_articles)
        trending_topics = [topic['keyword'] for topic in trending_topics_data[:10]]
        
        # Recent scraping activity
        recent_logs = ScrapingLog.objects.select_related('source').order_by('-scrape_date')[:10]
        recent_activity = [{
            'source': log.source.name,
            'time': log.scrape_date,
            'articles_new': log.articles_new,
            'success': log.success
        } for log in recent_logs]
        
        stats_data = {
            'total_articles': total_articles,
            'articles_today': articles_today,
            'articles_this_week': articles_this_week,
            'breaking_news_count': breaking_news_count,
            'trending_articles_count': trending_articles_count,
            'active_sources_count': active_sources_count,
            'top_sources': top_sources,
            'trending_topics': trending_topics,
            'recent_activity': recent_activity
        }
        
        serializer = StatsSerializer(stats_data)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def filter_options(self, request):
        """Get available filter options"""
        sources = Source.objects.filter(is_active=True).order_by('name')
        tags = Tag.objects.annotate(
            article_count=Count('articles')
        ).filter(article_count__gt=0).order_by('name')
        
        time_ranges = [
            {'value': '1hour', 'label': 'Last Hour'},
            {'value': '24hours', 'label': 'Last 24 Hours'},
            {'value': '1week', 'label': 'Last Week'},
            {'value': '1month', 'label': 'Last Month'},
            {'value': 'all', 'label': 'All Time'}
        ]
        
        sort_options = [
            {'value': '-priority_score,-published_date', 'label': 'Priority (High to Low)'},
            {'value': '-published_date', 'label': 'Newest First'},
            {'value': 'published_date', 'label': 'Oldest First'},
            {'value': '-views_count', 'label': 'Most Viewed'},
            {'value': '-scraped_date', 'label': 'Recently Added'}
        ]
        
        data = {
            'sources': SourceSerializer(sources, many=True).data,
            'tags': TagSerializer(tags, many=True).data,
            'time_ranges': time_ranges,
            'sort_options': sort_options
        }
        
        # Return the data directly instead of using FilterOptionsSerializer
        return Response(data)
    
    @action(detail=False, methods=['post'])
    def bulk_action(self, request):
        """Perform bulk actions on articles"""
        serializer = BulkActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        article_ids = serializer.validated_data['article_ids']
        action = serializer.validated_data['action']
        
        articles = Article.objects.filter(id__in=article_ids)
        
        if not articles.exists():
            return Response({'error': 'No articles found'}, status=status.HTTP_404_NOT_FOUND)
        
        updated_count = 0
        
        if action == 'bookmark':
            updated_count = articles.update(is_bookmarked=True)
        elif action == 'unbookmark':
            updated_count = articles.update(is_bookmarked=False)
        elif action == 'feature':
            updated_count = articles.update(is_featured=True)
        elif action == 'unfeature':
            updated_count = articles.update(is_featured=False)
        elif action == 'archive':
            updated_count = articles.update(is_archived=True)
        elif action == 'delete':
            updated_count = articles.count()
            articles.delete()
        
        return Response({
            'message': f'{action.title()} action completed',
            'articles_affected': updated_count
        })
    
    @action(detail=False, methods=['post'])
    def export(self, request):
        """Export articles to CSV/JSON/XML"""
        serializer = ExportRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Get filtered queryset based on export parameters
        queryset = self.get_queryset()
        
        # Apply export-specific filters
        data = serializer.validated_data
        
        # Check if specific article IDs are provided
        if data.get('article_ids'):
            queryset = queryset.filter(id__in=data['article_ids'])
        else:
            # Apply filters only if no specific article IDs are provided
            if data.get('time_range'):
                queryset = ArticleFilter.filter_by_time_range(queryset, data['time_range'])
            
            if data.get('sources'):
                queryset = ArticleFilter.filter_by_sources(queryset, data['sources'])
            
            if data.get('tags'):
                queryset = ArticleFilter.filter_by_tags(queryset, data['tags'])
            
            if data.get('min_priority_score'):
                queryset = queryset.filter(priority_score__gte=data['min_priority_score'])
            
            if data.get('only_breaking'):
                queryset = queryset.filter(is_breaking=True)
            
            if data.get('only_trending'):
                queryset = queryset.filter(is_trending=True)
            
            if data.get('only_featured'):
                queryset = queryset.filter(is_featured=True)
        
        # Limit to reasonable number for export
        queryset = queryset[:1000]
        
        # Format articles for export
        articles_data = [format_article_for_export(article) for article in queryset]
        
        # Create export file
        export_format = data.get('format', 'csv')
        
        if export_format == 'csv':
            response = self._create_csv_export(articles_data)
        elif export_format == 'json':
            response = self._create_json_export(articles_data)
        elif export_format == 'xml':
            response = self._create_xml_export(articles_data)
        else:
            return Response({'error': 'Invalid format'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Log export
        ExportHistory.objects.create(
            user=request.user if request.user.is_authenticated else None,
            format_type=export_format,
            filters_applied=data,
            articles_count=len(articles_data),
            file_size_bytes=len(response.content)
        )
        
        return response
    
    def _create_csv_export(self, articles_data):
        """Create CSV export response"""
        output = io.StringIO()
        
        if articles_data:
            writer = csv.DictWriter(output, fieldnames=articles_data[0].keys())
            writer.writeheader()
            writer.writerows(articles_data)
        
        response = HttpResponse(output.getvalue(), content_type='text/csv')
        filename = f"technews_export_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
    
    def _create_json_export(self, articles_data):
        """Create JSON export response"""
        response_data = {
            'export_date': timezone.now().isoformat(),
            'total_articles': len(articles_data),
            'articles': articles_data
        }
        
        response = HttpResponse(
            json.dumps(response_data, indent=2),
            content_type='application/json'
        )
        filename = f"technews_export_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
    
    def _create_xml_export(self, articles_data):
        """Create XML export response"""
        root = ET.Element('export')
        root.set('date', timezone.now().isoformat())
        root.set('total_articles', str(len(articles_data)))
        
        articles_elem = ET.SubElement(root, 'articles')
        
        for article_data in articles_data:
            article_elem = ET.SubElement(articles_elem, 'article')
            for key, value in article_data.items():
                elem = ET.SubElement(article_elem, key)
                elem.text = str(value) if value is not None else ''
        
        xml_string = ET.tostring(root, encoding='unicode')
        
        response = HttpResponse(xml_string, content_type='application/xml')
        filename = f"technews_export_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xml"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
    
    @action(detail=True, methods=['post'])
    def generate_summary(self, request, pk=None):
        """Generate AI summary for this article"""
        article = self.get_object()
        
        try:
            # Try async summary generation first
            task = generate_article_summary_task.delay(article.id)
            return Response({
                'message': 'Summary generation started',
                'task_id': task.id,
                'article_id': article.id,
                'mode': 'async'
            })
        except Exception as e:
            # Fallback to synchronous summary generation
            logger.warning(f"Celery not available, running synchronous summary generation: {e}")
            
            from .utils import generate_article_summary
            summary = generate_article_summary(
                title=article.title,
                content=article.content,
                description=article.description
            )
            
            # Update article with summary
            article.summary = summary
            article.save(update_fields=['summary'])
            
            return Response({
                'message': 'Summary generated successfully',
                'article_id': article.id,
                'summary': summary,
                'summary_length': len(summary),
                'mode': 'synchronous'
            })


class SourceViewSet(viewsets.ModelViewSet):
    """ViewSet for managing RSS sources"""
    
    queryset = Source.objects.all().order_by('name')
    serializer_class = SourceSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'url']
    ordering_fields = ['name', 'last_scraped', 'priority_weight']
    
    @action(detail=True, methods=['post'])
    def scrape_now(self, request, pk=None):
        """Trigger immediate scraping for this source"""
        source = self.get_object()
        
        try:
            # Try async scraping task first
            task = scrape_single_rss_source.delay(source.id)
            return Response({
                'message': f'Scraping started for {source.name}',
                'task_id': task.id,
                'source_id': source.id
            })
        except Exception as e:
            # Fallback to synchronous scraping if Celery/Redis not available
            logger.warning(f"Celery not available, running synchronous scraping: {e}")
            
            from .scrapers import scrape_single_source
            total_found, total_new, total_updated = scrape_single_source(source.id)
            
            return Response({
                'message': f'Scraping completed for {source.name}',
                'source_id': source.id,
                'articles_found': total_found,
                'articles_new': total_new,
                'articles_updated': total_updated,
                'mode': 'synchronous'
            })
    
    @action(detail=False, methods=['post'])
    def scrape_all(self, request):
        """Trigger scraping for all active sources"""
        try:
            # Try async scraping task first
            task = scrape_rss_feeds.delay()
            return Response({
                'message': 'Scraping started for all active sources',
                'task_id': task.id
            })
        except Exception as e:
            # Fallback to synchronous scraping if Celery/Redis not available
            logger.warning(f"Celery not available, running synchronous scraping: {e}")
            
            from .scrapers import scrape_all_sources
            scrape_all_sources()
            
            # Get stats after scraping
            total_sources = Source.objects.filter(is_active=True).count()
            
            return Response({
                'message': f'Scraping completed for {total_sources} active sources',
                'sources_processed': total_sources,
                'mode': 'synchronous'
            })
    
    @action(detail=False, methods=['post'])
    def validate_url(self, request):
        """Validate RSS feed URL"""
        serializer = SourceValidationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({'message': 'RSS feed URL is valid'})


class TagViewSet(viewsets.ModelViewSet):
    """ViewSet for managing tags"""
    
    queryset = Tag.objects.annotate(
        article_count=Count('articles')
    ).order_by('name')
    serializer_class = TagSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'description']


class ScrapingLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing scraping logs"""
    
    queryset = ScrapingLog.objects.select_related('source').order_by('-scrape_date')
    serializer_class = ScrapingLogSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['source', 'success']
    ordering_fields = ['scrape_date', 'duration_seconds']


class ExportHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing export history"""
    
    queryset = ExportHistory.objects.select_related('user').order_by('-export_date')
    serializer_class = ExportHistorySerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['format_type', 'user']
    ordering_fields = ['export_date', 'articles_count']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        # Filter to user's own exports if authenticated
        if self.request.user.is_authenticated:
            queryset = queryset.filter(user=self.request.user)
        return queryset
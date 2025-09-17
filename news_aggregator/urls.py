from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create router and register viewsets
router = DefaultRouter()
router.register(r'articles', views.ArticleViewSet, basename='article')
router.register(r'sources', views.SourceViewSet, basename='source')
router.register(r'tags', views.TagViewSet, basename='tag')
router.register(r'logs', views.ScrapingLogViewSet, basename='scrapinglog')
router.register(r'exports', views.ExportHistoryViewSet, basename='exporthistory')

app_name = 'news_aggregator'

urlpatterns = [
    # Template views
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('articles/', views.ArticleListView.as_view(), name='article_list'),
    path('articles/<int:pk>/', views.ArticleDetailView.as_view(), name='article_detail'),
    path('sources/', views.SourceListView.as_view(), name='source_list'),
    path('script-generator/', views.ScriptGeneratorView.as_view(), name='script_generator'),
    
    # API routes
    path('api/', include(router.urls)),
    path('api/script/generate/', views.ArticleViewSet.as_view({'post': 'generate_script'}), name='generate_script'),
]
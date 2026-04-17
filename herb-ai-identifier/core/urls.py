from django.urls import path
from . import views


urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('favicon.ico', views.favicon_view, name='favicon'),
    path('library/', views.library_view, name='library'),
    path('chat/', views.chat_view, name='chat'),
    path('unified-dashboard/', views.unified_dashboard, name='unified_dashboard'),
    path('analyzer/', views.analyzer_view, name='analyzer'),
    path('scan/', views.scan_herb, name='scan_herb'),
    path('knowledge-base/', views.knowledge_base_view, name='knowledge_base'),
    path('chat/send/', views.send_message, name='send_message'),
    path('manual-add/', views.manual_add, name='manual_add'),
    path('history/', views.ai_history, name='history'),
    path('delete-specimen/<int:specimen_id>/', views.delete_specimen, name='delete_specimen'),
]
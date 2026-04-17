from django.contrib import admin
from .models import ScannedSpecimen

@admin.register(ScannedSpecimen)
class ScannedSpecimenAdmin(admin.ModelAdmin):
    list_display  = ['common_name', 'scientific_name', 'confidence', 'timestamp']
    list_filter   = ['timestamp']
    search_fields = ['common_name', 'scientific_name']


import csv
from django.http import HttpResponse
from django.contrib import admin
from .models import Complaint


def export_csv(modeladmin, request, queryset):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="complaints.csv"'
    w = csv.writer(response)
    w.writerow(['ID', 'Category', 'Title', 'Status', 'Priority', 'Submitter', 'Location', 'Created'])
    for c in queryset:
        w.writerow([c.complaint_id, c.category, c.title,
                    c.status, c.priority, c.submitter_name,
                    c.location, c.created_at])
    return response


export_csv.short_description = 'Export selected as CSV'


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display    = ['complaint_id', 'title', 'category', 'status', 'priority', 'submitter_name', 'created_at']
    list_filter     = ['status', 'category', 'priority']
    search_fields   = ['complaint_id', 'title', 'submitter_name']
    readonly_fields = ['complaint_id', 'created_at', 'updated_at']
    actions         = [export_csv]
    list_per_page   = 25

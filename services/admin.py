from django.contrib import admin
from .models import ServiceRequest, ServiceRequestStatusHistory, PublicNotice

admin.site.register(ServiceRequest)
admin.site.register(PublicNotice)

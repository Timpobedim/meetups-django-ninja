from django.contrib import admin

from apps.events.models import Event, Tag


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "organizer", "starts_at", "city", "is_online", "capacity")
    list_filter = ("is_online",)
    search_fields = ("title", "summary")


admin.site.register(Tag)

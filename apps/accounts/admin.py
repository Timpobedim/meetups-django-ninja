from django.contrib import admin

from apps.accounts.models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "is_active", "is_staff", "date_joined")
    search_fields = ("username", "email")

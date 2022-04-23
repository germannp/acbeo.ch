from django.contrib import admin

from .models import Singup


class SingupAdmin(admin.ModelAdmin):
    list_display = ("date", "pilot", "status", "updated_on", "created_on")
    search_fields = ["date", "pilot"]


admin.site.register(Singup, SingupAdmin)

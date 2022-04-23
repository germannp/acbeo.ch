from django.contrib import admin

from .models import Training, Singup


class SingupAdmin(admin.ModelAdmin):
    list_display = ("training", "pilot", "status", "updated_on", "created_on")
    search_fields = ["training", "pilot"]


admin.site.register(Training)
admin.site.register(Singup, SingupAdmin)

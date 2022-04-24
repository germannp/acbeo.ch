from django.contrib import admin

from .models import Training, Signup


class SignupAdmin(admin.ModelAdmin):
    list_display = ("training", "pilot", "status", "signed_up_on")
    search_fields = ["training", "pilot"]


admin.site.register(Training)
admin.site.register(Signup, SignupAdmin)

from django.contrib import admin

from .models import Training, Signup


class TrainingAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "priority_date",
        "max_pilots",
        "emergency_mail_sender",
        "info",
    )


admin.site.register(Training, TrainingAdmin)


class SignupAdmin(admin.ModelAdmin):
    list_display = (
        "training",
        "pilot",
        "status",
        "signed_up_on",
        "is_certain",
        "for_time",
        "for_sketchy_weather",
        "comment",
    )
    search_fields = ["training", "pilot"]


admin.site.register(Signup, SignupAdmin)

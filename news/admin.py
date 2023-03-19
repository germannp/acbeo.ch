from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group

from .models import Post, Pilot


class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "created_on")
    search_fields = ("author", "content")
    prepopulated_fields = {"slug": ("title",)}


admin.site.register(Post, PostAdmin)


@admin.action(description="Ausgewählte zu Mitgliedern machen")
def make_member(modeladmin, request, queryset):
    queryset.update(role=Pilot.Role.Member)


@admin.action(description="Ausgewählte zu Leiter·innen machen")
def make_orga(modeladmin, request, queryset):
    queryset.update(role=Pilot.Role.Orga)


class PilotAdmin(BaseUserAdmin):
    list_display = (
        "email",
        "first_name",
        "last_name",
        "phone",
        "date_joined",
        "prepaid_flights",
        "role",
        "is_active",
    )
    ordering = ("-date_joined",)
    search_fields = ("first_name", "last_name", "email", "phone")
    list_filter = ("role", "is_active")
    filter_horizontal = ()
    actions = (make_member, make_orga)

    # Fields for creating Pilot from admin site
    add_fieldsets = (
        (
            None,
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "email",
                    "phone",
                    "prepaid_flights",
                    "role",
                    "is_active",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    # Fields for updating Pilot from admin site
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "email",
                    "phone",
                    "prepaid_flights",
                    "role",
                    "is_active",
                    "password",
                )
            },
        ),
    )


admin.site.register(Pilot, PilotAdmin)
admin.site.unregister(Group)

from django.contrib import admin

from .models import Absorption, Bill, Expense, Purchase, Report, Run


class ReportAdmin(admin.ModelAdmin):
    list_display = ("training", "cash_at_start", "cash_at_end")
    ordering = ("-training",)


admin.site.register(Report, ReportAdmin)


class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("report", "reason", "amount")
    ordering = ("-report",)


admin.site.register(Expense, ExpenseAdmin)


class AbsorptionAdmin(admin.ModelAdmin):
    list_display = ("report", "signup", "amount", "method")
    ordering = ("-report", "signup")


admin.site.register(Absorption, AbsorptionAdmin)


class RunAdmin(admin.ModelAdmin):
    list_display = ("report", "signup", "kind", "created_on")
    ordering = ("-created_on", "signup__pilot")


admin.site.register(Run, RunAdmin)


class BillAdmin(admin.ModelAdmin):
    list_display = ("report", "signup", "amount", "method")
    ordering = ("-report", "signup__pilot")


admin.site.register(Bill, BillAdmin)


class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("signup", "description", "price")
    ordering = ("-signup",)


admin.site.register(Purchase, PurchaseAdmin)

from django.contrib import admin

from .models import Bill, Expense, Report, Run


class ReportAdmin(admin.ModelAdmin):
    list_display = ("training", "cash_at_start", "cash_at_end")
    ordering = ("-training",)


admin.site.register(Report, ReportAdmin)


class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("report", "reason", "amount")
    ordering = ("-report",)


admin.site.register(Expense, ExpenseAdmin)


class RunAdmin(admin.ModelAdmin):
    list_display = ("report", "signup", "kind", "created_on")
    ordering = ("-created_on", "signup__pilot")


admin.site.register(Run, RunAdmin)


class BillAdmin(admin.ModelAdmin):
    list_display = ("report", "signup", "payed")
    ordering = ("-report", "signup__pilot")


admin.site.register(Bill, BillAdmin)

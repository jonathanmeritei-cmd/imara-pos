from django.contrib import admin
from .models import CreditPayment, Customer, Expense, Product, Sale, SaleItem


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "unit_type", "metres_per_roll", "buying_price", "selling_price", "stock_quantity")
    search_fields = ("name", "sku")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "credit_balance")
    search_fields = ("name", "phone")


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("id", "ticket_no", "customer", "total_amount", "payment_method", "mpesa_code", "date")
    list_filter = ("payment_method", "date")
    search_fields = ("ticket_no", "mpesa_code")
    inlines = [SaleItemInline]


@admin.register(CreditPayment)
class CreditPaymentAdmin(admin.ModelAdmin):
    list_display = ("customer", "amount", "method", "reference", "date")
    list_filter = ("method", "date")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "amount",
        "paid_via",
        "created_at",
    )
    list_filter = ("category", "paid_via", "created_at")
from django.contrib import admin
from .models import CreditPayment, Customer, Expense, Product, Sale, SaleItem


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "serial_number", "unit_type", "selling_price", "stock_quantity", "created_at")
    list_filter = ("unit_type", "created_at")
    search_fields = ("name", "sku", "serial_number")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "credit_balance", "created_at")
    search_fields = ("name", "phone", "email")


@admin.register(CreditPayment)
class CreditPaymentAdmin(admin.ModelAdmin):
    list_display = ("customer", "amount", "payment_method", "reference", "created_at")
    list_filter = ("payment_method", "created_at")
    search_fields = ("customer__name", "reference")


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("ticket_no", "customer", "served_by", "payment_method", "total_amount", "is_void", "created_at")
    list_filter = ("payment_method", "is_void", "created_at")
    search_fields = ("ticket_no", "customer__name", "mpesa_code")
    inlines = [SaleItemInline]


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "amount", "recorded_by", "is_void", "created_at")
    list_filter = ("category", "is_void", "created_at")
    search_fields = ("title", "category", "notes")
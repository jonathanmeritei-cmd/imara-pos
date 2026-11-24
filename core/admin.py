from django.contrib import admin
from .models import Product, Customer, Sale

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'buying_price', 'selling_price', 'stock_quantity')
    search_fields = ('name', 'sku')

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'credit_balance')
    search_fields = ('name', 'phone')

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('ticket_no', 'receipt_no', 'product', 'quantity', 'total_amount', 'payment_method', 'customer', 'date')
    list_filter = ('payment_method', 'date')
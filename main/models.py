from django.db import models
from django.utils import timezone


class Product(models.Model):
    UNIT_CHOICES = [
        ("PCS", "Pieces (PCS)"),
        ("ROLL", "Rolls (ROLL)"),
        ("METRE", "Metres (M)"),
        ("BOX", "Boxes (BOX)"),
        ("PACK", "Packets (PACK)"),
    ]

    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=60, blank=True, null=True)
    unit_type = models.CharField(max_length=10, choices=UNIT_CHOICES, default="PCS")
    metres_per_roll = models.DecimalField(max_digits=10, decimal_places=2, default=100)
    buying_price = models.DecimalField(max_digits=12, decimal_places=2)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    stock_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.stock_quantity} {self.unit_type})"


class Customer(models.Model):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=40, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    credit_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Sale(models.Model):
    PAYMENT_CHOICES = [
        ("CASH", "CASH"),
        ("MPESA", "MPESA"),
        ("CREDIT", "CREDIT"),
        ("BANK", "BANK"),
    ]

    ticket_no = models.CharField(max_length=40, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, blank=True, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default="CASH")
    mpesa_code = models.CharField(max_length=40, blank=True, null=True)
    date = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.ticket_no} - KES {self.total_amount}"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_sold = models.CharField(max_length=10, default="PCS")
    deducted_base_qty = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} {self.unit_sold} x {self.product.name}"


class CreditPayment(models.Model):
    customer = models.ForeignKey(Customer, related_name="payments", on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=10, default="MPESA")
    reference = models.CharField(max_length=120, blank=True, null=True)
    date = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.customer.name} - KES {self.amount}"


class Expense(models.Model):
    CATEGORY_CHOICES = [
        ("TRANSPORT", "Transport / Boda / Delivery"),
        ("UTILITIES", "Electricity / Water / Internet"),
        ("STAFF_MEALS", "Staff Meals / Tea"),
        ("MAINTENANCE", "Shop Repairs & Maintenance"),
        ("SUPPLIES", "Packaging / Stationery / Misc"),
        ("OTHER", "Other Operating Expense"),
    ]

    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="OTHER")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_via = models.CharField(max_length=10, choices=[("CASH", "CASH"), ("MPESA", "MPESA")], default="CASH")
    notes = models.CharField(max_length=255, blank=True, null=True)
created_at = models.DateTimeField(auto_now_add=True)

def __str__(self):
        return f"{self.title} - KES {self.amount}"
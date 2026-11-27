import random
from django.conf import settings
from django.db import models
from django.utils import timezone


def _generate_sku_and_serial(product_name="ITEM"):
    prefix = "".join(ch for ch in (product_name or "ITEM").upper() if ch.isalpha())[:3].ljust(3, "X")
    now = timezone.localtime(timezone.now())
    ymd = now.strftime("%y%m%d")
    sku = f"MES-{prefix}-{random.randint(1000, 9999)}"
    serial_number = f"SN-{ymd}-{random.randint(100000, 999999)}"
    return sku, serial_number


def _generate_ticket_no():
    now = timezone.localtime(timezone.now())
    ymd = now.strftime("%Y%m%d")
    return f"INV-{ymd}-{random.randint(1000, 9999)}"


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
    serial_number = models.CharField(max_length=100, blank=True, null=True)
    unit_type = models.CharField(max_length=10, choices=UNIT_CHOICES, default="PCS")
    metres_per_roll = models.DecimalField(max_digits=10, decimal_places=2, default=100)
    buying_price = models.DecimalField(max_digits=12, decimal_places=2)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    stock_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.sku or not self.serial_number:
            gen_sku, gen_sn = _generate_sku_and_serial(self.name)
            if not self.sku:
                self.sku = gen_sku
            if not self.serial_number:
                self.serial_number = gen_sn
        super().save(*args, **kwargs)

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


class CreditPayment(models.Model):
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="credit_payments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, default="CASH")
    reference = models.CharField(max_length=60, blank=True, null=True)
    notes = models.CharField(max_length=255, blank=True, null=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer.name} - KES {self.amount}"


class Sale(models.Model):
    PAYMENT_CHOICES = [
        ("CASH", "Cash"),
        ("MPESA", "M-Pesa"),
        ("PAYBILL", "M-Pesa Paybill"),
        ("CREDIT", "Credit"),
    ]

    ticket_no = models.CharField(max_length=40, unique=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, blank=True, null=True)
    served_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="sales_served",
    )
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default="CASH")
    mpesa_code = models.CharField(max_length=40, blank=True, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_void = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.ticket_no:
            self.ticket_no = _generate_ticket_no()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.ticket_no or f"Sale #{self.pk}"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, blank=True, null=True)
    product_name = models.CharField(max_length=200)
    unit_sold = models.CharField(max_length=15, default="PCS")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        if not self.product_name and self.product:
            self.product_name = self.product.name
        if not self.line_total:
            self.line_total = (self.quantity or 0) * (self.unit_price or 0)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"


class Expense(models.Model):
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True, null=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="expenses_recorded",
    )
    is_void = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - KES {self.amount}"
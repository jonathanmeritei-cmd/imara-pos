import random
from datetime import datetime
from django.utils import timezone

def generate_sku_and_serial(product_name="ITEM"):
    prefix = "".join(ch for ch in product_name.upper() if ch.isalpha())[:3].ljust(3, "X")
    now = timezone.localtime(timezone.now())
    rand_sku = random.randint(1000, 9999)
    sku = f"MES-{prefix}-{rand_sku}"

    date_part = now.strftime("%y%m%d")
    rand_sn = random.randint(100000, 999999)
    serial_number = f"SN-{date_part}-{rand_sn}"
    return sku, serial_number
import json
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import CreditPayment, Customer, Expense, Product, Sale, SaleItem


def _to_decimal(val, default="0"):
    try:
        return Decimal(str(val).strip())
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def _get_sale_items(sale):
    for attr in ("items", "saleitem_set"):
        mgr = getattr(sale, attr, None)
        if mgr is not None and hasattr(mgr, "all"):
            return list(mgr.select_related("product").all())
    return list(SaleItem.objects.select_related("product").filter(sale=sale))


def pos_view(request):
    tab = request.GET.get("tab", "pos")
    if tab not in ("pos", "inventory", "customers", "expenses"):
        tab = "pos"

    error_msg = None
    success_msg = None
    last_sale = None

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "add_product":
            tab = "inventory"
            name = (request.POST.get("name") or "").strip()
            sku = (request.POST.get("sku") or "").strip() or None
            serial_number = (request.POST.get("serial_number") or "").strip() or None
            unit_type = (request.POST.get("unit_type") or "PCS").strip().upper()
            if unit_type not in dict(Product.UNIT_CHOICES):
                unit_type = "PCS"

            metres_per_roll = _to_decimal(request.POST.get("metres_per_roll"), "100")
            if metres_per_roll <= 0:
                metres_per_roll = Decimal("100")

            buying_price = _to_decimal(request.POST.get("buying_price"), "0")
            selling_price = _to_decimal(request.POST.get("selling_price"), "0")
            stock_quantity = _to_decimal(request.POST.get("stock_quantity"), "0")

            if not name or selling_price <= 0:
                error_msg = "Enter a valid product name and selling price."
            elif stock_quantity < 0 or buying_price < 0:
                error_msg = "Prices and stock quantity cannot be negative."
            else:
                prod = Product.objects.create(
                    name=name,
                    sku=sku,
                    serial_number=serial_number,
                    unit_type=unit_type,
                    metres_per_roll=metres_per_roll,
                    buying_price=buying_price,
                    selling_price=selling_price,
                    stock_quantity=stock_quantity,
                )
                success_msg = f"Added '{prod.name}' ({prod.stock_quantity} {prod.unit_type}) • SKU: {prod.sku}"

        elif action == "restock":
            tab = "inventory"
            product_id = request.POST.get("product_id")
            add_qty = _to_decimal(request.POST.get("add_qty"), "0")
            product = get_object_or_404(Product, id=product_id)

            if add_qty <= 0:
                error_msg = "Restock quantity must be greater than zero."
            else:
                product.stock_quantity = (product.stock_quantity or Decimal("0")) + add_qty
                product.save(update_fields=["stock_quantity"])
                success_msg = f"Restocked +{add_qty} {product.unit_type} on '{product.name}'."

        elif action == "add_customer":
            tab = "customers"
            cust_name = (request.POST.get("customer_name") or request.POST.get("name") or "").strip()
            phone = (request.POST.get("phone") or "").strip() or None
            email = (request.POST.get("email") or "").strip() or None

            if not cust_name:
                error_msg = "Customer name is required."
            else:
                Customer.objects.create(name=cust_name, phone=phone, email=email)
                success_msg = f"Customer '{cust_name}' added."

        elif action == "repay_credit":
            tab = "customers"
            customer_id = request.POST.get("customer_id")
            amount = _to_decimal(request.POST.get("amount"), "0")
            method = (request.POST.get("method") or request.POST.get("payment_method") or "CASH").strip().upper()
            reference = (request.POST.get("reference") or "").strip() or None
            notes = (request.POST.get("notes") or "").strip() or None
            customer = get_object_or_404(Customer, id=customer_id)

            if amount <= 0:
                error_msg = "Repayment amount must be greater than zero."
            else:
                with transaction.atomic():
                    CreditPayment.objects.create(
                        customer=customer,
                        amount=amount,
                        payment_method=method,
                        reference=reference,
                        notes=notes,
                        recorded_by=request.user if request.user.is_authenticated else None,
                    )
                    current_debt = customer.credit_balance or Decimal("0.00")
                    customer.credit_balance = max(Decimal("0.00"), current_debt - amount)
                    customer.save(update_fields=["credit_balance"])
                success_msg = f"Recorded KES {amount} repayment for {customer.name}."

        elif action == "add_expense":
            tab = "expenses"
            title = (request.POST.get("title") or "").strip()
            category = (request.POST.get("category") or "OTHER").strip().upper()
            amount = _to_decimal(request.POST.get("amount"), "0")
            notes = (request.POST.get("notes") or "").strip() or None

            if not title or amount <= 0:
                error_msg = "Enter an expense title and a valid amount."
            else:
                Expense.objects.create(
                    title=title,
                    category=category,
                    amount=amount,
                    notes=notes,
                    recorded_by=request.user if request.user.is_authenticated else None,
                )
                success_msg = f"Recorded expense '{title}' (KES {amount})."

        elif action == "checkout":
            tab = "pos"
            raw_cart = request.POST.get("cart_json") or "[]"
            payment_method = (request.POST.get("payment_method") or "CASH").strip().upper()
            mpesa_code = (request.POST.get("mpesa_code") or "").strip() or None
            customer_id = request.POST.get("customer_id")

            try:
                cart_list = json.loads(raw_cart)
                if not isinstance(cart_list, list):
                    cart_list = []
            except json.JSONDecodeError:
                cart_list = []

            customer = Customer.objects.filter(id=customer_id).first() if customer_id else None

            if not cart_list:
                error_msg = "Cart is empty. Add at least one item."
            elif payment_method == "CREDIT" and not customer:
                error_msg = "Select a customer for CREDIT sales."
            else:
                try:
                    with transaction.atomic():
                        computed_total = Decimal("0.00")
                        prepared_lines = []

                        for item in cart_list:
                            pid = item.get("id")
                            qty = _to_decimal(item.get("qty"), "0")
                            sell_mode = (item.get("sell_mode") or "").strip().upper()
                            if not pid or qty <= 0:
                                continue

                            prod = Product.objects.select_for_update().get(id=pid)
                            mpr = (
                                prod.metres_per_roll
                                if prod.metres_per_roll and prod.metres_per_roll > 0
                                else Decimal("100")
                            )

                            if sell_mode == "ROLL":
                                if prod.unit_type == "ROLL":
                                    unit_price = prod.selling_price
                                    deduct_qty = qty
                                    unit_label = "ROLL"
                                else:
                                    unit_price = prod.selling_price * mpr
                                    deduct_qty = qty * mpr
                                    unit_label = "ROLL"
                            elif sell_mode == "METRE":
                                if prod.unit_type == "ROLL":
                                    unit_price = (prod.selling_price / mpr).quantize(Decimal("0.01"))
                                    deduct_qty = qty
                                    unit_label = "METRE"
                                else:
                                    unit_price = prod.selling_price
                                    deduct_qty = qty
                                    unit_label = "METRE"
                            else:
                                unit_price = prod.selling_price
                                deduct_qty = qty
                                unit_label = prod.unit_type

                            if (prod.stock_quantity or Decimal("0")) < deduct_qty:
                                raise ValueError(f"Insufficient stock for {prod.name}.")

                            line_total = (unit_price * qty).quantize(Decimal("0.01"))
                            computed_total += line_total

                            prod.stock_quantity = prod.stock_quantity - deduct_qty
                            prod.save(update_fields=["stock_quantity"])

                            prepared_lines.append((prod, qty, unit_label, deduct_qty, unit_price, line_total))

                        if not prepared_lines:
                            raise ValueError("No valid items in cart.")

                        today_local = timezone.localtime(timezone.now()).date()
                        count_today = Sale.objects.filter(created_at__date=today_local).count() + 1
                        ticket_no = f"INV-{today_local.strftime('%Y%m%d')}-{count_today:04d}"
                        if Sale.objects.filter(ticket_no=ticket_no).exists():
                            ticket_no = f"INV-{today_local.strftime('%Y%m%d')}-{Sale.objects.count() + 1001}"

                        sale = Sale.objects.create(
                            ticket_no=ticket_no,
                            customer=customer,
                            served_by=request.user if request.user.is_authenticated else None,
                            payment_method=payment_method,
                            mpesa_code=mpesa_code,
                            total_amount=computed_total,
                        )

                        for prod, qty, unit_label, deduct_qty, unit_price, line_total in prepared_lines:
                            SaleItem.objects.create(
                                sale=sale,
                                product=prod,
                                product_name=prod.name,
                                unit_sold=unit_label,
                                quantity=qty,
                                unit_price=unit_price,
                                line_total=line_total,
                            )

                        if payment_method == "CREDIT" and customer:
                            current_debt = customer.credit_balance or Decimal("0.00")
                            customer.credit_balance = current_debt + computed_total
                            customer.save(update_fields=["credit_balance"])

                        last_sale = sale
                        success_msg = f"Sale completed! Ticket {sale.ticket_no} • Total KES {sale.total_amount}"

                except ValueError as ve:
                    error_msg = str(ve)
                except Product.DoesNotExist:
                    error_msg = "One of the selected products no longer exists."

    today_local = timezone.localtime(timezone.now()).date()
    today_sales = Sale.objects.filter(is_void=False, created_at__date=today_local)
    today_expenses = Expense.objects.filter(is_void=False, created_at__date=today_local)
    repayments_today_qs = CreditPayment.objects.filter(created_at__date=today_local)

    daily_revenue = today_sales.aggregate(s=Sum("total_amount"))["s"] or Decimal("0.00")
    tx_count = today_sales.count()

    cost_basis = Decimal("0.00")
    for s_item in SaleItem.objects.select_related("product").filter(sale__in=today_sales):
        buying_price = getattr(s_item.product, "buying_price", Decimal("0.00")) or Decimal("0.00")
        cost_basis += buying_price * (s_item.quantity or Decimal("0.00"))

    daily_expenses = today_expenses.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    daily_profit = daily_revenue - cost_basis - daily_expenses

    cash_total = today_sales.filter(payment_method="CASH").aggregate(s=Sum("total_amount"))["s"] or Decimal("0.00")
    mpesa_total = today_sales.filter(payment_method__in=["MPESA", "PAYBILL"]).aggregate(s=Sum("total_amount"))["s"] or Decimal("0.00")
    credit_total = today_sales.filter(payment_method="CREDIT").aggregate(s=Sum("total_amount"))["s"] or Decimal("0.00")
    repayments_today = repayments_today_qs.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

    products = Product.objects.order_by("name")
    customers = Customer.objects.order_by("name")
    recent_sales = Sale.objects.prefetch_related("items", "customer", "served_by")[:25]
    recent_expenses = Expense.objects.select_related("recorded_by")[:25]
    recent_repayments = CreditPayment.objects.select_related("customer", "recorded_by")[:25]
    low_stock_products = Product.objects.filter(stock_quantity__lte=5).order_by("stock_quantity")
    total_credit_due = Customer.objects.aggregate(s=Sum("credit_balance"))["s"] or Decimal("0.00")

    context = {
        "active_tab": tab,
        "error_msg": error_msg,
        "success_msg": success_msg,
        "last_sale": last_sale,
        "products": products,
        "customers": customers,
        "recent_sales": recent_sales,
        "recent_expenses": recent_expenses,
        "recent_repayments": recent_repayments,
        "low_stock_products": low_stock_products,
        "total_credit_due": total_credit_due,
        "daily_revenue": daily_revenue,
        "daily_profit": daily_profit,
        "daily_expenses": daily_expenses,
        "tx_count": tx_count,
        "cash_total": cash_total,
        "mpesa_total": mpesa_total,
        "credit_total": credit_total,
        "repayments_today": repayments_today,
        "shop_name": "MUJTABA ELECTRICAL SUPPLIERS",
        "shop_location": "Loitokitok, Kenya",
        "shop_phone": "0707 937634",
        "paybill_no": "522533",
        "account_no": "8163185",
        "brand_footer": "Powered by IMARA POS • Imara Systems Tech",
        "brand_tagline": "POS Systems • Web Apps • Business Automation • Call/WhatsApp: 0790 576 915",
        "now_local": timezone.localtime(timezone.now()),
    }
    return render(request, "main/pos.html", context)


pos_dashboard = pos_view


def sale_receipt(request, sale_id):
    sale = get_object_or_404(Sale.objects.prefetch_related("items", "customer", "served_by"), id=sale_id)
    receipt_items = _get_sale_items(sale)
    context = {
        "sale": sale,
        "items": receipt_items,
        "receipt_items": receipt_items,
        "shop_name": "MUJTABA ELECTRICAL SUPPLIERS",
        "shop_location": "Loitokitok, Kenya",
        "shop_phone": "0707 937634",
        "paybill_no": "522533",
        "account_no": "8163185",
        "brand_footer": "Powered by IMARA POS • Imara Systems Tech",
        "brand_tagline": "POS Systems • Web Apps • Business Automation • Call/WhatsApp: 0790 576 915",
    }
    return render(request, "main/receipt.html", context)
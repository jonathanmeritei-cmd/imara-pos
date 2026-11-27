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


def _has_model_field(model_cls, field_name):
    return any(f.name == field_name for f in model_cls._meta.get_fields())


def pos_view(request):
    tab = request.GET.get("tab", "pos")
    if tab not in ("pos", "inventory", "customers", "expenses", "reports"):
        tab = "pos"

    error_msg = None
    success_msg = None

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "add_product":
            tab = "inventory"
            name = (request.POST.get("name") or "").strip()
            sku = (request.POST.get("sku") or "").strip()
            unit_type = (request.POST.get("unit_type") or "PCS").strip()
            if unit_type not in dict(Product.UNIT_CHOICES):
                unit_type = "PCS"

            metres_per_roll = _to_decimal(request.POST.get("metres_per_roll"), "100")
            if metres_per_roll <= 0:
                metres_per_roll = Decimal("100")

            buying_price = _to_decimal(request.POST.get("buying_price"), "0")
            selling_price = _to_decimal(request.POST.get("selling_price"), "0")
            stock_quantity = _to_decimal(request.POST.get("stock_quantity"), "0")

            if not name or selling_price <= 0:
                error_msg = "Enter a valid product name and selling price greater than 0."
            elif stock_quantity < 0 or buying_price < 0:
                error_msg = "Prices and stock quantity cannot be negative."
            else:
                Product.objects.create(
                    name=name,
                    sku=sku,
                    unit_type=unit_type,
                    metres_per_roll=metres_per_roll,
                    buying_price=buying_price,
                    selling_price=selling_price,
                    stock_quantity=stock_quantity,
                )
                success_msg = f"Added '{name}' ({stock_quantity} {unit_type})."

        elif action == "restock":
            tab = "inventory"
            product_id = request.POST.get("product_id")
            add_qty = _to_decimal(request.POST.get("add_qty"), "0")
            product = get_object_or_404(Product, id=product_id)

            if add_qty <= 0:
                error_msg = "Restock quantity must be greater than 0."
            else:
                product.stock_quantity = product.stock_quantity + add_qty
                product.save(update_fields=["stock_quantity"])
                success_msg = f"Restocked +{add_qty} {product.unit_type} of '{product.name}'."

        elif action == "add_customer":
            tab = "customers"
            cust_name = (request.POST.get("customer_name") or request.POST.get("name") or "").strip()
            phone = (request.POST.get("phone") or "").strip()
            email = (request.POST.get("email") or "").strip()

            if not cust_name:
                error_msg = "Customer name is required."
            else:
                Customer.objects.create(
                    name=cust_name,
                    phone=phone,
                    email=email,
                )
                success_msg = f"Customer '{cust_name}' added."

        elif action == "repay_credit":
            tab = "customers"
            customer_id = request.POST.get("customer_id")
            amount = _to_decimal(request.POST.get("amount"), "0")
            method = (request.POST.get("method") or "CASH").strip()
            reference = (request.POST.get("reference") or "").strip()
            customer = get_object_or_404(Customer, id=customer_id)

            if amount <= 0:
                error_msg = "Repayment amount must be greater than 0."
            else:
                with transaction.atomic():
                    CreditPayment.objects.create(
                        customer=customer,
                        amount=amount,
                        method=method,
                        reference=reference,
                    )
                    current_debt = getattr(customer, "credit_balance", Decimal("0.00")) or Decimal("0.00")
                    customer.credit_balance = max(Decimal("0.00"), current_debt - amount)
                    customer.save(update_fields=["credit_balance"])
                success_msg = f"Recorded KES {amount} repayment from {customer.name}."

        elif action == "add_expense":
            tab = "expenses"
            title = (request.POST.get("title") or "").strip()
            category = (request.POST.get("category") or "OTHER").strip()
            if category not in dict(Expense.CATEGORY_CHOICES):
                category = "OTHER"

            amount = _to_decimal(request.POST.get("amount"), "0")
            paid_via = (request.POST.get("paid_via") or "CASH").strip()
            if paid_via not in ("CASH", "MPESA"):
                paid_via = "CASH"
            notes = (request.POST.get("notes") or "").strip()

            if not title or amount <= 0:
                error_msg = "Enter an expense title and an amount greater than 0."
            else:
                Expense.objects.create(
                    title=title,
                    category=category,
                    amount=amount,
                    paid_via=paid_via,
                    notes=notes,
                )
                success_msg = f"Recorded expense '{title}' (KES {amount})."

        elif action == "checkout":
            tab = "pos"
            raw_cart = request.POST.get("cart_json") or "[]"
            payment_method = (request.POST.get("payment_method") or "CASH").strip()
            mpesa_code = (request.POST.get("mpesa_code") or "").strip()
            customer_id = request.POST.get("customer_id") or None

            try:
                cart_list = json.loads(raw_cart)
                if not isinstance(cart_list, list):
                    cart_list = []
            except json.JSONDecodeError:
                cart_list = []

            if not cart_list:
                error_msg = "Cart is empty. Add at least one item."
            elif payment_method == "CREDIT" and not customer_id:
                error_msg = "Select a customer for CREDIT sales."
            else:
                customer = Customer.objects.filter(id=customer_id).first() if customer_id else None

                try:
                    with transaction.atomic():
                        computed_total = Decimal("0.00")
                        prepared_lines = []

                        for item in cart_list:
                            pid = item.get("id")
                            qty = _to_decimal(item.get("qty"), "0")
                            sell_mode = (item.get("sell_mode") or "UNIT").upper()

                            if not pid or qty <= 0:
                                continue

                            prod = Product.objects.select_for_update().get(id=pid)
                            mpr = (
                                prod.metres_per_roll
                                if getattr(prod, "metres_per_roll", None) and prod.metres_per_roll > 0
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
                                    unit_price = prod.selling_price / mpr
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

                            if prod.stock_quantity < deduct_qty:
                                raise ValueError(
                                    f"Insufficient stock for {prod.name} (available: {prod.stock_quantity})."
                                )

                            line_total = (unit_price * qty).quantize(Decimal("0.01"))
                            computed_total += line_total

                            prod.stock_quantity = prod.stock_quantity - deduct_qty
                            prod.save(update_fields=["stock_quantity"])

                            prepared_lines.append((prod, qty, unit_label, deduct_qty, unit_price, line_total))

                        if not prepared_lines:
                            raise ValueError("No valid items in cart.")

                        today_local = timezone.localdate()
                        sale_date_field = "created_at" if _has_model_field(Sale, "created_at") else "date"
                        count_today = Sale.objects.filter(**{f"{sale_date_field}__date": today_local}).count()
                        ticket_no = f"INV-{today_local.strftime('%Y%m%d')}-{count_today + 1:04d}"

                        sale_kwargs = {
                            "ticket_no": ticket_no,
                            "customer": customer,
                            "total_amount": computed_total,
                        }
                        if _has_model_field(Sale, "payment_method"):
                            sale_kwargs["payment_method"] = payment_method
                        if _has_model_field(Sale, "mpesa_code"):
                            sale_kwargs["mpesa_code"] = mpesa_code

                        sale = Sale.objects.create(**sale_kwargs)

                        for prod, qty, unit_label, deduct_qty, unit_price, line_total in prepared_lines:
                            item_kwargs = {
                                "sale": sale,
                                "product": prod,
                                "quantity": qty,
                                "unit_sold": unit_label,
                                "unit_price": unit_price,
                                "line_total": line_total,
                            }
                            if _has_model_field(SaleItem, "product_name"):
                                item_kwargs["product_name"] = prod.name
                            if _has_model_field(SaleItem, "deducted_base_qty"):
                                item_kwargs["deducted_base_qty"] = deduct_qty
                            SaleItem.objects.create(**item_kwargs)

                        if payment_method == "CREDIT" and customer:
                            current_debt = getattr(customer, "credit_balance", Decimal("0.00")) or Decimal("0.00")
                            customer.credit_balance = current_debt + computed_total
                            customer.save(update_fields=["credit_balance"])

                        success_msg = f"Sale completed! Ticket {ticket_no} — KES {computed_total}."

                except ValueError as ve:
                    error_msg = str(ve)
                except Product.DoesNotExist:
                    error_msg = "One of the selected products no longer exists."

    today = timezone.localdate()

    sale_dt_field = "created_at" if _has_model_field(Sale, "created_at") else "date"
    today_sales = Sale.objects.filter(**{f"{sale_dt_field}__date": today})

    if _has_model_field(Expense, "created_at"):
        today_expenses = Expense.objects.filter(created_at__date=today)
    elif _has_model_field(Expense, "date"):
        today_expenses = Expense.objects.filter(date__date=today)
    else:
        today_expenses = Expense.objects.all()

    daily_revenue = today_sales.aggregate(s=Sum("total_amount"))["s"] or Decimal("0.00")
    tx_count = today_sales.count()

    daily_profit = Decimal("0.00")
    for s_item in SaleItem.objects.select_related("product").filter(sale__in=today_sales):
        deducted = (
            s_item.deducted_base_qty
            if getattr(s_item, "deducted_base_qty", None) and s_item.deducted_base_qty > 0
            else s_item.quantity
        )
        buying_price = getattr(s_item.product, "buying_price", Decimal("0.00")) or Decimal("0.00")
        cost_basis = buying_price * deducted
        daily_profit += s_item.line_total - cost_basis

    daily_expenses = today_expenses.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    cash_expenses = today_expenses.filter(paid_via="CASH").aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    mpesa_expenses = today_expenses.filter(paid_via="MPESA").aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    daily_net_profit = daily_profit - daily_expenses

    name_field = "product_name" if _has_model_field(SaleItem, "product_name") else "product__name"

    best_sellers = list(
        SaleItem.objects.values(name_field, "unit_sold")
        .annotate(total_sold=Sum("quantity"))
        .order_by("-total_sold")[:3]
    )

    items_sold_today = list(
        SaleItem.objects.filter(sale__in=today_sales)
        .values(name_field, "unit_sold")
        .annotate(total_qty=Sum("quantity"), total_revenue=Sum("line_total"))
        .order_by(name_field, "unit_sold")
    )

    low_stock_items = list(Product.objects.filter(stock_quantity__lte=5).order_by("stock_quantity", "name"))
    total_debt = Customer.objects.aggregate(s=Sum("credit_balance"))["s"] or Decimal("0.00")

    if _has_model_field(Sale, "payment_method"):
        cash_total = today_sales.filter(payment_method="CASH").aggregate(s=Sum("total_amount"))["s"] or Decimal("0.00")
        mpesa_total = today_sales.filter(payment_method="MPESA").aggregate(s=Sum("total_amount"))["s"] or Decimal("0.00")
        credit_total = today_sales.filter(payment_method="CREDIT").aggregate(s=Sum("total_amount"))["s"] or Decimal("0.00")
        bank_total = today_sales.filter(payment_method="BANK").aggregate(s=Sum("total_amount"))["s"] or Decimal("0.00")
    else:
        cash_total = daily_revenue
        mpesa_total = Decimal("0.00")
        credit_total = Decimal("0.00")
        bank_total = Decimal("0.00")

    pay_dt_field = "created_at" if _has_model_field(CreditPayment, "created_at") else "date"
    repayments_today = (
        CreditPayment.objects.filter(**{f"{pay_dt_field}__date": today}).aggregate(s=Sum("amount"))["s"]
        or Decimal("0.00")
    )
    cash_repayments_today = (
        CreditPayment.objects.filter(**{f"{pay_dt_field}__date": today, "method": "CASH"}).aggregate(s=Sum("amount"))["s"]
        or Decimal("0.00")
    )

    net_cash_and_mpesa = cash_total + mpesa_total + repayments_today - daily_expenses
    net_cash_in_drawer = cash_total + cash_repayments_today - cash_expenses
    generated_at = timezone.localtime(timezone.now())

    z_report = {
        "company_name": "MUJTABA ELECTRICAL SUPPLIERS",
        "system_name": "IMARA POS",
        "date": today,
        "generated_at": generated_at,
        "ticket_count": tx_count,
        "cash_total": cash_total,
        "mpesa_total": mpesa_total,
        "credit_total": credit_total,
        "bank_total": bank_total,
        "repayments_today": repayments_today,
        "gross_profit": daily_profit,
        "expenses_today": daily_expenses,
        "cash_expenses": cash_expenses,
        "mpesa_expenses": mpesa_expenses,
        "net_profit": daily_net_profit,
        "gross_sales": daily_revenue,
        "net_cash_and_mpesa": net_cash_and_mpesa,
        "net_cash_in_drawer": net_cash_in_drawer,
        "items_sold_today": items_sold_today,
    }

    recent_sales_order = f"-{sale_dt_field}" if _has_model_field(Sale, sale_dt_field) else "-id"
    expense_order = "-created_at" if _has_model_field(Expense, "created_at") else "-id"

    context = {
        "tab": tab,
        "error_msg": error_msg,
        "success_msg": success_msg,
        "products": Product.objects.order_by("name"),
        "customers": Customer.objects.order_by("name"),
        "recent_sales": Sale.objects.prefetch_related("items").order_by(recent_sales_order)[:25],
        "recent_expenses": Expense.objects.order_by(expense_order)[:25],
        "daily_revenue": daily_revenue,
        "daily_profit": daily_profit,
        "daily_expenses": daily_expenses,
        "daily_net_profit": daily_net_profit,
        "tx_count": tx_count,
        "best_sellers": best_sellers,
        "low_stock_items": low_stock_items,
        "total_debt": total_debt,
        "z_report": z_report,
    }
    return render(request, "main/pos.html", context)


pos_dashboard = pos_view


def sale_receipt(request, sale_id):
    sale = get_object_or_404(Sale.objects.prefetch_related("items__product"), id=sale_id)
    return render(request, "main/receipt.html", {"sale": sale})
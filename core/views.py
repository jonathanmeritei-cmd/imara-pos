from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum
from .models import Product, Customer, Sale

def pos_dashboard(request):
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        quantity = int(request.POST.get('quantity', 1))
        payment_method = request.POST.get('payment_method', 'CASH')
        customer_id = request.POST.get('customer_id')
        mpesa_code = request.POST.get('mpesa_code', '').strip().upper()

        product = get_object_or_404(Product, id=product_id)
        customer = Customer.objects.filter(id=customer_id).first() if customer_id else None

        # Validate Approved Credit requires a registered customer
        if payment_method == 'CREDIT' and not customer:
            messages.error(request, "You must select a registered customer for Approved Credit sales.")
            return redirect('pos_dashboard')

        # Validate Stock
        if product.stock_quantity >= quantity:
            sale = Sale.objects.create(
                product=product,
                customer=customer,
                quantity=quantity,
                payment_method=payment_method,
                mpesa_code=mpesa_code if payment_method == 'MPESA' else ''
            )
            return redirect('sale_receipt', sale_id=sale.id)
        else:
            messages.error(request, f"Not enough stock for {product.name} (Only {product.stock_quantity} left).")
            return redirect('pos_dashboard')

    products = Product.objects.all().order_by('name')
    customers = Customer.objects.all().order_by('name')
    recent_sales = Sale.objects.all().order_by('-date')[:10]

    # Live Database Analytics
    today = timezone.localdate()
    today_sales = Sale.objects.filter(date__date=today)
    
    daily_revenue = sum(s.total_amount for s in today_sales)
    daily_profit = sum((s.product.selling_price - s.product.buying_price) * s.quantity for s in today_sales)
    transaction_count = today_sales.count()
    
    # Top 3 Best-Selling Products across all sales
    best_sellers = (
        Sale.objects.values('product__name')
        .annotate(total_sold=Sum('quantity'))
        .order_by('-total_sold')[:3]
    )
    
    low_stock_items = Product.objects.filter(stock_quantity__lte=5)

    return render(request, 'main/pos.html', {
        'products': products,
        'customers': customers,
        'recent_sales': recent_sales,
        'daily_revenue': daily_revenue,
        'daily_profit': daily_profit,
        'transaction_count': transaction_count,
        'best_sellers': best_sellers,
        'low_stock_items': low_stock_items,
    })

def sale_receipt(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)
    return render(request, 'main/receipt.html', {'sale': sale})
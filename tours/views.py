# tour_quote/views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from .models import TourPackageQuote, City, Hotel, Service, GuideService, ServiceType, TourDay, TourDayService, TourDayGuideService, PredefinedTourQuote, ReferenceID, ServicePrice, TourPackType
import json
from django.views.decorators.http import require_http_methods
from django.urls import reverse
from django.core.serializers.json import DjangoJSONEncoder
from weasyprint import HTML, CSS
from django.template.loader import render_to_string
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Prefetch
import traceback

def calculate_totals(package):
    service_total = sum(
        service.price_at_booking for day in package.tour_days.all() for service in day.services.all()
    )

    # Assuming guide services are part of the total as well
    guide_service_total = sum(
        guide_service.price_at_booking for day in package.tour_days.all() for guide_service in day.guide_services.all()
    )

    # Assuming hotel costs are stored in the package as JSON (as in your earlier design)
    hotel_total = sum(
        Decimal(cost['price']) * int(cost['room']) * int(cost['nights']) for cost in package.hotel_costs
    )
    # Combine all totals for grand total

    # Calculate grand totals
    service_grand_total = Decimal(service_total) + guide_service_total
    hotel_grand_total = Decimal(hotel_total)
    total_discount = sum(Decimal(discount['amount']) for discount in package.discounts)
    grand_total = Decimal(service_total) + guide_service_total + hotel_total


    return service_grand_total, hotel_grand_total, grand_total, total_discount

@login_required
def save_tour_package(request, package_id=None):
    data = json.loads(request.body)
    errors = {}

    # Validate package name
    if not data.get('name'):
        errors['name'] = "Package name is required."

    # Validate customer name
    if not data.get('customer_name'):
        errors['customer_name'] = "Customer name is required."

    if not data.get('tour_pack_type'):
        errors['tour_pack_type'] = "Tour package type is required."

    # Validate days
    if not data.get('days'):
        errors['days'] = "At least one day is required."
    else:
        for i, day in enumerate(data['days']):
            if not day.get('date'):
                errors[f'day{i+1}_date'] = f"Date is required for Day {i+1}."
            if not day.get('city'):
                errors[f'day{i+1}_city'] = f"City is required for Day {i+1}."
            if not day.get('hotel'):
                errors[f'day{i+1}_hotel'] = f"Hotel is required for Day {i+1}."

    if errors:
        return JsonResponse({'status': 'error', 'errors': errors}, status=400)

    # Proceed with saving the package
    try:
        with transaction.atomic():
            if package_id:
                # Update existing package
                package = get_object_or_404(TourPackageQuote, id=package_id)
                package.name = data['name']
                package.customer_name = data['customer_name']
                package.remark = data.get('remark', '')
                package.tour_pack_type_id = data['tour_pack_type']
                package.tour_days.all().delete()  # Remove existing tour days to recreate them
            else:
                # Create new package
                package = TourPackageQuote.objects.create(
                    name=data['name'],
                    customer_name=data['customer_name'],
                    remark=data.get('remark', ''),
                    tour_pack_type_id=data['tour_pack_type']
                )
                # Generate package_reference if not provided
                if not package.package_reference:
                    package.package_reference = ReferenceID.get_next_reference()
                package.save()

            # Create Tour Days
            for day_data in data['days']:
                tour_day = TourDay.objects.create(
                    tour_package=package,
                    date=day_data['date'],
                    city_id=day_data['city'],
                    hotel_id=day_data['hotel']
                )

                # Handle services
                for service_data in day_data['services']:
                    service_price = ServicePrice.objects.get(
                    service_id=service_data['name'],
                    city_id=day_data['city'],
                    tour_pack_type_id=data['tour_pack_type']
                )
                    TourDayService.objects.create(
                        tour_day=tour_day,
                        service=service_price.service,
                         price_at_booking=service_data.get('price_at_booking', service_price.price)
                    )

                # Handle guide services
                for guide_service_data in day_data['guide_services']:
                    try:
                        guide_service = GuideService.objects.get(id=guide_service_data['name'])
                        TourDayGuideService.objects.create(
                            tour_day=tour_day,
                            guide_service=guide_service,
                            price_at_booking=guide_service_data.get('price_at_booking', guide_service.price)
                        )
                    except GuideService.DoesNotExist:
                        return JsonResponse({'status': 'error', 'message': 'Guide Service not found'}, status=400)

            # Handle hotel costs
            package.hotel_costs = data.get('hotelCosts', [])

            package.discounts = data.get('discounts', [])
            # Calculate totals
            service_grand_total, hotel_grand_total, grand_total_cost, total_discount = calculate_totals(package)

            # Save grand totals
            package.service_grand_total = service_grand_total
            package.hotel_grand_total = hotel_grand_total
            total_discount = sum(Decimal(discount['amount']) for discount in package.discounts)
            package.grand_total_cost = grand_total_cost - total_discount
            package.save()

        return JsonResponse({
            'status': 'success',
            'message': 'Tour package saved successfully',
            'package_id': package.id
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def tour_package_pdf(request, pk):
    package = get_object_or_404(TourPackageQuote, pk=pk)

    # Prepare hotel costs with total calculation
    hotel_costs_with_total = []
    for cost in package.hotel_costs:
        total_cost = float(cost['room']) * float(cost['nights']) * float(cost['price'])
        cost['total'] = total_cost
        hotel_costs_with_total.append(cost)

    # Render the template to HTML
    html_string = render_to_string('tour_quote/tour_package_pdf.html', {
        'package': package,
        'hotel_costs_with_total': hotel_costs_with_total,

    })

    # Create a response object and generate PDF
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="tour_package_{package.id}.pdf"'

    # WeasyPrint to generate the PDF
    HTML(string=html_string).write_pdf(response, stylesheets=[CSS(string='''
    @page {
        size: A4;
        margin: 2cm;
        @bottom-right {
            content: "Page " counter(page) " of " counter(pages);
            font-size: 10px;
            color: #666;
        }
    }
    body {
        font-family: sans-serif;
    }
''')])


    return response

@login_required
def tour_package_list(request):
    packages = TourPackageQuote.objects.all().order_by('-created_at')
    return render(request, 'tour_quote/tour_package_list.html', {'packages': packages})

@login_required
def tour_package_detail(request, pk):
    package = get_object_or_404(TourPackageQuote, pk=pk)

    # Calculate total costs for hotels
    hotel_costs_with_total = []
    for cost in package.hotel_costs:
        total_cost = float(cost['room']) * float(cost['nights']) * float(cost['price'])
        cost['total'] = total_cost  # Add total cost to the cost dictionary
        hotel_costs_with_total.append(cost)

      # Prepare discount information

    discounts = package.discounts
    total_discount = sum(float(discount['amount']) for discount in discounts)

    context = {
        'package': package,
        'hotel_costs_with_total': hotel_costs_with_total,  # Pass hotel costs with total calculation
        'tour_pack_type': package.tour_pack_type,  # Add this line
        'discounts': discounts,
        'total_discount': total_discount,
    }

    return render(request, 'tour_quote/tour_package_detail.html', context)

@login_required
def tour_package_edit(request, pk):
    package = get_object_or_404(TourPackageQuote, pk=pk)
    cities = City.objects.all()
    guide_services = list(GuideService.objects.values('id', 'name', 'price'))
    predefined_packages = PredefinedTourQuote.objects.all()
    tour_pack_types = TourPackType.objects.all()

    if request.method == 'POST':
        return save_tour_package(request, package.id)

    package_data = {
        'id': package.id,
        'name': package.name,
        'customer_name': package.customer_name,
        'remark': package.remark,
        'tour_pack_type': package.tour_pack_type_id,
        'days': [
            {
                'date': day.date.isoformat(),
                'city': str(day.city_id),
                'hotel': str(day.hotel_id),
                'city_name': day.city.name,
                'hotel_name': day.hotel.name,
                'services': [
                    {
                        'type': service.service.service_type.name.lower(),
                        'name': str(service.service_id),
                        'service_name': service.service.name,
                        'price_at_booking': float(service.price_at_booking)
                    }
                    for service in day.services.all()
                ],
                'guideServices': [
                    {
                        'name': str(guide_service.guide_service_id),
                        'price': float(guide_service.guide_service.price),
                        'price_at_booking': float(guide_service.price_at_booking)
                    }
                    for guide_service in day.guide_services.all()
                ]
            }
            for day in package.tour_days.all()
        ],
        'discounts': [
        {
            'item': discount['item'],
            'amount': float(discount['amount'])
        }
        for discount in package.discounts
    ],
         'hotelCosts': package.hotel_costs

    }

    context = {
        'package': package,
        'cities': cities,
        'guide_services_json': json.dumps(guide_services, cls=DjangoJSONEncoder),
        'package_json': json.dumps(package_data, cls=DjangoJSONEncoder),
        'predefined_packages': predefined_packages,
        'tour_pack_types': tour_pack_types,
    }

    return render(request, 'tour_quote/tour_package_edit.html', context)

@login_required
def tour_package_quote(request):
    cities = City.objects.all()
    service_types = ServiceType.objects.all()

    predefined_quotes = PredefinedTourQuote.objects.all()
    tour_pack_types = TourPackType.objects.all()
    # Query guide services and convert price (Decimal) to float
    guide_services = list(
        GuideService.objects.values('id', 'name', 'price')
    )
    # Convert the Decimal to float
    for guide_service in guide_services:
        guide_service['price'] = float(guide_service['price'])

    context = {
        'cities': cities,
        'service_types': service_types,
        'guide_services_json': json.dumps(guide_services, cls=DjangoJSONEncoder),
        'predefined_quotes': predefined_quotes,
        'tour_pack_types': tour_pack_types,
    }

    return render(request, 'tour_quote/tour_package_quote.html', context)

@login_required
@require_http_methods(["GET"])
def get_city_services(request, city_id):
    try:
        tour_pack_type_id = request.GET.get('tour_pack_type')
        city = get_object_or_404(City, id=city_id)
        tour_pack_type = get_object_or_404(TourPackType, id=tour_pack_type_id)

        hotels = list(Hotel.objects.filter(city=city).values('id', 'name'))

        service_prices = ServicePrice.objects.filter(
            city=city,
            tour_pack_type=tour_pack_type
        ).select_related('service__service_type')

        service_types = {}
        for sp in service_prices:
            service_type = sp.service.service_type.name
            if service_type not in service_types:
                service_types[service_type] = []

            service_types[service_type].append({
                'id': sp.service.id,
                'name': sp.service.name,
                'price': float(sp.price)
            })

        guide_services = list(GuideService.objects.all().values('id', 'name', 'price'))
        for gs in guide_services:
            gs['price'] = float(gs['price'])

        response_data = {
            'hotels': hotels,
            'service_types': [
                {'type': st, 'services': services}
                for st, services in service_types.items()
            ],
            'guide_services': guide_services
        }

        print("Response data:", response_data)
        return JsonResponse(response_data, safe=False, content_type='application/json')
    except Exception as e:
        print("Error in get_city_services:", str(e))
        return JsonResponse({'error': str(e)}, status=500, content_type='application/json')


@login_required
def tour_packages(request):
    query = request.GET.get('q', '')  # Get the search query

    # Filter packages based on search query
    if query:
        packages = TourPackageQuote.objects.filter(name__icontains=query) | TourPackageQuote.objects.filter(customer_name__icontains=query) | TourPackageQuote.objects.filter(package_reference__icontains=query)
    else:
        packages = TourPackageQuote.objects.all()

    # Pagination: Show 10 packages per page

    packages = packages.order_by('-created_at')

    paginator = Paginator(packages, 10)
    page_number = request.GET.get('page')
    packages_page = paginator.get_page(page_number)

    context = {
        'packages': packages_page,
        'query': query,
    }
    return render(request, 'tour_quote/tour_packages.html', context)

@login_required
@require_http_methods(["GET"])
def get_predefined_tour_quote(request, quote_id):
    quote = get_object_or_404(PredefinedTourQuote.objects.select_related('tour_pack_type'), id=quote_id)
    days = []

    for day in quote.days.all().select_related('city', 'hotel'):
        day_data = {
            'city': day.city.id,
            'hotel': day.hotel.id,
            'services': [],
            'guideServices': []
        }

        for day_service in day.services.all().select_related('service__service_type'):
            service = day_service.service
            service_prices = ServicePrice.objects.filter(
                service=service,
                tour_pack_type=quote.tour_pack_type,
                city=day.city
            )

            price = service_prices.first().price if service_prices.exists() else None

            day_data['services'].append({
                'id': service.id,
                'name': service.name,
                'type': service.service_type.name,
                'price': float(price) if price is not None else None,
                'quantity': day_service.quantity
            })

        for guide_service in day.guide_services.all().select_related('guide_service'):
            day_data['guideServices'].append({
                'id': guide_service.guide_service.id,
                'name': guide_service.guide_service.name,
                'price': float(guide_service.guide_service.price)
            })

        days.append(day_data)

    response_data = {
        'id': quote.id,
        'name': quote.name,
        'description': quote.description,
        'tour_pack_type': quote.tour_pack_type_id,
        'days': days
    }

    print("Predefined tour quote response data:", response_data)  # Add this line for debugging

    return JsonResponse(response_data)

@login_required
@require_http_methods(["GET"])
def get_city_services(request, city_id):
    try:
        tour_pack_type_id = request.GET.get('tour_pack_type')
        city = get_object_or_404(City, id=city_id)
        tour_pack_type = get_object_or_404(TourPackType, id=tour_pack_type_id)

        hotels = list(Hotel.objects.filter(city=city).values('id', 'name'))

        service_prices = ServicePrice.objects.filter(
            city=city,
            tour_pack_type=tour_pack_type
        ).select_related('service__service_type')

        service_types = {}
        for sp in service_prices:
            service_type = sp.service.service_type.name
            if service_type not in service_types:
                service_types[service_type] = []

            service_types[service_type].append({
                'id': sp.service.id,
                'name': sp.service.name,
                'price': float(sp.price)
            })

        guide_services = list(GuideService.objects.all().values('id', 'name', 'price'))
        for gs in guide_services:
            gs['price'] = float(gs['price'])

        response_data = {
            'hotels': hotels,
            'service_types': [
                {'type': st, 'services': services}
                for st, services in service_types.items()
            ],
            'guide_services': guide_services
        }

        print("Response data:", response_data)
        return JsonResponse(response_data)
    except Exception as e:
        print("Error in get_city_services:", str(e))
        print(traceback.format_exc())
        return JsonResponse({'error': str(e)}, status=500)
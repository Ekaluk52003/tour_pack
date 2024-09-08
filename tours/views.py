# tour_quote/views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from .models import TourPackageQuote, City, Hotel, Service, GuideService, ServiceType, TourDay, TourDayService, TourDayGuideService, PredefinedPackage
import json
from django.views.decorators.http import require_http_methods
from django.urls import reverse
from django.core.serializers.json import DjangoJSONEncoder
from weasyprint import HTML, CSS
from django.template.loader import render_to_string
from decimal import Decimal

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

    grand_total = Decimal(service_total) + guide_service_total + hotel_total


    return service_grand_total, hotel_grand_total, grand_total

def save_tour_package(request, package_id=None):
    data = json.loads(request.body)

    # If package_id is provided, update the existing package
    if package_id:
        package = get_object_or_404(TourPackageQuote, id=package_id)
        package.name = data['name']
        package.customer_name = data['customer_name']
        package.remark = data.get('remark', '')  # Update remark
        package.save()
        package.tour_days.all().delete()  # Remove existing tour days to recreate them
    else:
        # Create a new package if package_id is None
        package = TourPackageQuote.objects.create(
            name=data['name'],
            customer_name=data['customer_name'],
            remark=data.get('remark', '')  # Set remark for new package
        )

    for day_data in data['days']:
        hotel_id = day_data.get('hotel')
        if not hotel_id:
            return JsonResponse({'error': 'Hotel is required for each tour day.'}, status=400)

        tour_day = TourDay.objects.create(
            tour_package=package,
            date=day_data['date'],
            city_id=day_data['city'],
            hotel_id=hotel_id
        )

        # Handle services with price_at_booking
        for service_data in day_data['services']:
            service = Service.objects.get(id=service_data['name'])
            TourDayService.objects.create(
                tour_day=tour_day,
                service=service,
                # Retain price_at_booking if provided, otherwise, store the current service price
                price_at_booking=service_data.get('price_at_booking', service.price)
            )

        # Handle guide services with price_at_booking
        for guide_service_data in day_data['guide_services']:
            guide_service = GuideService.objects.get(id=guide_service_data['name'])
            TourDayGuideService.objects.create(
                tour_day=tour_day,
                guide_service=guide_service,
                # Retain price_at_booking if provided, otherwise, store the current guide service price
                price_at_booking=guide_service_data.get('price_at_booking', guide_service.price)
            )

    # Handle hotel costs
    package.hotel_costs = data.get('hotelCosts', [])


     # Calculate totals
    service_grand_total, hotel_grand_total, grand_total_cost = calculate_totals(package)

    # Save the grand total cost
    package.service_grand_total = service_grand_total
    package.hotel_grand_total = hotel_grand_total
    package.grand_total_cost = grand_total_cost
    package.save()

    return JsonResponse({
        'status': 'success',
        'redirect_url': reverse('tour_package_detail', args=[package.id])
    })


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


def tour_package_list(request):
    packages = TourPackageQuote.objects.all().order_by('-created_at')
    return render(request, 'tour_quote/tour_package_list.html', {'packages': packages})

def tour_package_detail(request, pk):
    package = get_object_or_404(TourPackageQuote, pk=pk)

    # Calculate total costs for hotels
    hotel_costs_with_total = []
    for cost in package.hotel_costs:
        total_cost = float(cost['room']) * float(cost['nights']) * float(cost['price'])
        cost['total'] = total_cost  # Add total cost to the cost dictionary
        hotel_costs_with_total.append(cost)

    context = {
        'package': package,
        'hotel_costs_with_total': hotel_costs_with_total,  # Pass hotel costs with total calculation
    }

    return render(request, 'tour_quote/tour_package_detail.html', context)


def tour_package_edit(request, pk):
    package = get_object_or_404(TourPackageQuote, pk=pk)
    cities = City.objects.all()
    guide_services = list(GuideService.objects.values('id', 'name', 'price'))
    predefined_packages = PredefinedPackage.objects.all()

    if request.method == 'POST':
        return save_tour_package(request, package)

    package_data = {
        'id': package.id,
        'name': package.name,
        'customer_name': package.customer_name,
        'remark': package.remark,
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
                        'price': float(service.service.price),
                        'price_at_booking': float(service.price_at_booking)
                    }
                    for service in day.services.all()
                ],
                'guideServices': [
                    {
                       'name': str(guide_service.guide_service_id),
                        'price': float(guide_service.guide_service.price),  # Current price
                        'price_at_booking': float(guide_service.price_at_booking)
                    }
                    for guide_service in day.guide_services.all()
                ]
            }
            for day in package.tour_days.all()
        ],
        'hotelCosts': package.hotel_costs
    }


    context = {
        'package': package,
        'cities': cities,
        'guide_services_json': json.dumps(guide_services, cls=DjangoJSONEncoder),
        'package_json': json.dumps(package_data, cls=DjangoJSONEncoder),
        'predefined_packages': predefined_packages,

    }

    return render(request, 'tour_quote/tour_package_edit.html', context)

def tour_package_quote(request):
    cities = City.objects.all()
    service_types = ServiceType.objects.all()
    predefined_packages = PredefinedPackage.objects.all()
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
        'predefined_packages': predefined_packages,
    }

    return render(request, 'tour_quote/tour_package_quote.html', context)

@require_http_methods(["GET"])
def get_city_services(request, city_id):
    hotels = Hotel.objects.filter(city_id=city_id).values('id', 'name')
    services = Service.objects.filter(city_id=city_id).select_related('service_type')

    service_types = {}
    for service in services:
        if service.service_type.name not in service_types:
            service_types[service.service_type.name] = []
        service_types[service.service_type.name].append({
            'id': service.id,
            'name': service.name,
             'price': service.price
        })

    return JsonResponse({
        'hotels': list(hotels),
        'service_types': [
            {'type': st, 'services': services}
            for st, services in service_types.items()
        ]
    })



from django.core.paginator import Paginator
from django.shortcuts import render
from .models import TourPackageQuote

def tour_packages(request):
    query = request.GET.get('q', '')  # Get the search query

    # Filter packages based on search query
    if query:
        packages = TourPackageQuote.objects.filter(name__icontains=query) | TourPackageQuote.objects.filter(customer_name__icontains=query)
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


def get_predefined_package(request, package_id):
    package = PredefinedPackage.objects.get(id=package_id)
    days = [
        {
            'city': day.city.id,
            'hotel': day.hotel.id,
            'services': [{'name': service.id, 'price': service.price} for service in day.services.all()],
            'guideServices': [{'name': guide_service.id, 'price': guide_service.price} for guide_service in day.guide_services.all()]
        }
        for day in package.days.all()
    ]
    return JsonResponse({'days': days})
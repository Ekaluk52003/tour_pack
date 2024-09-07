# tour_quote/views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from .models import TourPackageQuote, City, Hotel, Service, GuideService, ServiceType, TourDay, TourDayService, TourDayGuideService
import json
from django.views.decorators.http import require_http_methods
from django.urls import reverse
from django.core.serializers.json import DjangoJSONEncoder


def tour_package_list(request):
    packages = TourPackageQuote.objects.all().order_by('-created_at')
    return render(request, 'tour_quote/tour_package_list.html', {'packages': packages})

def tour_package_detail(request, pk):
    package = get_object_or_404(TourPackageQuote, pk=pk)
    return render(request, 'tour_quote/tour_package_detail.html', {'package': package})

def tour_package_edit(request, pk):
    package = get_object_or_404(TourPackageQuote, pk=pk)
    cities = City.objects.all()
    guide_services = list(GuideService.objects.values('id', 'name', 'price'))  # Include price

    if request.method == 'POST':
        return save_tour_package(request, package)

    package_data = {
        'id': package.id,
        'name': package.name,
        'customer_name': package.customer_name,
        'days': [
            {
                'date': day.date.isoformat(),
                'city': day.city_id,
                'hotel': day.hotel_id,
                'services': [
                    {'type': service.service.service_type.name.lower(), 'name': service.service_id, 'price': service.service.price}  # Add price
                    for service in day.services.all()
                ],
                'guideServices': [
                    {'name': guide_service.guide_service_id, 'price': guide_service.guide_service.price}  # Add price
                    for guide_service in day.guide_services.all()
                ]
            }
            for day in package.tour_days.all()
        ]
    }

    context = {
        'package': package,
        'cities': cities,
        'guide_services_json': json.dumps(guide_services, cls=DjangoJSONEncoder),
        'package_json': json.dumps(package_data, cls=DjangoJSONEncoder),
    }

    return render(request, 'tour_quote/tour_package_edit.html', context)



def tour_package_quote(request):
    cities = City.objects.all()
    service_types = ServiceType.objects.all()

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



def save_tour_package(request, package=None):
    data = json.loads(request.body)

    if package:
        # Update existing package
        package.name = data['name']
        package.customer_name = data['customer_name']
        package.save()
        package.tour_days.all().delete()  # Remove existing days
    else:
        # Create new package
        package = TourPackageQuote.objects.create(
            name=data['name'],
            customer_name=data['customer_name']
        )

    for day_data in data['days']:
        tour_day = TourDay.objects.create(
            tour_package=package,
            date=day_data['date'],
            city_id=day_data['city'],
            hotel_id=day_data['hotel']
        )

        for service_data in day_data['services']:
            TourDayService.objects.create(
                tour_day=tour_day,
                service_id=service_data['name']
            )

        for guide_service_id in day_data['guide_services']:
            TourDayGuideService.objects.create(
                tour_day=tour_day,
                guide_service_id=guide_service_id
            )

    # Handle the total cost
    total_cost = data.get('total_cost', 0)

    # If you have a field in the TourPackageQuote model for the total cost, save it:
    package.total_service_cost = total_cost  # Assuming you added this field in your model
    package.save()

    return JsonResponse({
        'status': 'success',
        'redirect_url': reverse('tour_package_detail', args=[package.id])
    })

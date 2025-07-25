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
from decimal import Decimal, InvalidOperation
import json
import logging
from django.conf import settings
from django.core.mail import EmailMessage
from io import BytesIO
from django.contrib import messages
import os
import base64
from datetime import datetime
import uuid
import csv
import io

logger = logging.getLogger(__name__)


def safe_decimal(value, default=Decimal('0')):
    if isinstance(value, (list, tuple)):
        return default  # Return default if value is a sequence
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        logger.warning(
            f"Failed to convert {value} to Decimal. Using default value {default}")
        return default


def calculate_totals(package):
    service_total = sum(
        service.price_at_booking for day in package.tour_days.all() for service in day.services.all()
    )

    guide_service_total = sum(
        guide_service.price_at_booking for day in package.tour_days.all() for guide_service in day.guide_services.all()
    )

    hotel_total = sum(
        (Decimal(cost['price']) * int(cost['room']) * int(cost['nights'])) +
        (Decimal(cost.get('extraBedPrice', 0)) * int(cost['nights']))
        for cost in package.hotel_costs
    )

    service_grand_total = Decimal(service_total) + guide_service_total
    hotel_grand_total = Decimal(hotel_total)
    total_discount = sum(Decimal(discount['amount'])
                         for discount in package.discounts)
    total_extra_cost = sum(Decimal(extra_cost['amount']) for extra_cost in package.extra_costs)
    grand_total = Decimal(service_total) + guide_service_total + hotel_total + total_extra_cost - total_discount

    return service_grand_total, hotel_grand_total, grand_total, total_discount, total_extra_cost


@login_required
@require_http_methods(["POST"])
def save_tour_package(request, package_reference=None):
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            # Determine if it's a new package or an update
            if package_reference:
                package = get_object_or_404(TourPackageQuote, package_reference=package_reference)
                is_new = False
            else:
                if request.user.is_superuser:
                    package = TourPackageQuote()
                    is_new = True
                else:
                    return JsonResponse({'status': 'error', 'message': 'You do not have permission to create new packages'}, status=403)

            if request.user.is_superuser:
                # Superusers can edit everything, and new packages can be created with all fields
                package.name = data['name']
                package.customer_name = data['customer_name']
                package.remark = data.get('remark', '')
                package.remark2 = data.get('remark2', '')
                package.tour_pack_type_id = data['tour_pack_type']
                package.commission_rate_hotel = data.get(
                    'commission_rate_hotel', 0)
                package.commission_rate_services = data.get(
                    'commission_rate_services', 0)


            # Both superusers and non-superusers can edit hotel costs
            package.hotel_costs = data['hotelCosts']
            package.remark_of_hotels = data.get('remark_of_hotels', '')
            package.discounts = data.get('discounts', [])
            package.extra_costs = data.get('extraCosts', [])

            # Save the package to get a primary key
            package.save()

            if request.user.is_superuser or is_new:
                # Clear existing days and services if it's an update
                if not is_new:
                    package.tour_days.all().delete()

                # Create new days and services
                for day_data in data['days']:
                    tour_day = TourDay.objects.create(
                        tour_package=package,
                        date=day_data['date'],
                        city_id=day_data['city'],
                        hotel_id=day_data['hotel']
                    )

                    # Create services for the day
                    for service_data in day_data['services']:
                        service = Service.objects.get(id=service_data['name'])
                        TourDayService.objects.create(
                            tour_day=tour_day,
                            service=service,
                            price_at_booking=service_data['price_at_booking']
                        )

                    # Create guide services for the day
                    for guide_service_data in day_data['guide_services']:
                        guide_service = GuideService.objects.get(id=guide_service_data['name'])
                        TourDayGuideService.objects.create(
                            tour_day=tour_day,
                            guide_service=guide_service,
                            price_at_booking=guide_service_data['price_at_booking']
                        )

            # Recalculate totals
            service_grand_total, hotel_grand_total, grand_total, total_discount, total_extra_cost = calculate_totals(package)

            package.service_grand_total = service_grand_total
            package.hotel_grand_total = hotel_grand_total
            package.grand_total_cost = grand_total

            # Recalculate commission amounts
            total_room_nights = sum(
                safe_decimal(hotel.get('room')) *
                safe_decimal(hotel.get('nights'))
                for hotel in package.hotel_costs
            )

            package.commission_rate_hotel = safe_decimal(
                package.commission_rate_hotel)
            package.commission_rate_services = safe_decimal(
                package.commission_rate_services)

            package.commission_amount_hotel = package.commission_rate_hotel * total_room_nights
            package.commission_amount_services = package.commission_rate_services * \
                package.service_grand_total / Decimal('100')

            package.save()  # Save the package with all updates

        return JsonResponse({
            'status': 'success',
            'message': 'Tour package saved successfully',
            'package_reference': package.package_reference
        })


    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data provided'}, status=400)
    except TourPackageQuote.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Tour package not found'}, status=404)
    except PermissionError:
        return JsonResponse({'status': 'error', 'message': 'You do not have permission to perform this action'}, status=403)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'An unexpected error occurred: {str(e)}'}, status=500)


@login_required
def tour_package_pdf(request, pk):
    package = get_object_or_404(TourPackageQuote, pk=pk)

    # Define the image path based on your project structure
    logo_data_uri = None

    # Try multiple possible paths for Docker environment
    possible_paths = [
      os.path.join(settings.BASE_DIR, 'static', 'image', 'rsz_animo1.png')        # Add more paths if needed
    ]

    # Try to find and load the image
    for logo_path in possible_paths:

        if os.path.exists(logo_path):
            try:
                with open(logo_path, 'rb') as f:
                    logo_binary = f.read()
                    logo_base64 = base64.b64encode(logo_binary).decode('utf-8')
                    logo_data_uri = f'data:image/png;base64,{logo_base64}'
                    break
            except Exception as e:
                print(f"Error reading file at {logo_path}: {str(e)}")  # Debug print

    if not logo_data_uri:
        print("Could not find or load the logo image")  # Debug print

    # Your existing code for hotel costs calculations...
    hotel_costs_with_total = []
    for cost in package.hotel_costs:
        room_cost = float(cost['room']) * \
            float(cost['nights']) * float(cost['price'])
        extra_bed_price = cost.get('extraBedPrice', '')
        extra_bed_cost = float(extra_bed_price) * float(
            cost['nights']) if extra_bed_price and extra_bed_price.strip() else 0
        total_cost = room_cost + extra_bed_cost

        cost_with_total = cost.copy()
        cost_with_total['room_cost'] = room_cost
        cost_with_total['extra_bed_cost'] = extra_bed_cost
        cost_with_total['total'] = total_cost

        hotel_costs_with_total.append(cost_with_total)

    discounts = package.discounts
    total_discount = sum(float(discount['amount']) for discount in discounts)

    extra_costs = package.extra_costs
    total_extra_cost = sum(float(extra_cost['amount']) for extra_cost in extra_costs)

    remark2 = package.remark2.replace(
        '\n', '<br>') if package.remark2 is not None else ''

    remark_of_hotels = package.remark_of_hotels.replace(
        '\n', '<br>') if package.remark_of_hotels is not None else ''

    ordered_tour_days = package.tour_days.all().order_by('date')

    html_string = render_to_string('tour_quote/tour_package_pdf.html', {
        'package': package,
        'ordered_tour_days': ordered_tour_days,
        'tour_pack_type': package.tour_pack_type,
        'hotel_costs_with_total': hotel_costs_with_total,
        'base_url': request.build_absolute_uri('/'),
        'discounts': discounts,
        'total_discount': total_discount,
        'extra_costs': extra_costs,
        'total_extra_cost': total_extra_cost,
        'static_url': settings.STATIC_URL,
        'remark2': remark2,
        'remark_of_hotels': remark_of_hotels,
        'logo_data_uri': logo_data_uri
    })

    # Create response and set filename
    response = HttpResponse(content_type='application/pdf')
    package_name = package.name if package.name else 'unknown'
    reference = package.package_reference if package.package_reference else str(package.id)
    package_name = ''.join(e for e in package_name if e.isalnum() or e in ['-', '_','(', ')']).strip()
    reference = ''.join(e for e in reference if e.isalnum() or e in ['-', '_']).strip()
    filename = f"{package_name}_{reference}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'

    # Generate PDF with custom styles
    HTML(
        string=html_string,
        base_url=request.build_absolute_uri()
    ).write_pdf(
        response,
        stylesheets=[CSS(string='''
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
        ''')]
    )

    return response


@login_required
def tour_package_pdf_no_cost(request, pk):
    package = get_object_or_404(TourPackageQuote, pk=pk)

    # Define the image path based on your project structure
    logo_data_uri = None

    # Try multiple possible paths for Docker environment
    possible_paths = [
      os.path.join(settings.BASE_DIR, 'static', 'image', 'rsz_animo1.png')        # Add more paths if needed
    ]

    # Try to find and load the image
    for logo_path in possible_paths:
        if os.path.exists(logo_path):
            try:
                with open(logo_path, 'rb') as f:
                    logo_binary = f.read()
                    logo_base64 = base64.b64encode(logo_binary).decode('utf-8')
                    logo_data_uri = f'data:image/png;base64,{logo_base64}'
                    break
            except Exception as e:
                print(f"Error reading file at {logo_path}: {str(e)}")  # Debug print

    if not logo_data_uri:
        print("Could not find or load the logo image")  # Debug print

    # We still need the hotel costs structure but without prices for the template
    hotel_costs_with_total = []
    for cost in package.hotel_costs:
        cost_with_total = cost.copy()
        # Keep structure but zero out costs
        cost_with_total['room_cost'] = 0
        cost_with_total['extra_bed_cost'] = 0
        cost_with_total['total'] = 0
        hotel_costs_with_total.append(cost_with_total)

    # We keep the structure but zero out all costs
    discounts = package.discounts
    extra_costs = package.extra_costs
    
    remark2 = package.remark2.replace(
        '\n', '<br>') if package.remark2 is not None else ''
    remark_of_hotels = package.remark_of_hotels.replace(
        '\n', '<br>') if package.remark_of_hotels is not None else ''
    
    ordered_tour_days = package.tour_days.all().order_by('date')
    
    html_string = render_to_string('tour_quote/tour_package_pdf_no_cost.html', {
        'package': package,
        'ordered_tour_days': ordered_tour_days,
        'tour_pack_type': package.tour_pack_type,
        'hotel_costs_with_total': hotel_costs_with_total,
        'base_url': request.build_absolute_uri('/'),
        'discounts': discounts,
        'extra_costs': extra_costs,
        'static_url': settings.STATIC_URL,
        'remark2': remark2,
        'remark_of_hotels': remark_of_hotels,
        'logo_data_uri': logo_data_uri,
        'hide_costs': True  # Flag to hide costs in template
    })
    
    # Create response and set filename
    response = HttpResponse(content_type='application/pdf')
    package_name = package.name if package.name else 'unknown'
    reference = package.package_reference if package.package_reference else str(package.id)
    package_name = ''.join(e for e in package_name if e.isalnum() or e in ['-', '_','(', ')']).strip()
    reference = ''.join(e for e in reference if e.isalnum() or e in ['-', '_']).strip()
    filename = f"{package_name}_{reference}_no_cost.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    
    # Generate PDF with custom styles
    HTML(
        string=html_string,
        base_url=request.build_absolute_uri()
    ).write_pdf(
        response,
        stylesheets=[CSS(string='''
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
        ''')]
    )
    
    return response


@login_required
@require_http_methods(["POST"])
def send_tour_package_email(request, pk):
    try:
        package = get_object_or_404(TourPackageQuote, pk=pk)

        # Define the image path based on your project structure
        logo_data_uri = None
        # Try multiple possible paths for Docker environment
        possible_paths = [
        os.path.join(settings.BASE_DIR, 'static', 'image', 'rsz_animo1.png')         ]

        # Try to find and load the image
        for logo_path in possible_paths:
            if os.path.exists(logo_path):
                try:
                    with open(logo_path, 'rb') as f:
                        logo_binary = f.read()
                        logo_base64 = base64.b64encode(logo_binary).decode('utf-8')
                        logo_data_uri = f'data:image/png;base64,{logo_base64}'
                        break
                except Exception as e:
                    print(f"Error reading file at {logo_path}: {str(e)}")  # Debug print

        if not logo_data_uri:
            print("Could not find or load the logo image")  # Debug print
        cc_email = request.POST.get('cc_email')


        # Calculate totals (replicating logic from tour_package_pdf)
        hotel_costs_with_total = []
        for cost in package.hotel_costs:
            room_cost = float(cost['room']) * \
                float(cost['nights']) * float(cost['price'])
            extra_bed_price = cost.get('extraBedPrice', '')
            extra_bed_cost = float(extra_bed_price) * float(
                cost['nights']) if extra_bed_price and extra_bed_price.strip() else 0
            total_cost = room_cost + extra_bed_cost

            cost_with_total = cost.copy()
            cost_with_total['room_cost'] = room_cost
            cost_with_total['extra_bed_cost'] = extra_bed_cost
            cost_with_total['total'] = total_cost

            hotel_costs_with_total.append(cost_with_total)

        discounts = package.discounts
        total_discount = sum(float(discount['amount'])
                             for discount in discounts)

        extra_costs = package.extra_costs
        total_extra_cost = sum(float(extra_cost['amount']) for extra_cost in extra_costs)

        remark2 = package.remark2.replace(
        '\n', '<br>') if package.remark2 is not None else ''

        remark_of_hotels = package.remark_of_hotels.replace(
        '\n', '<br>') if package.remark_of_hotels is not None else ''

        # Get ordered tour days
        ordered_tour_days = package.tour_days.all().order_by('date')
        # Render the template to HTML
        html_string = render_to_string('tour_quote/tour_package_pdf.html', {
            'package': package,
            'ordered_tour_days': ordered_tour_days,
            'tour_pack_type': package.tour_pack_type,
            'hotel_costs_with_total': hotel_costs_with_total,
            'base_url': request.build_absolute_uri('/'),
            'discounts': discounts,
            'total_discount': total_discount,
            'extra_costs': extra_costs,
            'total_extra_cost': total_extra_cost,
            'static_url': settings.STATIC_URL,
            'remark2': remark2,
            'remark_of_hotels':remark_of_hotels,
            'logo_data_uri': logo_data_uri
        })

        # Generate PDF
        pdf_file = BytesIO()
        HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(pdf_file, stylesheets=[CSS(string='''
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
        pdf_file.seek(0)


          # Generate filename
        package_name = package.name if package.name else 'unknown'
        reference = package.package_reference if package.package_reference else str(package.id)

        # Clean the filename components
        package_name = ''.join(e for e in package_name if e.isalnum() or e in ['-', '_','(', ')']).strip()
        reference = ''.join(e for e in reference if e.isalnum() or e in ['-', '_']).strip()

        filename = f"{package_name}_{reference}.pdf"

        # Prepare email
        subject = f'Tour Package {package.package_reference}: {package.name}'
        message = f'Please find attached the tour package quote for {package.customer_name}.'
        from_email = settings.DEFAULT_FROM_EMAIL
        # You might want to change this to use the customer's email
        to_email = ['jimforanimo@gmail.com']
        if cc_email:
            to_email.append(cc_email)

        # Send email
        email = EmailMessage(subject, message, from_email, to_email)
        email.attach(filename, pdf_file.getvalue(), 'application/pdf')

        email.send(fail_silently=False)

        context = {
            'message': f'Email sent successfully to {", ".join(to_email)}',
            'class': 'text-green-600'
        }
        return render(request, 'tour_quote/notification.html', context)
    except Exception as e:
        logger.error(f"Error in send_tour_package_email: {str(e)}")
        context = {
            'message': f'Failed to send email: {str(e)}',
            'class': 'text-red-600'
        }
        return render(request, 'tour_quote/notification.html', context)




@login_required
def tour_package_detail(request, package_reference):
    package = get_object_or_404(TourPackageQuote, package_reference=package_reference)

    # Calculate total costs for hotels
    hotel_costs_with_total = []
    for cost in package.hotel_costs:
        room_cost = float(cost['room']) * \
            float(cost['nights']) * float(cost['price'])

        extra_bed_price = cost.get('extraBedPrice', '')
        extra_bed_cost = float(extra_bed_price) * float(
            cost['nights']) if extra_bed_price and extra_bed_price.strip() else 0

        total_cost = room_cost + extra_bed_cost

        cost_with_total = cost.copy()  # Create a copy to avoid modifying the original
        cost_with_total['room_cost'] = room_cost
        cost_with_total['extra_bed_cost'] = extra_bed_cost
        cost_with_total['total'] = total_cost

        hotel_costs_with_total.append(cost_with_total)

      # Prepare discount information

    discounts = package.discounts
    total_discount = sum(float(discount['amount']) for discount in discounts)

    # Prepare extra costs information
    extra_costs = package.extra_costs
    total_extra_cost = sum(float(extra_cost['amount']) for extra_cost in extra_costs)
    ordered_tour_days = package.tour_days.all().order_by('date')
    remark2 = package.remark2.replace(
        '\n', '<br>') if package.remark2 is not None else ''
    # remark2 = package.remark2.replace('\n', '<br>')

    comission_total = package.commission_amount_hotel + package.commission_amount_services
    context = {
        'package': package,
        # Pass hotel costs with total calculation
        'hotel_costs_with_total': hotel_costs_with_total,
        'tour_pack_type': package.tour_pack_type,  # Add this line
        'discounts': discounts,
        'total_discount': total_discount,
        'extra_costs': extra_costs,
        'total_extra_cost': total_extra_cost,
        'remark2': remark2,
        'comission_total': comission_total,
        'ordered_tour_days': ordered_tour_days
    }

    return render(request, 'tour_quote/tour_package_detail.html', context)


@login_required
def tour_package_edit(request, package_reference):
    package = get_object_or_404(TourPackageQuote, package_reference=package_reference)
    cities = City.objects.all()
    guide_services = list(GuideService.objects.values('id', 'name', 'price'))
    predefined_quotes = PredefinedTourQuote.objects.all()
    tour_pack_types = TourPackType.objects.all()

    if request.method == 'POST':
        return save_tour_package(request, package.id)

    package_data = {
        'package_reference': package.package_reference,
        'name': package.name,
        'customer_name': package.customer_name,
        'remark': package.remark,
        'remark2': package.remark2,
        'remark_of_hotels': package.remark_of_hotels,
        'tour_pack_type': package.tour_pack_type_id,
        # Add hotel commission rate
        'commission_rate_hotel': float(package.commission_rate_hotel),
        'commission_rate_services': float(package.commission_rate_services),
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
            for day in package.tour_days.all().order_by('date')
        ],
        'discounts': [
            {
                'item': discount['item'],
                'amount': float(discount['amount'])
            }
            for discount in package.discounts
        ],

          'extraCosts': [
            {
                'item': extra_cost['item'],
                'amount': float(extra_cost['amount'])
            }
            for extra_cost in package.extra_costs
        ],
        'hotelCosts': package.hotel_costs

    }

    context = {
        'package': package,
        'cities': cities,
        'guide_services_json': json.dumps(guide_services, cls=DjangoJSONEncoder),
        'package_json': json.dumps(package_data, cls=DjangoJSONEncoder),
        'predefined_quotes': predefined_quotes,
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

    print("Guide Services:", guide_services)

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

        services = Service.objects.filter(
            cities=city
        ).prefetch_related('prices').select_related('service_type')

        service_types = {}
        for service in services:
            service_type = service.service_type.name
            if service_type not in service_types:
                service_types[service_type] = []

            price = service.prices.filter(tour_pack_type=tour_pack_type).first()
            if price:
                service_types[service_type].append({
                    'id': service.id,
                    'name': service.name,
                    'price': float(price.price)
                })

        guide_services = list(
            GuideService.objects.all().values('id', 'name', 'price'))
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

        return JsonResponse(response_data, safe=False, content_type='application/json')
    except Exception as e:
        print("Error in get_city_services:", str(e))
        return JsonResponse({'error': str(e)}, status=500, content_type='application/json')


@login_required
def tour_packages(request):
    query = request.GET.get('q', '')  # Get the search query

    # Filter packages based on search query
    if query:
        packages = TourPackageQuote.objects.filter(name__icontains=query) | TourPackageQuote.objects.filter(
            customer_name__icontains=query) | TourPackageQuote.objects.filter(package_reference__icontains=query)
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
    try:
        quote = get_object_or_404(PredefinedTourQuote.objects, id=quote_id)
        tour_pack_type_id = request.GET.get('tour_pack_type')

        if not tour_pack_type_id:
            return JsonResponse({'error': 'Tour package type is required'}, status=400)

        tour_pack_type = get_object_or_404(TourPackType, id=tour_pack_type_id)
        days = []

        for day in quote.days.all().select_related('city', 'hotel'):
            day_data = {
                'city': day.city.id,
                'hotel': day.hotel.id,
                'services': [],
                'guideServices': []
            }

            # Get services for the day
            for day_service in day.services.all().select_related('service__service_type'):
                service = day_service.service

                # Check if this service is available in this city
                if service.cities.filter(id=day.city.id).exists():
                    # Get price for the selected tour pack type
                    try:
                        price = ServicePrice.objects.get(
                            service=service,
                            tour_pack_type=tour_pack_type
                        ).price
                    except ServicePrice.DoesNotExist:
                        price = None

                    if price is not None:
                        day_data['services'].append({
                            'id': service.id,
                            'name': service.name,
                            'type': service.service_type.name,
                            'price': float(price),
                            'quantity': day_service.quantity,
                            'order': day_service.order
                        })

            # Get guide services
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
            'days': days
        }

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error in get_predefined_tour_quote: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)




@login_required
@require_http_methods(["GET"])
def duplicate_tour_package(request, package_reference):
    # Check if the user is a superuser
    if not request.user.is_superuser:
        messages.error(request, "You do not have permission to duplicate tour packages.")
        return redirect('tour_package_detail', package_reference=package_reference)

    # Get the original package
    original_package = get_object_or_404(TourPackageQuote, package_reference=package_reference)

    # Create a new package with copied data
    new_package = TourPackageQuote.objects.create(
        name=f"{original_package.name}_(copy)",
        customer_name=original_package.customer_name,
        remark=original_package.remark,
        remark2=original_package.remark2,
        remark_of_hotels=original_package.remark_of_hotels,
        tour_pack_type=original_package.tour_pack_type,
        commission_rate_hotel=original_package.commission_rate_hotel,
        commission_rate_services=original_package.commission_rate_services,
        hotel_costs=original_package.hotel_costs,
        discounts=original_package.discounts,
        extra_costs=original_package.extra_costs
    )

    # Copy tour days and their associated services
    for original_day in original_package.tour_days.all():
        new_day = TourDay.objects.create(
            tour_package=new_package,
            date=original_day.date,
            city=original_day.city,
            hotel=original_day.hotel
        )

        # Copy services
        for original_service in original_day.services.all():
            TourDayService.objects.create(
                tour_day=new_day,
                service=original_service.service,
                price_at_booking=original_service.price_at_booking
            )

        # Copy guide services
        for original_guide_service in original_day.guide_services.all():
            TourDayGuideService.objects.create(
                tour_day=new_day,
                guide_service=original_guide_service.guide_service,
                price_at_booking=original_guide_service.price_at_booking
            )

    # Recalculate totals for the new package
    service_grand_total, hotel_grand_total, grand_total, total_discount, total_extra_cost = calculate_totals(new_package)

    new_package.service_grand_total = service_grand_total
    new_package.hotel_grand_total = hotel_grand_total
    new_package.grand_total_cost = grand_total

    # Recalculate commission amounts
    total_room_nights = sum(
        safe_decimal(hotel.get('room')) * safe_decimal(hotel.get('nights'))
        for hotel in new_package.hotel_costs
    )

    new_package.commission_amount_hotel = new_package.commission_rate_hotel * total_room_nights
    new_package.commission_amount_services = new_package.commission_rate_services * new_package.service_grand_total / Decimal('100')

    new_package.save()

    messages.success(request, f"Tour package '{new_package.name}' has been created as a copy.")
    return redirect('tour_package_edit', package_reference=new_package.package_reference)


@login_required
def service_price_form(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            with transaction.atomic():
                # Get or create service type
                service_type, _ = ServiceType.objects.get_or_create(
                    name=data['service_type']
                )

                # Create service
                service = Service.objects.create(
                    name=data['name'],
                    service_type=service_type
                )

                # Add cities
                for city_id in data['cities']:
                    city = City.objects.get(id=city_id)
                    service.cities.add(city)

                # Create prices
                for price_data in data['prices']:
                    ServicePrice.objects.create(
                        service=service,
                        tour_pack_type_id=price_data['tour_pack_type'],
                        price=price_data['price']
                    )

            return JsonResponse({'status': 'success', 'message': 'Service created successfully'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    # GET request - render form
    cities = City.objects.all()
    tour_pack_types = TourPackType.objects.all()
    service_types = ServiceType.objects.all()

    context = {
        'cities': cities,
        'tour_pack_types': tour_pack_types,
        'service_types': service_types,
    }
    return render(request, 'tour_quote/service_price_form.html', context)

@login_required
def service_price_edit(request):
    """
    View for editing service prices.
    """
    services = Service.objects.all().select_related('service_type')
    tour_pack_types = TourPackType.objects.all()
    
    # Convert services to JSON for safe handling of special characters
    services_list = [{
        'id': service.id,
        'name': service.name,
        'service_type': service.service_type.name if service.service_type else ''
    } for service in services]
    services_json = json.dumps(services_list)
    
    context = {
        'services': services,
        'tour_pack_types': tour_pack_types,
        'services_json': services_json,
    }
    return render(request, 'tour_quote/service_price_edit.html', context)

@login_required
@require_http_methods(['GET'])
def get_service_prices(request, service_id):
    """
    API endpoint to get prices for a specific service.
    Returns empty string for blank prices, but actual 0 for zero prices.
    """
    try:
        service = Service.objects.get(id=service_id)
        prices = ServicePrice.objects.filter(service=service).select_related('tour_pack_type')

        return JsonResponse({
            'service': {
                'id': service.id,
                'name': service.name,
                'service_type': service.service_type.name,
            },
            'prices': [{
                'id': price.id,
                'tour_pack_type_id': price.tour_pack_type.id,
                'tour_pack_type_name': price.tour_pack_type.name,
                'price': str(price.price) if price.price is not None else ''  # Keep 0 as "0", blank as ""
            } for price in prices]
        })
    except Service.DoesNotExist:
        return JsonResponse({'error': 'Service not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_http_methods(['POST'])
def save_service_prices(request):
    """
    API endpoint to save service prices.
    - Accepts 0 as a valid price
    - Skips creation/removes existing prices for blank inputs
    """
    try:
        data = json.loads(request.body)
        service_id = data['service_id']
        prices = data['prices']
        service = Service.objects.get(id=service_id)

        with transaction.atomic():
            processed_price_ids = []

            for price_data in prices:
                tour_pack_type_id = price_data['tour_pack_type_id']
                price_id = price_data.get('price_id')
                price_input = price_data['price']

                # Handle blank input case
                if price_input == '' or price_input is None:
                    # If there's an existing price record, delete it
                    if price_id:
                        ServicePrice.objects.filter(id=price_id).delete()
                    continue

                # Convert price to Decimal
                try:
                    price_value = Decimal(str(price_input))
                except (ValueError, TypeError, InvalidOperation):
                    continue

                # Handle existing price record
                if price_id:
                    try:
                        price_obj = ServicePrice.objects.get(id=price_id)
                        price_obj.price = price_value
                        price_obj.save()
                        processed_price_ids.append(price_obj.id)
                    except ServicePrice.DoesNotExist:
                        # If price record doesn't exist anymore, create new if not blank
                        price_obj = ServicePrice.objects.create(
                            service=service,
                            tour_pack_type_id=tour_pack_type_id,
                            price=price_value
                        )
                        processed_price_ids.append(price_obj.id)
                else:
                    # Create new price record
                    price_obj = ServicePrice.objects.create(
                        service=service,
                        tour_pack_type_id=tour_pack_type_id,
                        price=price_value
                    )
                    processed_price_ids.append(price_obj.id)

            # Delete any price records that weren't processed
            ServicePrice.objects.filter(
                service=service
            ).exclude(
                id__in=processed_price_ids
            ).delete()

            # Get updated prices for response
            updated_prices = ServicePrice.objects.filter(
                service=service
            ).select_related('tour_pack_type')

            return JsonResponse({
                'status': 'success',
                'message': 'Prices updated successfully',
                'prices': [{
                    'id': price.id,
                    'tour_pack_type_id': price.tour_pack_type.id,
                    'tour_pack_type_name': price.tour_pack_type.name,
                    'price': str(price.price) if price.price is not None else ''
                } for price in updated_prices]
            })

    except Service.DoesNotExist:
        return JsonResponse({'error': 'Service not found'}, status=404)
    except Exception as e:
        print(f"Error in save_service_prices: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def service_list(request):
    """
    View to list all services with their prices.
    """
    services = Service.objects.all().select_related('service_type').prefetch_related('prices__tour_pack_type')
    context = {
        'services': services
    }
    return render(request, 'tour_quote/service_list.html', context)

@login_required
def export_tour_package_json(request, pk):
    """
    Exports a single TourPackageQuote and all its related data into a JSON file.
    This view manually constructs a dictionary to ensure all related data (days, hotels, costs)
    is included in a clean, nested format.
    """
    # Retrieve the specific tour package or return a 404 error if not found
    tour_package = get_object_or_404(TourPackageQuote, pk=pk)

    # Manually build the dictionary with all the required data
    package_data = {
        "id": tour_package.id,
        "name": tour_package.name,
        "customer_name": tour_package.customer_name,
        "created_at": tour_package.created_at.isoformat(),
        "package_reference": tour_package.package_reference,
        "grand_total_cost": str(tour_package.grand_total_cost),  # Use string to avoid float precision issues
        "service_grand_total": str(tour_package.service_grand_total),
        "hotel_grand_total": str(tour_package.hotel_grand_total),
        "remark": tour_package.remark,
        "remark2": tour_package.remark2,
        "remark_of_hotels": tour_package.remark_of_hotels,
        "tour_pack_type": tour_package.tour_pack_type.name if tour_package.tour_pack_type else None,
        "hotel_costs": tour_package.hotel_costs,
        "discounts": tour_package.discounts,
        "extra_costs": tour_package.extra_costs,
        "commission_info": {
            "hotel_rate": str(tour_package.commission_rate_hotel),
            "hotel_amount": str(tour_package.commission_amount_hotel),
            "services_rate": str(tour_package.commission_rate_services),
            "services_amount": str(tour_package.commission_amount_services),
            "total": str(tour_package.commission_amount_hotel + tour_package.commission_amount_services)
        },
        "tour_days": []
    }

    # Add related tour days to the dictionary
    for day in tour_package.tour_days.all():
        day_data = {
            "date": day.date.isoformat(),
            "city": day.city.name,
            "hotel": day.hotel.name,
            "services": [],
            "guide_services": []
        }
        
        # Add services for this day
        for service in day.services.all():
            day_data["services"].append({
                "name": service.service.name,
                "service_type": service.service.service_type.name,
                "price_at_booking": str(service.price_at_booking)
            })
            
        # Add guide services for this day
        for guide_service in day.guide_services.all():
            day_data["guide_services"].append({
                "name": guide_service.guide_service.name,
                "price_at_booking": str(guide_service.price_at_booking)
            })
            
        package_data["tour_days"].append(day_data)

    # Create a JSON response. The `Content-Disposition` header tells the
    # browser to treat the response as a file download.
    response = JsonResponse(package_data, json_dumps_params={'indent': 2})
    response['Content-Disposition'] = f'attachment; filename="tour_package_{tour_package.pk}.json"'

    return response

@login_required
def import_tour_package_json(request):
    """
    Import a tour package from a JSON file and create a new TourPackageQuote.
    """
    if request.method == 'POST' and request.FILES.get('json_file'):
        try:
            # Read the uploaded JSON file
            json_file = request.FILES['json_file']
            json_data = json.loads(json_file.read().decode('utf-8'))
            
            # Extract basic package information
            with transaction.atomic():
                # Create the tour package
                tour_package = TourPackageQuote(
                    name=json_data.get('name', 'Imported Package'),
                    customer_name=json_data.get('customer_name', 'Imported Customer'),
                    remark=json_data.get('remark'),
                    remark2=json_data.get('remark2'),
                    remark_of_hotels=json_data.get('remark_of_hotels'),
                    hotel_costs=json_data.get('hotel_costs', []),
                    discounts=json_data.get('discounts', []),
                    extra_costs=json_data.get('extra_costs', []),
                    grand_total_cost=Decimal(json_data.get('grand_total_cost', '0')),
                    service_grand_total=Decimal(json_data.get('service_grand_total', '0')),
                    hotel_grand_total=Decimal(json_data.get('hotel_grand_total', '0')),
                    commission_rate_hotel=Decimal(json_data.get('commission_info', {}).get('hotel_rate', '0')),
                    commission_amount_hotel=Decimal(json_data.get('commission_info', {}).get('hotel_amount', '0')),
                    commission_rate_services=Decimal(json_data.get('commission_info', {}).get('services_rate', '0')),
                    commission_amount_services=Decimal(json_data.get('commission_info', {}).get('services_amount', '0'))
                )
                
                # Set tour pack type if it exists
                if json_data.get('tour_pack_type'):
                    tour_pack_type, _ = TourPackType.objects.get_or_create(
                        name=json_data.get('tour_pack_type')
                    )
                    tour_package.tour_pack_type = tour_pack_type
                
                # Save the package to generate a reference ID
                tour_package.save()
                
                # Process tour days if they exist
                if json_data.get('tour_days'):
                    for day_data in json_data['tour_days']:
                        # Get or create city
                        city, _ = City.objects.get_or_create(name=day_data.get('city'))
                        
                        # Get or create hotel
                        hotel, _ = Hotel.objects.get_or_create(
                            name=day_data.get('hotel'),
                            city=city
                        )
                        
                        # Create tour day
                        tour_day = TourDay.objects.create(
                            tour_package=tour_package,
                            date=datetime.fromisoformat(day_data.get('date')).date(),
                            city=city,
                            hotel=hotel
                        )
                        
                        # Add services
                        if day_data.get('services'):
                            for service_data in day_data['services']:
                                # Get or create service type
                                service_type, _ = ServiceType.objects.get_or_create(
                                    name=service_data.get('service_type', 'General')
                                )
                                
                                # Get or create service
                                service, _ = Service.objects.get_or_create(
                                    name=service_data.get('name'),
                                    service_type=service_type
                                )
                                service.cities.add(city)
                                
                                # Create tour day service
                                TourDayService.objects.create(
                                    tour_day=tour_day,
                                    service=service,
                                    price_at_booking=Decimal(service_data.get('price_at_booking', '0'))
                                )
                        
                        # Add guide services
                        if day_data.get('guide_services'):
                            for guide_service_data in day_data['guide_services']:
                                # Get or create guide service
                                guide_service, _ = GuideService.objects.get_or_create(
                                    name=guide_service_data.get('name')
                                )
                                
                                # Create tour day guide service
                                TourDayGuideService.objects.create(
                                    tour_day=tour_day,
                                    guide_service=guide_service,
                                    price_at_booking=Decimal(guide_service_data.get('price_at_booking', '0'))
                                )
            
            messages.success(request, f"Successfully imported tour package: {tour_package.name}")
            return redirect('tour_package_detail', package_reference=tour_package.package_reference)
            
        except json.JSONDecodeError:
            messages.error(request, "Invalid JSON file. Please upload a valid JSON file.")
        except Exception as e:
            messages.error(request, f"Error importing tour package: {str(e)}")
    
    return render(request, 'tour_quote/import_tour_package.html')
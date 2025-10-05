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
from django.db.models import Prefetch, Q
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
                # Check if user can create packages (superuser or assistance group)
                can_create = request.user.is_superuser or request.user.groups.filter(name='assistance').exists()
                if can_create:
                    package = TourPackageQuote()
                    package.prepare_by_user = request.user
                    is_new = True
                else:
                    return JsonResponse({'status': 'error', 'message': 'You do not have permission to create new packages'}, status=403)

            # Check if user can edit basic fields (superuser or assistance group)
            can_edit = request.user.is_superuser or request.user.groups.filter(name='assistance').exists()
            if can_edit:
                # Users with edit permissions can edit basic fields
                package.name = data['name']
                package.customer_name = data['customer_name']
                package.remark = data.get('remark', '')
                package.remark2 = data.get('remark2', '')
                package.tour_pack_type_id = data['tour_pack_type']
                
                # Only superusers can edit commission rates
                if request.user.is_superuser:
                    package.commission_rate_hotel = data.get(
                        'commission_rate_hotel', 0)
                    package.commission_rate_services = data.get(
                        'commission_rate_services', 0)
                
                # Note: prepare_by_user is only set during creation, never during updates
                # This field is immutable after the tour quote is created


            # all login users can update these field
            package.hotel_costs = data['hotelCosts']
            package.remark_of_hotels = data.get('remark_of_hotels', '')
            package.discounts = data.get('discounts', [])
            package.extra_costs = data.get('extraCosts', [])

            # Save the package to get a primary key
            package.save()

            if can_edit or is_new:
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
    # Check if user should see commission info (not in assistance group)
    show_commission = not request.user.groups.filter(name='assistance').exists()
    
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
        'ordered_tour_days': ordered_tour_days,
        'show_commission': show_commission,
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

    # Check if user should see commission info (not in assistance group)
    show_commission = not request.user.groups.filter(name='assistance').exists()
    # Check if user can edit (superuser or assistance group)
    can_edit = request.user.is_superuser or request.user.groups.filter(name='assistance').exists()
    
    context = {
        'package': package,
        'cities': cities,
        'guide_services_json': json.dumps(guide_services, cls=DjangoJSONEncoder),
        'package_json': json.dumps(package_data, cls=DjangoJSONEncoder),
        'predefined_quotes': predefined_quotes,
        'tour_pack_types': tour_pack_types,
        'show_commission': show_commission,
        'can_edit': can_edit,
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

    # Check if user can use AI email parser
    # can_use_ai = request.user.is_superuser or request.user.groups.filter(name='assistance').exists()
    
    # only superuser can use AI email parser
    can_use_ai = request.user.is_superuser
    
    context = {
        'cities': cities,
        'service_types': service_types,
        'guide_services_json': json.dumps(guide_services, cls=DjangoJSONEncoder),
        'predefined_quotes': predefined_quotes,
        'tour_pack_types': tour_pack_types,
        'is_superuser': request.user.is_superuser,
        'can_use_ai': can_use_ai,
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
        extra_costs=original_package.extra_costs,
        prepare_by_user=request.user
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
                    commission_amount_services=Decimal(json_data.get('commission_info', {}).get('services_amount', '0')),
                    prepare_by_user=request.user
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

@login_required
def parse_email_with_ai(request):
    """
    Parse customer email using AI to extract tour information.
    Only accessible by superusers or users in 'assistance' group.
    """
    # Check if user is superuser
    can_use_ai = request.user.is_superuser
    if not can_use_ai:
        return JsonResponse({'error': 'Permission denied. Only authorized users can use AI email parsing.'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        email_content = data.get('email_content', '').strip()
        
        if not email_content:
            return JsonResponse({'error': 'Email content is required'}, status=400)
        
        # Limit email content to prevent token bloat (2000 chars ≈ 500 tokens)
        MAX_EMAIL_LENGTH = 2000
        if len(email_content) > MAX_EMAIL_LENGTH:
            return JsonResponse({
                'error': f'Email content too long. Maximum {MAX_EMAIL_LENGTH} characters allowed (current: {len(email_content)})'
            }, status=400)
        
        # Step-by-step AI analysis
        analysis_result = analyze_email_step_by_step(email_content)
        
        # Query Django models to match extracted data
        matched_data = match_extracted_data_with_models(analysis_result)
        
        return JsonResponse({
            'success': True,
            'analysis': analysis_result,
            'matched_data': matched_data
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error processing email: {str(e)}'}, status=500)

def analyze_email_step_by_step(email_content):
    """
    STEP 1: Extract basic information from email (cities, people, duration).
    """
    from django.conf import settings
    from datetime import datetime
    import openai
    import json
    
    # Initialize OpenAI client
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    
    # Get available cities from database for context
    available_cities = list(City.objects.values_list('name', flat=True))

    
    # Get current date for context
    from datetime import datetime as dt
    current_date = dt.now()
    current_date_str = current_date.strftime('%B %d, %Y')  # e.g., "October 04, 2025"
    current_month = current_date.month
    current_year = current_date.year
    
    # STEP 1 PROMPT: Extract basic info only
    prompt = f"""
You are a Thailand tour specialist analyzing customer emails to extract tour information.
**CURRENT DATE: {current_date_str}** (Month: {current_month}, Year: {current_year})
Available Thailand cities in our system: {', '.join(available_cities)}

Customer Email:
{email_content}

Extract ONLY the following BASIC information as JSON:
{{
    "customer_name": "customer name if mentioned (e.g., from signature, 'My name is...', 'I am...')",
    "number_of_people": "number of travelers - extract NUMBER (1 for solo/'I', 2 for couple/'we', 4 for family, etc.)",
    "destinations": ["cities mentioned - ONLY from available cities list],
    "days_per_city": {{
        "Bangkok": 2,
        "Chiang Mai": 5,
        "Phuket": 7
    }},
    "travel_months": ["months mentioned like December, January, February"],
    "travel_start_date": "specific start date if mentioned (format: YYYY-MM-DD). IMPORTANT: Use correct year based on current date - if month is AFTER current month use CURRENT year, if month is BEFORE current month use NEXT year",
    "travel_timing": "time of month if mentioned: 'early', 'mid', 'end', 'late', 'beginning' (e.g., 'end of November' → 'end')",
    "duration_days": "total trip duration in days (e.g., 7 for 1 week, 14 for 2 weeks, 2 for 2 days)",
    "raw_hotel_mentions": "any hotel names or brands mentioned in the email (exact text)",
    "raw_activity_mentions": "any activities or interests mentioned (exact text)"
}}

IMPORTANT RULES:
1. **NUMBER OF PEOPLE**: 
   - "I" or "alone" = 1 person
   - "we" or "couple" or "my wife and I" = 2 people
   - "family" = 4 people (default)
   - ALWAYS extract a number, never leave as None
2. For destinations: ONLY use cities from the available cities list
3. If a city is not in the list, find the closest match
4. **YEAR LOGIC**: 
   - Current date is {current_date_str}
   - If travel month is AFTER current month ({current_month}) → use {current_year}
   - If travel month is BEFORE or EQUAL to current month → use {current_year + 1}
   - Example: Today is Oct (month 10). "Dec" (month 12) → {current_year}, "Sep" (month 9) → {current_year + 1}
5. DURATION: Extract trip duration from phrases like "2 weeks", "10 days", "1 week" (convert weeks to days: 1 week = 7 days, 2 weeks = 14 days)
6. For raw_hotel_mentions and raw_activity_mentions: Extract the EXACT text from the email, don't interpret or modify
7. **DAYS PER CITY**: 
   - If customer specifies days per city (e.g., "7 days in Phuket and 2 nights in Bangkok"), extract those exact numbers
   - Pay attention to phrases like "stay for X days", "spend X nights", "X days in [city]"
   - Calculate total duration by ADDING all days mentioned
   - If NOT specified, distribute days intelligently based on city type:
     * Gateway cities (Bangkok): 2-3 days (arrival/shopping/temples)
     * Cultural cities (Chiang Mai, Chiang Rai): 3-5 days (temples/activities/nature)
     * Beach destinations (Phuket, Krabi, Koh Samui): 4-7 days (relaxation/beach time)
   - Example: "7 days beach + 2 nights Bangkok" → Phuket: 7, Bangkok: 2, Total: 9 days
   - Include ALL cities mentioned in email in days_per_city

8. **CITY ORDER (IMPORTANT - Realistic Tour Routing)**:
   - If customer specifies order (e.g., "start in Bangkok, then Chiang Mai, end in Phuket"), follow their order.
   - If customer does NOT specify order, use this LOGICAL ROUTING based on Thailand geography and typical tour flow.
"""
    try:
        # Call OpenAI API
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a Thailand tour specialist. Extract only factual information from emails. Always respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,  # Low temperature for consistent extraction
            max_tokens=800
        )
        
        # Parse the response
        ai_response = response.choices[0].message.content.strip()
        
        # Clean up the response to ensure it's valid JSON
        if ai_response.startswith('```json'):
            ai_response = ai_response[7:]
        if ai_response.endswith('```'):
            ai_response = ai_response[:-3]
        ai_response = ai_response.strip()
        
        analysis = json.loads(ai_response)
        
        # Log the STEP 1 extraction for debugging
        print("=" * 50)
        print("STEP 1 - BASIC EXTRACTION:")
        print(f"Customer name: {analysis.get('customer_name')}")
        print(f"Number of people: {analysis.get('number_of_people')}")
        print(f"Destinations: {analysis.get('destinations')}")
        print(f"Duration: {analysis.get('duration_days')}")
        print(f"Days per city: {analysis.get('days_per_city')}")
        print(f"Raw hotel mentions: {analysis.get('raw_hotel_mentions')}")
        print(f"Raw activity mentions: {analysis.get('raw_activity_mentions')}")
        print("=" * 50)
        
        # Ensure required fields exist
        if 'customer_name' not in analysis:
            analysis['customer_name'] = ''
        if 'number_of_people' not in analysis:
            analysis['number_of_people'] = None
        if 'destinations' not in analysis:
            analysis['destinations'] = []
        if 'days_per_city' not in analysis:
            analysis['days_per_city'] = {}
        if 'travel_months' not in analysis:
            analysis['travel_months'] = []
        if 'travel_start_date' not in analysis:
            analysis['travel_start_date'] = None
        if 'travel_timing' not in analysis:
            analysis['travel_timing'] = ''
        if 'duration_days' not in analysis:
            analysis['duration_days'] = None
        if 'raw_hotel_mentions' not in analysis:
            analysis['raw_hotel_mentions'] = ''
        if 'raw_activity_mentions' not in analysis:
            analysis['raw_activity_mentions'] = ''
        
        return analysis
        
    except Exception as e:
        print(f"OpenAI API error in Step 1: {str(e)}")
        # Return minimal structure on error
        return {
            'customer_name': '',
            'number_of_people': None,
            'destinations': [],
            'days_per_city': {},
            'travel_months': [],
            'travel_start_date': None,
            'travel_timing': '',
            'duration_days': None,
            'raw_hotel_mentions': '',
            'raw_activity_mentions': '',
            'error': str(e)
        }

def analyze_hotels_and_services_step2(basic_analysis, cities):
    """
    STEP 2: With selected cities, get available hotels and services from DB,
    then ask AI to match with customer requirements.
    """
    from django.conf import settings
    import openai
    import json
    
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    
    # Get tour pack type for pricing
    num_people = basic_analysis.get('number_of_people')
    tour_pack_type = None
    if num_people:
        pax_name = f"{num_people}pax"
        tour_pack_type = TourPackType.objects.filter(name__iexact=pax_name).first()
        print(f"Looking for tour pack type: {pax_name}, Found: {tour_pack_type.name if tour_pack_type else 'NOT FOUND'}")
    
    # Collect available hotels and services for each city
    city_options = []
    for city_data in cities:
        city_id = city_data['id']
        city_name = city_data['name']
        
        # Get hotels for this city
        hotels = Hotel.objects.filter(city_id=city_id)
        hotel_list = [{'id': h.id, 'name': h.name} for h in hotels]
        
        # Get services for this city
        services = Service.objects.filter(cities__id=city_id)
        print(f"Services for {city_name} (before price filter): {services.count()}")
        
        if tour_pack_type:
            services = services.filter(prices__tour_pack_type=tour_pack_type).distinct()
            print(f"Services for {city_name} (after {tour_pack_type.name} price filter): {services.count()}")
        
        service_list = []
        for service in services:
            price = None
            if tour_pack_type:
                price_obj = ServicePrice.objects.filter(
                    service=service,
                    tour_pack_type=tour_pack_type
                ).first()
                if price_obj:
                    price = str(price_obj.price)
            
            service_list.append({
                'id': service.id,
                'name': service.name,
                'type': service.service_type.name,
                'price': price
            })
        
        city_options.append({
            'city': city_name,
            'hotels': hotel_list,
            'services': service_list
        })
    
    # Debug: Log what we're sending to AI
    print("=" * 50)
    print("STEP 2 - CONTEXT FOR AI:")
    print(f"Customer hotel mentions: {basic_analysis.get('raw_hotel_mentions', 'Not specified')}")
    print(f"Customer activity mentions: {basic_analysis.get('raw_activity_mentions', 'Not specified')}")
    for city_opt in city_options:
        print(f"\nCity: {city_opt['city']}")
        print(f"  Hotels available: {len(city_opt['hotels'])}")
        print(f"  Services available: {len(city_opt['services'])}")
        if city_opt['services']:
            print(f"  Sample services: {[s['name'] for s in city_opt['services'][:3]]}")
    print("=" * 50)
    
    # STEP 2 PROMPT: Match with available options
    prompt = f"""
You are a Thailand tour specialist. Based on customer requirements, select the best matching hotels and services from available options.

Customer mentioned:
- Hotels: {basic_analysis.get('raw_hotel_mentions', 'Not specified')}
- Activities/Interests: {basic_analysis.get('raw_activity_mentions', 'Not specified')}

Available options by city:
{json.dumps(city_options, indent=2)}

Return JSON with matched selections:
{{
    "matched_hotels": [
        {{"city": "Bangkok", "hotel_id": 123, "hotel_name": "...", "match_reason": "customer mentioned Ibis"}},
        {{"city": "Chiang Mai", "hotel_id": 456, "hotel_name": "...", "match_reason": "similar to customer preference"}},
        {{"city": "Phuket", "hotel_id": 789, "hotel_name": "...", "match_reason": "beach resort matching preference"}}
    ],
    "matched_services": [
        {{"city": "Bangkok", "service_id": 111, "service_name": "...", "match_reason": "matches shopping interest"}},
        {{"city": "Bangkok", "service_id": 222, "service_name": "...", "match_reason": "matches cultural tours"}},
        {{"city": "Chiang Mai", "service_id": 333, "service_name": "...", "match_reason": "matches cultural tours"}},
        {{"city": "Chiang Mai", "service_id": 444, "service_name": "...", "match_reason": "matches activities"}},
        {{"city": "Phuket", "service_id": 555, "service_name": "...", "match_reason": "matches beach time"}},
        {{"city": "Phuket", "service_id": 666, "service_name": "...", "match_reason": "water activities"}}
    ]
}}

CRITICAL RULES:
1. **MUST select hotels for EVERY city** in the destinations list
2. **MUST select AT LEAST 2-3 services per city** to cover multiple days
3. Match hotel names even with spelling variations (e.g., "Ibis reviver side" → "Ibis Riverside")
4. Match services based on activity keywords (e.g., "shopping" → shopping tour services, "cultural" → temple/palace tours, "beach" → island/water activities)
5. Only select from the provided available options
6. Provide match_reason to explain why you selected each item
7. Prioritize variety - select different types of services for each city
"""
    
    try:
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a hotel and service matching expert. Always respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=1000
        )
        
        ai_response = response.choices[0].message.content.strip()
        
        # Clean JSON
        if ai_response.startswith('```json'):
            ai_response = ai_response[7:]
        if ai_response.endswith('```'):
            ai_response = ai_response[:-3]
        ai_response = ai_response.strip()
        
        matches = json.loads(ai_response)
        
        print("=" * 50)
        print("STEP 2 - HOTEL & SERVICE MATCHING:")
        print(f"Matched hotels: {matches.get('matched_hotels')}")
        print(f"Matched services: {matches.get('matched_services')}")
        print("=" * 50)
        
        return matches
        
    except Exception as e:
        print(f"OpenAI API error in Step 2: {str(e)}")
        return {
            'matched_hotels': [],
            'matched_services': [],
            'error': str(e)
        }

def match_extracted_data_with_models(analysis_result):
    """
    Match extracted data with Django models following the manual import pattern.
    Returns structured data ready for tour package creation.
    """
    from datetime import datetime, timedelta
    
    matched_data = {
        'tour_pack_type': None,  # Single tour pack type based on number of people
        'cities': [],
        'tour_days': [],  # Structured tour days ready for form
        'package_name_suggestion': '',
        'customer_name_suggestion': ''
    }
    
    # 1. Match Tour Pack Type based on number of people
    num_people = analysis_result.get('number_of_people')
    if num_people:
        # Convert to pax format (e.g., 2 -> "2pax")
        pax_name = f"{num_people}pax"
        pack_type = TourPackType.objects.filter(name__iexact=pax_name).first()
        if pack_type:
            matched_data['tour_pack_type'] = {
                'id': pack_type.id,
                'name': pack_type.name
            }
    
    # 2. Match cities (already ordered by AI: Central -> North -> South)
    for destination in analysis_result.get('destinations', []):
        city = City.objects.filter(name__iexact=destination).first()
        if city:
            matched_data['cities'].append({
                'id': city.id,
                'name': city.name
            })
    
    # 2.5 STEP 2: Get AI to match hotels and services from available options
    step2_matches = analyze_hotels_and_services_step2(analysis_result, matched_data['cities'])
    
    # 3. Create tour days - distribute intelligently across cities based on duration
    # Start date: Use specific date > travel month > tomorrow
    start_date = datetime.now().date() + timedelta(days=1)
    
    # Priority 1: Use specific start date if provided
    travel_start_date = analysis_result.get('travel_start_date')
    if travel_start_date:
        try:
            from datetime import datetime as dt
            parsed_date = dt.strptime(travel_start_date, '%Y-%m-%d').date()
            
            # If the date is in the past, move it to next year
            today = datetime.now().date()
            if parsed_date < today:
                # Move to next year
                parsed_date = parsed_date.replace(year=today.year + 1)
                print(f"Date was in past, moved to next year: {parsed_date}")
            
            start_date = parsed_date
            print(f"Using specific start date: {start_date}")
        except Exception as e:
            print(f"Error parsing start date '{travel_start_date}': {e}")
    
    # Priority 2: Use travel month if no specific date
    if not travel_start_date:
        travel_months = analysis_result.get('travel_months', [])
        raw_activity = analysis_result.get('raw_activity_mentions', '').lower()
        raw_hotel = analysis_result.get('raw_hotel_mentions', '').lower()
        
        if travel_months:
            try:
                import calendar
                
                month_name = travel_months[0]
                current_year = datetime.now().year
                
                # Parse month name to month number
                month_num = None
                for i in range(1, 13):
                    if calendar.month_name[i].lower() == month_name.lower():
                        month_num = i
                        break
                
                if month_num:
                    # If month is in the past, use next year
                    if month_num < datetime.now().month:
                        current_year += 1
                    
                    # Determine day based on travel_timing
                    day = 1  # Default to first day
                    travel_timing = analysis_result.get('travel_timing', '').lower()
                    
                    if travel_timing in ['end', 'late']:
                        # End of month: use 20th
                        day = 20
                        print(f"Detected '{travel_timing}' of {month_name} → Using day {day}")
                    elif travel_timing in ['early', 'beginning', 'start']:
                        # Early month: use 1st
                        day = 1
                        print(f"Detected '{travel_timing}' {month_name} → Using day {day}")
                    elif travel_timing in ['mid', 'middle']:
                        # Mid month: use 15th
                        day = 15
                        print(f"Detected '{travel_timing}' {month_name} → Using day {day}")
                    
                    start_date = datetime(current_year, month_num, day).date()
                    print(f"Using travel month {month_name} → Start date: {start_date}")
            except Exception as e:
                print(f"Error parsing travel month: {e}, using tomorrow as start date")
    
    duration_days = analysis_result.get('duration_days')
    days_per_city_ai = analysis_result.get('days_per_city', {})
    tour_pack_type_id = matched_data['tour_pack_type']['id'] if matched_data['tour_pack_type'] else None
    
    # Get matched hotels and services from Step 2
    matched_hotels_by_city = {}
    for hotel_match in step2_matches.get('matched_hotels', []):
        city_name = hotel_match.get('city')
        matched_hotels_by_city[city_name] = hotel_match
    
    matched_services_by_city = {}
    for service_match in step2_matches.get('matched_services', []):
        city_name = service_match.get('city')
        if city_name not in matched_services_by_city:
            matched_services_by_city[city_name] = []
        matched_services_by_city[city_name].append(service_match)
    
    # Convert duration to integer if it's a string
    if isinstance(duration_days, str):
        try:
            duration_days = int(duration_days)
        except:
            duration_days = None
    
    # Calculate how many days per city
    num_cities = len(matched_data['cities'])
    if num_cities == 0:
        return matched_data
    
    # Use AI-recommended days per city if available
    city_day_distribution = []
    if days_per_city_ai:
        print(f"Using AI-recommended days per city: {days_per_city_ai}")
        for city_data in matched_data['cities']:
            city_name = city_data['name']
            num_days = days_per_city_ai.get(city_name, 1)  # Default to 1 if not specified
            city_day_distribution.append((city_data, num_days))
    elif duration_days and duration_days > 0:
        # Fallback: Distribute days evenly across cities
        days_per_city = max(1, duration_days // num_cities)
        remaining_days = duration_days % num_cities
        
        for idx, city_data in enumerate(matched_data['cities']):
            # Give extra days to later cities (beach destinations get more time)
            extra_day = 1 if idx >= (num_cities - remaining_days) else 0
            num_days_in_city = days_per_city + extra_day
            city_day_distribution.append((city_data, num_days_in_city))
    else:
        # Default: 1 day per city
        city_day_distribution = [(city_data, 1) for city_data in matched_data['cities']]
    
    # Recalculate total duration from AI recommendations
    if days_per_city_ai:
        duration_days = sum(days for _, days in city_day_distribution)
    
    # Now create tour days based on distribution
    current_day = 0
    for city_data, num_days_in_city in city_day_distribution:
        city_id = city_data['id']
        city_name = city_data['name']
        
        # Create multiple days for this city
        for day_in_city in range(num_days_in_city):
            # Calculate date for this day
            day_date = start_date + timedelta(days=current_day)
            is_first_day_in_city = (day_in_city == 0)
            is_last_day_in_city = (day_in_city == num_days_in_city - 1)
            is_first_day_overall = (current_day == 0)
            is_last_day_overall = (current_day == (duration_days - 1) if duration_days else False)
        
            # 3.1 Find hotel for this city using Step 2 AI matches
            hotel = None
            if city_name in matched_hotels_by_city:
                hotel_match = matched_hotels_by_city[city_name]
                hotel_id = hotel_match.get('hotel_id')
                if hotel_id:
                    hotel = Hotel.objects.filter(id=hotel_id).first()
                    print(f"Using AI-matched hotel: {hotel.name if hotel else 'Not found'} (Reason: {hotel_match.get('match_reason')})")
            
            # Fallback: get first hotel from database for this city
            if not hotel:
                hotel = Hotel.objects.filter(city_id=city_id).first()
                print(f"Using fallback hotel: {hotel.name if hotel else 'No hotel available'}")
            
            # 3.2 Find services for this city using Step 2 AI matches
            suggested_services = []
            
            # Add AI-matched services (activities) - ONE service per day to avoid duplicates
            if city_name in matched_services_by_city:
                available_services = matched_services_by_city[city_name]
                
                # Use round-robin to distribute services across days in this city
                if available_services and day_in_city < len(available_services):
                    service_match = available_services[day_in_city]
                    service_id = service_match.get('service_id')
                    if service_id:
                        service = Service.objects.filter(id=service_id).first()
                        if service:
                            # Get the price for this tour pack type
                            price = None
                            if tour_pack_type_id:
                                price_obj = ServicePrice.objects.filter(
                                    service=service,
                                    tour_pack_type_id=tour_pack_type_id
                                ).first()
                                if price_obj:
                                    price = str(price_obj.price)
                            
                            suggested_services.append({
                                'id': service.id,
                                'name': service.name,
                                'service_type': service.service_type.name,
                                'price': price,
                                'activity_match': service_match.get('match_reason', '')
                            })
                            print(f"Day {current_day + 1} - Using AI-matched service: {service.name} (Reason: {service_match.get('match_reason')})")
                elif available_services:
                    # If we have more days than services, cycle through services
                    service_match = available_services[day_in_city % len(available_services)]
                    service_id = service_match.get('service_id')
                    if service_id:
                        service = Service.objects.filter(id=service_id).first()
                        if service:
                            price = None
                            if tour_pack_type_id:
                                price_obj = ServicePrice.objects.filter(
                                    service=service,
                                    tour_pack_type_id=tour_pack_type_id
                                ).first()
                                if price_obj:
                                    price = str(price_obj.price)
                            
                            suggested_services.append({
                                'id': service.id,
                                'name': service.name,
                                'service_type': service.service_type.name,
                                'price': price,
                                'activity_match': service_match.get('match_reason', '')
                            })
                            print(f"Day {current_day + 1} - Using AI-matched service (cycled): {service.name}")
            
            # 3.3 Add inter-city transfer when changing cities
            if is_first_day_in_city and not is_first_day_overall:
                # This is the first day in a new city (not the first day of trip)
                # Need transfer from previous city to this city
                prev_city_idx = matched_data['cities'].index(city_data) - 1
                if prev_city_idx >= 0:
                    prev_city_name = matched_data['cities'][prev_city_idx]['name']
                    
                    # Search for train/bus transfer FROM previous city TO current city
                    # Look in PREVIOUS city's services for transfers going TO current city
                    prev_city_id = matched_data['cities'][prev_city_idx]['id']
                    
                    # Strategy 1: Exact route match (e.g., "Bangkok to Chiang Mai")
                    transfer = Service.objects.filter(
                        service_type__name__icontains='transfer',
                        cities__id=prev_city_id
                    ).filter(
                        name__icontains=prev_city_name
                    ).filter(
                        name__icontains=city_name
                    ).exclude(
                        name__icontains='Bangkok'  # Exclude if going TO Bangkok (wrong direction)
                    ).first() if city_name != 'Bangkok' else Service.objects.filter(
                        service_type__name__icontains='transfer',
                        cities__id=prev_city_id,
                        name__icontains=prev_city_name
                    ).filter(
                        name__icontains=city_name
                    ).first()
                    
                    # Strategy 2: Transfer mentioning destination city (flight/train/bus)
                    if not transfer:
                        transfer = Service.objects.filter(
                            service_type__name__icontains='transfer',
                            cities__id=prev_city_id
                        ).filter(
                            name__icontains=city_name  # Must mention destination
                        ).filter(
                            Q(name__icontains='flight') | Q(name__icontains='train') | Q(name__icontains='bus')
                        ).first()
                    
                    # Strategy 3: Generic transfer with destination keyword
                    if not transfer:
                        # For long distances (e.g., Chiang Mai to Phuket), prefer flight
                        if (prev_city_name == 'Chiang Mai' and city_name == 'Phuket') or \
                           (prev_city_name == 'Phuket' and city_name == 'Chiang Mai'):
                            transfer = Service.objects.filter(
                                service_type__name__icontains='transfer',
                                cities__id=prev_city_id,
                                name__icontains='flight'
                            ).first()
                        
                        # For shorter distances, train/bus is fine
                        if not transfer:
                            transfer = Service.objects.filter(
                                service_type__name__icontains='transfer',
                                cities__id=prev_city_id
                            ).filter(
                                Q(name__icontains='train') | Q(name__icontains='bus')
                            ).first()
                    
                    if transfer and tour_pack_type_id:
                        price_obj = ServicePrice.objects.filter(
                            service=transfer,
                            tour_pack_type_id=tour_pack_type_id
                        ).first()
                        if price_obj:
                            suggested_services.insert(0, {
                                'id': transfer.id,
                                'name': transfer.name,
                                'service_type': transfer.service_type.name,
                                'price': str(price_obj.price),
                                'activity_match': f'transfer_{prev_city_name}_to_{city_name}'
                            })
                            print(f"Day {current_day + 1} - Added inter-city transfer: {transfer.name}")
            
            # 3.4 Add arrival transfer for first day of trip
            if is_first_day_overall:
                # Search for transfer services with 'airport' AND city name
                transfer = Service.objects.filter(
                    service_type__name__icontains='transfer',
                    cities__id=city_id
                ).filter(
                    name__icontains='airport'
                ).filter(
                    name__icontains=city_name
                ).first()
                
                if transfer and tour_pack_type_id:
                    price_obj = ServicePrice.objects.filter(
                        service=transfer,
                        tour_pack_type_id=tour_pack_type_id
                    ).first()
                    if price_obj:
                        suggested_services.insert(0, {
                            'id': transfer.id,
                            'name': transfer.name,
                            'service_type': transfer.service_type.name,
                            'price': str(price_obj.price),
                            'activity_match': 'arrival_transfer'
                        })
            
            # 3.5 Add departure transfer for last day of trip
            if is_last_day_overall:
                # Search for transfer services with 'airport' AND city name
                transfer = Service.objects.filter(
                    service_type__name__icontains='transfer',
                    cities__id=city_id
                ).filter(
                    name__icontains='airport'
                ).filter(
                    name__icontains=city_name
                ).first()
                
                if transfer and tour_pack_type_id:
                    price_obj = ServicePrice.objects.filter(
                        service=transfer,
                        tour_pack_type_id=tour_pack_type_id
                    ).first()
                    if price_obj:
                        suggested_services.append({
                            'id': transfer.id,
                            'name': transfer.name,
                            'service_type': transfer.service_type.name,
                            'price': str(price_obj.price),
                            'activity_match': 'departure_transfer'
                        })
            
            # Build tour day object
            tour_day = {
                'date': day_date.isoformat(),
                'city_id': city_id,
                'city_name': city_name,
                'hotel_id': hotel.id if hotel else None,
                'hotel_name': hotel.name if hotel else 'No hotel available',
                'services': suggested_services
            }
            
            matched_data['tour_days'].append(tour_day)
            current_day += 1
    
    # 4. Generate package name suggestion
    if matched_data['cities']:
        city_names = ' - '.join([c['name'] for c in matched_data['cities']])
        pax_info = matched_data['tour_pack_type']['name'] if matched_data['tour_pack_type'] else ''
        matched_data['package_name_suggestion'] = f"{city_names} Tour ({pax_info})"
    
    # 5. Customer name suggestion
    customer_name = analysis_result.get('customer_name', '')
    if customer_name:
        matched_data['customer_name_suggestion'] = customer_name
    
    return matched_data
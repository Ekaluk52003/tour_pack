# admin.py

from django.contrib import admin, messages
from import_export import resources, fields, widgets
from import_export.widgets import ManyToManyWidget, ForeignKeyWidget
from import_export.admin import ImportExportModelAdmin

from django.core.exceptions import ValidationError
from django import forms
from django.forms import ModelForm
from .models import (
    City, Hotel, Service, GuideService, ServiceType, TourPackType,
    PredefinedTourQuote, PredefinedTourDay, PredefinedTourDayService,
    PredefinedTourDayGuideService, TourPackageQuote, TourDay,
    TourDayService, TourDayGuideService, ServicePrice, ReferenceID
)
from import_export.formats import base_formats
from import_export.results import Result, RowResult
from import_export.signals import post_import, post_export
from import_export.fields import Field
from django.db import IntegrityError
import logging


logger = logging.getLogger(__name__)


class CityWidget(widgets.ForeignKeyWidget):
    def clean(self, value, row=None, *args, **kwargs):
        if value:
            try:
                city, created = City.objects.get_or_create(name=value)
            except IntegrityError:
                # If the city already exists, just get it
                city = City.objects.get(name=value)
            return city
        return None

class HotelResource(resources.ModelResource):
    city = fields.Field(
        column_name='city',
        attribute='city',
        widget=CityWidget(City, 'name')
    )

    class Meta:
        model = Hotel
        fields = ('id', 'name', 'city')
        import_id_fields = ('name', 'city')
        skip_unchanged = True
        report_skipped = True

    def before_import(self, dataset, *args, **kwargs):
        # Ensure all cities exist before processing hotels
        city_names = set(dataset['city'])
        for city_name in city_names:
            City.objects.get_or_create(name=city_name)

    def skip_row(self, instance, original, row, import_validation_errors=None):
        try:
            instance.full_clean()
            return False
        except ValidationError as e:
            if import_validation_errors is not None:
                import_validation_errors.append(ValidationError(f"Row {row}: {str(e)}"))
            return True


@admin.register(Hotel)
class HotelAdmin(ImportExportModelAdmin):
    resource_class = HotelResource
    list_display = ('name', 'city', 'id')
    list_filter = ('city',)
    search_fields = ('name', 'city__name')
    ordering = ('city', 'name')

@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ('name', 'id')
    search_fields = ('name',)

@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


class ServicePriceInline(admin.TabularInline):
    model = ServicePrice
    extra = 1


class CustomManyToManyWidget:
    def __init__(self, model, separator=','):
        self.model = model
        self.separator = separator

    def clean(self, value, row=None, *args, **kwargs):
        if not value:
            return []
        if isinstance(value, (list, tuple)):
            return value
        city_names = [name.strip() for name in value.split(self.separator) if name.strip()]
        cities = []
        for name in city_names:
            city, _ = self.model.objects.get_or_create(name=name)
            cities.append(city)
        return cities

    def render(self, value, obj=None):
        if value:
            return self.separator.join(city.name for city in value.all())
        return ""

class CityForeignKeyWidget(ForeignKeyWidget):
    def __init__(self):
        super().__init__(City, 'name')

    def clean(self, value, row=None, *args, **kwargs):
        if value:
            city, created = City.objects.get_or_create(name=value.strip())
            return city
        return None

    def render(self, value, obj=None):
        if value:
            return value.name
        return ""

class ServiceResource(resources.ModelResource):

    service = fields.Field(
        column_name='service',
        attribute='name'

    )

    service_type = fields.Field(
        column_name='service_type',
        attribute='service_type',
        widget=ForeignKeyWidget(ServiceType, 'name')
    )

    city = fields.Field(
        column_name='city',
        attribute='city',
        widget=ForeignKeyWidget(City, 'name')
    )

    class Meta:
        model = Service
        import_id_fields = ['service', 'service_type']
        fields = ('service', 'service_type', 'city')
        export_order = fields
        skip_unchanged = True

    def dehydrate_city(self, service):
        """Create a comma-separated list of city names for the city field."""
        return ", ".join(city.name for city in service.cities.all())

    def before_import_row(self, row, **kwargs):
        """Ensure service type and city exist"""
        if 'service_type' in row and row['service_type']:
            service_type_name = row['service_type'].strip()
            ServiceType.objects.get_or_create(name=service_type_name)

        if 'city' in row and row['city']:
            city_name = row['city'].strip()
            City.objects.get_or_create(name=city_name)

    def get_diff_headers(self):
        """Custom headers for the diff preview"""
        headers = super().get_diff_headers()
        # Make sure city is included in preview
        if 'city' not in headers:
            headers.append('city')
        return headers

    def after_import_row(self, row, row_result, row_number=None, **kwargs):
        """Associate city with service after import"""
        if row_result.import_type != row_result.IMPORT_TYPE_ERROR:
            try:
                service = Service.objects.get(
                    name=row['service'],
                    service_type__name=row['service_type']
                )
                city = City.objects.get(name=row['city'])
                service.cities.add(city)
            except Exception as e:
                row_result.errors.append(f'Error associating city: {str(e)}')
                row_result.import_type = row_result.IMPORT_TYPE_ERROR

    def skip_row(self, instance, original, row, import_validation_errors=None):
        try:
            if not row.get('service') or not row.get('service_type') or not row.get('city'):
                raise ValidationError("Name, service type, and city are all required.")
            return False
        except ValidationError as e:
            import_validation_errors.append(e)
            return True

@admin.register(Service)
class ServiceAdmin(ImportExportModelAdmin):
    resource_class = ServiceResource
    list_display = ('name', 'service_type', 'get_cities')
    list_filter = ('service_type', 'cities')
    search_fields = ['name', 'service_type__name', 'cities__name']
    filter_horizontal = ['cities']

    def get_cities(self, obj):
        return ", ".join(city.name for city in obj.cities.all())
    get_cities.short_description = 'Cities'

    def get_import_formats(self):
        formats = [base_formats.XLSX, base_formats.CSV]
        return [f for f in formats if f().can_import()]

    def get_export_formats(self):
        formats = [base_formats.XLSX, base_formats.CSV]
        return [f for f in formats if f().can_export()]

    def get_search_results(self, request, queryset, search_term):
        """Customize search results for autocomplete"""
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)

        # If this is an autocomplete request and we have a referring page
        if 'autocomplete' in request.path and request.META.get('HTTP_REFERER'):
            try:
                # Extract tour day ID from referer if possible
                from urllib.parse import urlparse, parse_qs
                parsed_url = urlparse(request.META['HTTP_REFERER'])
                path_parts = parsed_url.path.split('/')
                if 'predefinedtourday' in path_parts and 'change' in path_parts:
                    tour_day_id = path_parts[path_parts.index('predefinedtourday') + 1]
                    if tour_day_id.isdigit():
                        tour_day = PredefinedTourDay.objects.filter(id=tour_day_id).first()
                        if tour_day:
                            queryset = queryset.filter(cities=tour_day.city)
            except Exception as e:
                pass  # If any error occurs, fall back to unfiltered queryset

        return queryset, use_distinct


@admin.register(GuideService)
class GuideServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'price')
    search_fields = ('name',)

@admin.register(TourPackType)
class TourPackTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)




class PredefinedTourDayServiceForm(forms.ModelForm):
    class Meta:
        model = PredefinedTourDayService
        fields = ['service', 'quantity', 'order']

    def clean(self):
        cleaned_data = super().clean()
        service = cleaned_data.get('service')

        if service and self.instance and hasattr(self.instance, 'tour_day') and self.instance.tour_day:
            city = self.instance.tour_day.city
            if not service.cities.filter(id=city.id).exists():
                available_cities = ', '.join(c.name for c in service.cities.all())
                raise forms.ValidationError(
                    f"The service '{service}' is not available in {city}. "
                    f"Available cities: {available_cities}"
                )
        return cleaned_data


class PredefinedTourDayServiceInline(admin.TabularInline):
    model = PredefinedTourDayService
    extra = 1
    autocomplete_fields = ['service']

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.city_being_updated = getattr(request, '_city_being_updated', False)
        return formset


class PredefinedTourDayGuideServiceInline(admin.TabularInline):
    model = PredefinedTourDayGuideService
    extra = 1
    autocomplete_fields = ['guide_service']

class PredefinedTourDayInline(admin.StackedInline):
    model = PredefinedTourDay
    extra = 1
    autocomplete_fields = ['city', 'hotel']
    inlines = [PredefinedTourDayServiceInline, PredefinedTourDayGuideServiceInline]

@admin.register(PredefinedTourQuote)
class PredefinedTourQuoteAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at', 'updated_at')
    search_fields = ('name', 'description')

    inlines = [PredefinedTourDayInline]

    fieldsets = (
        (None, {
            'fields': ('name', 'description')
        }),
    )

@admin.register(PredefinedTourDay)
class PredefinedTourDayAdmin(admin.ModelAdmin):
    list_display = ('predefined_tour_quote', 'day_number', 'city', 'hotel')
    list_filter = ('predefined_tour_quote', 'city')
    search_fields = ('predefined_tour_quote__name', 'city__name', 'hotel__name')
    autocomplete_fields = ['predefined_tour_quote', 'city', 'hotel']
    inlines = [PredefinedTourDayServiceInline, PredefinedTourDayGuideServiceInline]

    def get_form(self, request, obj=None, **kwargs):
        # Store if we're updating city
        if obj and request.method == "POST":
            data = request.POST
            if 'city' in data and str(obj.city.id) != data['city']:
                request._city_being_updated = True
        return super().get_form(request, obj, **kwargs)

    def save_model(self, request, obj, form, change):
        if change and 'city' in form.changed_data:
            # Store old services before saving
            if obj.pk:
                old_services = list(obj.services.all())
            else:
                old_services = []

            # Save the model with new city
            super().save_model(request, obj, form, change)

            # Process the services
            invalid_services = []
            for service in old_services:
                if not service.service.cities.filter(id=obj.city.id).exists():
                    invalid_services.append(service)
                    service.delete()

            if invalid_services:
                service_names = ", ".join(s.service.name for s in invalid_services)
                messages.warning(
                    request,
                    f"The following services were removed as they are not available in {obj.city}: {service_names}"
                )
        else:
            super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        if formset.model == PredefinedTourDayService:
            instances = formset.save(commit=False)

            # Check if we're updating the city
            city_being_updated = getattr(request, '_city_being_updated', False)

            if city_being_updated:
                # If updating city, just save without validation
                for instance in instances:
                    instance.save()
                formset.save_m2m()
                return

            # Normal case - validate services against city
            valid_instances = []
            for instance in instances:
                if instance.service and instance.tour_day:
                    if instance.service.cities.filter(id=instance.tour_day.city.id).exists():
                        valid_instances.append(instance)
                    else:
                        available_cities = ', '.join(c.name for c in instance.service.cities.all())
                        messages.error(
                            request,
                            f"The service '{instance.service}' is not available in {instance.tour_day.city}. "
                            f"Available cities: {available_cities}"
                        )
                        continue

            # Save valid instances
            for instance in valid_instances:
                instance.save()
            formset.save_m2m()
        else:
            formset.save()

    def response_change(self, request, obj):
        try:
            response = super().response_change(request, obj)
            # Clear any temporary flags
            if hasattr(request, '_city_being_updated'):
                delattr(request, '_city_being_updated')
            return response
        except ValidationError as e:
            messages.error(request, str(e))
            return self.render_change_form(
                request,
                context=self.get_changeform_initial_data(request),
                obj=obj,
                form=self.get_form(request, obj)(instance=obj)
            )

class TourDayServiceInline(admin.TabularInline):
    model = TourDayService
    extra = 1
    autocomplete_fields = ['service']

class TourDayGuideServiceInline(admin.TabularInline):
    model = TourDayGuideService
    extra = 1
    autocomplete_fields = ['guide_service']

class TourDayInline(admin.StackedInline):
    model = TourDay
    extra = 1
    autocomplete_fields = ['city', 'hotel']
    inlines = [TourDayServiceInline, TourDayGuideServiceInline]

@admin.register(TourPackageQuote)
class TourPackageQuoteAdmin(admin.ModelAdmin):
    list_display = ('name', 'customer_name', 'tour_pack_type', 'created_at', 'grand_total_cost')
    list_filter = ('tour_pack_type', 'created_at')
    search_fields = ('name', 'customer_name', 'package_reference')
    autocomplete_fields = ['tour_pack_type']
    inlines = [TourDayInline]

    fieldsets = (
        (None, {
            'fields': ('name', 'customer_name', 'tour_pack_type', 'remark')
        }),
        ('Costs', {
            'fields': ('hotel_costs', 'discounts', 'service_grand_total', 'hotel_grand_total', 'grand_total_cost')
        }),
        ('Reference', {
            'fields': ('package_reference',)
        })
    )

    readonly_fields = ('service_grand_total', 'hotel_grand_total', 'grand_total_cost', 'package_reference')

@admin.register(TourDay)
class TourDayAdmin(admin.ModelAdmin):
    list_display = ('tour_package', 'date', 'city', 'hotel')
    list_filter = ('tour_package', 'city')
    search_fields = ('tour_package__name', 'city__name', 'hotel__name')
    autocomplete_fields = ['tour_package', 'city', 'hotel']
    inlines = [TourDayServiceInline, TourDayGuideServiceInline]

# Optionally, you can register the inline models if you want to manage them directly
admin.site.register(PredefinedTourDayService)
admin.site.register(PredefinedTourDayGuideService)
admin.site.register(TourDayService)
admin.site.register(TourDayGuideService)

####Service Price
class ServicePriceResource(resources.ModelResource):
    service = fields.Field(
        column_name='service',
        attribute='service',
        widget=ForeignKeyWidget(Service, 'name')
    )
    service_type = fields.Field(
        column_name='service_type',
        attribute='service__service_type__name',
        readonly=True
    )
    tour_pack_type = fields.Field(
        column_name='tour_pack_type',
        attribute='tour_pack_type',
        widget=ForeignKeyWidget(TourPackType, 'name')
    )

    class Meta:
        model = ServicePrice
        fields = ('id', 'service', 'service_type', 'tour_pack_type', 'price')
        export_order = fields
        import_id_fields = ('service', 'tour_pack_type')
        skip_unchanged = True
        report_skipped = True

    def before_import_row(self, row, **kwargs):
        try:
            row['price'] = "{:.2f}".format(float(row['price']))
        except ValueError:
            raise ValueError("Invalid price format in row.")

        service_name = row.get('service')
        service_type_name = row.get('service_type')
        tour_pack_type_name = row.get('tour_pack_type')

        if not all([service_name, service_type_name, tour_pack_type_name]):
            raise ValueError("Missing required fields")

        try:
            service_type, _ = ServiceType.objects.get_or_create(name=service_type_name)
            service, _ = Service.objects.get_or_create(name=service_name, service_type=service_type)
            tour_pack_type, _ = TourPackType.objects.get_or_create(name=tour_pack_type_name)

            row['service'] = service.name
            row['tour_pack_type'] = tour_pack_type.name

        except IntegrityError as e:
            raise ValueError(f"Error processing row: {str(e)}")

    def skip_row(self, instance, original, row, import_validation_errors=None):
        # Your skip logic (already implemented as discussed previously)

        return False

@admin.register(ServicePrice)
class ServicePriceAdmin(ImportExportModelAdmin):
    resource_class = ServicePriceResource
    list_display = ('id', 'service', 'get_service_type', 'tour_pack_type', 'price')
    list_filter = ('service__service_type', 'tour_pack_type')
    search_fields = ('service__name', 'service__service_type__name', 'tour_pack_type__name')
    autocomplete_fields = ['service', 'tour_pack_type']

    def get_service_type(self, obj):
        return obj.service.service_type
    get_service_type.short_description = 'Service Type'
    get_service_type.admin_order_field = 'service__service_type__name'



@admin.register(ReferenceID)
class ReferenceIDAdmin(admin.ModelAdmin):
    list_display = ('formatted_reference', 'year', 'last_number')
    readonly_fields = ('formatted_reference',)

    def formatted_reference(self, obj):
        return f"{str(obj.year % 100).zfill(2)}{str(obj.last_number).zfill(3)}"
    formatted_reference.short_description = 'Reference'

    def has_add_permission(self, request):
        # Prevent manual creation of new references
        return False

    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of references
        return False
# admin.py

from django.contrib import admin
from import_export import resources, fields, widgets
from import_export.widgets import ForeignKeyWidget
from import_export.admin import ImportExportModelAdmin
from django.core.exceptions import ValidationError
from .models import (
    City, Hotel, Service, GuideService, ServiceType, TourPackType,
    PredefinedTourQuote, PredefinedTourDay, PredefinedTourDayService,
    PredefinedTourDayGuideService, TourPackageQuote, TourDay,
    TourDayService, TourDayGuideService, ServicePrice, ReferenceID
)
from import_export.formats import base_formats
from import_export.fields import Field

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

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'service_type')
    list_filter = ('service_type',)
    search_fields = ('name', 'service_type__name')
    autocomplete_fields = ['service_type']

@admin.register(GuideService)
class GuideServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'price')
    search_fields = ('name',)

@admin.register(TourPackType)
class TourPackTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)



class PredefinedTourDayServiceInline(admin.TabularInline):
    model = PredefinedTourDayService
    extra = 1
    autocomplete_fields = ['service']

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
    city = fields.Field(
        column_name='city',
        attribute='city',
        widget=ForeignKeyWidget(City, 'name')
    )

    class Meta:
        model = ServicePrice
        fields = ('service', 'service_type', 'tour_pack_type', 'price', 'city')
        export_order = fields
        import_id_fields = ('service', 'tour_pack_type', 'city')
        skip_unchanged = True
        report_skipped = True

    def before_import_row(self, row, **kwargs):
        service_name = row['service']
        service_type_name = row['service_type']
        tour_pack_type_name = row['tour_pack_type']
        city_name = row['city']

        # Get or create related objects
        service_type, _ = ServiceType.objects.get_or_create(name=service_type_name)
        service, _ = Service.objects.get_or_create(name=service_name, service_type=service_type)
        tour_pack_type, _ = TourPackType.objects.get_or_create(name=tour_pack_type_name)
        city, _ = City.objects.get_or_create(name=city_name)

        # Update row with object instances
        row['service'] = service.name
        row['tour_pack_type'] = tour_pack_type.name
        row['city'] = city.name

    def export_field(self, field, obj):
        if field.column_name == 'service_type':
            return obj.service.service_type.name
        return super().export_field(field, obj)

@admin.register(ServicePrice)
class ServicePriceAdmin(ImportExportModelAdmin):
    resource_class = ServicePriceResource
    list_display = ('id', 'service', 'get_service_type', 'tour_pack_type', 'city', 'price')
    list_filter = ('service__service_type', 'tour_pack_type', 'city')
    search_fields = ('service__name', 'service__service_type__name', 'tour_pack_type__name', 'city__name')
    autocomplete_fields = ['service', 'tour_pack_type', 'city']

    def get_service_type(self, obj):
        return obj.service.service_type
    get_service_type.short_description = 'Service Type'
    get_service_type.admin_order_field = 'service__service_type__name'


####Service Price end
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
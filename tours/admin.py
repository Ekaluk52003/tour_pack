# tour_quote/admin.py

from django.contrib import admin
from .models import City, Hotel, ServiceType, Service, GuideService, TourPackageQuote, TourDay, TourDayService, TourDayGuideService, PredefinedPackage, PredefinedPackageDay

from import_export import resources
from import_export.admin import ImportExportModelAdmin

@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ('name',)

# @admin.register(Hotel)
# class HotelAdmin(admin.ModelAdmin):
#     list_display = ('name', 'city')
#     list_filter = ('city',)

@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)

# @admin.register(Service)
# class ServiceAdmin(admin.ModelAdmin):
#     list_display = ('name', 'service_type', 'city')
#     list_filter = ('service_type', 'city')

@admin.register(GuideService)
class GuideServiceAdmin(admin.ModelAdmin):
    list_display = ('name',)

class TourDayServiceInline(admin.TabularInline):
    model = TourDayService
    extra = 1

class TourDayGuideServiceInline(admin.TabularInline):
    model = TourDayGuideService
    extra = 1

class TourDayInline(admin.StackedInline):
    model = TourDay
    extra = 1
    inlines = [TourDayServiceInline, TourDayGuideServiceInline]

@admin.register(TourPackageQuote)
class TourPackageQuoteAdmin(admin.ModelAdmin):
    list_display = ('name', 'customer_name', 'created_at')
    inlines = [TourDayInline]

@admin.register(TourDay)
class TourDayAdmin(admin.ModelAdmin):
    list_display = ('tour_package', 'date', 'city', 'hotel')
    list_filter = ('city', 'hotel')
    inlines = [TourDayServiceInline, TourDayGuideServiceInline]



class PredefinedPackageDayInline(admin.TabularInline):
    model = PredefinedPackageDay
    extra = 1  # Allow users to add multiple days easily

@admin.register(PredefinedPackage)
class PredefinedPackageAdmin(admin.ModelAdmin):
    inlines = [PredefinedPackageDayInline]
    list_display = ('name',)


class ServiceResource(resources.ModelResource):
    class Meta:
        model = Service
        fields = ('name', 'service_type', 'city', 'price')
        import_id_fields = ['name']

    def before_import_row(self, row, **kwargs):
        # Ensure service_type__name is present and trim any extra spaces
        service_type_name = row.get('service_type__name', '').strip()
        if not service_type_name or service_type_name == 'None':
            raise ValueError("ServiceType name is missing or None")

        # Lookup the ServiceType by its name and replace it with the service_type ID
        try:
            service_type = ServiceType.objects.get(name=service_type_name)
            row['service_type'] = service_type.id
        except ServiceType.DoesNotExist:
            raise ValueError(f"ServiceType '{service_type_name}' does not exist.")

        # Ensure city__name is present and trim any extra spaces
        city_name = row.get('city__name', '').strip()
        if not city_name or city_name == 'None':
            raise ValueError("City name is missing or None")
        try:
            city = City.objects.get(name=city_name)
            row['city'] = city.id
        except City.DoesNotExist:
            raise ValueError(f"City '{city_name}' does not exist.")


# Use ImportExportModelAdmin to enable import/export functionality in the admin
@admin.register(Service)
class ServiceAdmin(ImportExportModelAdmin):
    resource_class = ServiceResource
    list_display = ('name', 'service_type', 'city', 'price')  # Add any fields you want to display in the admin





class HotelResource(resources.ModelResource):
    class Meta:
        model = Hotel
        fields = ('name', 'city')  # Only include name and city
        import_id_fields = ['name'] # Explicitly exclude the 'id' field

    def before_import_row(self, row, **kwargs):
              # Lookup the city by its name and replace it with the city ID
        city_name = row.get('cityName')  # Ensure this matches the column name in your file
        try:
            city = City.objects.get(name=city_name)
            row['city'] = city.id  # Replace city name with its ID
        except City.DoesNotExist:
            raise ValueError(f"City '{city_name}' does not exist.")


@admin.register(Hotel)
class HotelAdmin(ImportExportModelAdmin):
    resource_class = HotelResource
    list_display = ('name', 'city')  # Customize the list display if needed

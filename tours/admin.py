from django.contrib import admin
from .models import City, Hotel, ServiceType, Service, GuideService, TourPackageQuote, TourDay, TourDayService, TourDayGuideService, PredefinedPackage, PredefinedPackageDay, TourPackType, ServicePrice

@admin.register(TourPackType)
class TourPackTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ('name', 'city')
    list_filter = ('city',)
    search_fields = ('name', 'city__name')

@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

class ServicePriceInline(admin.TabularInline):
    model = ServicePrice
    extra = 1

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'service_type', 'city')
    list_filter = ('service_type', 'city')
    search_fields = ('name', 'city__name', 'service_type__name')
    inlines = [ServicePriceInline]

@admin.register(ServicePrice)
class ServicePriceAdmin(admin.ModelAdmin):
    list_display = ('service', 'tour_pack_type', 'price')
    list_filter = ('tour_pack_type', 'service__service_type', 'service__city')
    search_fields = ('service__name', 'tour_pack_type__name')

@admin.register(GuideService)
class GuideServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'price')
    search_fields = ('name',)

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
    list_display = ('name', 'customer_name', 'created_at', 'tour_pack_type', 'package_reference', 'grand_total_cost')
    list_filter = ('created_at', 'tour_pack_type')
    search_fields = ('name', 'customer_name', 'package_reference')
    inlines = [TourDayInline]
    readonly_fields = ('package_reference',)

class PredefinedPackageDayInline(admin.StackedInline):
    model = PredefinedPackageDay
    extra = 1
    filter_horizontal = ('services', 'guide_services')

@admin.register(PredefinedPackage)
class PredefinedPackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'tour_pack_type')
    list_filter = ('tour_pack_type',)
    search_fields = ('name',)
    inlines = [PredefinedPackageDayInline]
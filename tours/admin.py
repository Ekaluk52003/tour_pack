# tour_quote/admin.py

from django.contrib import admin
from .models import City, Hotel, ServiceType, Service, GuideService, TourPackageQuote, TourDay, TourDayService, TourDayGuideService

@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ('name', 'city')
    list_filter = ('city',)

@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'service_type', 'city')
    list_filter = ('service_type', 'city')

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
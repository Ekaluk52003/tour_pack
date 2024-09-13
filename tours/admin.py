# admin.py

from django.contrib import admin
from .models import (
    City, Hotel, Service, GuideService, ServiceType, TourPackType,
    PredefinedTourQuote, PredefinedTourDay, PredefinedTourDayService,
    PredefinedTourDayGuideService, TourPackageQuote, TourDay,
    TourDayService, TourDayGuideService, ServicePrice
)

@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ('name', 'city')
    list_filter = ('city',)
    search_fields = ('name', 'city__name')
    autocomplete_fields = ['city']

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

class ServicePriceInline(admin.TabularInline):
    model = ServicePrice
    extra = 1
    autocomplete_fields = ['service', 'city', 'tour_pack_type']

@admin.register(ServicePrice)
class ServicePriceAdmin(admin.ModelAdmin):
    list_display = ('service', 'tour_pack_type', 'city', 'price')
    list_filter = ('tour_pack_type', 'city')
    search_fields = ('service__name', 'tour_pack_type__name', 'city__name')
    autocomplete_fields = ['service', 'tour_pack_type', 'city']

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
    list_display = ('name', 'tour_pack_type', 'created_at', 'updated_at')
    list_filter = ('tour_pack_type', 'created_at')
    search_fields = ('name', 'description')
    autocomplete_fields = ['tour_pack_type']
    inlines = [PredefinedTourDayInline]

    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'tour_pack_type')
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
from django.urls import path, include
from django.conf import settings
from . import views

urlpatterns = [
    # AI email parsing endpoint - must be before other patterns
    path('parse-email-ai/', views.parse_email_with_ai, name='parse_email_with_ai'),
    
    # put save-tour-package as it may match to tour_package_detail or other route
    path('save-tour-package/', views.save_tour_package, name='save_tour_package'),
    path('save-tour-package/<int:package_reference>/', views.save_tour_package, name='update_tour_package'),
    path('create/', views.tour_package_quote, name='tour_package_quote'),
    path('<int:package_reference>/', views.tour_package_detail, name='tour_package_detail'),
    path('<int:package_reference>/edit/', views.tour_package_edit, name='tour_package_edit'),
    path('get-city-services/<int:city_id>/', views.get_city_services, name='get_city_services'),
    path('tour-package/<int:pk>/pdf/', views.tour_package_pdf, name='tour_package_pdf'),
    path('tour-package/<int:pk>/pdf-no-cost/', views.tour_package_pdf_no_cost, name='tour_package_pdf_no_cost'),
    path('', views.tour_packages, name='tour_packages'),
    path('get-predefined-tour-quote/<int:quote_id>/', views.get_predefined_tour_quote, name='get_predefined_tour_quote'),
    path('tour-package/<int:pk>/send-email/', views.send_tour_package_email, name='send_tour_package_email'),
    path('tour-package/<str:package_reference>/duplicate/', views.duplicate_tour_package, name='duplicate_tour_package'),
    path('services/price-form/', views.service_price_form, name='service_price_form'),

    path('service-price-edit/', views.service_price_edit, name='service_price_edit'),
    path('get-service-prices/<int:service_id>/', views.get_service_prices, name='get_service_prices'),
    path('save-service-prices/', views.save_service_prices, name='save_service_prices'),
    path('service-list/', views.service_list, name='service_list'),
    
    path('tour-package/<int:pk>/export-json/', views.export_tour_package_json, name='export_tour_package_json'),
    path('tour-package/import-json/', views.import_tour_package_json, name='import_tour_package_json'),
    path('tour-package/<int:pk>/export-excel/', views.export_tourday_excel, name='export_tourday_excel'),
]


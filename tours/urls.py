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

    # Invoice URLs
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/<str:package_reference>/create/', views.create_invoice, name='create_invoice'),
    path('invoices/<int:invoice_id>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<int:invoice_id>/edit/', views.edit_invoice, name='edit_invoice'),
    path('invoices/<int:invoice_id>/pdf/', views.invoice_pdf, name='invoice_pdf'),
    path('invoices/<int:invoice_id>/payment-list/', views.payment_list_view, name='payment_list_view'),
    path('supplier-payments/', views.supplier_payment_overview, name='supplier_payment_overview'),
    path('supplier-payments/<str:supplier_name>/', views.supplier_payment_detail, name='supplier_payment_detail'),
    path('supplier-expenses/<int:expense_id>/update-status/', views.update_supplier_expense_status, name='update_supplier_expense_status'),

    # Supplier management
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/create/', views.supplier_create, name='supplier_create'),
    path('suppliers/<int:supplier_id>/edit/', views.supplier_edit, name='supplier_edit'),
    path('suppliers/<int:supplier_id>/delete/', views.supplier_delete, name='supplier_delete'),
]


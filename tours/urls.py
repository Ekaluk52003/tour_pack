from django.urls import path
from . import views

urlpatterns = [
    path('old-list', views.tour_package_list, name='tour_package_list'),
    path('create/', views.tour_package_quote, name='tour_package_quote'),
    path('<int:pk>/', views.tour_package_detail, name='tour_package_detail'),
    path('<int:pk>/edit/', views.tour_package_edit, name='tour_package_edit'),
    path('get-city-services/<int:city_id>/', views.get_city_services, name='get_city_services'),
    path('save-tour-package/', views.save_tour_package, name='save_tour_package'),
    path('tour-package/<int:pk>/pdf/', views.tour_package_pdf, name='tour_package_pdf'),
    path('', views.tour_packages, name='tour_packages'),
    path('get-predefined-tour-quote/<int:quote_id>/', views.get_predefined_tour_quote, name='get_predefined_tour_quote'),
    path('tour-package/<int:pk>/send-email/', views.send_tour_package_email, name='send_tour_package_email'),
    # Update existing package with package_id
    path('save-tour-package/<int:package_id>/', views.save_tour_package, name='update_tour_package'),
   
]
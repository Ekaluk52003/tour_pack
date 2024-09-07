from django.urls import path
from . import views

urlpatterns = [
    path('', views.tour_package_list, name='tour_package_list'),
    path('create/', views.tour_package_quote, name='tour_package_quote'),
    path('<int:pk>/', views.tour_package_detail, name='tour_package_detail'),
    path('<int:pk>/edit/', views.tour_package_edit, name='tour_package_edit'),
    path('get-city-services/<int:city_id>/', views.get_city_services, name='get_city_services'),
    path('save-tour-package/', views.save_tour_package, name='save_tour_package'),
]
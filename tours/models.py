# tour_quote/models.py

from django.db import models
from django.utils import timezone
from django.db import transaction
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.db.utils import IntegrityError

class City(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Hotel(models.Model):
    name = models.CharField(max_length=100)
    city = models.ForeignKey(City, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.name} - {self.city}"

class ServiceType(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Service(models.Model):
    name = models.CharField(max_length=200)
    service_type = models.ForeignKey(ServiceType, on_delete=models.CASCADE)
    city = models.ForeignKey(City, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.name} - {self.service_type} - {self.city}"

class TourPackType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class ServicePrice(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='prices')
    tour_pack_type = models.ForeignKey(TourPackType, on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('service', 'tour_pack_type')


class GuideService(models.Model):
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return self.name


class ReferenceID(models.Model):
    year = models.IntegerField()
    last_number = models.IntegerField(default=0)

    @classmethod
    def get_next_reference(cls):
        from datetime import datetime
        current_year = int(datetime.now().year % 100)  # Get last two digits of current year

        # Get or create reference for the current year
        reference, created = cls.objects.get_or_create(year=current_year)

        # Increment the last number and format it
        reference.last_number += 1
        reference.save()

        # Return the new reference in the format YYNNN
        return f"{str(current_year).zfill(2)}{str(reference.last_number).zfill(3)}"

class TourPackageQuote(models.Model):
    name = models.CharField(max_length=200)
    customer_name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    hotel_costs = models.JSONField(default=list)
    grand_total_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # New fields for totals
    service_grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    hotel_grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    remark = models.TextField(blank=True, null=True)
    package_reference = models.CharField(max_length=5, unique=True, blank=True, null=True)
    tour_pack_type = models.ForeignKey(TourPackType, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"{self.name} - {self.customer_name}"

    def save(self, *args, **kwargs):
        if not self.package_reference:
            # Fetch the reference from the Reference table (explained below)
            self.package_reference = ReferenceID.get_next_reference()
        super().save(*args, **kwargs)

class TourDay(models.Model):
    tour_package = models.ForeignKey(TourPackageQuote, on_delete=models.CASCADE, related_name='tour_days')
    date = models.DateField()
    city = models.ForeignKey(City, on_delete=models.CASCADE)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.tour_package} - Day {self.date}"

class TourDayService(models.Model):
    tour_day = models.ForeignKey(TourDay, on_delete=models.CASCADE, related_name='services')
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
     # Store the price at the time of creation
    price_at_booking = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.tour_day} - {self.service}"

class TourDayGuideService(models.Model):
    tour_day = models.ForeignKey(TourDay, on_delete=models.CASCADE, related_name='guide_services')
    guide_service = models.ForeignKey(GuideService, on_delete=models.CASCADE)
    price_at_booking = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.tour_day} - {self.guide_service}"


class PredefinedPackage(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    tour_pack_type = models.ForeignKey(TourPackType, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return self.name

class PredefinedPackageDay(models.Model):
    predefined_package = models.ForeignKey(PredefinedPackage, on_delete=models.CASCADE, related_name="days")
    city = models.ForeignKey(City, on_delete=models.CASCADE)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE)
    services = models.ManyToManyField(Service)
    guide_services = models.ManyToManyField(GuideService, blank=True)


    def __str__(self):
        return f"{self.predefined_package.name} - Day {self.id}"



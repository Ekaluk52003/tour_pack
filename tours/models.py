# tour_quote/models.py

from django.db import models
from django.utils import timezone
from django.db import transaction
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.db.utils import IntegrityError
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.db.models import Sum
from decimal import Decimal
from datetime import datetime

class City(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "cities"

class Hotel(models.Model):
    name = models.CharField(max_length=100)
    city = models.ForeignKey(City, on_delete=models.CASCADE)


    class Meta:
        unique_together = ['name', 'city']
        ordering = ['name']


    def clean(self):
        existing_hotel = Hotel.objects.filter(name=self.name, city=self.city).exclude(pk=self.pk).first()
        if existing_hotel:
            raise ValidationError(f"A hotel named '{self.name}' already exists in {self.city.name}.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} in {self.city.name}"

class ServiceType(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Service(models.Model):
    name = models.CharField(max_length=200)
    service_type = models.ForeignKey(ServiceType, on_delete=models.CASCADE)
    cities = models.ManyToManyField(City)

    class Meta:
        unique_together = ['name', 'service_type']
        ordering = ['name']

    def clean(self):
        existing_service = Service.objects.filter(name=self.name, service_type=self.service_type).exclude(pk=self.pk).first()
        if existing_service:
            raise ValidationError(f"A service named '{self.name}' with the service type '{self.service_type}' already exists.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        cities_str = ", ".join(city.name for city in self.cities.all())
        return f"{self.name} - {self.service_type} - ({cities_str})"

    def get_cities(self):
        return list(set([price.city for price in self.prices.all()]))

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
        unique_together = ['service', 'tour_pack_type']
        ordering = ['service__name']

    def __str__(self):
        return f"{self.service} - {self.tour_pack_type} - ${self.price}"


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
    discounts = models.JSONField(default=list)
    extra_costs = models.JSONField(default=list)
    grand_total_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # New fields for totals
    service_grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    hotel_grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    remark = models.TextField(blank=True, null=True)
    connection_ref = models.CharField(max_length=100, blank=True, null=True)
    package_reference = models.CharField(max_length=5, unique=True, blank=True, null=True)
    tour_pack_type = models.ForeignKey(TourPackType, on_delete=models.SET_NULL, null=True)
    remark2 = models.TextField(blank=True, null=True)
    remark_of_hotels = models.TextField(blank=True, null=True)
    special_note = models.TextField(blank=True, null=True)
    
    commission_rate_hotel = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    commission_amount_hotel = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    commission_rate_services = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    commission_amount_services = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    prepare_by_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='prepared_tour_packages')


    def __str__(self):
        return f"{self.name} - {self.customer_name}"

    def save(self, *args, **kwargs):
        if not self.package_reference:
            # Fetch the reference from the Reference table (explained below)
            self.package_reference = ReferenceID.get_next_reference()
        
        # Protect prepare_by_user from being changed after creation
        if self.pk is not None:  # This is an update, not a new record
            # Get the original record from database
            original = TourPackageQuote.objects.get(pk=self.pk)
            # Preserve the original prepare_by_user value
            self.prepare_by_user = original.prepare_by_user
        
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
class PredefinedTourQuote(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    # tour_pack_type = models.ForeignKey(TourPackType, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class PredefinedTourDay(models.Model):
    predefined_tour_quote = models.ForeignKey(PredefinedTourQuote, on_delete=models.CASCADE, related_name='days')
    day_number = models.PositiveIntegerField()
    city = models.ForeignKey(City, on_delete=models.CASCADE)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE)


    class Meta:
        ordering = ['day_number']

    def __str__(self):
        return f"{self.predefined_tour_quote.name} - Day {self.day_number}"

class PredefinedTourDayService(models.Model):
    tour_day = models.ForeignKey(PredefinedTourDay, on_delete=models.CASCADE, related_name='services')
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.tour_day} - {self.service}"

class PredefinedTourDayGuideService(models.Model):
    tour_day = models.ForeignKey(PredefinedTourDay, on_delete=models.CASCADE, related_name='guide_services')
    guide_service = models.ForeignKey(GuideService, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.tour_day} - {self.guide_service}"


class Agency(models.Model):
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'agencies'

    def __str__(self):
        return self.name


class InvoiceReferenceID(models.Model):
    year = models.IntegerField()
    last_number = models.IntegerField(default=0)

    @classmethod
    def get_next_reference(cls):
        current_year = datetime.now().year
        with transaction.atomic():
            ref, _ = cls.objects.select_for_update().get_or_create(year=current_year)
            ref.last_number += 1
            ref.save()
        return f"INV-{current_year}-{str(ref.last_number).zfill(3)}"

    def __str__(self):
        return f"INV-{self.year}-{str(self.last_number).zfill(3)}"


class Invoice(models.Model):
    STATUS_DRAFT = 'Draft'
    STATUS_SENT = 'Sent'
    STATUS_PAID = 'Paid'
    STATUS_OVERDUE = 'Overdue'
    STATUS_CANCELLED = 'Cancelled'

    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_SENT, 'Sent'),
        (STATUS_PAID, 'Paid'),
        (STATUS_OVERDUE, 'Overdue'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    invoice_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    tour_package = models.ForeignKey(TourPackageQuote, on_delete=models.PROTECT, related_name='invoices')
    agency = models.ForeignKey(Agency, on_delete=models.PROTECT, related_name='invoices', null=True, blank=True)
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_invoices')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.invoice_number} - {self.tour_package.customer_name}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = InvoiceReferenceID.get_next_reference()
        super().save(*args, **kwargs)

    def recalculate_total(self):
        result = self.items.aggregate(total=Sum('amount'))
        self.total_amount = result['total'] or Decimal('0.00')
        self.save(update_fields=['total_amount'])


class InvoiceItem(models.Model):
    ITEM_TYPE_HOTEL = 'Hotel'
    ITEM_TYPE_SERVICE = 'Service'
    ITEM_TYPE_GUIDE = 'Guide'
    ITEM_TYPE_EXTRA = 'Extra'
    ITEM_TYPE_DISCOUNT = 'Discount'
    ITEM_TYPE_OTHER = 'Other'

    ITEM_TYPE_CHOICES = [
        (ITEM_TYPE_HOTEL, 'Hotel'),
        (ITEM_TYPE_SERVICE, 'Service'),
        (ITEM_TYPE_GUIDE, 'Guide Service'),
        (ITEM_TYPE_EXTRA, 'Extra Cost'),
        (ITEM_TYPE_DISCOUNT, 'Discount'),
        (ITEM_TYPE_OTHER, 'Other'),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    item_type = models.CharField(max_length=20, choices=ITEM_TYPE_CHOICES, default=ITEM_TYPE_OTHER)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.description}"

    def save(self, *args, **kwargs):
        self.amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)


class Supplier(models.Model):
    name = models.CharField(max_length=200, unique=True)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class SupplierService(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='supplier_services')
    name = models.CharField(max_length=200)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    description = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['name']
        unique_together = ['supplier', 'name']

    def __str__(self):
        return f"{self.supplier.name} — {self.name}"


class SupplierExpense(models.Model):
    STATUS_PENDING = 'Pending'
    STATUS_PAID = 'Paid'
    STATUS_CANCELLED = 'Cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PAID, 'Paid'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    CATEGORY_HOTEL = 'Hotel'
    CATEGORY_TRANSPORT = 'Transport'
    CATEGORY_GUIDE = 'Guide'
    CATEGORY_OTHER = 'Other'

    CATEGORY_CHOICES = [
        (CATEGORY_HOTEL, 'Hotel'),
        (CATEGORY_TRANSPORT, 'Transport'),
        (CATEGORY_GUIDE, 'Guide'),
        (CATEGORY_OTHER, 'Other'),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='supplier_expenses')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    supplier_name = models.CharField(max_length=200)
    description = models.CharField(max_length=500)
    qty = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default=CATEGORY_OTHER)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'category', 'id']

    def __str__(self):
        return f"{self.supplier_name} - {self.description} ({self.amount})"
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase

from .models import (City, Hotel, Service, ServicePrice, ServiceType, TourDay, TourDayService,
                     TourPackageQuote, TourPackType)


class SuggestTourQuoteTest(TestCase):
    """/suggest-tour-quote/ copies whole blocks of days from past quotes that share the route."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('tester')
        cls.pack = TourPackType.objects.create(name='Standard')
        cls.cities = {n: City.objects.create(name=n) for n in ('Aaa', 'Bbb', 'Ccc', 'Ddd')}
        cls.hotels = {n: Hotel.objects.create(name=f'Hotel {n}', city=c) for n, c in cls.cities.items()}
        cls.tour_type = ServiceType.objects.create(name='Tour')
        cls.transfer_type = ServiceType.objects.create(name='Transfer')
        cls.ref = 1000

    def service(self, name, city, transfer=False):
        sv, created = Service.objects.get_or_create(
            name=name, service_type=self.transfer_type if transfer else self.tour_type)
        if created:
            sv.cities.add(self.cities[city])
            ServicePrice.objects.create(service=sv, tour_pack_type=self.pack, price=100)
        return sv

    def quote(self, stops):
        """stops = [(city, nights, hotel_city, [[service per night], ...])]; returns package_reference."""
        SuggestTourQuoteTest.ref += 1
        q = TourPackageQuote.objects.create(name='q', customer_name='c', package_reference=str(self.ref))
        day = date(2026, 1, 1)
        for city, nights, hotel, per_night in stops:
            for n in range(nights):
                td = TourDay.objects.create(tour_package=q, date=day, city=self.cities[city], hotel=self.hotels[hotel])
                for sv in (per_night[n] if n < len(per_night) else []):
                    TourDayService.objects.create(tour_day=td, service=sv, price_at_booking=100)
                day += timedelta(days=1)
        return q.package_reference

    def suggest(self, route):
        self.client.force_login(self.user)
        r = self.client.get('/suggest-tour-quote/', {'route': route, 'tour_pack_type': self.pack.id})
        self.assertEqual(r.status_code, 200)
        return r.json()['days']

    def test_whole_route_copied_from_one_quote_most_common_pattern_wins(self):
        tour_a, tour_b = self.service('Tour A', 'Bbb'), self.service('Tour B', 'Bbb')
        common = lambda t: [('Aaa', 2, 'Aaa', []), ('Bbb', 2, 'Bbb', [[t], []])]
        self.quote(common(tour_a))
        newest_common = self.quote(common(tour_a))   # same pattern twice
        self.quote(common(tour_b))                   # newer, but a rarer pattern
        days = self.suggest('Aaa:2,Bbb:2')
        self.assertEqual(len(days), 4)
        self.assertEqual({d['source_ref'] for d in days}, {newest_common})
        self.assertEqual([s['name'] for s in days[2]['services']], ['Tour A'])
        self.assertEqual((days[0]['same'], days[0]['matches']), (2, 3))

    def test_next_leg_fills_only_new_stop_and_never_changes_previous(self):
        first = self.quote([('Aaa', 2, 'Aaa', []), ('Bbb', 2, 'Bbb', [])])
        second = self.quote([('Bbb', 2, 'Ddd', []), ('Ccc', 2, 'Ccc', [])])  # its Bbb uses another hotel
        days = self.suggest('Aaa:2,Bbb:2,Ccc:2')
        self.assertEqual([d['source_ref'] for d in days], [first] * 4 + [second] * 2)
        self.assertEqual({d['hotel_name'] for d in days[2:4]}, {'Hotel Bbb'})

    def test_no_route_match_is_left_for_user(self):
        self.quote([('Aaa', 2, 'Aaa', []), ('Bbb', 2, 'Bbb', [])])
        for route in ('Aaa:3,Bbb:2', 'Bbb:2,Aaa:2', 'Ccc:2,Ddd:2'):  # nights differ / order differs / unknown pair
            days = self.suggest(route)
            self.assertTrue(all(d['mode'] == 'none' and d['manual'] and not d['services'] for d in days), route)

    def test_transfer_not_copied_when_next_leg_is_not_in_the_past_quote(self):
        transfer = self.service('Transfer to Ccc', 'Bbb', transfer=True)
        tour = self.service('Tour', 'Bbb')
        self.quote([('Aaa', 2, 'Aaa', []), ('Bbb', 2, 'Bbb', [[], [transfer, tour]])])  # Bbb's last night
        days = self.suggest('Aaa:2,Bbb:2,Ccc:2')
        self.assertEqual([s['name'] for s in days[3]['services']], ['Tour'])  # tour kept, transfer dropped
        self.assertIn('departure transfer not copied', days[3]['reason'])
        self.assertEqual(days[4]['mode'], 'none')  # Ccc has no match

    def test_arrival_transfer_kept_when_route_matches(self):
        transfer = self.service('Airport transfer', 'Aaa', transfer=True)
        self.quote([('Aaa', 2, 'Aaa', [[transfer]]), ('Bbb', 1, 'Bbb', [])])
        days = self.suggest('Aaa:2,Bbb:1')
        self.assertEqual([s['name'] for s in days[0]['services']], ['Airport transfer'])
        self.assertEqual(days[0]['reason'], '')

    def test_bad_route_is_rejected(self):
        self.client.force_login(self.user)
        r = self.client.get('/suggest-tour-quote/', {'route': 'Nowhere:2', 'tour_pack_type': self.pack.id})
        self.assertEqual(r.status_code, 400)

window.tourPackage = function() {

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    return {
        errors: {},
        name: '',
        customerName: '',
        remark: '',
        tourPackType: '',
        selectedPredefinedQuote: '',
        days: [{
            date: '',
            city: '',
            hotel: '',
            hotelCosts: [],
            services: [],
            guideServices: [],
            cityServices: {
                hotels: [],
                service_types: []
            }
        }],
        guideServices: [],
        hotelCosts: [],
        discounts: [],
        packageId: null,
        draggingIndex: null,


        initEditForm(existingData) {
            if (existingData) {
                this.packageId = existingData.id;
                this.name = existingData.name;
                this.customerName = existingData.customer_name;
                this.remark = existingData.remark || '';
                this.tourPackType = existingData.tour_pack_type;
                this.days = existingData.days.map(day => ({
                    date: day.date,
                    city: day.city,
                    hotel: day.hotel,
                    services: day.services.map(service => ({
                        type: service.type,
                        name: service.name,
                        price: parseFloat(service.price_at_booking) || 0,
                        price_at_booking: parseFloat(service.price_at_booking) || 0
                    })),
                    guideServices: day.guideServices.map(gs => ({
                        name: gs.name,
                        price: parseFloat(gs.price_at_booking) || 0,
                        price_at_booking: parseFloat(gs.price_at_booking) || 0
                    })),
                    cityServices: {
                        hotels: [],
                        service_types: []
                    }
                }));
                this.hotelCosts = existingData.hotelCosts || [];
                this.discounts = existingData.discounts || [];

                // Initialize city services for each day
                this.days.forEach((day, index) => {
                    this.updateCityServices(index);
                });
            }
        },
        initializeCityServices(index) {
            if (!this.days[index]) {
                this.days[index] = {};
            }
            if (!this.days[index].cityServices) {
                this.days[index].cityServices = { hotels: [], service_types: [] };
            }
        },
        applyPredefinedQuote() {
            if (!this.selectedPredefinedQuote) {
                alert('Please select a predefined quote first.');
                return;
            }

            fetch(`/get-predefined-tour-quote/${this.selectedPredefinedQuote}/`)
                .then(response => response.json())
                .then(data => {
                    console.log('Received predefined quote data:', data);

                    if (!this.tourPackType) {
                        this.tourPackType = data.tour_pack_type;
                    }

                    const today = new Date().toISOString().split('T')[0];
                    const newDays = data.days.map(day => ({
                        date: today,
                        city: Number(day.city),
                        hotel: Number(day.hotel), // Ensure hotel is stored as a number
                        services: day.services.map(service => ({
                            type: service.type.toLowerCase(),
                            name: Number(service.id),
                            price: service.price,
                            quantity: service.quantity
                        })),
                        guideServices: day.guideServices.map(gs => ({
                            name: Number(gs.id),
                            price: gs.price
                        })),
                        cityServices: { hotels: [], service_types: [] }
                    }));

                    console.log('Processed new days:', newDays);

                    // Append new days to the existing days array
                    this.days = [...this.days, ...newDays];

                    // Update city services and select hotels and services for each new day
                    const startIndex = this.days.length - newDays.length;
                    const updatePromises = newDays.map((_, index) => {
                        const dayIndex = startIndex + index;
                        return this.updateCityServices(dayIndex).then(() => {
                            this.selectHotelAndServices(dayIndex);
                        });
                    });

                    Promise.all(updatePromises).then(() => {
                        console.log('Final days after applying predefined quote:', this.days);
                        alert('Predefined tour quote applied successfully!');
                    });
                })
                .catch(error => {
                    console.error('Error applying predefined quote:', error);
                    alert('Error applying predefined quote. Please try again.');
                });
        },
        addHotelCost() {
            this.hotelCosts.push({ name: '', type: '', room: 1, nights: 1, price: 0, extraBedPrice: 0 });
        },

        removeHotelCost(index) {
            this.hotelCosts.splice(index, 1);
        },

        addDiscount() {
            this.discounts.push({ item: '', amount: 0 });
        },

        removeDiscount(index) {
            this.discounts.splice(index, 1);
        },

        validateForm() {
            this.errors = {};

            if (!this.name.trim()) {
                this.errors.name = "Package name is required.";
            }

            if (!this.customerName.trim()) {
                this.errors.customerName = "Customer name is required.";
            }
            if (!this.tourPackType) this.errors.tourPackType = "Tour package type is required.";

            if (this.days.length === 0) {
                this.errors.days = "At least one day is required.";
            }

            this.days.forEach((day, index) => {
                if (!day.date) {
                    this.errors[`day${index + 1}_date`] = `Date is required for Day ${index + 1}.`;
                }
                if (!day.city) {
                    this.errors[`day${index + 1}_city`] = `City is required for Day ${index + 1}.`;
                }
                if (!day.hotel) {
                    this.errors[`day${index + 1}_hotel`] = `Hotel is required for Day ${index + 1}.`;
                }
            });

            return Object.keys(this.errors).length === 0;
        },

        calculateHotelCostTotal() {
            return this.hotelCosts.reduce((total, cost) => {
                const roomCost = (parseFloat(cost.room) || 0) * (parseFloat(cost.nights) || 0) * (parseFloat(cost.price) || 0);
                const extraBedCost = (parseFloat(cost.nights) || 0) * (parseFloat(cost.extraBedPrice) || 0);
                return total + roomCost + extraBedCost;
            }, 0).toFixed(2);
        },

        calculateTotalDiscounts() {
            return this.discounts.reduce((total, discount) => {
                return total + (parseFloat(discount.amount) || 0);
            }, 0).toFixed(2);
        },

        updateGuideService(dayIndex, guideIndex) {
            const guideService = this.days[dayIndex].guideServices[guideIndex];
            const selectedGuideService = this.guideServices.find(gs => String(gs.id) === String(guideService.name));

            if (selectedGuideService) {
                guideService.price = parseFloat(selectedGuideService.price);
                console.log('Updated guide service:', guideService);
            } else {
                guideService.price = 0;
            }
        },

        updateService(dayIndex, serviceIndex) {
            const service = this.days[dayIndex].services[serviceIndex];
            const serviceOptions = this.getServiceNames(dayIndex, service.type);
            const selectedService = serviceOptions.find(option => String(option.id) === service.name);

            if (selectedService) {
                service.price = parseFloat(selectedService.price) || 0;
            } else {
                service.price = 0;
            }
        },

        getServiceNames(dayIndex, serviceType) {
            this.initializeCityServices(dayIndex);
            const cityServices = this.days[dayIndex].cityServices.service_types || [];
            if (!serviceType) {
                return [];
            }

            const serviceTypeObj = cityServices.find(st => st.type.toLowerCase() === serviceType.toLowerCase());
            if (serviceTypeObj && serviceTypeObj.services) {
                return serviceTypeObj.services.map(service => ({
                    id: service.id,
                    name: service.name,
                    price: parseFloat(service.price) || 0
                }));
            }

            return [];
        },

        calculateGrandTotal() {

            let serviceTotal = 0;
            let guideServiceTotal = 0;
            let hotelTotal = 0;

            if (!this.days || !Array.isArray(this.days)) {
                console.error('this.days is not an array:', this.days);
                return {
                    serviceGrandTotal: '0.00',
                    hotelGrandTotal: '0.00',
                    grandTotal: '0.00'
                };
            }

            this.days.forEach((day, index) => {


                if (day.services && Array.isArray(day.services)) {
                    day.services.forEach(service => {
                        console.log('Regular service:', service);
                        serviceTotal += parseFloat(service.price) || 0; // Changed from price_at_booking to price
                    });
                } else {
                    console.warn(`Day ${index + 1} services is not an array:`, day.services);
                }

                if (day.guideServices && Array.isArray(day.guideServices)) {
                    day.guideServices.forEach(guideService => {
                        console.log('Guide service:', guideService);
                        guideServiceTotal += parseFloat(guideService.price) || 0; // Changed from price_at_booking to price
                    });
                } else {
                    console.warn(`Day ${index + 1} guideServices is not an array:`, day.guideServices);
                }
            });


            hotelTotal = parseFloat(this.calculateHotelCostTotal());

            const serviceGrandTotal = serviceTotal + guideServiceTotal;
            const hotelGrandTotal = hotelTotal;
            const grandTotal = serviceGrandTotal + hotelGrandTotal;

            console.log('Calculation complete. Returning:', {
                serviceGrandTotal: serviceGrandTotal.toFixed(2),
                hotelGrandTotal: hotelGrandTotal.toFixed(2),
                grandTotal: grandTotal.toFixed(2)
            });

            return {
                serviceGrandTotal: serviceGrandTotal.toFixed(2),
                hotelGrandTotal: hotelGrandTotal.toFixed(2),
                grandTotal: grandTotal.toFixed(2)
            };
        },

        insertDayAbove(index) {
            const newDay = {
                date: '',
                city: '',
                hotel: '',
                services: [],
                guideServices: [],
                cityServices: {
                    hotels: [],
                    service_types: []
                }
            };
            this.days.splice(index, 0, newDay);
        },

        insertDayBelow(index) {
            const newDay = {
                date: '',
                city: '',
                hotel: '',
                services: [],
                guideServices: [],
                cityServices: {
                    hotels: [],
                    service_types: []
                }
            };
            this.days.splice(index + 1, 0, newDay);
        },

        removeDay(index) {
            this.days.splice(index, 1);
            // Re-initialize cityServices for all days after removal
            for (let i = index; i < this.days.length; i++) {
                this.initializeCityServices(i);
            }
        },

        addService(dayIndex) {
            this.days[dayIndex].services.push({ type: '', name: '', price: 0 });
        },

        addGuideService(dayIndex) {
            if (this.guideServices.length > 0) {
                const firstGuideService = this.guideServices[0];
                this.days[dayIndex].guideServices.push({
                    name: String(firstGuideService.id),
                    price: parseFloat(firstGuideService.price) || 0,
                    price_at_booking: parseFloat(firstGuideService.price) || 0
                });
                this.updateGuideService(dayIndex, this.days[dayIndex].guideServices.length - 1);
            }
        },

        removeService(dayIndex, serviceIndex) {
            this.days[dayIndex].services.splice(serviceIndex, 1);
        },

        removeGuideService(dayIndex, guideIndex) {
            this.days[dayIndex].guideServices.splice(guideIndex, 1);
        },

        updateServicesForPackageType() {
            if (this.tourPackType) {
                this.days.forEach((day, index) => {
                    if (day.city) {
                        this.updateCityServices(index);
                    }
                });
            } else {
                this.days.forEach(day => {
                    day.services = [];
                    day.cityServices = { hotels: [], service_types: [] };
                });
            }
        },

        updateCityServices(index) {
            return new Promise((resolve, reject) => {
                this.initializeCityServices(index);
                const cityId = this.days[index].city;


                if (cityId && this.tourPackType) {
                    fetch(`/get-city-services/${cityId}/?tour_pack_type=${this.tourPackType}`)
                        .then(response => {
                            if (!response.ok) {
                                throw new Error(`HTTP error! status: ${response.status}`);
                            }
                            return response.text(); // Get the raw response text
                        })
                        .then(text => {

                            try {
                                return JSON.parse(text); // Try to parse it as JSON
                            } catch (e) {
                                console.error('Failed to parse JSON:', e);
                                throw new Error('Invalid JSON response from server');
                            }
                        })
                        .then(data => {
                            console.log(`Received city services data for day ${index}:`, data);

                            if (data.error) {
                                console.error(`Error from server for day ${index}:`, data.error);
                                throw new Error(data.error);
                            }

                            if (data.hotels && Array.isArray(data.hotels)) {
                                this.days[index].cityServices.hotels = data.hotels;
                            } else {
                                console.warn(`No hotels data received for day ${index}`);
                                this.days[index].cityServices.hotels = [];
                            }

                            if (data.service_types && Array.isArray(data.service_types)) {
                                this.days[index].cityServices.service_types = data.service_types;
                            } else {
                                console.warn(`No service types data received for day ${index}`);
                                this.days[index].cityServices.service_types = [];
                            }

                            console.log(`Updated cityServices for day ${index}:`, this.days[index].cityServices);

                            resolve();
                        })
                        .catch(error => {
                            console.error(`Error fetching city services for day ${index}:`, error);
                            this.initializeCityServices(index);
                            reject(error);
                        });
                } else {
                    console.log(`No city ID or tour pack type for day ${index}, initializing empty city services`);
                    this.initializeCityServices(index);
                    resolve();
                }
            });
        },
        selectHotelAndServices(index) {
            const day = this.days[index];
            console.log(`Debugging selectHotelAndServices for day ${index}:`, day);

            // Select hotel
            if (day.hotel && day.cityServices.hotels && day.cityServices.hotels.length > 0) {
                console.log('Available hotels:', day.cityServices.hotels);
                console.log('Trying to select hotel with id:', day.hotel);

                // Convert both IDs to numbers for comparison
                const selectedHotel = day.cityServices.hotels.find(h => Number(h.id) === Number(day.hotel));

                console.log('Selected hotel:', selectedHotel);
                if (selectedHotel) {
                    day.hotel = selectedHotel.id;
                    console.log('Hotel selected:', day.hotel);
                } else {
                    console.log('No matching hotel found, keeping the original value:', day.hotel);
                }
            } else {
                console.log('No hotel data or cityServices.hotels available');
            }

            // Select services
            if (day.services && day.services.length > 0) {
                console.log('Selecting services for day:', index);
                day.services.forEach((service, serviceIndex) => {
                    const serviceType = day.cityServices.service_types.find(st =>
                        st.type.toLowerCase() === service.type.toLowerCase()
                    );
                    if (serviceType) {
                        const selectedService = serviceType.services.find(s => Number(s.id) === Number(service.name));
                        if (selectedService) {
                            service.name = selectedService.id;
                            service.price = selectedService.price;
                            console.log(`Service selected for day ${index}, service ${serviceIndex}:`, selectedService);
                        } else {
                            console.log(`No matching service found for day ${index}, service ${serviceIndex}. Keeping original:`, service);
                        }
                    } else {
                        console.log(`No matching service type found for day ${index}, service ${serviceIndex}.`);
                    }
                });
            } else {
                console.log(`No services to select for day ${index}`);
            }

            // Select guide services
            if (day.guideServices && day.guideServices.length > 0) {
                console.log('Selecting guide services for day:', index);
                day.guideServices.forEach((guideService, guideIndex) => {
                    const selectedGuideService = this.guideServices.find(gs => Number(gs.id) === Number(guideService.name));
                    if (selectedGuideService) {
                        guideService.name = selectedGuideService.id;
                        guideService.price = selectedGuideService.price;
                        console.log(`Guide service selected for day ${index}, guide service ${guideIndex}:`, selectedGuideService);
                    } else {
                        console.log(`No matching guide service found for day ${index}, guide service ${guideIndex}. Keeping original:`, guideService);
                    }
                });
            } else {
                console.log(`No guide services to select for day ${index}`);
            }

            console.log(`Final day ${index} data after selection:`, day);
        },
        dragStart(event, index) {
            this.draggingIndex = index;
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('text/plain', index);

            let dragGhost = event.target.cloneNode(true);
            dragGhost.classList.add('drag-ghost');
            dragGhost.style.position = 'absolute';
            dragGhost.style.top = '-1000px';
            document.body.appendChild(dragGhost);
            event.dataTransfer.setDragImage(dragGhost, 20, 20);

            setTimeout(() => {
                document.body.removeChild(dragGhost);
            }, 0);
        },

        dragEnd(event) {
            this.draggingIndex = null;
            document.querySelectorAll('.day-container').forEach(el => {
                el.classList.remove('drop-zone-active');
            });
        },

        drop(event, index) {
            event.preventDefault();
            const fromIndex = parseInt(event.dataTransfer.getData('text/plain'));
            const toIndex = index;

            if (fromIndex !== toIndex) {
                const movedDay = this.days.splice(fromIndex, 1)[0];
                this.days.splice(toIndex, 0, movedDay);
                this.updateDayNumbers();
            }

            this.draggingIndex = null;
            document.querySelectorAll('.day-container').forEach(el => {
                el.classList.remove('drop-zone-active');
            });
        },


        // Save the tour package data to the backend
        saveTourPackage() {
            if (!this.validateForm()) {
                alert("Please correct the errors before submitting.");
                return;
            }

            const totals = this.calculateGrandTotal();
            
            const data = {
                name: this.name,
                customer_name: this.customerName,
                remark: this.remark,
                tour_pack_type: this.tourPackType,
                days: this.days.map(day => ({
                    date: day.date,
                    city: day.city,
                    hotel: day.hotel,
                    services: day.services.map(service => ({
                        name: service.name,
                        price_at_booking: service.price_at_booking
                    })),
                    guide_services: day.guideServices.map(gs => ({
                        name: gs.name,
                        price_at_booking: gs.price_at_booking
                    }))
                })),
                hotelCosts: this.hotelCosts,
                discounts: this.discounts,
                total_cost: this.calculateGrandTotal()
            };

            fetch('/save-tour-package/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify(data)
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    alert('Tour package saved successfully!');
                    window.location.href = `/${data.package_id}/`;
                } else {
                    alert('Error saving tour package');
                }
            });
        },

        addDay() {
            this.days.push({
                date: '',
                city: '',
                hotel: '',
                services: [],
                guideServices: [],
                cityServices: { hotels: [], service_types: [] } // Initialize with empty arrays
            });
        },
        applyPredefinedPackage(packageId) {
            if (!packageId) return;

            fetch(`/get-predefined-package/${packageId}/`, {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': getCookie('csrftoken')
                },
            })
            .then(response => response.json())
            .then(data => {
                const today = new Date().toISOString().slice(0, 10);
                // Append the predefined days to the current days array
                const newDays = data.days.map(day => ({
                    date: today,
                    city: day.city,
                    hotel: String(day.hotel),
                    services: day.services.map(service => ({
                        type: 'tour',
                        name: String(service.name),
                        price: service.price
                    })),
                    guideServices: day.guideServices.map(guideService => ({
                        name: String(guideService.name),
                        price: guideService.price
                    })),
                    cityServices: { hotels: [], service_types: [] }
                }));

                // Append new predefined days to the existing days array
                this.days.push(...newDays);

                // Trigger city services update for the new days
                const startIndex = this.days.length - newDays.length;
                for (let i = startIndex; i < this.days.length; i++) {
                    this.updateCityServices(i);
                }
            })
            .catch(error => {
                console.error('Error applying predefined package:', error);
            });
        },


    };
  }

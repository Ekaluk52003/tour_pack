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
        name: '',
        customerName: '',
        remark: '',
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
        hotelCosts: [],  // Array to manage hotel costs
        packageId: null,  // This will hold the package ID for updates
        draggingIndex: null,
        // Initialize the form with existing data for editing
        initEditForm(existingData) {
            console.log("initEditForm called with data:", existingData);
            if (existingData) {
                this.packageId = existingData.id;  // Assign the package ID
                this.name = existingData.name;
                this.customerName = existingData.customer_name;
                this.remark = existingData.remark || '';
                this.days = existingData.days.map(day => ({
                    ...day,
                    hotel: String(day.hotel),  // Ensure hotel ID is a string
                    services: day.services.map(service => ({
                        ...service,
                        name: String(service.name),  // Ensure service name (ID) is a string
                        price: service.price || 0  // Ensure price is populated or set to 0
                    })),
                    guideServices: day.guideServices.map(gs => ({
                        ...gs,
                        name: String(gs.name),
                        price: parseFloat(gs.price),
                        price_at_booking: parseFloat(gs.price_at_booking)
                    })),
                    cityServices: {
                        hotels: [],
                        service_types: []
                    }
                }));

                // Load hotel costs (assuming existingData.hotelCosts is the list of hotel costs)
                this.hotelCosts = existingData.hotelCosts || [];

                // Load city services for each day
                this.days.forEach((day, index) => this.updateCityServices(index));
            }
        },

        // Function to add a hotel cost entry
        addHotelCost() {
            this.hotelCosts.push({ name: '', type: '', room: 1, nights: 1, price: 0 });
        },

        // Function to remove a hotel cost entry by index
        removeHotelCost(index) {
            this.hotelCosts.splice(index, 1);
        },

        // Function to calculate the total hotel cost
        calculateHotelCostTotal() {
            let total = 0;
            this.hotelCosts.forEach(hotelCost => {
                total += (hotelCost.room || 1) * (hotelCost.nights || 1) * (hotelCost.price || 0);
            });
            return total.toFixed(2);
        },
        updateGuideService(dayIndex, guideIndex) {
            const guideService = this.days[dayIndex].guideServices[guideIndex];
            const selectedGuideService = this.guideServices.find(gs => String(gs.id) === String(guideService.name));

            if (selectedGuideService) {
                guideService.price = parseFloat(selectedGuideService.price);
                // if (!guideService.price_at_booking) {
                //     guideService.price_at_booking = guideService.price;
                // }
                console.log('Updated guide service:', guideService);  // Debugging line
            } else {
                guideService.price = 0;
                // guideService.price_at_booking = 0;
                // console.log('Reset guide service prices to 0');  // Debugging line
            }
        },
        updateService(dayIndex, serviceIndex) {
            const service = this.days[dayIndex].services[serviceIndex];
            const serviceOptions = this.getServiceNames(dayIndex, service.type);
            const selectedService = serviceOptions.find(option => String(option.id) === service.name);

            if (selectedService) {
                service.price = parseFloat(selectedService.price) || 0;
                // if (!service.price_at_booking) {
                //     service.price_at_booking = service.price;
                // }
            } else {
                service.price = 0;
                // service.price_at_booking = 0;
            }
        },

        // Function to calculate the grand total for services, guide services, and hotel costs
        calculateGrandTotal() {
            let serviceTotal = 0;
            let guideServiceTotal = 0;
            let hotelTotal = 0;

            // Calculate total for services
            this.days.forEach(day => {
                day.services.forEach(service => {
                    const price = parseFloat(service.price) || 0;
                    serviceTotal += price;
                });
            });

            // Calculate total for guide services
            this.days.forEach(day => {
                day.guideServices.forEach(guideService => {
                    const guideServiceObj = this.guideServices.find(gs => gs.id == guideService.name);
                    const price = guideServiceObj ? parseFloat(guideServiceObj.price) : 0;
                    guideServiceTotal += price;
                });
            });

            // Calculate total for hotel costs
            this.hotelCosts.forEach(hotelCost => {
                const room = parseFloat(hotelCost.room) || 1;
                const nights = parseFloat(hotelCost.nights) || 1;
                const price = parseFloat(hotelCost.price) || 0;
                hotelTotal += room * nights * price;
            });

            const serviceGrandTotal = serviceTotal + guideServiceTotal;
            const hotelGrandTotal = hotelTotal;
            const grandTotal = serviceTotal + guideServiceTotal + hotelTotal;

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

        // Remove a day by index
        removeDay(index) {
            this.days.splice(index, 1);
        },

        // Add a service to a day
        addService(dayIndex) {
            this.days[dayIndex].services.push({ type: '', name: '', price: 0 });
        },

        // Add a guide service to a day
        addGuideService(dayIndex) {
            this.days[dayIndex].guideServices.push({
              name: '',
              price: 0,
              price_at_booking: 0
            });
          },

        // Remove a service from a day
        removeService(dayIndex, serviceIndex) {
            this.days[dayIndex].services.splice(serviceIndex, 1);
        },

        // Remove a guide service from a day
        removeGuideService(dayIndex, guideIndex) {
            this.days[dayIndex].guideServices.splice(guideIndex, 1);
        },

        // Update service details based on selection
        updateService(dayIndex, serviceIndex) {
            const service = this.days[dayIndex].services[serviceIndex];
            const serviceOptions = this.getServiceNames(dayIndex, service.type);
            const selectedService = serviceOptions.find(option => option.id == service.name);

            if (selectedService) {
                service.price = selectedService.price || 0;
            } else {
                service.price = 0;
            }
        },

        // Update available services and hotels based on selected city
        updateCityServices(index) {
            const cityId = this.days[index].city;
            if (cityId) {
                fetch(`/get-city-services/${cityId}/`)
                    .then(response => response.json())
                    .then(data => {
                        this.days[index].cityServices = data;

                        // After loading city services, ensure the hotel and service are properly selected
                        const selectedHotel = this.days[index].hotel;
                        const selectedServices = this.days[index].services.map(service => service.name);

                        // Check if the selected hotel is in the fetched list, if not, clear it
                        const hotelFound = data.hotels.some(hotel => hotel.id == selectedHotel);
                        if (!hotelFound) {
                            this.days[index].hotel = '';
                        }

                        // For each service, check if it is in the fetched list, if not, clear it
                        this.days[index].services.forEach(service => {
                            const serviceFound = data.service_types.some(st =>
                                st.services.some(s => s.id == service.name)
                            );
                            if (!serviceFound) {
                                service.name = '';
                            }
                        });
                    });
            } else {
                this.days[index].cityServices = { hotels: [], service_types: [] };
                this.days[index].hotel = '';
                this.days[index].services = [];
            }
        },

        // Get service names based on the selected service type
        getServiceNames(dayIndex, serviceType) {
            const cityServices = this.days[dayIndex]?.cityServices?.service_types || [];
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





        dragStart(event, index) {
            this.draggingIndex = index;
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('text/plain', index);

            // Create a custom drag image
            let dragGhost = event.target.cloneNode(true);
            dragGhost.classList.add('drag-ghost');
            dragGhost.style.position = 'absolute';
            dragGhost.style.top = '-1000px';
            document.body.appendChild(dragGhost);
            event.dataTransfer.setDragImage(dragGhost, 20, 20);

            // Remove the ghost element after the drag operation
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
            const data = {
                name: this.name,
                customer_name: this.customerName,
                remark: this.remark,
                days: this.days.map(day => ({
                    date: day.date,
                    city: day.city,
                    hotel: day.hotel,
                    services: day.services.map(service => ({
                        type: service.type,
                        name: service.name,
                        price_at_booking: service.price
                    })),
                    guide_services: day.guideServices.map(gs => ({
                        name: gs.name,  // ID of the guide service
                        price_at_booking: gs.price
                    }))
                })),
                hotelCosts: this.hotelCosts,
                total_cost: this.calculateGrandTotal()
            };

            const url = this.packageId
                ? `/save-tour-package/${this.packageId}/`
                : '/save-tour-package/';

            fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify(data)
            })
            .then(response => {
                if (response.ok) {
                    alert('Tour package saved successfully!');
                    window.location.href = '/';  // Redirect to list view
                } else {
                    alert('Error saving tour package');
                }
            });
        },
        applyPredefinedPackage(packageId) {
     
            if (!packageId) return;

            fetch(`/get-predefined-package/${packageId}/`)
                .then(response => response.json())
                .then(data => {

                    const today = new Date().toISOString().slice(0, 10);
                    // Append the predefined days to the current days array
                    const newDays = data.days.map(day => ({
                        date: today, // Allow the user to set the date
                        city: day.city,
                        hotel: String(day.hotel),  // Convert hotel ID to string
                        services: day.services.map(service => ({
                            type: 'tour',  // Assuming predefined services are of type 'tour' or 'transfer'
                            name: String(service.name),  // Convert service ID to string
                            price: service.price
                        })),
                        guideServices: day.guideServices.map(guideService => ({
                            name: String(guideService.name),  // Convert guide service ID to string
                            price: guideService.price
                        })),
                        cityServices: { hotels: [], service_types: [] }  // This will be populated after selecting the city
                    }));

                    // Append new predefined days to the existing days array
                    this.days.push(...newDays);

                    // Trigger city services update for the new days
                    const startIndex = this.days.length - newDays.length;
                    for (let i = startIndex; i < this.days.length; i++) {
                        this.updateCityServices(i);
                    }
                });
        }
    };
  }

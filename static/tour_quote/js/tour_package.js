window.tourPackage = function () {
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";");
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === name + "=") {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }




  return {


    errors: {},
    name: "",
    customerName: "",
    remark: "",
    remark2: "",
    remark_of_hotels: "",
    tourPackType: "",
    selectedPredefinedQuote: "",
    commission_rate_hotel: 0,
    commission_rate_services: 0,
    days: [
      {
        date: "",
        city: "",
        hotel: "",
        hotelCosts: [],
        services: [],
        guideServices: [],
        cityServices: {
          hotels: [],
          service_types: [],
        },
      },
    ],
    guideServices: [],
    hotelCosts: [],
    discounts: [],
    extraCosts: [],
    packageId: null,
    packageReference: null,
    isSuperUser: false,


    updateHotelDateDisplay(cost) {
      if (!cost.date) return;

      // Check if input is in the format "STARTDATE to ENDDATE"
      if (cost.date.includes('to')) {
        const [startDate, endDate] = cost.date.split('to').map(d => d.trim());

        // If start and end dates are the same day
        if (startDate === endDate) {
          cost.date = `${startDate}\nto\n${endDate}`;
        }
        // If different days but same month and year
        else {
          const startParts = startDate.match(/(\d{2})-([A-Za-z]{3})-(\d{2})/);
          const endParts = endDate.match(/(\d{2})-([A-Za-z]{3})-(\d{2})/);

          if (startParts && endParts &&
              startParts[2] === endParts[2] &&
              startParts[3] === endParts[3]) {
            cost.date = `${startParts[1]}-${endParts[1]}-${startParts[2]}-${startParts[3]}`;
          } else {
            cost.date = `${startDate}\nto\n${endDate}`;
          }
        }
      }
    },


    fetchHotelsFromTourDays() {
      // Create a map to store hotels and their nights
      const hotelCounts = new Map();

      // Count nights for each hotel
      this.days.forEach(day => {
        if (!day.hotel || !day.date) return;

        const hotelName = day.cityServices.hotels.find(h => h.id.toString() === day.hotel)?.name;
        if (!hotelName) return;

        if (hotelCounts.has(hotelName)) {
          hotelCounts.set(hotelName, hotelCounts.get(hotelName) + 1);
        } else {
          hotelCounts.set(hotelName, 1);
        }
      });

      // Create fresh hotel cost entries
      const newHotelCosts = Array.from(hotelCounts).map(([hotelName, nights]) => ({
        date: '',
        name: hotelName,
        type: '',
        room: 1,
        nights: nights,
        price: '0',
        extraBedPrice: '0',
        _tempDisplay: {  // Add temporary display values that will trigger the x-data bindings
          priceDisplay: '0.00',
          extraBedPriceDisplay: '0.00'
        }
      }));

      // Update the hotel costs array
      this.hotelCosts = newHotelCosts;

      // Force a reactive update and wait for the next tick to ensure template is updated
      this.$nextTick(() => {
        // Force all inputs to update their display values
        const inputs = document.querySelectorAll('input[x-model="displayValue"]');
        inputs.forEach(input => {
          input.dispatchEvent(new Event('input', { bubbles: true }));
        });

        // Recalculate totals
        this.calculateHotelCostTotal();
        this.calculateGrandTotal();
      });
    },
    // Update the calculateHotelCostTotal method to ensure proper calculation
    calculateHotelCostTotal() {
      return this.hotelCosts.reduce((total, cost) => {
        const roomCost = (parseFloat(cost.room) || 0) *
                        (parseFloat(cost.nights) || 0) *
                        (parseFloat(cost.price) || 0);
        const extraBedCost = (parseFloat(cost.nights) || 0) *
                            (parseFloat(cost.extraBedPrice) || 0);
        return total + roomCost + extraBedCost;
      }, 0).toFixed(2);
    },

    initEditForm(existingData, isSuperUser) {
      this.isSuperUser = isSuperUser;
      if (existingData) {
        this.packageReference = existingData.package_reference;
        this.name = existingData.name;
        this.customerName = existingData.customer_name;
        this.remark = existingData.remark || "";
        this.remark2 = existingData.remark2 || "";
        this.remark_of_hotels = existingData.remark_of_hotels || "";
        this.tourPackType = existingData.tour_pack_type;
        this.commission_rate_hotel = existingData.commission_rate_hotel || 0;
        this.commission_rate_services =
          existingData.commission_rate_services || 0;
        this.days = existingData.days.map((day) => ({
          date: day.date,
          city: day.city.toString(), // Ensure city is a string
          hotel: day.hotel.toString(), // Ensure hotel is a string
          services: day.services.map((service) => ({
            type: service.type || "",
            name: (service.name || "").toString(),
            price: parseFloat(service.price_at_booking) || 0,
            price_at_booking: parseFloat(service.price_at_booking) || 0,
          })),
          guideServices: day.guideServices.map((gs) => ({
            name: gs.name.toString(), // Ensure guide service name is a string
            price: parseFloat(gs.price_at_booking) || 0,
            price_at_booking: parseFloat(gs.price_at_booking) || 0,
          })),
          cityServices: {
            hotels: [],
            service_types: [],
          },
        }));
        this.hotelCosts = existingData.hotelCosts || [];
        this.discounts = existingData.discounts || [];
        this.extraCosts  = existingData.extraCosts  || [];

        this.initializeCityServicesForAllDays();
      }
    },

    initializeCityServicesForAllDays() {
      const promises = this.days.map((day, index) =>
        this.updateCityServices(day)
      );
      Promise.all(promises).then(() => {
        this.days.forEach((day) => this.selectCorrectOptions(day));
      });
    },



    init() {
      // Initialize with one day
      if (this.days.length === 0) {
        this.addDay();
      }
      // Initialize guide services
      this.guideServices = window.guideServicesData || [];


      if (this.guideServices.length === 0) {
        console.warn('No guide services available');
      } else {
        console.log('Guide services loaded:', this.guideServices);
      }

      // Fetch guide services if they're not already available
    },

    addDay() {
      this.days.push({
        date: "",
        city: "",
        hotel: "",
        services: [],
        guideServices: [],
        cityServices: { hotels: [], service_types: [] },
      });
    },

    removeDay(index) {
      this.days.splice(index, 1);
    },

    addService(day) {
      if (!day || !Array.isArray(day.services)) {
        console.log("Invalid day object or services array");
        return;
      }
      day.services.push({ type: "", name: "", price: 0 });
    },

    removeService(day, serviceIndex) {
      if (!day || !Array.isArray(day.services)) {
        console.log("Invalid day object or services array");
        return;
      }
      day.services.splice(serviceIndex, 1);
    },

    addGuideService(day) {
      if (!day.guideServices) {
        day.guideServices = [];
      }
      if (this.guideServices && this.guideServices.length > 0) {
        const firstGuideService = this.guideServices[0];
        day.guideServices.push({
          name: firstGuideService.id.toString(),
          price: parseFloat(firstGuideService.price) || 0,
        });
        this.updateGuideService(day.guideServices[day.guideServices.length - 1]);
      } else {
        console.log("No guide services available");
      }
    },

    removeGuideService(day, guideIndex) {
      day.guideServices.splice(guideIndex, 1);
    },

    insertDayBelow(index) {
      const previousDay = this.days[index];
      let newDate;

      if (previousDay && previousDay.date) {
        // Create a new Date object from the previous day's date and increment it by one day
        newDate = new Date(previousDay.date);
        newDate.setDate(newDate.getDate() + 1);
      } else {
        // If there's no previous day or it has no date, use tomorrow's date
        newDate = new Date();
        newDate.setDate(newDate.getDate() + 1);
      }

      // Format the new date as YYYY-MM-DD
      const formattedDate = newDate.toISOString().split('T')[0];

      const newDay = {
        date: formattedDate,
        city: "",
        hotel: "",
        services: [],
        guideServices: [],
        cityServices: {
          hotels: [],
          service_types: [],
        },
      };
      this.days.splice(index + 1, 0, newDay);

        // Update all subsequent days' dates
  for (let i = index + 2; i < this.days.length; i++) {
    if (this.days[i].date) {
      // Create date object for the previous day
      const prevDate = new Date(this.days[i - 1].date);
      // Increment by one day
      prevDate.setDate(prevDate.getDate() + 1);
      // Update the current day's date
      this.days[i].date = prevDate.toISOString().split('T')[0];
    }
  }

      this.days = [...this.days];

    },

    updateServicesForPackageType() {
      if (this.tourPackType) {
        const promises = this.days.map((day) => {
          if (day.city) {
            return this.updateCityServices(day);
          }
          return Promise.resolve();
        });

        Promise.all(promises).then(() => {
          this.days.forEach((day) => {
            this.selectCorrectOptions(day);
            day.services.forEach((service) => this.updateService(day, service));
            day.guideServices.forEach((guideService) => this.updateGuideService(guideService));
          });
          // Trigger a recalculation of all costs
          this.$nextTick(() => {
            this.calculateGrandTotal();
          });
        });
      } else {
        this.days.forEach((day) => {
          day.services = [];
          day.guideServices = [];
          day.cityServices = { hotels: [], service_types: [] };
        });
        // Trigger a recalculation of all costs
        this.$nextTick(() => {
          this.calculateGrandTotal();
        });
      }
    },

    updateCityServices(day) {
      return new Promise((resolve, reject) => {
        if (day.city && this.tourPackType) {
          fetch(
            `/get-city-services/${
              day.city
            }/?tour_pack_type=${encodeURIComponent(this.tourPackType)}`
          )
            .then((response) => response.json())
            .then((data) => {
              day.cityServices = {
                hotels: data.hotels || [],
                service_types: data.service_types || [],
              };
              // Update hotel costs when city services are updated
              this.updateHotelCosts(day);
              resolve();
            })
            .catch((error) => {
              console.error("Error fetching city services:", error);
              day.cityServices = { hotels: [], service_types: [] };
              reject(error);
            });
        } else {
          day.cityServices = { hotels: [], service_types: [] };
          resolve();
        }
      });
    },

    updateHotelCosts(day) {
      const selectedHotel = day.cityServices.hotels.find(h => h.id.toString() === day.hotel);
      if (selectedHotel) {
        const existingCost = this.hotelCosts.find(cost => cost.name === selectedHotel.name);
        if (existingCost) {
          existingCost.price = parseFloat(selectedHotel.price) || 0;
        } else {
          this.hotelCosts.push({
            name: selectedHotel.name,
            type: selectedHotel.type || '',
            room: 1,
            nights: 1,
            price: parseFloat(selectedHotel.price) || 0,
            extraBedPrice: 0,
          });
        }
      }
    },

    selectCorrectOptions(day) {
      console.log("Selecting correct options for day:", day);

      // Select the correct hotel
      if (day.hotel) {
        const selectedHotel = day.cityServices.hotels.find(
          (h) => h.id.toString() === day.hotel
        );
        if (selectedHotel) {
          console.log("Selected hotel:", selectedHotel);
          day.hotel = selectedHotel.id.toString();
        } else {
          console.log("Hotel not found:", day.hotel);
        }
      }

      // Select the correct services
      // Select the correct services
      day.services.forEach((service) => {
        console.log("Processing service for selection:", service);
        const serviceType = day.cityServices.service_types.find(
          (st) => st.type.toLowerCase() === service.type.toLowerCase()
        );
        if (serviceType) {
          console.log("Found service type:", serviceType);
          const selectedService = serviceType.services.find(
            (s) => s.id.toString() === service.name
          );
          if (selectedService) {
            console.log("Selected service:", selectedService);
            service.name = selectedService.id.toString();
            service.price = parseFloat(selectedService.price) || 0;
          } else {
            console.log("Service not found:", service.name);
          }
        } else {
          console.log("Service type not found:", service.type);
        }
      });

      // Select the correct guide services
      day.guideServices.forEach((guideService) => {
        console.log("Processing guide service for selection:", guideService);
        const selectedGuideService = this.guideServices.find(
          (gs) => gs.id.toString() === guideService.name
        );
        if (selectedGuideService) {
          console.log("Selected guide service:", selectedGuideService);
          guideService.name = selectedGuideService.id.toString();
          guideService.price = parseFloat(selectedGuideService.price) || 0;
        } else {
          console.log("Guide service not found:", guideService.name);
        }
      });
    },
    getServiceNames(day, serviceType) {
        if (!day || !serviceType) {
            console.log("No day or service type provided.");
            return [];
        }

        const serviceTypeObj = day.cityServices.service_types.find(st => st.type.toLowerCase() === serviceType.toLowerCase());
        if (serviceTypeObj && Array.isArray(serviceTypeObj.services)) {
            console.log("Found services for type:", serviceType, serviceTypeObj.services);
            return serviceTypeObj.services;
        }

        console.log("No services found for type:", serviceType);
        return [];
    },
    updateService(day, service) {
      const serviceNames = this.getServiceNames(day, service.type);
      const selectedService = serviceNames.find(s => s.id.toString() === service.name);
      if (selectedService) {
        service.price = parseFloat(selectedService.price) || 0;
        service.price_at_booking = parseFloat(selectedService.price) || 0;
      } else {
        service.price = 0;
        service.price_at_booking = 0;
      }
    },

    updateGuideService(guideService) {
      const selectedGuideService = this.guideServices.find(
        (gs) => gs.id.toString() === guideService.name
      );
      if (selectedGuideService) {
        guideService.price = parseFloat(selectedGuideService.price) || 0;
        guideService.price_at_booking = parseFloat(selectedGuideService.price) || 0;
      } else {
        guideService.price = 0;
        guideService.price_at_booking = 0;
      }
      // No need for explicit recalculation, Alpine.js will handle it
    },

    updateCityServices(day) {
        return new Promise((resolve, reject) => {
            if (day.city && this.tourPackType) {
                fetch(`/get-city-services/${day.city}/?tour_pack_type=${encodeURIComponent(this.tourPackType)}`)
                    .then(response => response.json())
                    .then(data => {
                        day.cityServices = {
                            hotels: data.hotels || [],
                            service_types: data.service_types || []
                        };
                        resolve();
                    })
                    .catch(error => {
                        console.error('Error fetching city services:', error);
                        day.cityServices = { hotels: [], service_types: [] };
                        reject(error);
                    });
            } else {
                day.cityServices = { hotels: [], service_types: [] };
                resolve();
            }
        });
    },


    applyPredefinedQuote() {
      if (!this.selectedPredefinedQuote) {
        alert("Please select a predefined quote first.");
        return;
      }

      if (!this.tourPackType) {
        alert("Please select a Tour Package Type before applying a predefined quote.");
        return;
      }

       // Check if there are existing days with missing dates
  const hasInvalidDays = this.days.some(day => !day.date);
  if (hasInvalidDays) {
    const confirmContinue = confirm(
      "Some existing days don't have dates selected. Would you like to:\n\n" +
      "• Click 'OK' to remove incomplete days and apply the predefined quote\n" +
      "• Click 'Cancel' to go back and fill in missing dates"
    );

    if (confirmContinue) {
      // Remove days with missing dates
      this.days = this.days.filter(day => day.date);
    } else {
      return;
    }
  }

      // Add the tour pack type to the request
      const url = `/get-predefined-tour-quote/${this.selectedPredefinedQuote}/?tour_pack_type=${encodeURIComponent(this.tourPackType)}`;

      fetch(url)
        .then((response) => response.json())
        .then(async (data) => {
          // Find the date of the last existing day, or use today's date if no days exist
          let currentDate;
          if (this.days.length > 0) {
            const lastDay = this.days[this.days.length - 1];
            currentDate = new Date(lastDay.date);
          } else {
            currentDate = new Date();
          }

          // Process each day sequentially using async/await
          for (const dayData of data.days) {
            // Increment the date by 1 day
            currentDate.setDate(currentDate.getDate() + 1);
            const formattedDate = currentDate.toISOString().split('T')[0];

            const newDay = {
              date: formattedDate,
              city: dayData.city.toString(),
              hotel: dayData.hotel.toString(),
              services: [],
              guideServices: [],
              cityServices: { hotels: [], service_types: [] }
            };

            // First update city services to ensure we have the correct data
            await this.updateCityServices(newDay);

            // Now add the services after we have the city services data
            if (dayData.services) {
              dayData.services.sort((a, b) => a.order - b.order);
              for (const service of dayData.services) {
                // Find the service type from available city services
                const serviceTypeData = newDay.cityServices.service_types.find(
                  st => st.type.toLowerCase() === service.type.toLowerCase()
                );

                if (serviceTypeData) {
                  // Find the specific service within the type
                  const availableService = serviceTypeData.services.find(
                    s => s.id.toString() === service.id.toString()
                  );

                  if (availableService) {
                    newDay.services.push({
                      type: service.type.toLowerCase(),
                      name: service.id.toString(),
                      price: parseFloat(availableService.price) || 0,
                      price_at_booking: parseFloat(availableService.price) || 0,
                      quantity: service.quantity || 1,
                      order: service.order
                    });
                  }
                }
              }
            }

            // Add guide services
            if (dayData.guideServices) {
              for (const gs of dayData.guideServices) {
                const guideService = this.guideServices.find(
                  g => g.id.toString() === gs.id.toString()
                );
                if (guideService) {
                  newDay.guideServices.push({
                    name: gs.id.toString(),
                    price: parseFloat(guideService.price) || 0,
                    price_at_booking: parseFloat(guideService.price) || 0
                  });
                }
              }
            }

            this.days.push(newDay);
          }

          // Final update of all days
          await Promise.all(this.days.map(day => this.selectCorrectOptions(day)));

          // Recalculate totals
          this.calculateGrandTotal();
        })
        .catch((error) => {
          console.error("Error applying predefined quote:", error);
          alert("Error applying predefined quote. Please try again.");
        });
    },


    updateAndSelectServices(day) {
      if (day.city && this.tourPackType) {
        fetch(
          `/get-city-services/${day.city}/?tour_pack_type=${this.tourPackType}`
        )
          .then((response) => response.json())
          .then((data) => {
            day.cityServices = {
              hotels: data.hotels || [],
              service_types: data.service_types || [],
            };

            // Select the correct hotel
            if (day.hotel) {
              const selectedHotel = day.cityServices.hotels.find(
                (h) => h.id === day.hotel
              );
              if (selectedHotel) {
                day.hotel = selectedHotel.id;
              }
            }

            // Select the correct services
            day.services.forEach((service) => {
              const serviceType = day.cityServices.service_types.find(
                (st) => st.type.toLowerCase() === service.type.toLowerCase()
              );
              if (serviceType) {
                const selectedService = serviceType.services.find(
                  (s) => s.id === service.name
                );
                if (selectedService) {
                  service.name = selectedService.id;
                  service.price = parseFloat(selectedService.price) || 0;
                }
              }
            });

            // Select the correct guide services
            day.guideServices.forEach((guideService) => {
              const selectedGuideService = this.guideServices.find(
                (gs) => gs.id === guideService.name
              );
              if (selectedGuideService) {
                guideService.name = selectedGuideService.id;
                guideService.price =
                  parseFloat(selectedGuideService.price) || 0;
              }
            });
          })
          .catch((error) => {
            console.error("Error fetching city services:", error);
            day.cityServices = { hotels: [], service_types: [] };
          });
      } else {
        day.cityServices = { hotels: [], service_types: [] };
      }
    },

    dragStart(event, index) {

      event.target.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", index);
      this.isDragging = true;
    },

    dragEnd(event) {
      event.target.classList.remove("dragging"); // Remove dragging class
      console.log("Dragging ended, class removed:", event.target); // Debugging
  },
    dragEnter(event) {
      if (!event.target.classList.contains("border-dashed")) {
        event.target.classList.add("border-dashed", "border-blue-500");
      }
    },
    dragOver(event) {

        // Scroll when near the top or bottom of the viewport
      const scrollMargin = 300; // Pixels from the edge to trigger scroll
      const scrollSpeed = 20; // Speed of scrolling


      if (event.clientY < scrollMargin) {
          // Near the top
          window.scrollBy(0, -scrollSpeed);
      } else if (window.innerHeight - event.clientY < scrollMargin) {
          // Near the bottom
          window.scrollBy(0, scrollSpeed);
      }

      event.preventDefault(); // Prevent default to allow drop
  },
    dragLeave(event) {

      if (
        !event.relatedTarget ||
        !event.currentTarget.contains(event.relatedTarget)
      ) {
        event.target.classList.remove("border-dashed", "border-blue-500");
      }
    },

    drop(event, toIndex) {
      event.preventDefault();

      const fromIndex = parseInt(event.dataTransfer.getData("text/plain"));

      if (fromIndex !== toIndex) {
          const movedDay = this.days.splice(fromIndex, 1)[0];
          this.days.splice(toIndex, 0, movedDay);
      }

      this.isDragging = false;

      event.target.classList.remove("border-dashed", "border-blue-500");
  },

    //#############################################this is for submit create#####################################################################

    validateForm() {
      this.errors = {};

      if (!this.name.trim()) {
        this.errors.name = "Package name is required.";
      }

      if (!this.customerName.trim()) {
        this.errors.customerName = "Customer name is required.";
      }
      if (!this.tourPackType)
        this.errors.tourPackType = "Tour package type is required.";

      if (this.days.length === 0) {
        this.errors.days = "At least one day is required.";
      }

      this.days.forEach((day, index) => {
        if (!day.date) {
          this.errors[`day${index + 1}_date`] = `Date is required for Day ${
            index + 1
          }.`;
        }
        if (!day.city) {
          this.errors[`day${index + 1}_city`] = `City is required for Day ${
            index + 1
          }.`;
        }
        if (!day.hotel) {
          this.errors[`day${index + 1}_hotel`] = `Hotel is required for Day ${
            index + 1
          }.`;
        }
      });

      return Object.keys(this.errors).length === 0;
    },

    saveTourPackage() {
      if (!this.validateForm()) {
        console.log("Form validation failed", this.errors);
        alert("Please correct the errors before submitting.");
        return;
      }

       // Helper function to ensure numeric values are properly formatted
  const formatNumber = (value) => {
    if (typeof value === 'number') {
      return value.toFixed(2);
    }
    return value ? parseFloat(value).toFixed(2) : '0.00';
  };

      data = {
    // Include the package ID for existing packages
        package_reference: this.packageReference,
        hotelCosts: this.hotelCosts.map(cost => ({
          ...cost,
          date: cost.date || '',
          room: parseInt(cost.room) || 0,
          nights: parseInt(cost.nights) || 0,
          price: formatNumber(cost.price),
          extraBedPrice: formatNumber(cost.extraBedPrice),
        })),
        name: this.name,
        customer_name: this.customerName,
        remark: this.remark,
        remark2: this.remark2,
        remark_of_hotels: this.remark_of_hotels,
        tour_pack_type: this.tourPackType,
        commission_rate_hotel: this.commission_rate_hotel,
        commission_rate_services: this.commission_rate_services,
        days: this.days.map((day) => ({
          date: day.date,
          city: day.city,
          hotel: day.hotel,
          services: day.services.map((service) => ({
            name: service.name,
            price_at_booking: service.price
          })),
          guide_services: day.guideServices.map((gs) => ({
            name: gs.name,
            price_at_booking: gs.price
          })),
        })),
        // hotelCosts: this.hotelCosts,

        discounts: this.discounts.map(discount => ({
          ...discount,
          amount: formatNumber(discount.amount),
        })),
        extraCosts: this.extraCosts.map(cost => ({
          ...cost,
          amount: formatNumber(cost.amount),
        })),
        total_cost: this.calculateGrandTotal(),
      };

      const url = this.packageReference
    ? `/save-tour-package/${this.packageReference}/`
    : "/save-tour-package/";

      fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify(data),
      })
        .then((response) => response.json())
        .then((data) => {
          if (data.status === "success") {
            alert("Tour package saved successfully!");
            window.location.href = `/${data.package_reference}/`;
          } else {
            alert("Error saving tour package: " + data.message);
          }
        }).catch((error) => {
          console.error("Error:", error);
          alert("An error occurred while saving the tour package.");
        });
    },
    //  #########################cal

    addHotelCost() {
      this.hotelCosts.push({
        name: "",
        type: "",
        room: 1,
        nights: 1,
        price: 0,
        extraBedPrice: "",
      });
    },

    removeHotelCost(index) {
      this.hotelCosts.splice(index, 1);
    },

    addDiscount() {
      this.discounts.push({ item: "", amount: 0 });
    },

    removeDiscount(index) {
      this.discounts.splice(index, 1);
    },

    addExtraCost() {
      this.extraCosts.push({ item: "", amount: 0 });
    },

    removeExtraCost(index) {
      this.extraCosts.splice(index, 1);
    },

    calculateHotelCostTotal() {
      return this.hotelCosts
        .reduce((total, cost) => {
          const roomCost =
            (parseFloat(cost.room) || 0) *
            (parseFloat(cost.nights) || 0) *
            (parseFloat(cost.price) || 0);
          const extraBedCost =
            (parseFloat(cost.nights) || 0) *
            (parseFloat(cost.extraBedPrice) || 0);
          return total + roomCost + extraBedCost;
        }, 0)
        .toFixed(2);
    },

    calculateTotalDiscounts() {
      return this.discounts
        .reduce((total, discount) => {
          return total + (parseFloat(discount.amount) || 0);
        }, 0)
        .toFixed(2);
    },
    calculateTotalExtraCosts() {
      return this.extraCosts
        .reduce((total, cost) => {
          return total + (parseFloat(cost.amount) || 0);
        }, 0)
        .toFixed(2);
    },


    calculateGrandTotal() {
      let serviceTotal = 0;
      let guideServiceTotal = 0;
      let hotelTotal = 0;
      this.days.forEach((day, index) => {
        day.services.forEach((service) => {
          const price = parseFloat(service.price) || 0;
          const quantity = parseInt(service.quantity) || 1;
          serviceTotal += price * quantity;
          console.log(
            `Day ${index + 1} service: ${
              service.name
            }, Price: ${price}, Quantity: ${quantity}, Total: ${
              price * quantity
            }`
          );
        });

        day.guideServices.forEach((guideService) => {
          const price = parseFloat(guideService.price) || 0;
          guideServiceTotal += price;
          console.log(
            `Day ${index + 1} guide service: ${
              guideService.name
            }, Price: ${price}`
          );
        });
      });

      hotelTotal = this.hotelCosts.reduce((total, cost) => {
        const roomCost =
          (parseFloat(cost.room) || 0) *
          (parseFloat(cost.nights) || 0) *
          (parseFloat(cost.price) || 0);
        const extraBedCost =
          (parseFloat(cost.nights) || 0) *
          (parseFloat(cost.extraBedPrice) || 0);
        console.log(
          `Hotel: ${cost.name}, Room Cost: ${roomCost}, Extra Bed Cost: ${extraBedCost}`
        );
        return total + roomCost + extraBedCost;
      }, 0);

      const serviceGrandTotal = serviceTotal + guideServiceTotal;
      const hotelGrandTotal = hotelTotal;
      const extraCostsTotal = parseFloat(this.calculateTotalExtraCosts());
      const grandTotal = serviceGrandTotal + hotelGrandTotal;

      const totalRoomNights = this.hotelCosts.reduce((total, cost) => {
        return (
          total + (parseFloat(cost.room) || 0) * (parseFloat(cost.nights) || 0)
        );
      }, 0);

      const commission_amount_hotel = (
        parseFloat(this.commission_rate_hotel) * totalRoomNights
      ).toFixed(2);
      const commission_amount_services = (
        (parseFloat(this.commission_rate_services) * serviceGrandTotal) /
        100
      ).toFixed(2);

      const totalDiscounts = this.discounts.reduce((total, discount) => {
        return total + (parseFloat(discount.amount) || 0);
      }, 0);

      const finalGrandTotal = grandTotal - totalDiscounts;

      return {
        serviceGrandTotal: serviceGrandTotal.toFixed(2),
        hotelGrandTotal: hotelGrandTotal.toFixed(2),
        extraCostsTotal: extraCostsTotal.toFixed(2),
        grandTotal: grandTotal.toFixed(2),
        finalGrandTotal: finalGrandTotal.toFixed(2),
        commission_amount_hotel: commission_amount_hotel,
        commission_amount_services: commission_amount_services,
        totalDiscounts: totalDiscounts.toFixed(2),
      };
    },

    async copyDay(index) {
      if (index < 0 || index >= this.days.length) return; // Invalid index

      const originalDay = this.days[index];


      // Create a new day object with only the essential information
      const newDay = {
        date: '',
        city: originalDay.city,
        hotel: '', // We'll set this after updating city services
        services: [], // Empty array for services
        guideServices: [], // Empty array for guide services
        cityServices: { hotels: [], service_types: [] },
      };

      // Increment the date
      if (originalDay.date) {
        const nextDate = new Date(originalDay.date);
        nextDate.setDate(nextDate.getDate() + 1);
        newDay.date = nextDate.toISOString().split('T')[0]; // Format as YYYY-MM-DD
      } else {
        // If no valid date, use tomorrow's date
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        newDay.date = tomorrow.toISOString().split('T')[0];
      }

      // Update city services for the new day
      if (newDay.city) {
        try {
          await this.updateCityServices(newDay);
          console.log('City services updated:', newDay.cityServices);
          // Select the hotel after city services are updated
          await this.selectHotelForCopiedDay(newDay, originalDay.hotel);
          console.log('Hotel selected:', newDay.hotel);
        } catch (error) {
          console.error('Error updating city services or selecting hotel:', error);
        }
      }

      // Insert the new day after the original day
      this.days.splice(index + 1, 0, newDay);

      // Trigger Alpine.js to re-evaluate the template
      this.days = [...this.days];


    },

    async updateCityServices(day) {
      if (day.city && this.tourPackType) {
        try {
          const response = await fetch(
            `/get-city-services/${day.city}/?tour_pack_type=${encodeURIComponent(this.tourPackType)}`
          );
          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
          }
          const data = await response.json();
          day.cityServices = {
            hotels: data.hotels || [],
            service_types: data.service_types || [],
          };
          console.log('Updated city services:', day.cityServices);
        } catch (error) {
          console.error("Error fetching city services:", error);
          day.cityServices = { hotels: [], service_types: [] };
        }
      } else {
        console.log('No city or tour pack type set, skipping city services update');
        day.cityServices = { hotels: [], service_types: [] };
      }
    },

    async selectHotelForCopiedDay(newDay, originalHotel) {


      if (originalHotel && newDay.cityServices && newDay.cityServices.hotels) {
        const selectedHotel = newDay.cityServices.hotels.find(
          h => h.id.toString() === originalHotel.toString()
        );
        if (selectedHotel) {
          newDay.hotel = selectedHotel.id.toString();
          console.log('Selected hotel for copied day:', newDay.hotel);
        } else {
          newDay.hotel = '';
          console.log('Original hotel not found in new day\'s options. Hotel selection reset.');
        }
      } else {
        newDay.hotel = '';
        console.log('No hotel to copy or no hotel options available. Hotel selection reset.');
      }
    },

     formatCommaNumber(num) {
      return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    },
    unformatCommaNumber(num) {
      return num.replace(/,/g, '');
    }

  };
};

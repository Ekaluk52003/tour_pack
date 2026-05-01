export default function invoiceForm() {
  return {
    invoiceItems: [],
    supplierExpenses: [],
    allSuppliers: JSON.parse(document.getElementById('suppliers-data').textContent),
    groupedItems: JSON.parse(document.getElementById('grouped-items-data').textContent),

    init() {
      // Initialize groupedItems with edit flags and hotel defaults
      this.groupedItems = this.groupedItems.map(item => ({
        ...item,
        arrivalEdit: false,
        departureEdit: false,
        room_count: item.room_count || 1,
        nights: item.nights || 1,
        room_price: item.room_price || 0,
        extra_bed_price: item.extra_bed_price || 0,
      }));
      // Load supplier expenses from the JSON script if available
      const expensesData = document.getElementById('supplier-expenses-data');
      if (expensesData) {
        this.supplierExpenses = JSON.parse(expensesData.textContent);
      }
      // Initialize supplierExpenses with UI state
      this.supplierExpenses = this.supplierExpenses.map(exp => {
        const matched = this.allSuppliers.find(s =>
          exp.supplier_id ? s.id === exp.supplier_id : s.name === exp.supplier_name
        );
        return {
          ...exp,
          supplierId: matched ? matched.id : null,
          supplierQuery: exp.supplier_name || '',
          serviceQuery: exp.description || '',
          supplierOpen: false,
          serviceOpen: false,
          supplierDropStyle: '',
          serviceDropStyle: '',
        };
      });

      // Robust outside-click close: if the user mousedowns anywhere that
      // isn't inside a combobox wrapper, close every open dropdown.
      document.addEventListener('mousedown', (e) => {
        if (!e.target.closest || !e.target.closest('[data-combobox]')) {
          this._closeAllDrops();
        }
      });
    },

    get groupedTotal() {
      return this.groupedItems.reduce((s, i) => s + parseFloat(i.price || 0), 0).toFixed(2);
    },
    get expenseTotal() {
      return this.supplierExpenses.reduce((s, e) => s + parseFloat(e.amount || 0), 0).toFixed(2);
    },

    formatDateShort(dateStr) {
      if (!dateStr) return '';
      const [y, m, d] = dateStr.split('-');
      if (!y || !m || !d) return '';
      const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      return `${d}-${months[parseInt(m,10)-1]}-${y.slice(-2)}`;
    },

    calcAmount(item) {
      item.amount = (parseFloat(item.quantity || 1) * parseFloat(item.unit_price || 0)).toFixed(2);
    },

    calcHotelPrice(item) {
      const rooms = parseFloat(item.room_count || 0);
      const nights = parseFloat(item.nights || 0);
      const pricePerNight = parseFloat(item.room_price || 0);
      const extraBed = parseFloat(item.extra_bed_price || 0);
      item.price = ((rooms * pricePerNight + extraBed) * nights).toFixed(2);
    },

    // --- Dropdown positioning (fixed so it never causes page scroll) ---
    _dropStyle(el, minWidth = 200) {
      const r = el.getBoundingClientRect();
      const dropH = 192; // max-h-48 = 192px
      const top = r.bottom + dropH > window.innerHeight ? r.top - dropH : r.bottom;
      return `position:fixed;top:${top}px;left:${r.left}px;min-width:${Math.max(r.width, minWidth)}px;z-index:9999`;
    },

    _closeAllDrops(exceptExp = null) {
      this.supplierExpenses.forEach(e => {
        if (e !== exceptExp) {
          e.supplierOpen = false;
          e.serviceOpen = false;
        }
      });
    },

    openSupplierDrop(exp, el) {
      this._closeAllDrops(exp);
      exp.serviceOpen = false;
      exp.supplierDropStyle = this._dropStyle(el, 200);
      exp.supplierOpen = true;
    },
    openServiceDrop(exp, el) {
      this._closeAllDrops(exp);
      exp.supplierOpen = false;
      exp.serviceDropStyle = this._dropStyle(el, 220);
      exp.serviceOpen = !!exp.supplierId;
    },

    closeServiceDrop(exp) {
      exp.serviceOpen = false;
    },

    // --- Supplier combobox ---
    filteredSuppliers(query) {
      if (!query || !query.trim()) return this.allSuppliers;
      const q = query.toLowerCase();
      return this.allSuppliers.filter(s => s.name.toLowerCase().includes(q));
    },

    selectSupplier(exp, supplier) {
      exp.supplier_name = supplier.name;
      exp.supplier_id = supplier.id;
      exp.supplierId = supplier.id;
      exp.supplierQuery = supplier.name;
      exp.supplierOpen = false;
      exp.serviceOpen = false;
      exp.description = '';
      exp.serviceQuery = '';
      exp.unit_price = '0';
    },

    closeSupplierDrop(exp) {
      exp.supplierOpen = false;
      exp.supplierQuery = exp.supplier_name || '';
    },

    // --- Service combobox ---
    filteredServices(exp) {
      if (!exp.supplierId) return [];
      const supplier = this.allSuppliers.find(s => s.id === exp.supplierId);
      if (!supplier) return [];
      const q = (exp.serviceQuery || '').toLowerCase();
      if (!q) return supplier.services;
      return supplier.services.filter(s => s.name.toLowerCase().includes(q));
    },

    selectService(exp, service) {
      exp.description = service.name;
      exp.serviceQuery = service.name;
      exp.unit_price = service.cost;
      exp.serviceOpen = false;
      exp.amount = parseFloat(service.cost).toFixed(2);
    },

    // --- Row management ---
    addInvoiceItem() {
      this.invoiceItems.push({
        description: '', quantity: '1', unit_price: '0', amount: '0',
        item_type: 'Other', order: this.invoiceItems.length,
      });
    },
    removeInvoiceItem(idx) { this.invoiceItems.splice(idx, 1); },

    addGroupedItem() {
      this.groupedItems.push({
        arrival_date: '', departure_date: '', nights: '',
        service_name: '', price: '0',
        is_hotel: false, is_discount: false, is_extra_cost: false,
        arrivalEdit: false, departureEdit: false,
        room_count: 1, room_price: 0, extra_bed_price: 0,
      });
    },
    removeGroupedItem(idx) { this.groupedItems.splice(idx, 1); },

    addExpense() {
      this.supplierExpenses.push({
        supplier_name: '', supplier_id: null,
        description: '', unit_price: '0',
        amount: '0',
        due_date: '', status: 'Pending', reference_number: '',
        order: this.supplierExpenses.length,
        supplierId: null, supplierQuery: '', serviceQuery: '',
        supplierOpen: false, serviceOpen: false,
        supplierDropStyle: '', serviceDropStyle: '',
      });
    },
    removeExpense(idx) { this.supplierExpenses.splice(idx, 1); },

    submitForm() {
      const cleanedExpenses = this.supplierExpenses.map(({
        supplierId, supplierQuery, serviceQuery,
        supplierOpen, serviceOpen,
        supplierDropStyle, serviceDropStyle,
        ...rest
      }) => rest);
      // Derive invoice items from grouped items
      const derivedInvoiceItems = this.groupedItems.map((item, idx) => ({
        description: item.service_name || '',
        quantity: '1',
        unit_price: String(item.price || 0),
        amount: String(item.price || 0),
        item_type: item.is_hotel ? 'Hotel' : (item.is_discount ? 'Discount' : (item.is_extra_cost ? 'Extra' : 'Service')),
        order: idx,
      }));
      document.getElementById('invoice_items_json').value = JSON.stringify(derivedInvoiceItems);
      document.getElementById('supplier_expenses_json').value = JSON.stringify(cleanedExpenses);
      document.getElementById('invoice-form').submit();
    },
  };
}

export default function invoiceForm() {
  return {
    invoiceItems: [],
    supplierExpenses: [],
    tourPackTypeId: null,
    allSuppliers: JSON.parse(document.getElementById('suppliers-data').textContent),
    groupedItems: JSON.parse(document.getElementById('grouped-items-data').textContent),
    insertMenuIdx: null,

    init() {
      this.tourPackTypeId = document.getElementById('invoice-meta')?.dataset.tourPackType || null;

      // Initialize groupedItems with edit flags, hotel defaults, stable key, and autocomplete state
      this.groupedItems = this.groupedItems.map(item => ({
        ...item,
        _key: crypto.randomUUID(),
        arrivalEdit: false,
        departureEdit: false,
        insertOpen: false,
        room_count: item.room_count || 1,
        nights: item.nights || 1,
        room_price: item.room_price || 0,
        extra_bed_price: item.extra_bed_price || 0,
        serviceAcOpen: false,
        serviceAcResults: [],
      }));

      // Load supplier expenses from the JSON script if available
      const expensesData = document.getElementById('supplier-expenses-data');
      if (expensesData) {
        this.supplierExpenses = JSON.parse(expensesData.textContent);
      }
      // Initialize supplierExpenses with UI state, linking to grouped items via source_item_index
      this.supplierExpenses = this.supplierExpenses.map(exp => {
        const matched = this.allSuppliers.find(s =>
          exp.supplier_id ? s.id === exp.supplier_id : s.name === exp.supplier_name
        );
        let sourceItem = null;
        let sourceKey = null;
        if (exp.source_item_index != null) {
          sourceItem = this.groupedItems[exp.source_item_index];
          if (sourceItem) sourceKey = sourceItem._key;
        }
        return {
          _key: crypto.randomUUID(),
          ...exp,
          _source_key: sourceKey,
          supplierId: matched ? matched.id : null,
          supplierQuery: exp.supplier_name || '',
          serviceQuery: exp.description || '',
          supplierOpen: false,
          serviceOpen: false,
          supplierDropStyle: '',
          serviceDropStyle: '',
          room_count: exp.room_count || 1,
          nights: exp.nights || 1,
          room_price: exp.room_price !== undefined ? exp.room_price : 0,
          extra_bed_price: exp.extra_bed_price !== undefined ? exp.extra_bed_price : 0,
          promotion: exp.promotion || (sourceItem?.promotion || ''),
        };
      });

      // Robust outside-click close for supplier dropdowns and insert menus
      document.addEventListener('mousedown', (e) => {
        if (!e.target.closest || !e.target.closest('[data-combobox]')) {
          this._closeAllDrops();
        }
        if (!e.target.closest || !e.target.closest('[data-insert-menu]')) {
          this.groupedItems.forEach(i => { i.insertOpen = false; });
          this.insertMenuIdx = null;
        }
        if (!e.target.closest || !e.target.closest('[data-service-ac]')) {
          this.groupedItems.forEach(i => { i.serviceAcOpen = false; });
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

    fmtNum(val) {
      const n = parseFloat(val || 0);
      return n.toLocaleString('th-TH', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    },
    parseNum(str) {
      if (str === '' || str === null || str === undefined) return 0;
      const cleaned = String(str).replace(/,/g, '');
      return parseFloat(cleaned) || 0;
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

    linkedItem(exp) {
      if (!exp._source_key) return null;
      return this.groupedItems.find(i => i._key === exp._source_key);
    },

    calcExpenseHotelPrice(exp) {
      const rooms = parseFloat(exp.room_count || 0);
      const nights = parseFloat(exp.nights || 0);
      const pricePerNight = parseFloat(exp.room_price || 0);
      const extraBed = parseFloat(exp.extra_bed_price || 0);
      exp.amount = ((rooms * pricePerNight + extraBed) * nights).toFixed(2);
      exp.unit_price = exp.amount;
    },

    updateExpenseHotel(exp, field, value) {
      exp[field] = value;
      if (['room_count','nights','room_price','extra_bed_price'].includes(field)) {
        this.calcExpenseHotelPrice(exp);
      }
      const item = this.linkedItem(exp);
      if (item) {
        const parts = [item.service_name || ''];
        if (item.arrival_date && item.departure_date) {
          parts.push(`- ${this.formatDateShort(item.arrival_date)} to ${this.formatDateShort(item.departure_date)}, ${item.nights || ''} nights`);
        }
        if (exp.promotion) {
          parts.push(`(${exp.promotion})`);
        }
        exp.description = parts.join(' ');
        exp.serviceQuery = exp.description;
      }
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

    // --- Supplier combobox (right panel) ---
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
      exp.supplier_service_id = null;
    },

    blurSupplier(exp) {
      exp.supplierOpen = false;
      const trimmed = (exp.supplierQuery || '').trim();
      if (!trimmed) {
        exp.supplier_name = '';
        exp.supplier_id = null;
        exp.supplierId = null;
        exp.supplierQuery = '';
        return;
      }
      // If query doesn't match the currently selected supplier name, treat as free text
      if (trimmed !== exp.supplier_name) {
        exp.supplier_name = trimmed;
        exp.supplier_id = null;
        exp.supplierId = null;
        exp.supplier_service_id = null;
      }
    },

    // --- SupplierService combobox (right panel) ---
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
      exp.supplier_service_id = service.id;
      exp.serviceOpen = false;
      exp.amount = parseFloat(service.cost).toFixed(2);
    },

    // --- Service autocomplete (left panel grouped items) ---
    async searchServices(item) {
      if (!this.tourPackTypeId || !item.service_name.trim()) {
        item.serviceAcOpen = false;
        item.serviceAcResults = [];
        return;
      }
      try {
        const res = await fetch(
          `/invoices/service-search/?q=${encodeURIComponent(item.service_name)}&tour_pack_type=${this.tourPackTypeId}`
        );
        item.serviceAcResults = await res.json();
        item.serviceAcOpen = item.serviceAcResults.length > 0;
      } catch (_) {
        item.serviceAcOpen = false;
      }
    },

    selectServiceAc(item, svc) {
      item.service_name = svc.name;
      item.price = svc.price;
      item.serviceAcOpen = false;
      item.serviceAcResults = [];
      if (svc.expense_templates && svc.expense_templates.length) {
        this.addExpensesFromTemplates(item, svc.expense_templates);
      }
    },

    addExpensesFromTemplates(item, templates) {
      console.log('[addExpensesFromTemplates] item._key=', item._key, 'templates=', templates.length);
      templates.forEach(t => {
        const matched = this.allSuppliers.find(s => t.supplier_id ? s.id === t.supplier_id : s.name === t.supplier_name);
        const sourceKey = item._key;
        console.log('[addExpensesFromTemplates] pushing expense with _source_key=', sourceKey);
        this.supplierExpenses.push({
          _key: crypto.randomUUID(),
          supplier_name: t.supplier_name,
          supplier_id: t.supplier_id,
          supplier_service_id: t.supplier_service_id || null,
          description: t.description || item.service_name,
          unit_price: t.unit_price,
          amount: t.unit_price,
          due_date: '',
          status: 'Pending',
          reference_number: '',
          order: this.supplierExpenses.length,
          _source_key: sourceKey,
          supplierId: matched ? matched.id : null,
          supplierQuery: t.supplier_name,
          serviceQuery: t.description || '',
          supplierOpen: false,
          serviceOpen: false,
          supplierDropStyle: '',
          serviceDropStyle: '',
        });
      });
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
        _key: crypto.randomUUID(),
        arrival_date: '', departure_date: '', nights: '',
        service_name: '', price: '0',
        is_hotel: false, is_discount: false, is_extra_cost: false,
        arrivalEdit: false, departureEdit: false,
        insertOpen: false,
        room_count: 1, room_price: 0, extra_bed_price: 0,
        serviceAcOpen: false, serviceAcResults: [],
      });
    },

    removeGroupedItem(idx) {
      this._closeAllDrops();
      const key = this.groupedItems[idx]._key;
      console.log('[removeGroupedItem] idx=', idx, 'key=', key);
      console.log('[removeGroupedItem] expense _source_keys=', this.supplierExpenses.map(e => e._source_key));
      this.groupedItems.splice(idx, 1);
      if (key) {
        for (let i = this.supplierExpenses.length - 1; i >= 0; i--) {
          const sk = this.supplierExpenses[i]._source_key;
          console.log('[removeGroupedItem] checking expense[', i, '] _source_key=', sk, 'match=', sk === key);
          if (sk === key) {
            this.supplierExpenses.splice(i, 1);
          }
        }
      }
    },

    openInsertMenu(idx, item) {
      const wasOpen = item.insertOpen;
      this.groupedItems.forEach(i => { i.insertOpen = false; });
      if (!wasOpen) {
        item.insertOpen = true;
        this.insertMenuIdx = idx;
      } else {
        this.insertMenuIdx = null;
      }
    },

    insertServiceAfter(idx) {
      if (idx === null) return;
      this.groupedItems[idx].insertOpen = false;
      this.groupedItems.splice(idx + 1, 0, {
        _key: crypto.randomUUID(),
        arrival_date: '', departure_date: '', nights: '',
        service_name: '', price: '0',
        is_hotel: false, is_discount: false, is_extra_cost: false,
        arrivalEdit: false, departureEdit: false,
        insertOpen: false,
        room_count: 1, room_price: 0, extra_bed_price: 0,
        serviceAcOpen: false, serviceAcResults: [],
      });
      this.insertMenuIdx = null;
    },

    insertHotelAfter(idx) {
      if (idx === null) return;
      this.groupedItems[idx].insertOpen = false;
      const hotelKey = crypto.randomUUID();
      this.groupedItems.splice(idx + 1, 0, {
        _key: hotelKey,
        arrival_date: '', departure_date: '', nights: 1,
        service_name: '', price: '0',
        is_hotel: true, is_discount: false, is_extra_cost: false,
        arrivalEdit: false, departureEdit: false,
        insertOpen: false,
        room_count: 1, room_price: 0, extra_bed_price: 0,
        serviceAcOpen: false, serviceAcResults: [],
      });
  
      this.insertMenuIdx = null;
    },

    addExpense() {
      this.supplierExpenses.push({
        _key: crypto.randomUUID(),
        supplier_name: '', supplier_id: null,
        supplier_service_id: null,
        description: '', unit_price: '0',
        amount: '0',
        due_date: '', status: 'Pending', reference_number: '',
        order: this.supplierExpenses.length,
        supplierId: null, supplierQuery: '', serviceQuery: '',
        supplierOpen: false, serviceOpen: false,
        supplierDropStyle: '', serviceDropStyle: '',
      });
    },

    addExpenseForItem(item) {
      this.supplierExpenses.push({
        _key: crypto.randomUUID(),
        supplier_name: '', supplier_id: null,
        supplier_service_id: null,
        description: '', unit_price: '0',
        amount: '0',
        due_date: '', status: 'Pending', reference_number: '',
        order: this.supplierExpenses.length,
        _source_key: item._key,
        supplierId: null, supplierQuery: '', serviceQuery: '',
        supplierOpen: false, serviceOpen: false,
        supplierDropStyle: '', serviceDropStyle: '',
        room_count: item.room_count || 1,
        nights: item.nights || 1,
        room_price: item.room_price !== undefined ? item.room_price : 0,
        extra_bed_price: item.extra_bed_price !== undefined ? item.extra_bed_price : 0,
        promotion: item.promotion || '',
      });
    },
    insertExpenseAfter(idx) {
      this.supplierExpenses.splice(idx + 1, 0, {
        _key: crypto.randomUUID(),
        supplier_name: '', supplier_id: null,
        supplier_service_id: null,
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
        _source_key,
        source_item_index: _oldIdx,
        description,
        room_count, nights, room_price, extra_bed_price, promotion,
        ...rest
      }) => {
        const sourceIdx = _source_key
          ? this.groupedItems.findIndex(item => item._key === _source_key)
          : -1;
        let updatedDescription = description;
        if (sourceIdx >= 0) {
          const item = this.groupedItems[sourceIdx];
          const parts = [item.service_name || ''];
          if (item.is_hotel) {
            if (item.arrival_date && item.departure_date) {
              parts.push(`- ${this.formatDateShort(item.arrival_date)} to ${this.formatDateShort(item.departure_date)}, ${item.nights || ''} nights`);
            }
            if (promotion) {
              parts.push(`(${promotion})`);
            }
          } else if (item.arrival_date) {
            parts.push(`(${item.arrival_date})`);
          }
          updatedDescription = parts.join(' ');
        }
        return { ...rest, description: updatedDescription, source_item_index: sourceIdx >= 0 ? sourceIdx : null };
      });

      const derivedInvoiceItems = this.groupedItems.map((item, idx) => ({
        description: `${item.service_name || ''}|||${item.arrival_date || ''}|||${item.departure_date || ''}|||${item.nights || ''}|||${item.room_count || ''}|||${item.room_price || ''}|||${item.extra_bed_price || ''}|||${item.promotion || ''}`,
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

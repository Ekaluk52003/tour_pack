export default function invoiceForm() {
  return {
    invoiceItems: JSON.parse(document.getElementById('invoice-items-data').textContent),
    supplierExpenses: JSON.parse(document.getElementById('supplier-expenses-data').textContent),
    allSuppliers: JSON.parse(document.getElementById('suppliers-data').textContent),

    init() {
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
    },

    get invoiceTotal() {
      return this.invoiceItems.reduce((s, i) => s + parseFloat(i.amount || 0), 0).toFixed(2);
    },
    get expenseTotal() {
      return this.supplierExpenses.reduce((s, e) => s + parseFloat(e.amount || 0), 0).toFixed(2);
    },

    calcAmount(item) {
      item.amount = (parseFloat(item.quantity || 1) * parseFloat(item.unit_price || 0)).toFixed(2);
    },
    calcExpenseAmount(exp) {
      exp.amount = (parseFloat(exp.qty || 1) * parseFloat(exp.unit_price || 0)).toFixed(2);
    },

    // --- Dropdown positioning (fixed so it never causes page scroll) ---
    _dropStyle(el, minWidth = 200) {
      const r = el.getBoundingClientRect();
      const dropH = 192; // max-h-48 = 192px
      const top = r.bottom + dropH > window.innerHeight ? r.top - dropH : r.bottom;
      return `position:fixed;top:${top}px;left:${r.left}px;min-width:${Math.max(r.width, minWidth)}px;z-index:9999`;
    },

    openSupplierDrop(exp, el) {
      exp.supplierDropStyle = this._dropStyle(el, 200);
      exp.supplierOpen = true;
    },
    openServiceDrop(exp, el) {
      exp.serviceDropStyle = this._dropStyle(el, 220);
      exp.serviceOpen = !!exp.supplierId;
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
      exp.amount = (parseFloat(exp.qty || 1) * parseFloat(service.cost)).toFixed(2);
    },

    // --- Row management ---
    addInvoiceItem() {
      this.invoiceItems.push({
        description: '', quantity: '1', unit_price: '0', amount: '0',
        item_type: 'Other', order: this.invoiceItems.length,
      });
    },
    removeInvoiceItem(idx) { this.invoiceItems.splice(idx, 1); },

    addExpense() {
      this.supplierExpenses.push({
        supplier_name: '', supplier_id: null,
        description: '', qty: '1', unit_price: '0',
        category: 'Other', amount: '0',
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
      document.getElementById('invoice_items_json').value = JSON.stringify(this.invoiceItems);
      document.getElementById('supplier_expenses_json').value = JSON.stringify(cleanedExpenses);
      document.getElementById('invoice-form').submit();
    },
  };
}

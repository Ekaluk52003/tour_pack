export default function datePicker(day, index) {
  return {
    showDatepicker: false,
    dateValue: '',
    month: '',
    year: '',
    days: [],
    blankdays: [],
    MONTH_NAMES: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
    DAYS: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],


    init() {
      this.dateValue = day.date;
      this.syncCalendar();

      this.$watch('day.date', (newValue) => {
        this.dateValue = newValue;
        this.syncCalendar();
      });
    },

    syncCalendar() {
      if (this.dateValue) {
        const date = new Date(this.dateValue);
        this.month = date.getMonth();
        this.year = date.getFullYear();
      } else {
        const date = new Date();
        this.month = date.getMonth();
        this.year = date.getFullYear();
      }
      this.generateDays();
    },


    generateDays() {
      let daysInMonth = new Date(this.year, this.month + 1, 0).getDate();
      let dayOfWeek = new Date(this.year, this.month, 1).getDay();

      this.blankdays = Array(dayOfWeek).fill('');
      this.days = Array.from({length: daysInMonth}, (_, i) => i + 1);
    },

    isToday(date) {
      const today = new Date();
      const d = new Date(this.year, this.month, date);
      return today.toDateString() === d.toDateString();
    },

    isSelected(date) {
      if (!this.dateValue) return false;
      const d = new Date(this.year, this.month, date);
      const selected = new Date(this.dateValue);
      return d.toDateString() === selected.toDateString();
    },

    selectDate(date) {
      let selectedDate = new Date(this.year, this.month, date);
      let offset = selectedDate.getTimezoneOffset();
      selectedDate = new Date(selectedDate.getTime() - (offset * 60 * 1000));

      const formattedDate = selectedDate.toISOString().split('T')[0];
      this.dateValue = formattedDate;
      day.date = formattedDate;
      this.showDatepicker = false;

      if (index === 0) {
        window.dispatchEvent(new CustomEvent('first-day-changed'));
      }
    },

    formatDateForDisplay(dateStr) {
      if (!dateStr) return '';
      const date = new Date(dateStr);
      const day = date.getDate().toString().padStart(2, '0');
      const month = this.MONTH_NAMES[date.getMonth()].slice(0, 3);
      const year = date.getFullYear().toString().slice(-2);
      return `${day}-${month}-${year}`;
    },

    incrementMonth() {
      if (this.month === 11) {
        this.month = 0;
        this.year++;
      } else {
        this.month++;
      }
      this.generateDays();
    },

    decrementMonth() {
      if (this.month === 0) {
        this.month = 11;
        this.year--;
      } else {
        this.month--;
      }
      this.generateDays();
    }
  };
}
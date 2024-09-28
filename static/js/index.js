import "../css/styles.css";
import Alpine from "alpinejs";
import ajax from "@imacrayon/alpine-ajax";
import persist from '@alpinejs/persist'
import "../tour_quote/js/tour_package.js";
// Initialize Alpine and plugins
window.Alpine = Alpine;
Alpine.plugin(ajax);
Alpine.plugin(persist)
Alpine.start();
// Your custom JavaScript here

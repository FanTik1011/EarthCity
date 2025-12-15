import { cities } from './data.js';
import { updateCityPanel } from './ui.js';

const map = L.map('map', {
  zoomControl: false,
  attributionControl: false
}).setView([49.8397, 24.0297], 6);

L.tileLayer(
  'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
  { maxZoom: 19 }
).addTo(map);

let activeMarker = null;

cities.forEach(city => {
  const marker = L.circleMarker([city.lat, city.lng], {
    radius: 8,
    color: '#4da3ff',
    fillColor: '#4da3ff',
    fillOpacity: 0.9
  }).addTo(map);

  marker.on('click', () => {
    focusCity(city, marker);
  });

  marker.bindTooltip(city.name, {
    direction: 'top',
    offset: [0, -6]
  });
});

function focusCity(city, marker) {
  map.flyTo([city.lat, city.lng], 10, {
    duration: 1.2,
    easeLinearity: 0.25
  });

  if (activeMarker) {
    activeMarker.setStyle({
      radius: 8,
      color: '#4da3ff',
      fillColor: '#4da3ff'
    });
  }

  marker.setStyle({
    radius: 12,
    color: '#ffffff',
    fillColor: '#4da3ff'
  });

  activeMarker = marker;
  setTimeout(() => {
  map.invalidateSize();
}, 200);

  updateCityPanel(city);
}

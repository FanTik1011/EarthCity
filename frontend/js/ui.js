export function updateCityPanel(city) {
  document.querySelector('.city-title').textContent = city.name;
  document.querySelector('.city-country').textContent = city.country;

  const stats = document.querySelectorAll('.stat span:last-child');

  stats[0].textContent = city.rating + '%';
  stats[1].textContent = city.population.toLocaleString();
  stats[2].textContent = city.safety;
  stats[3].textContent = city.tax + '%';
}

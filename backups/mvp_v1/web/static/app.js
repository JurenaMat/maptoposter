/**
 * MapToPoster Homepage
 * Simple gallery and navigation to /generate
 */

const gallery = document.getElementById('gallery');

document.addEventListener('DOMContentLoaded', () => {
    loadExamples();
});

async function loadExamples() {
    try {
        const response = await fetch('/api/examples');
        const examples = await response.json();
        
        gallery.innerHTML = examples.map(example => `
            <div class="gallery-item" data-city="${example.city}" data-country="${example.country}" data-theme="${example.theme}">
                <img src="${example.image}" alt="${example.city} map poster" loading="lazy">
                <div class="gallery-item-overlay">
                    <div class="gallery-item-city">${example.city}</div>
                    <div class="gallery-item-theme">${example.description}</div>
                </div>
            </div>
        `).join('');
        
        // Click on gallery item -> go to generate page with city pre-filled
        document.querySelectorAll('.gallery-item').forEach(item => {
            item.addEventListener('click', () => {
                const city = item.dataset.city;
                const country = item.dataset.country;
                const theme = item.dataset.theme;
                
                window.location.href = `/generate?city=${encodeURIComponent(city)}&country=${encodeURIComponent(country)}&theme=${encodeURIComponent(theme)}`;
            });
        });
    } catch (error) {
        console.error('Failed to load examples:', error);
    }
}

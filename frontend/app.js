/**
 * MapToPoster Homepage
 * Hero carousel, gallery, and navigation
 */

const gallery = document.getElementById('gallery');
const heroCarousel = document.getElementById('heroCarousel');

let carouselImages = [];
let currentCarouselIndex = 0;

document.addEventListener('DOMContentLoaded', () => {
    loadExamples();
});

async function loadExamples() {
    try {
        const response = await fetch((window.API_BASE || '') + '/api/examples');
        const examples = await response.json();
        
        // Setup hero carousel with poster images
        setupHeroCarousel(examples);
        
        // Render gallery with optimized lazy loading
        const apiBase = window.API_BASE || '';
        gallery.innerHTML = examples.map(example => `
            <div class="gallery-item" data-city="${example.city}" data-country="${example.country}" data-theme="${example.theme}">
                <div class="gallery-item-placeholder"></div>
                <img 
                    src="${apiBase}${example.image}" 
                    data-preview="${apiBase}${example.preview || example.image}"
                    alt="${example.city} map poster" 
                    loading="lazy"
                    decoding="async"
                    fetchpriority="low"
                    onload="this.parentElement.classList.add('loaded')"
                >
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

function setupHeroCarousel(examples) {
    if (!heroCarousel || examples.length === 0) return;
    
    const apiBase = window.API_BASE || '';
    carouselImages = examples.map(e => apiBase + e.image);
    
    // Create carousel slides
    heroCarousel.innerHTML = carouselImages.map((img, index) => `
        <div class="hero-carousel-image ${index === 0 ? 'active' : ''}">
            <img src="${img}" alt="Map poster">
        </div>
    `).join('');
    
    // Start rotation
    if (carouselImages.length > 1) {
        setInterval(rotateCarousel, 5000);
    }
}

function rotateCarousel() {
    const slides = heroCarousel.querySelectorAll('.hero-carousel-image');
    if (slides.length === 0) return;
    
    slides[currentCarouselIndex].classList.remove('active');
    currentCarouselIndex = (currentCarouselIndex + 1) % slides.length;
    slides[currentCarouselIndex].classList.add('active');
}

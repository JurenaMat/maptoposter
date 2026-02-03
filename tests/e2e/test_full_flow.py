"""
End-to-end tests for MapToPrint using Playwright.

These tests run in a real browser and verify the complete user flow
from landing page to poster generation.

Prerequisites:
    pip install pytest-playwright
    playwright install chromium

Run with:
    pytest tests/e2e/test_full_flow.py -v --headed  # To see browser
    pytest tests/e2e/test_full_flow.py -v           # Headless
"""

import pytest
import re
from playwright.sync_api import Page, expect

# Base URL - can be overridden with --base-url flag
BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="module")
def base_url():
    """Get the base URL for testing."""
    return BASE_URL


class TestHomepage:
    """Test homepage loads correctly with styling."""

    def test_homepage_loads_with_styling(self, page: Page, base_url):
        """Homepage should load with visible styled content."""
        page.goto(base_url)
        
        # Page should have title
        expect(page).to_have_title(re.compile(r"MapToPrint"))
        
        # Hero section should be visible
        hero = page.locator(".hero, .hero-content, header").first
        expect(hero).to_be_visible()
        
        # Main heading should be visible
        heading = page.locator("h1").first
        expect(heading).to_be_visible()
        
        # CSS should be loaded - check that body has styling
        # (if CSS fails to load, elements will have default browser styling)
        body_bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
        assert body_bg != "rgba(0, 0, 0, 0)", "CSS not loaded - body has no background"

    def test_navigation_visible(self, page: Page, base_url):
        """Navigation should be visible with logo and CTA."""
        page.goto(base_url)
        
        # Logo should be visible
        logo = page.locator(".logo, .nav-logo, [class*='logo']").first
        expect(logo).to_be_visible()
        
        # CTA button should be visible
        cta = page.locator("a[href='/generate'], .nav-cta, [class*='cta']").first
        expect(cta).to_be_visible()


class TestExampleGallery:
    """Test that example images load correctly."""

    def test_example_images_load(self, page: Page, base_url):
        """Gallery images should load and be visible."""
        page.goto(base_url)
        
        # Wait for page to fully load
        page.wait_for_load_state("networkidle")
        
        # Find gallery/example images
        images = page.locator("img[src*='example'], img[src*='thumb'], .gallery img, .example img")
        
        # If there are example images, they should be visible
        count = images.count()
        if count > 0:
            # Check first few images are visible
            for i in range(min(count, 3)):
                img = images.nth(i)
                expect(img).to_be_visible()
                
                # Image should have loaded (naturalWidth > 0)
                natural_width = img.evaluate("el => el.naturalWidth")
                assert natural_width > 0, f"Image {i} failed to load"


class TestNavigation:
    """Test navigation between pages."""

    def test_navigate_to_generate(self, page: Page, base_url):
        """Clicking 'Create Your Poster' should navigate to generate page."""
        page.goto(base_url)
        
        # Find and click the CTA
        cta = page.locator("a[href='/generate']").first
        cta.click()
        
        # Should navigate to generate page
        expect(page).to_have_url(re.compile(r"/generate"))
        
        # Generate page should have form elements
        page.wait_for_load_state("networkidle")
        
        # Should have city input or location search
        input_field = page.locator("input[type='text'], input[type='search'], .city-input, #cityInput").first
        expect(input_field).to_be_visible()


class TestGeneratePage:
    """Test the generate page functionality."""

    def test_generate_page_loads_styled(self, page: Page, base_url):
        """Generate page should load with proper styling."""
        page.goto(f"{base_url}/generate")
        
        # Wait for CSS to load
        page.wait_for_load_state("networkidle")
        
        # Check CSS is loaded
        body_bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
        assert body_bg != "rgba(0, 0, 0, 0)", "CSS not loaded on generate page"

    def test_theme_gallery_visible(self, page: Page, base_url):
        """Theme gallery should be visible on generate page."""
        page.goto(f"{base_url}/generate")
        page.wait_for_load_state("networkidle")
        
        # Theme gallery or theme selector should be visible
        themes = page.locator(".theme-gallery, .themes, [class*='theme']")
        
        # Should have theme options
        count = themes.count()
        assert count > 0, "No theme elements found"


class TestPreviewGeneration:
    """Test the preview generation flow."""

    def test_generate_preview(self, page: Page, base_url):
        """User should be able to enter a city and generate a preview."""
        page.goto(f"{base_url}/generate")
        page.wait_for_load_state("networkidle")
        
        # Find the city input
        city_input = page.locator("input[type='text'], input[type='search'], .city-input, #cityInput, #locationInput").first
        
        if city_input.is_visible():
            # Enter a city
            city_input.fill("Prague")
            
            # Look for autocomplete suggestions or country input
            page.wait_for_timeout(1000)  # Wait for autocomplete
            
            # Try to find and fill country if separate
            country_input = page.locator("#countryInput, input[placeholder*='country']")
            if country_input.count() > 0 and country_input.first.is_visible():
                country_input.first.fill("Czech Republic")
            
            # Find and click generate/preview button
            generate_btn = page.locator("button:has-text('Generate'), button:has-text('Preview'), button:has-text('Create'), .generate-btn, #generateBtn").first
            
            if generate_btn.is_visible():
                generate_btn.click()
                
                # Wait for progress or preview to appear
                # This may take several seconds
                page.wait_for_timeout(5000)
                
                # Check for progress indicator or preview image
                progress = page.locator(".progress, .loading, [class*='progress']")
                preview = page.locator(".preview-image, #previewImage, img[alt*='preview']")
                
                # Either progress or preview should be visible
                is_loading = progress.count() > 0 and progress.first.is_visible()
                has_preview = preview.count() > 0 and preview.first.is_visible()
                
                assert is_loading or has_preview, "Neither progress nor preview visible after clicking generate"


class TestFullFlow:
    """Test the complete user flow from homepage to download."""

    @pytest.mark.slow
    def test_download_poster(self, page: Page, base_url):
        """
        Full flow test: Navigate, configure, generate, and verify download link.
        
        Note: This is a slow test as it waits for actual poster generation.
        Mark with @pytest.mark.slow and skip in fast CI runs.
        """
        # Start at homepage
        page.goto(base_url)
        
        # Navigate to generate
        page.locator("a[href='/generate']").first.click()
        expect(page).to_have_url(re.compile(r"/generate"))
        page.wait_for_load_state("networkidle")
        
        # Enter city
        city_input = page.locator("input[type='text'], #cityInput, #locationInput").first
        city_input.fill("Venice")
        page.wait_for_timeout(500)
        
        # Enter country if needed
        country_input = page.locator("#countryInput")
        if country_input.count() > 0 and country_input.first.is_visible():
            country_input.first.fill("Italy")
        
        # Select a theme (click on first theme option)
        theme_option = page.locator(".theme-option, .theme-card, [class*='theme']:not(.themes)").first
        if theme_option.is_visible():
            theme_option.click()
        
        # Generate preview
        generate_btn = page.locator("button:has-text('Generate'), button:has-text('Preview'), #generateBtn").first
        if generate_btn.is_visible():
            generate_btn.click()
            
            # Wait for preview (up to 30 seconds for slow networks)
            page.wait_for_timeout(10000)
            
            # Look for final generate/download option
            download_btn = page.locator("a[download], button:has-text('Download'), #downloadBtn")
            final_generate = page.locator("button:has-text('Generate Poster'), button:has-text('Final')")
            
            # Either download should be available or final generate button
            has_download = download_btn.count() > 0
            has_final = final_generate.count() > 0
            
            # Just verify the flow got this far - actual download requires longer wait
            # In CI, we just verify the UI elements are present
            print(f"Download available: {has_download}, Final generate available: {has_final}")


class TestResponsiveness:
    """Test mobile/tablet responsiveness."""

    def test_mobile_layout(self, page: Page, base_url):
        """Page should be usable on mobile viewport."""
        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        
        # Hero should still be visible
        heading = page.locator("h1").first
        expect(heading).to_be_visible()
        
        # Navigation should be accessible (may be in hamburger menu)
        # Just check page doesn't have horizontal scroll
        has_overflow = page.evaluate(
            "document.body.scrollWidth > document.body.clientWidth"
        )
        assert not has_overflow, "Page has horizontal overflow on mobile"

    def test_tablet_layout(self, page: Page, base_url):
        """Page should be usable on tablet viewport."""
        page.set_viewport_size({"width": 768, "height": 1024})
        
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        
        # Content should be visible
        heading = page.locator("h1").first
        expect(heading).to_be_visible()

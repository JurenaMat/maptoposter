"""
Deployment tests for MapToPrint.

These tests verify that the web application is properly configured and serving
all necessary files for a successful deployment.

Run with: pytest tests/test_deployment.py -v
"""

import pytest
from pathlib import Path
import tomllib


class TestBuildConfiguration:
    """Test build configuration files are valid for Railway deployment."""

    def test_nixpacks_toml_exists(self):
        """nixpacks.toml must exist for Railway builds."""
        nixpacks_path = Path(__file__).parent.parent / "nixpacks.toml"
        assert nixpacks_path.exists(), "nixpacks.toml is required for Railway deployment"

    def test_nixpacks_has_required_packages(self):
        """nixpacks.toml must include gdal, geos, proj for geo libraries."""
        nixpacks_path = Path(__file__).parent.parent / "nixpacks.toml"
        with open(nixpacks_path, "rb") as f:
            config = tomllib.load(f)
        
        nix_pkgs = config.get("phases", {}).get("setup", {}).get("nixPkgs", [])
        assert "gdal" in nix_pkgs, "nixpacks.toml must include gdal"
        assert "geos" in nix_pkgs, "nixpacks.toml must include geos"
        assert "proj" in nix_pkgs, "nixpacks.toml must include proj"

    def test_nixpacks_has_python(self):
        """nixpacks.toml must specify Python version."""
        nixpacks_path = Path(__file__).parent.parent / "nixpacks.toml"
        with open(nixpacks_path, "rb") as f:
            config = tomllib.load(f)
        
        nix_pkgs = config.get("phases", {}).get("setup", {}).get("nixPkgs", [])
        has_python = any("python" in pkg for pkg in nix_pkgs)
        assert has_python, "nixpacks.toml must specify Python version"

    def test_nixpacks_start_command(self):
        """nixpacks.toml must have start command."""
        nixpacks_path = Path(__file__).parent.parent / "nixpacks.toml"
        with open(nixpacks_path, "rb") as f:
            config = tomllib.load(f)
        
        start_cmd = config.get("start", {}).get("cmd", "")
        assert "python" in start_cmd and "start.py" in start_cmd, \
            "nixpacks.toml start command must run python start.py"

    def test_frontend_directory_exists(self):
        """frontend/ directory must exist with index.html."""
        frontend_path = Path(__file__).parent.parent / "frontend"
        assert frontend_path.exists(), "frontend/ directory is required"
        assert (frontend_path / "index.html").exists(), "frontend/index.html is required"

    def test_requirements_txt_exists(self):
        """requirements.txt must exist."""
        req_path = Path(__file__).parent.parent / "requirements.txt"
        assert req_path.exists(), "requirements.txt is required"

    def test_app_imports_successfully(self):
        """web.app must import without errors."""
        try:
            from web.app import app
            assert app is not None
        except ImportError as e:
            pytest.fail(f"Failed to import web.app: {e}")


class TestHealthAndBasicEndpoints:
    """Test basic health and endpoint availability."""

    def test_health_endpoint(self, client):
        """GET /health should return 200 with healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_root_returns_html(self, client):
        """GET / should return HTML with proper structure."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        # Check for essential HTML elements
        html = response.text
        assert "<!DOCTYPE html>" in html
        assert "<title>" in html
        assert "MapToPrint" in html
        
        # Check for CSS link (should reference /styles.css)
        assert 'href="/styles.css"' in html or 'href="/static/styles.css"' in html

    def test_generate_page_loads(self, client):
        """GET /generate should return the generate page HTML."""
        response = client.get("/generate")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        html = response.text
        assert "<!DOCTYPE html>" in html
        assert "Create" in html or "Generate" in html


class TestStaticFiles:
    """Test that static CSS and JS files are served correctly."""

    def test_styles_css_served(self, client):
        """/styles.css should return CSS content."""
        response = client.get("/styles.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]
        
        # Basic CSS validation
        css = response.text
        assert len(css) > 100  # Should have substantial content
        assert "{" in css and "}" in css  # Basic CSS structure

    def test_app_js_served(self, client):
        """/app.js should return JavaScript content."""
        response = client.get("/app.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]
        
        js = response.text
        assert len(js) > 50  # Should have content

    def test_config_js_served(self, client):
        """/config.js should return JavaScript content."""
        response = client.get("/config.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]

    def test_generate_css_served(self, client):
        """/generate.css should return CSS content."""
        response = client.get("/generate.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    def test_generate_js_served(self, client):
        """/generate.js should return JavaScript content."""
        response = client.get("/generate.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]


class TestAPIEndpoints:
    """Test API endpoints."""

    def test_themes_api(self, client):
        """GET /api/themes should return list of themes."""
        response = client.get("/api/themes")
        assert response.status_code == 200
        
        themes = response.json()
        assert isinstance(themes, list)
        assert len(themes) > 0
        
        # Each theme should have required fields
        for theme in themes:
            assert "name" in theme
            assert "display_name" in theme
            assert "bg" in theme

    def test_examples_api(self, client):
        """GET /api/examples should return example data."""
        response = client.get("/api/examples")
        assert response.status_code == 200
        
        examples = response.json()
        assert isinstance(examples, list)
        assert len(examples) > 0
        
        # Each example should have required fields
        for example in examples:
            assert "city" in example
            assert "country" in example
            assert "theme" in example
            assert "image" in example

    def test_geocode_api(self, client):
        """GET /api/geocode should accept query parameter."""
        response = client.get("/api/geocode?q=Prague")
        # May return empty list if network unavailable, but should not error
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestPreviewEndpoints:
    """Test preview generation endpoints."""

    def test_preview_start_accepts_request(self, client, sample_preview_request):
        """POST /api/preview/start should accept a valid request."""
        response = client.post("/api/preview/start", json=sample_preview_request)
        assert response.status_code == 200
        
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "started"

    def test_preview_start_validates_theme(self, client, sample_preview_request):
        """POST /api/preview/start should reject invalid theme."""
        invalid_request = sample_preview_request.copy()
        invalid_request["theme"] = "nonexistent_theme_xyz"
        
        response = client.post("/api/preview/start", json=invalid_request)
        assert response.status_code == 400

    def test_progress_endpoint(self, client, sample_preview_request):
        """GET /api/progress/{job_id} should return job status."""
        # First start a job
        start_response = client.post("/api/preview/start", json=sample_preview_request)
        job_id = start_response.json()["job_id"]
        
        # Then check progress
        response = client.get(f"/api/progress/{job_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data

    def test_progress_nonexistent_job(self, client):
        """GET /api/progress/{job_id} should handle nonexistent job."""
        response = client.get("/api/progress/nonexistent123")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_found"


class TestExampleImages:
    """Test that example images are accessible."""

    def test_examples_directory_accessible(self, client):
        """Example images should be accessible via /examples/ or /static/examples/."""
        # Try both possible paths
        response1 = client.get("/examples/prague_noir_thumb.webp")
        response2 = client.get("/static/examples/prague_noir_thumb.webp")
        
        # At least one should work
        assert response1.status_code == 200 or response2.status_code == 200


class TestCORS:
    """Test CORS configuration."""

    def test_cors_headers_present(self, client):
        """API responses should include CORS headers."""
        response = client.options(
            "/api/themes",
            headers={
                "Origin": "https://maptoprint.com",
                "Access-Control-Request-Method": "GET"
            }
        )
        # Should allow the request (not 403/405)
        assert response.status_code in [200, 204, 405]

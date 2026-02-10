from flask import Flask, jsonify, send_file, request
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint
from datetime import datetime
from pathlib import Path
import sys
import yaml
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.database import get_database
from src.utils.xml_generator import XMLGenerator
from src.utils.logger import setup_logger
from run import SCRAPER_MAP, ALL_COMPANY_CHOICES

app = Flask(__name__)
CORS(app)

db = get_database()
xml_gen = XMLGenerator()
logger = setup_logger('api')

# Swagger UI Configuration
SWAGGER_URL = '/api/docs'
API_URL = '/api/swagger.yaml'

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "Job Scraper API - 125 Companies"
    }
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

@app.route('/api/swagger.yaml')
def swagger_yaml():
    """Serve Swagger YAML file"""
    swagger_path = Path(__file__).resolve().parent.parent.parent / 'swagger.yaml'
    return send_file(swagger_path, mimetype='text/yaml')

@app.route('/')
def index():
    """API info endpoint"""
    return jsonify({
        'message': 'Job Scraper API',
        'version': '2.0.0',
        'total_scrapers': 125,
        'documentation': f'{request.host_url.rstrip("/")}{SWAGGER_URL}',
        'endpoints': {
            'GET /': 'API information',
            'GET /api/docs': 'Swagger UI documentation',
            'GET /api/jobs': 'Get all jobs',
            'GET /api/jobs/<company>': 'Get jobs by company',
            'GET /api/stats': 'Get statistics',
            'GET /api/companies': 'List all 125 companies',
            'GET /api/health': 'Health check',
            'POST /api/scrape/<company>': 'Trigger scraping',
            'GET /api/export/xml': 'Export all jobs as XML',
            'GET /api/export/xml/<company>': 'Export company jobs as XML'
        }
    })

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        db_status = "connected"
        try:
            db.get_job_counts_by_company()
        except:
            db_status = "disconnected"
        
        return jsonify({
            'status': 'healthy' if db_status == 'connected' else 'degraded',
            'database': db_status,
            'scrapers': len(set(SCRAPER_MAP.values())),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

@app.route('/api/companies')
def get_companies():
    """Get list of all supported companies"""
    try:
        return jsonify({
            'success': True,
            'total': len(ALL_COMPANY_CHOICES),
            'companies': sorted(ALL_COMPANY_CHOICES),
            'categories': {
                'Technology': 25,
                'Financial Services': 22,
                'Consulting & IT': 15,
                'E-commerce': 15,
                'Manufacturing': 15,
                'Pharma & Healthcare': 11,
                'Consumer Goods': 10,
                'Automotive': 8,
                'Energy & Industrial': 4
            }
        })
    except Exception as e:
        logger.error(f"Error getting companies: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/jobs')
def get_all_jobs():
    """Get all jobs with pagination"""
    try:
        # Get query parameters
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        location = request.args.get('location', None)
        department = request.args.get('department', None)
        
        jobs = db.get_all_jobs()
        
        # Apply filters
        if location:
            jobs = [j for j in jobs if location.lower() in j.get('city', '').lower()]
        if department:
            jobs = [j for j in jobs if department.lower() in j.get('department', '').lower()]
        
        # Apply pagination
        total = len(jobs)
        jobs_paginated = jobs[offset:offset + limit]
        
        return jsonify({
            'success': True,
            'total': total,
            'count': len(jobs_paginated),
            'limit': limit,
            'offset': offset,
            'jobs': jobs_paginated
        })
    except Exception as e:
        logger.error(f"Error getting jobs: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/jobs/<company_name>')
def get_company_jobs(company_name):
    """Get jobs for a specific company"""
    try:
        jobs = db.get_jobs_by_company(company_name)
        
        return jsonify({
            'success': True,
            'company': company_name,
            'count': len(jobs),
            'jobs': jobs
        })
    except Exception as e:
        logger.error(f"Error getting jobs for {company_name}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stats')
def get_stats():
    """Get statistics"""
    try:
        counts = db.get_job_counts_by_company()
        history = db.get_scraping_history()
        
        # Calculate totals
        total_jobs = sum(c.get('count', 0) for c in counts)
        companies_with_jobs = len(counts)
        
        return jsonify({
            'success': True,
            'summary': {
                'total_jobs': total_jobs,
                'companies_with_jobs': companies_with_jobs,
                'total_companies': 125,
                'coverage_percentage': round((companies_with_jobs / 125) * 100, 2)
            },
            'job_counts': [{'company': c['company_name'], 'count': c['count']} for c in counts],
            'scraping_history': [
                {
                    'company': h['company_name'],
                    'run_date': str(h['run_date']),
                    'jobs_scraped': h['jobs_scraped'],
                    'status': h['status'],
                    'error': h.get('error_message')
                } for h in history
            ]
        })
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/scrape/<company_name>', methods=['POST'])
def trigger_scrape(company_name):
    """Trigger scraping for a specific company"""
    try:
        # Check if company exists
        scraper_class = SCRAPER_MAP.get(company_name.lower())
        if not scraper_class:
            return jsonify({
                'success': False,
                'error': f'Company "{company_name}" not found. Use /api/companies to see available companies.'
            }), 400
        
        # Get parameters
        data = request.get_json() or {}
        max_pages = data.get('max_pages', 1)
        
        # Note: Actual scraping would be done asynchronously in production
        return jsonify({
            'success': True,
            'message': f'Scraping initiated for {company_name}',
            'company': company_name,
            'max_pages': max_pages,
            'note': 'In production, this would trigger an async scraping task'
        })
    except Exception as e:
        logger.error(f"Error triggering scrape for {company_name}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/export/xml')
def export_xml():
    """Export all jobs as XML"""
    try:
        xml_file = xml_gen.generate_xml()
        return send_file(
            xml_file,
            mimetype='application/xml',
            as_attachment=True,
            download_name=f'jobs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xml'
        )
    except Exception as e:
        logger.error(f"Error exporting XML: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/export/xml/<company_name>')
def export_company_xml(company_name):
    """Export jobs for specific company as XML"""
    try:
        xml_file = xml_gen.generate_company_xml(company_name)
        return send_file(
            xml_file,
            mimetype='application/xml',
            as_attachment=True,
            download_name=f'{company_name.lower()}_jobs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xml'
        )
    except Exception as e:
        logger.error(f"Error exporting XML for {company_name}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Endpoint not found',
        'documentation': f'{request.host_url.rstrip("/")}{SWAGGER_URL}'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500

if __name__ == '__main__':
    from src.config import API_HOST, API_PORT, DEBUG_MODE
    logger.info(f"Starting API server on {API_HOST}:{API_PORT}")
    logger.info(f"Swagger documentation available at: http://{API_HOST}:{API_PORT}{SWAGGER_URL}")
    app.run(host=API_HOST, port=API_PORT, debug=DEBUG_MODE)

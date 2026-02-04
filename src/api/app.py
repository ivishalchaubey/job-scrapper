from flask import Flask, jsonify, send_file
from flask_cors import CORS
from datetime import datetime
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.database import get_database
from src.utils.xml_generator import XMLGenerator
from src.utils.logger import setup_logger

app = Flask(__name__)
CORS(app)

db = get_database()
xml_gen = XMLGenerator()
logger = setup_logger('api')

@app.route('/')
def index():
    """API info endpoint"""
    return jsonify({
        'message': 'Job Scraper API',
        'version': '1.0.0',
        'endpoints': {
            'GET /api/jobs': 'Get all jobs',
            'GET /api/jobs/<company>': 'Get jobs by company',
            'GET /api/stats': 'Get statistics',
            'GET /api/export/xml': 'Export all jobs as XML',
            'GET /api/export/xml/<company>': 'Export company jobs as XML'
        }
    })

@app.route('/api/jobs')
def get_all_jobs():
    """Get all jobs as JSON"""
    try:
        jobs = db.get_all_jobs()

        return jsonify({
            'success': True,
            'count': len(jobs),
            'jobs': jobs
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

        return jsonify({
            'success': True,
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

@app.route('/api/export/xml')
def export_xml():
    """Export jobs as XML"""
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

if __name__ == '__main__':
    from src.config import API_HOST, API_PORT, DEBUG_MODE
    logger.info(f"Starting API server on {API_HOST}:{API_PORT}")
    app.run(host=API_HOST, port=API_PORT, debug=DEBUG_MODE)

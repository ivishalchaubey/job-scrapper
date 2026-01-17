import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.database.db import JobDatabase
from src.utils.logger import setup_logger
from src.config import OUTPUT_DIR

logger = setup_logger('xml_generator')

class XMLGenerator:
    def __init__(self):
        self.db = JobDatabase()
    
    def prettify_xml(self, elem):
        """Return a pretty-printed XML string"""
        rough_string = ET.tostring(elem, encoding='utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ", encoding='utf-8').decode('utf-8')
    
    def generate_xml(self, output_file=None):
        """Generate XML file from database jobs following Scoutit schema"""
        if not output_file:
            output_file = OUTPUT_DIR / f'jobs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xml'
        
        # Create root element
        root = ET.Element('opportunities')
        root.set('xmlns', 'http://www.scoutit.com/schema/opportunities')
        root.set('generated', datetime.now().isoformat())
        
        # Get all jobs from database
        with self.db.get_connection() as conn:
            conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM jobs WHERE status = "active"')
            jobs = cursor.fetchall()
        
        logger.info(f"Generating XML for {len(jobs)} jobs")
        
        # Add each job as opportunity
        for job in jobs:
            opportunity = ET.SubElement(root, 'opportunity')
            
            # Required fields
            self._add_element_if_value(opportunity, 'external_id', job.get('external_id'))
            self._add_element_if_value(opportunity, 'company', job.get('company_name'))
            self._add_element_if_value(opportunity, 'title', job.get('title'))
            self._add_element_if_value(opportunity, 'apply_url', job.get('apply_url'))
            
            # Optional fields - only add if value exists
            self._add_element_if_value(opportunity, 'description', job.get('description'))
            self._add_element_if_value(opportunity, 'location', job.get('location'))
            self._add_element_if_value(opportunity, 'city', job.get('city'))
            self._add_element_if_value(opportunity, 'state', job.get('state'))
            self._add_element_if_value(opportunity, 'country', job.get('country'))
            self._add_element_if_value(opportunity, 'employment_type', job.get('employment_type'))
            self._add_element_if_value(opportunity, 'department', job.get('department'))
            self._add_element_if_value(opportunity, 'posted_date', job.get('posted_date'))
            self._add_element_if_value(opportunity, 'job_function', job.get('job_function'))
            self._add_element_if_value(opportunity, 'experience_level', job.get('experience_level'))
            self._add_element_if_value(opportunity, 'salary_range', job.get('salary_range'))
            self._add_element_if_value(opportunity, 'remote_type', job.get('remote_type'))
        
        # Write to file
        xml_string = self.prettify_xml(root)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(xml_string)
        
        logger.info(f"XML file generated: {output_file}")
        return str(output_file)
    
    def _add_element_if_value(self, parent, tag, value):
        """Add XML element only if value is not empty"""
        if value and str(value).strip():
            elem = ET.SubElement(parent, tag)
            elem.text = str(value).strip()
    
    def generate_company_xml(self, company_name, output_file=None):
        """Generate XML for a specific company"""
        if not output_file:
            output_file = OUTPUT_DIR / f'{company_name.lower()}_jobs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xml'
        
        root = ET.Element('opportunities')
        root.set('xmlns', 'http://www.scoutit.com/schema/opportunities')
        root.set('generated', datetime.now().isoformat())
        root.set('company', company_name)
        
        # Get jobs for specific company
        with self.db.get_connection() as conn:
            conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM jobs WHERE company_name = ? AND status = "active"', (company_name,))
            jobs = cursor.fetchall()
        
        logger.info(f"Generating XML for {len(jobs)} jobs from {company_name}")
        
        for job in jobs:
            opportunity = ET.SubElement(root, 'opportunity')
            
            self._add_element_if_value(opportunity, 'external_id', job.get('external_id'))
            self._add_element_if_value(opportunity, 'company', job.get('company_name'))
            self._add_element_if_value(opportunity, 'title', job.get('title'))
            self._add_element_if_value(opportunity, 'apply_url', job.get('apply_url'))
            self._add_element_if_value(opportunity, 'description', job.get('description'))
            self._add_element_if_value(opportunity, 'location', job.get('location'))
            self._add_element_if_value(opportunity, 'city', job.get('city'))
            self._add_element_if_value(opportunity, 'state', job.get('state'))
            self._add_element_if_value(opportunity, 'country', job.get('country'))
            self._add_element_if_value(opportunity, 'employment_type', job.get('employment_type'))
            self._add_element_if_value(opportunity, 'department', job.get('department'))
            self._add_element_if_value(opportunity, 'posted_date', job.get('posted_date'))
            self._add_element_if_value(opportunity, 'job_function', job.get('job_function'))
            self._add_element_if_value(opportunity, 'experience_level', job.get('experience_level'))
            self._add_element_if_value(opportunity, 'salary_range', job.get('salary_range'))
            self._add_element_if_value(opportunity, 'remote_type', job.get('remote_type'))
        
        xml_string = self.prettify_xml(root)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(xml_string)
        
        logger.info(f"XML file generated for {company_name}: {output_file}")
        return str(output_file)

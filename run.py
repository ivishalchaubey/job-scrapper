#!/usr/bin/env python3
"""
Main runner script for job scraping system
"""
import argparse
from datetime import datetime
from pathlib import Path
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
sys.path.append(str(Path(__file__).resolve().parent))

from src.database import get_database
# Existing scrapers
from src.scrapers.amazon_scraper import AmazonScraper
from src.scrapers.aws_scraper import AWSScraper
from src.scrapers.accenture_scraper import AccentureScraper
from src.scrapers.jll_scraper import JLLScraper
from src.scrapers.bain_scraper import BainScraper
from src.scrapers.bcg_scraper import BCGScraper
from src.scrapers.infosys_scraper import InfosysScraper
from src.scrapers.loreal_scraper import LorealScraper
from src.scrapers.mahindra_scraper import MahindraScraper
from src.scrapers.marico_scraper import MaricoScraper
from src.scrapers.meta_scraper import MetaScraper
from src.scrapers.microsoft_scraper import MicrosoftScraper
from src.scrapers.morganstanley_scraper import MorganStanleyScraper
from src.scrapers.nestle_scraper import NestleScraper
from src.scrapers.nvidia_scraper import NvidiaScraper
from src.scrapers.samsung_scraper import SamsungScraper
from src.scrapers.swiggy_scraper import SwiggyScraper
from src.scrapers.tcs_scraper import TCSScraper
from src.scrapers.tataconsumer_scraper import TataConsumerScraper
from src.scrapers.techmahindra_scraper import TechMahindraScraper
from src.scrapers.varunbeverages_scraper import VarunBeveragesScraper
from src.scrapers.wipro_scraper import WiproScraper
from src.scrapers.pepsico_scraper import PepsiCoScraper
from src.scrapers.bookmyshow_scraper import BookMyShowScraper
from src.scrapers.abbott_scraper import AbbottScraper

# New scrapers - Tech Giants
from src.scrapers.google_scraper import GoogleScraper
from src.scrapers.ibm_scraper import IBMScraper
from src.scrapers.apple_scraper import AppleScraper
from src.scrapers.intel_scraper import IntelScraper
from src.scrapers.dell_scraper import DellScraper
from src.scrapers.cisco_scraper import CiscoScraper

# New scrapers - Consulting & IT Services
from src.scrapers.hcltech_scraper import HCLTechScraper
from src.scrapers.cognizant_scraper import CognizantScraper
from src.scrapers.capgemini_scraper import CapgeminiScraper
from src.scrapers.deloitte_scraper import DeloitteScraper
from src.scrapers.ey_scraper import EYScraper
from src.scrapers.kpmg_scraper import KPMGScraper
from src.scrapers.pwc_scraper import PwCScraper

# New scrapers - Financial Services
from src.scrapers.goldmansachs_scraper import GoldmanSachsScraper
from src.scrapers.jpmorganchase_scraper import JPMorganChaseScraper
from src.scrapers.citigroup_scraper import CitigroupScraper
from src.scrapers.hdfcbank_scraper import HDFCBankScraper
from src.scrapers.icicibank_scraper import ICICIBankScraper
from src.scrapers.axisbank_scraper import AxisBankScraper
from src.scrapers.kotakmahindrabank_scraper import KotakMahindraBankScraper
from src.scrapers.bankofamerica_scraper import BankofAmericaScraper
from src.scrapers.hsbc_scraper import HSBCScraper
from src.scrapers.standardchartered_scraper import StandardCharteredScraper

# New scrapers - E-commerce & Startups
from src.scrapers.flipkart_scraper import FlipkartScraper
from src.scrapers.walmart_scraper import WalmartScraper
from src.scrapers.myntra_scraper import MyntraScraper
from src.scrapers.meesho_scraper import MeeshoScraper
from src.scrapers.zepto_scraper import ZeptoScraper
from src.scrapers.paytm_scraper import PaytmScraper
from src.scrapers.zomato_scraper import ZomatoScraper
from src.scrapers.phonepe_scraper import PhonePeScraper
from src.scrapers.olaelectric_scraper import OlaElectricScraper
from src.scrapers.uber_scraper import UberScraper
from src.scrapers.nykaa_scraper import NykaaScraper
from src.scrapers.bigbasket_scraper import BigBasketScraper
from src.scrapers.delhivery_scraper import DelhiveryScraper
from src.scrapers.indigo_scraper import IndiGoScraper
from src.scrapers.jio_scraper import JioScraper

# New scrapers - Manufacturing & Conglomerates
from src.scrapers.itclimited_scraper import ITCLimitedScraper
from src.scrapers.larsentoubro_scraper import LarsenToubroScraper
from src.scrapers.relianceindustries_scraper import RelianceIndustriesScraper
from src.scrapers.adanigroup_scraper import AdaniGroupScraper
from src.scrapers.tatasteel_scraper import TataSteelScraper
from src.scrapers.tatamotors_scraper import TataMotorsScraper
from src.scrapers.hindustanunilever_scraper import HindustanUnileverScraper
from src.scrapers.proctergamble_scraper import ProcterGambleScraper
from src.scrapers.colgatepalmolive_scraper import ColgatePalmoliveScraper
from src.scrapers.asianpaints_scraper import AsianPaintsScraper
from src.scrapers.godrejgroup_scraper import GodrejGroupScraper
from src.scrapers.bajajauto_scraper import BajajAutoScraper

# Batch 2 - New scrapers (50 more)
from src.scrapers.mckinsey_scraper import McKinseyScraper
from src.scrapers.parleagro_scraper import ParleAgroScraper
from src.scrapers.zoho_scraper import ZohoScraper
from src.scrapers.adityabirla_scraper import AdityaBirlaScraper
from src.scrapers.adobe_scraper import AdobeScraper
from src.scrapers.mondelez_scraper import MondelezScraper
from src.scrapers.reckitt_scraper import ReckittScraper
from src.scrapers.cocacola_scraper import CocaColaScraper
from src.scrapers.statebankofindia_scraper import StateBankOfIndiaScraper
from src.scrapers.tesla_scraper import TeslaScraper
from src.scrapers.abbvie_scraper import AbbVieScraper
from src.scrapers.americanexpress_scraper import AmericanExpressScraper
from src.scrapers.angelone_scraper import AngelOneScraper
from src.scrapers.att_scraper import ATTScraper
from src.scrapers.boeing_scraper import BoeingScraper
from src.scrapers.cipla_scraper import CiplaScraper
from src.scrapers.cummins_scraper import CumminsScraper
from src.scrapers.cyient_scraper import CyientScraper
from src.scrapers.drreddys_scraper import DrReddysScraper
from src.scrapers.royalenfield_scraper import RoyalEnfieldScraper
from src.scrapers.elililly_scraper import EliLillyScraper
from src.scrapers.exxonmobil_scraper import ExxonMobilScraper
from src.scrapers.fedex_scraper import FedExScraper
from src.scrapers.fortishealthcare_scraper import FortisHealthcareScraper
from src.scrapers.herofincorp_scraper import HeroFinCorpScraper
from src.scrapers.heromotocorp_scraper import HeroMotoCorpScraper
from src.scrapers.hindalco_scraper import HindalcoScraper
from src.scrapers.honeywell_scraper import HoneywellScraper
from src.scrapers.hp_scraper import HPScraper
from src.scrapers.iifl_scraper import IIFLScraper
from src.scrapers.johnsonjohnson_scraper import JohnsonJohnsonScraper
from src.scrapers.jswenergy_scraper import JSWEnergyScraper
from src.scrapers.jubilantfoodworks_scraper import JubilantFoodWorksScraper
from src.scrapers.kpittechnologies_scraper import KPITTechnologiesScraper
from src.scrapers.lowes_scraper import LowesScraper
from src.scrapers.marutisuzuki_scraper import MarutiSuzukiScraper
from src.scrapers.maxlifeinsurance_scraper import MaxLifeInsuranceScraper
from src.scrapers.metlife_scraper import MetLifeScraper
from src.scrapers.muthootfinance_scraper import MuthootFinanceScraper
from src.scrapers.netflix_scraper import NetflixScraper
from src.scrapers.nike_scraper import NikeScraper
from src.scrapers.oraclecorporation_scraper import OracleCorporationScraper
from src.scrapers.persistentsystems_scraper import PersistentSystemsScraper
from src.scrapers.pfizer_scraper import PfizerScraper
from src.scrapers.piramalgroup_scraper import PiramalGroupScraper
from src.scrapers.qualcomm_scraper import QualcommScraper
from src.scrapers.salesforce_scraper import SalesforceScraper
from src.scrapers.shoppersstop_scraper import ShoppersStopScraper
from src.scrapers.starbucks_scraper import StarbucksScraper
from src.scrapers.sunpharma_scraper import SunPharmaScraper

from src.utils.xml_generator import XMLGenerator
from src.utils.logger import setup_logger
from src.config import LOGS_DIR

# Setup logger
log_file = LOGS_DIR / f'scraper_{datetime.now().strftime("%Y%m%d")}.log'
logger = setup_logger('main', log_file)

# Map of company names to their scraper classes
SCRAPER_MAP = {
    # Existing scrapers
    'amazon': AmazonScraper,
    'aws': AWSScraper,
    'accenture': AccentureScraper,
    'jll': JLLScraper,
    'bain': BainScraper,
    'bcg': BCGScraper,
    'infosys': InfosysScraper,
    'loreal': LorealScraper,
    'mahindra': MahindraScraper,
    'marico': MaricoScraper,
    'meta': MetaScraper,
    'microsoft': MicrosoftScraper,
    'morgan stanley': MorganStanleyScraper,
    'nestle': NestleScraper,
    'nvidia': NvidiaScraper,
    'samsung': SamsungScraper,
    'swiggy': SwiggyScraper,
    'tcs': TCSScraper,
    'tata consumer': TataConsumerScraper,
    'tech mahindra': TechMahindraScraper,
    'varun beverages': VarunBeveragesScraper,
    'wipro': WiproScraper,
    'pepsico': PepsiCoScraper,
    'bookmyshow': BookMyShowScraper,
    'abbott': AbbottScraper,
    # New scrapers - Tech Giants
    'google': GoogleScraper,
    'ibm': IBMScraper,
    'apple': AppleScraper,
    'intel': IntelScraper,
    'dell': DellScraper,
    'dell technologies': DellScraper,
    'cisco': CiscoScraper,
    # New scrapers - Consulting & IT Services
    'hcltech': HCLTechScraper,
    'cognizant': CognizantScraper,
    'capgemini': CapgeminiScraper,
    'deloitte': DeloitteScraper,
    'ey': EYScraper,
    'kpmg': KPMGScraper,
    'pwc': PwCScraper,
    # New scrapers - Financial Services
    'goldman sachs': GoldmanSachsScraper,
    'jpmorgan chase': JPMorganChaseScraper,
    'citigroup': CitigroupScraper,
    'hdfc bank': HDFCBankScraper,
    'icici bank': ICICIBankScraper,
    'axis bank': AxisBankScraper,
    'kotak mahindra bank': KotakMahindraBankScraper,
    'bank of america': BankofAmericaScraper,
    'hsbc': HSBCScraper,
    'standard chartered': StandardCharteredScraper,
    # New scrapers - E-commerce & Startups
    'flipkart': FlipkartScraper,
    'walmart': WalmartScraper,
    'myntra': MyntraScraper,
    'meesho': MeeshoScraper,
    'zepto': ZeptoScraper,
    'paytm': PaytmScraper,
    'zomato': ZomatoScraper,
    'phonepe': PhonePeScraper,
    'ola electric': OlaElectricScraper,
    'uber': UberScraper,
    'nykaa': NykaaScraper,
    'bigbasket': BigBasketScraper,
    'delhivery': DelhiveryScraper,
    'indigo': IndiGoScraper,
    'jio': JioScraper,
    # New scrapers - Manufacturing & Conglomerates
    'itc limited': ITCLimitedScraper,
    'larsen & toubro': LarsenToubroScraper,
    'reliance industries': RelianceIndustriesScraper,
    'adani group': AdaniGroupScraper,
    'tata steel': TataSteelScraper,
    'tata motors': TataMotorsScraper,
    'hindustan unilever': HindustanUnileverScraper,
    'procter & gamble': ProcterGambleScraper,
    'colgate-palmolive': ColgatePalmoliveScraper,
    'asian paints': AsianPaintsScraper,
    'godrej group': GodrejGroupScraper,
    'bajaj auto': BajajAutoScraper,
    # Batch 2 - Additional 50 scrapers
    'mckinsey': McKinseyScraper,
    'mckinsey & company': McKinseyScraper,
    'parle agro': ParleAgroScraper,
    'zoho': ZohoScraper,
    'zoho corporation': ZohoScraper,
    'aditya birla': AdityaBirlaScraper,
    'aditya birla group': AdityaBirlaScraper,
    'adobe': AdobeScraper,
    'mondelez': MondelezScraper,
    'mondelez international': MondelezScraper,
    'reckitt': ReckittScraper,
    'coca-cola': CocaColaScraper,
    'state bank of india': StateBankOfIndiaScraper,
    'sbi': StateBankOfIndiaScraper,
    'tesla': TeslaScraper,
    'abbvie': AbbVieScraper,
    'american express': AmericanExpressScraper,
    'amex': AmericanExpressScraper,
    'angel one': AngelOneScraper,
    'att': ATTScraper,
    'at&t': ATTScraper,
    'boeing': BoeingScraper,
    'cipla': CiplaScraper,
    'cummins': CumminsScraper,
    'cyient': CyientScraper,
    'dr reddys': DrReddysScraper,
    "dr. reddy's laboratories": DrReddysScraper,
    'royal enfield': RoyalEnfieldScraper,
    'eli lilly': EliLillyScraper,
    'eli lilly and company': EliLillyScraper,
    'exxonmobil': ExxonMobilScraper,
    'fedex': FedExScraper,
    'fortis': FortisHealthcareScraper,
    'fortis healthcare': FortisHealthcareScraper,
    'hero fincorp': HeroFinCorpScraper,
    'hero motocorp': HeroMotoCorpScraper,
    'hindalco': HindalcoScraper,
    'hindalco industries': HindalcoScraper,
    'honeywell': HoneywellScraper,
    'hp': HPScraper,
    'hp inc': HPScraper,
    'iifl': IIFLScraper,
    'india infoline': IIFLScraper,
    'johnson & johnson': JohnsonJohnsonScraper,
    'jsw energy': JSWEnergyScraper,
    'jubilant foodworks': JubilantFoodWorksScraper,
    'kpit': KPITTechnologiesScraper,
    'kpit technologies': KPITTechnologiesScraper,
    'lowes': LowesScraper,
    "lowe's": LowesScraper,
    'maruti suzuki': MarutiSuzukiScraper,
    'max life insurance': MaxLifeInsuranceScraper,
    'metlife': MetLifeScraper,
    'muthoot finance': MuthootFinanceScraper,
    'netflix': NetflixScraper,
    'nike': NikeScraper,
    'oracle': OracleCorporationScraper,
    'oracle corporation': OracleCorporationScraper,
    'persistent systems': PersistentSystemsScraper,
    'pfizer': PfizerScraper,
    'piramal': PiramalGroupScraper,
    'piramal group': PiramalGroupScraper,
    'qualcomm': QualcommScraper,
    'salesforce': SalesforceScraper,
    'shoppers stop': ShoppersStopScraper,
    'starbucks': StarbucksScraper,
    'sun pharma': SunPharmaScraper,
}

ALL_COMPANY_CHOICES = [
    # Existing scrapers (25)
    'Amazon', 'AWS', 'Accenture', 'JLL', 'Bain', 'BCG',
    'Infosys', 'Loreal', 'Mahindra', 'Marico', 'Meta', 'Microsoft',
    'Morgan Stanley', 'Nestle', 'Nvidia', 'Samsung', 'Swiggy', 'TCS',
    'Tata Consumer', 'Tech Mahindra', 'Varun Beverages', 'Wipro',
    'PepsiCo', 'BookMyShow', 'Abbott',
    # Batch 1 - New scrapers - Tech Giants (6)
    'Google', 'IBM', 'Apple', 'Intel', 'Dell', 'Cisco',
    # Batch 1 - Consulting & IT Services (7)
    'HCLTech', 'Cognizant', 'Capgemini', 'Deloitte', 'EY', 'KPMG', 'PwC',
    # Batch 1 - Financial Services (10)
    'Goldman Sachs', 'JPMorgan Chase', 'Citigroup', 'HDFC Bank', 'ICICI Bank',
    'Axis Bank', 'Kotak Mahindra Bank', 'Bank of America', 'HSBC', 'Standard Chartered',
    # Batch 1 - E-commerce & Startups (15)
    'Flipkart', 'Walmart', 'Myntra', 'Meesho', 'Zepto', 'Paytm', 'Zomato',
    'PhonePe', 'Ola Electric', 'Uber', 'Nykaa', 'BigBasket', 'Delhivery', 'IndiGo', 'Jio',
    # Batch 1 - Manufacturing & Conglomerates (12)
    'ITC Limited', 'Larsen & Toubro', 'Reliance Industries', 'Adani Group',
    'Tata Steel', 'Tata Motors', 'Hindustan Unilever', 'Procter & Gamble',
    'Colgate-Palmolive', 'Asian Paints', 'Godrej Group', 'Bajaj Auto',
    # Batch 2 - Additional 50 scrapers
    'McKinsey', 'Parle Agro', 'Zoho', 'Aditya Birla', 'Adobe', 'Mondelez',
    'Reckitt', 'Coca-Cola', 'State Bank of India', 'Tesla', 'AbbVie',
    'American Express', 'Angel One', 'AT&T', 'Boeing', 'Cipla', 'Cummins',
    'Cyient', 'Dr Reddys', 'Royal Enfield', 'Eli Lilly', 'ExxonMobil',
    'FedEx', 'Fortis Healthcare', 'Hero FinCorp', 'Hero MotoCorp', 'Hindalco',
    'Honeywell', 'HP', 'IIFL', 'Johnson & Johnson', 'JSW Energy',
    'Jubilant FoodWorks', 'KPIT Technologies', 'Lowes', 'Maruti Suzuki',
    'Max Life Insurance', 'MetLife', 'Muthoot Finance', 'Netflix', 'Nike',
    'Oracle', 'Persistent Systems', 'Pfizer', 'Piramal Group', 'Qualcomm',
    'Salesforce', 'Shoppers Stop', 'Starbucks', 'Sun Pharma'
]

def scrape_company(company_name):
    """Scrape jobs for a specific company"""
    db = get_database()
    start_time = time.time()
    
    result = {
        'company': company_name,
        'success': False,
        'jobs_count': 0,
        'error': None,
        'duration': 0
    }

    try:
        scraper_class = SCRAPER_MAP.get(company_name.lower())
        if not scraper_class:
            logger.error(f"Unknown company: {company_name}")
            result['error'] = "Unknown company"
            return result

        scraper = scraper_class()
        logger.info(f"Starting scrape for {company_name}")

        # Scrape jobs
        jobs = scraper.scrape()

        if not jobs:
            logger.warning(f"No jobs found for {company_name}")
            db.log_scraping_run(company_name, 0, 'success', 'No jobs found')
            result['success'] = True
            result['jobs_count'] = 0
            result['duration'] = time.time() - start_time
            return result

        # Save to database
        for job in jobs:
            db.insert_job(job)

        logger.info(f"Saved {len(jobs)} jobs for {company_name}")
        db.log_scraping_run(company_name, len(jobs), 'success')
        
        result['success'] = True
        result['jobs_count'] = len(jobs)
        result['duration'] = time.time() - start_time
        return result

    except Exception as e:
        logger.error(f"Error scraping {company_name}: {str(e)}")
        db.log_scraping_run(company_name, 0, 'failed', str(e))
        result['error'] = str(e)
        result['duration'] = time.time() - start_time
        return result

def scrape_all_parallel(max_workers=5):
    """Scrape all companies using multithreading for speed"""
    logger.info(f"Starting parallel scrape for all {len(ALL_COMPANY_CHOICES)} companies with {max_workers} workers")
    
    start_time = time.time()
    results = []
    print_lock = Lock()
    
    def scrape_with_progress(company):
        """Scrape and print progress"""
        result = scrape_company(company)
        with print_lock:
            status = "✓" if result['success'] else "✗"
            print(f"{status} {result['company']}: {result['jobs_count']} jobs ({result['duration']:.1f}s)")
        return result
    
    # Use ThreadPoolExecutor for parallel scraping
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_company = {
            executor.submit(scrape_with_progress, company): company 
            for company in ALL_COMPANY_CHOICES
        }
        
        for future in as_completed(future_to_company):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                company = future_to_company[future]
                logger.error(f"Exception scraping {company}: {str(e)}")
                results.append({
                    'company': company,
                    'success': False,
                    'jobs_count': 0,
                    'error': str(e),
                    'duration': 0
                })
    
    total_time = time.time() - start_time
    logger.info(f"Scraping completed for all companies in {total_time:.2f} seconds")
    
    # Generate analytics report
    generate_analytics_report(results, total_time)
    
    return results

def scrape_all():
    """Legacy single-threaded scrape - redirects to parallel version"""
    return scrape_all_parallel(max_workers=5)

def generate_analytics_report(results, total_time):
    """Generate detailed analytics report in markdown format"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    date_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Calculate statistics
    total_companies = len(results)
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    total_jobs = sum(r['jobs_count'] for r in results)
    
    # Sort results by job count
    results_sorted = sorted(results, key=lambda x: x['jobs_count'], reverse=True)
    
    # Generate report
    report = f"""# Scraping Analytics Report

**Generated:** {timestamp}  
**Total Duration:** {total_time:.2f} seconds ({total_time/60:.1f} minutes)  
**Average per Company:** {total_time/total_companies:.2f} seconds

---

## 📊 Summary Statistics

| Metric | Count | Percentage |
|--------|-------|------------|
| **Total Companies** | {total_companies} | 100% |
| **✅ Successful** | {len(successful)} | {len(successful)/total_companies*100:.1f}% |
| **❌ Failed** | {len(failed)} | {len(failed)/total_companies*100:.1f}% |
| **Total Jobs Scraped** | {total_jobs:,} | - |
| **Avg Jobs per Company** | {total_jobs/len(successful) if successful else 0:.1f} | - |

---

## 🏆 Top Performers (Jobs Scraped)

| Rank | Company | Jobs | Duration |
|------|---------|------|----------|
"""
    
    # Top 10 companies by job count
    for i, r in enumerate(results_sorted[:10], 1):
        if r['jobs_count'] > 0:
            report += f"| {i} | {r['company']} | {r['jobs_count']} | {r['duration']:.1f}s |\n"
    
    report += "\n---\n\n## ✅ Successful Scrapes\n\n"
    report += "| Company | Jobs | Duration | Status |\n"
    report += "|---------|------|----------|--------|\n"
    
    for r in sorted(successful, key=lambda x: x['company']):
        report += f"| {r['company']} | {r['jobs_count']} | {r['duration']:.1f}s | ✓ |\n"
    
    if failed:
        report += "\n---\n\n## ❌ Failed Scrapes\n\n"
        report += "| Company | Error | Duration |\n"
        report += "|---------|-------|----------|\n"
        
        for r in sorted(failed, key=lambda x: x['company']):
            error_msg = r['error'][:100] if r['error'] else 'Unknown error'
            report += f"| {r['company']} | {error_msg} | {r['duration']:.1f}s |\n"
    
    report += "\n---\n\n## 📈 Performance Breakdown\n\n"
    
    # Jobs distribution
    jobs_ranges = {
        '0 jobs': len([r for r in results if r['jobs_count'] == 0]),
        '1-10 jobs': len([r for r in results if 1 <= r['jobs_count'] <= 10]),
        '11-25 jobs': len([r for r in results if 11 <= r['jobs_count'] <= 25]),
        '26-50 jobs': len([r for r in results if 26 <= r['jobs_count'] <= 50]),
        '51-100 jobs': len([r for r in results if 51 <= r['jobs_count'] <= 100]),
        '100+ jobs': len([r for r in results if r['jobs_count'] > 100]),
    }
    
    report += "### Jobs per Company Distribution\n\n"
    report += "| Range | Companies |\n"
    report += "|-------|----------|\n"
    for range_name, count in jobs_ranges.items():
        report += f"| {range_name} | {count} |\n"
    
    report += "\n### Duration Statistics\n\n"
    durations = [r['duration'] for r in results]
    avg_duration = sum(durations) / len(durations)
    max_duration = max(durations)
    min_duration = min(durations)
    
    report += f"- **Average:** {avg_duration:.2f}s\n"
    report += f"- **Fastest:** {min_duration:.2f}s\n"
    report += f"- **Slowest:** {max_duration:.2f}s\n"
    
    report += f"\n---\n\n## 🎯 Recommendations\n\n"
    
    if failed:
        report += f"- ⚠️  {len(failed)} companies failed - check error messages above\n"
    if len([r for r in results if r['jobs_count'] == 0]) > 10:
        report += f"- 💡 {len([r for r in results if r['jobs_count'] == 0])} companies returned 0 jobs - may need URL updates\n"
    if total_jobs > 0:
        report += f"- ✅ Successfully scraped {total_jobs:,} total jobs\n"
    
    report += f"\n---\n\n**Report saved:** `SCRAPING_ANALYTICS_{date_str}.md`\n"
    
    # Save report
    filename = f"SCRAPING_ANALYTICS_{date_str}.md"
    filepath = Path(__file__).parent / filename
    
    with open(filepath, 'w') as f:
        f.write(report)
    
    logger.info(f"Analytics report saved to {filename}")
    print(f"\n📊 Analytics report saved: {filename}")
    
    return filepath

def export_xml(company=None):
    """Export jobs to XML"""
    xml_gen = XMLGenerator()

    try:
        if company:
            xml_file = xml_gen.generate_company_xml(company)
            logger.info(f"Exported {company} jobs to XML: {xml_file}")
        else:
            xml_file = xml_gen.generate_xml()
            logger.info(f"Exported all jobs to XML: {xml_file}")

        return xml_file
    except Exception as e:
        logger.error(f"Error exporting XML: {str(e)}")
        return None

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Job Scraper System - Fast multithreaded scraping with analytics',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py scrape                    # Scrape all companies (5 workers)
  python run.py scrape --workers 10       # Scrape all with 10 workers (faster)
  python run.py scrape --company Google   # Scrape single company
  python run.py api                       # Start API server
        """
    )
    parser.add_argument('action', choices=['scrape', 'export', 'api', 'clean'],
                       help='Action to perform')
    parser.add_argument('--company', choices=ALL_COMPANY_CHOICES,
                       help='Specific company to scrape/export')
    parser.add_argument('--workers', type=int, default=5,
                       help='Number of parallel workers (default: 5, recommended: 5-10)')

    args = parser.parse_args()

    if args.action == 'scrape':
        if args.company:
            # Single company scrape
            result = scrape_company(args.company)
            print(f"\n{'='*60}")
            print(f"Company: {result['company']}")
            print(f"Status: {'✓ Success' if result['success'] else '✗ Failed'}")
            print(f"Jobs: {result['jobs_count']}")
            print(f"Duration: {result['duration']:.2f}s")
            if result['error']:
                print(f"Error: {result['error']}")
            print(f"{'='*60}\n")
        else:
            # Multi-company parallel scrape
            print(f"\n{'='*60}")
            print(f"PARALLEL SCRAPING - {len(ALL_COMPANY_CHOICES)} COMPANIES")
            print(f"Workers: {args.workers}")
            print(f"{'='*60}\n")
            scrape_all_parallel(max_workers=args.workers)

    elif args.action == 'export':
        export_xml(args.company)

    elif args.action == 'clean':
        db = get_database()
        logger.info("Cleaning database...")
        db.drop_all_tables()
        logger.info("Database cleaned successfully")
        print("Database cleaned and reset successfully!")

    elif args.action == 'api':
        from src.api.app import app
        from src.config import API_HOST, API_PORT, DEBUG_MODE
        logger.info(f"Starting API server on {API_HOST}:{API_PORT}")
        app.run(host=API_HOST, port=API_PORT, debug=DEBUG_MODE)

if __name__ == '__main__':
    main()

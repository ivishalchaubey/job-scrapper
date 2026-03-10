from core.logging import setup_logger

logger = setup_logger('csv_missing_scrapers')

class GallanttIspatPlaceholderScraper:
    def __init__(self):
        self.company_name = 'Gallantt Ispat'
        self.url = 'https://gallantt.com/careers'

    def scrape(self, max_pages=1):
        logger.warning(f'No real scraper implemented for {self.company_name}')
        return []

class TeamleaseServicesPlaceholderScraper:
    def __init__(self):
        self.company_name = 'TeamLease Services'
        self.url = 'https://group.teamlease.com/careers/'

    def scrape(self, max_pages=1):
        logger.warning(f'No real scraper implemented for {self.company_name}')
        return []

class BhartiAxaLifeInsuranceCompanyPlaceholderScraper:
    def __init__(self):
        self.company_name = 'Bharti Axa Life Insurance Company'
        self.url = 'https://www.linkedin.com/jobs/search/?currentJobId=4351025516&f_C=312468&geoId=92000000&origin=COMPANY_PAGE_JOBS_CLUSTER_EXPANSION&originToLandingJobPostings=4351025516%2C4351592288'

    def scrape(self, max_pages=1):
        logger.warning(f'No real scraper implemented for {self.company_name}')
        return []

class HdbFinancialServicesPlaceholderScraper:
    def __init__(self):
        self.company_name = 'HDB Financial Services'
        self.url = 'https://careers.hdbfs.com/'

    def scrape(self, max_pages=1):
        logger.warning(f'No real scraper implemented for {self.company_name}')
        return []

class ServicenowPlaceholderScraper:
    def __init__(self):
        self.company_name = 'ServiceNow'
        self.url = 'https://careers.servicenow.com/jobs/?search=&country=India&pagesize=20#results'

    def scrape(self, max_pages=1):
        logger.warning(f'No real scraper implemented for {self.company_name}')
        return []

class SmollanPlaceholderScraper:
    def __init__(self):
        self.company_name = 'Smollan'
        self.url = 'https://www.linkedin.com/company/smollan-group/jobs/'

    def scrape(self, max_pages=1):
        logger.warning(f'No real scraper implemented for {self.company_name}')
        return []

class VirtusaPlaceholderScraper:
    def __init__(self):
        self.company_name = 'Virtusa'
        self.url = 'https://www.virtusa.com/careers/job-search#India'

    def scrape(self, max_pages=1):
        logger.warning(f'No real scraper implemented for {self.company_name}')
        return []

class AdityaBirlaFashionAndRetailPlaceholderScraper:
    def __init__(self):
        self.company_name = 'Aditya Birla Fashion and Retail'
        self.url = 'https://careers.adityabirla.com/fashion-retail'

    def scrape(self, max_pages=1):
        logger.warning(f'No real scraper implemented for {self.company_name}')
        return []

class AdvancedMicroDevicesPlaceholderScraper:
    def __init__(self):
        self.company_name = 'Advanced Micro Devices'
        self.url = 'https://careers.amd.com/careers-home/jobs?country=India&page=1'

    def scrape(self, max_pages=1):
        logger.warning(f'No real scraper implemented for {self.company_name}')
        return []

class IqviaPlaceholderScraper:
    def __init__(self):
        self.company_name = 'IQVIA'
        self.url = 'https://jobs.iqvia.com/en/jobs?locations=India'

    def scrape(self, max_pages=1):
        logger.warning(f'No real scraper implemented for {self.company_name}')
        return []

class LululemonPlaceholderScraper:
    def __init__(self):
        self.company_name = 'Lululemon'
        self.url = 'https://www.linkedin.com/jobs/lululemon-jobs/?currentJobId=4373936903&originalSubdomain=in'

    def scrape(self, max_pages=1):
        logger.warning(f'No real scraper implemented for {self.company_name}')
        return []

class PhysicsWallahPlaceholderScraper:
    def __init__(self):
        self.company_name = 'Physics Wallah'
        self.url = 'https://www.linkedin.com/jobs/search/?currentJobId=4369437931&f_C=78087354&geoId=92000000&origin=COMPANY_PAGE_JOBS_CLUSTER_EXPANSION&originToLandingJobPostings=4367913315%2C4368349055%2C4369072699%2C4368171130%2C4371823053%2C4371837109%2C4368355116%2C4373907634%2C4369460114'

    def scrape(self, max_pages=1):
        logger.warning(f'No real scraper implemented for {self.company_name}')
        return []

class SevenIHoldingsPlaceholderScraper:
    def __init__(self):
        self.company_name = 'Seven & I Holdings'
        self.url = 'https://7-eleven-gsc.ripplehire.com/candidate/?token=AdexT4WYTKbaWH7lieeK&lang=en&source=LINKEDIN&ref=LI02#list'

    def scrape(self, max_pages=1):
        logger.warning(f'No real scraper implemented for {self.company_name}')
        return []

class GlgPlaceholderScraper:
    def __init__(self):
        self.company_name = 'GLG'
        self.url = 'https://glginsights.com/careers/list/filter/tax/offices:gurugram,mumbai/'

    def scrape(self, max_pages=1):
        logger.warning(f'No real scraper implemented for {self.company_name}')
        return []

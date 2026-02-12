"""
Scraper Registry - Maps company names to their scraper classes.
"""
from datetime import datetime

from core.logging import setup_logger
from config.scraper import LOGS_DIR

log_file = LOGS_DIR / f'registry_{datetime.now().strftime("%Y%m%d")}.log'
logger = setup_logger('registry', log_file)

# Existing scrapers
from scrapers.amazon_scraper import AmazonScraper
from scrapers.aws_scraper import AWSScraper
from scrapers.accenture_scraper import AccentureScraper
from scrapers.jll_scraper import JLLScraper
from scrapers.bain_scraper import BainScraper
from scrapers.bcg_scraper import BCGScraper
from scrapers.infosys_scraper import InfosysScraper
from scrapers.loreal_scraper import LorealScraper
from scrapers.mahindra_scraper import MahindraScraper
from scrapers.marico_scraper import MaricoScraper
from scrapers.meta_scraper import MetaScraper
from scrapers.microsoft_scraper import MicrosoftScraper
from scrapers.morganstanley_scraper import MorganStanleyScraper
from scrapers.nestle_scraper import NestleScraper
from scrapers.nvidia_scraper import NvidiaScraper
from scrapers.samsung_scraper import SamsungScraper
from scrapers.swiggy_scraper import SwiggyScraper
from scrapers.tcs_scraper import TCSScraper
from scrapers.tataconsumer_scraper import TataConsumerScraper
from scrapers.techmahindra_scraper import TechMahindraScraper
from scrapers.varunbeverages_scraper import VarunBeveragesScraper
from scrapers.wipro_scraper import WiproScraper
from scrapers.pepsico_scraper import PepsiCoScraper
from scrapers.bookmyshow_scraper import BookMyShowScraper
from scrapers.abbott_scraper import AbbottScraper

# New scrapers - Tech Giants
from scrapers.google_scraper import GoogleScraper
from scrapers.ibm_scraper import IBMScraper
from scrapers.apple_scraper import AppleScraper
from scrapers.intel_scraper import IntelScraper
from scrapers.dell_scraper import DellScraper
from scrapers.cisco_scraper import CiscoScraper

# New scrapers - Consulting & IT Services
from scrapers.hcltech_scraper import HCLTechScraper
from scrapers.cognizant_scraper import CognizantScraper
from scrapers.capgemini_scraper import CapgeminiScraper
from scrapers.deloitte_scraper import DeloitteScraper
from scrapers.ey_scraper import EYScraper
from scrapers.kpmg_scraper import KPMGScraper
from scrapers.pwc_scraper import PwCScraper

# New scrapers - Financial Services
from scrapers.goldmansachs_scraper import GoldmanSachsScraper
from scrapers.jpmorganchase_scraper import JPMorganChaseScraper
from scrapers.citigroup_scraper import CitigroupScraper
from scrapers.hdfcbank_scraper import HDFCBankScraper
from scrapers.icicibank_scraper import ICICIBankScraper
from scrapers.axisbank_scraper import AxisBankScraper
from scrapers.kotakmahindrabank_scraper import KotakMahindraBankScraper
from scrapers.bankofamerica_scraper import BankofAmericaScraper
from scrapers.hsbc_scraper import HSBCScraper
from scrapers.standardchartered_scraper import StandardCharteredScraper

# New scrapers - E-commerce & Startups
from scrapers.flipkart_scraper import FlipkartScraper
from scrapers.walmart_scraper import WalmartScraper
from scrapers.myntra_scraper import MyntraScraper
from scrapers.meesho_scraper import MeeshoScraper
from scrapers.zepto_scraper import ZeptoScraper
from scrapers.paytm_scraper import PaytmScraper
from scrapers.zomato_scraper import ZomatoScraper
from scrapers.phonepe_scraper import PhonePeScraper
from scrapers.olaelectric_scraper import OlaElectricScraper
from scrapers.uber_scraper import UberScraper
from scrapers.nykaa_scraper import NykaaScraper
from scrapers.bigbasket_scraper import BigBasketScraper
from scrapers.delhivery_scraper import DelhiveryScraper
from scrapers.indigo_scraper import IndiGoScraper
from scrapers.jio_scraper import JioScraper

# New scrapers - Manufacturing & Conglomerates
from scrapers.itclimited_scraper import ITCLimitedScraper
from scrapers.larsentoubro_scraper import LarsenToubroScraper
from scrapers.relianceindustries_scraper import RelianceIndustriesScraper
from scrapers.adanigroup_scraper import AdaniGroupScraper
from scrapers.tatasteel_scraper import TataSteelScraper
from scrapers.tatamotors_scraper import TataMotorsScraper
from scrapers.hindustanunilever_scraper import HindustanUnileverScraper
from scrapers.proctergamble_scraper import ProcterGambleScraper
from scrapers.colgatepalmolive_scraper import ColgatePalmoliveScraper
from scrapers.asianpaints_scraper import AsianPaintsScraper
from scrapers.godrejgroup_scraper import GodrejGroupScraper
from scrapers.bajajauto_scraper import BajajAutoScraper

# Batch 2 - New scrapers (50 more)
from scrapers.mckinsey_scraper import McKinseyScraper
from scrapers.parleagro_scraper import ParleAgroScraper
from scrapers.zoho_scraper import ZohoScraper
from scrapers.adityabirla_scraper import AdityaBirlaScraper
from scrapers.adobe_scraper import AdobeScraper
from scrapers.mondelez_scraper import MondelezScraper
from scrapers.reckitt_scraper import ReckittScraper
from scrapers.cocacola_scraper import CocaColaScraper
from scrapers.statebankofindia_scraper import StateBankOfIndiaScraper
from scrapers.tesla_scraper import TeslaScraper
from scrapers.abbvie_scraper import AbbVieScraper
from scrapers.americanexpress_scraper import AmericanExpressScraper
from scrapers.angelone_scraper import AngelOneScraper
from scrapers.att_scraper import ATTScraper
from scrapers.boeing_scraper import BoeingScraper
from scrapers.cipla_scraper import CiplaScraper
from scrapers.cummins_scraper import CumminsScraper
from scrapers.cyient_scraper import CyientScraper
from scrapers.drreddys_scraper import DrReddysScraper
from scrapers.royalenfield_scraper import RoyalEnfieldScraper
from scrapers.elililly_scraper import EliLillyScraper
from scrapers.exxonmobil_scraper import ExxonMobilScraper
from scrapers.fedex_scraper import FedExScraper
from scrapers.fortishealthcare_scraper import FortisHealthcareScraper
from scrapers.herofincorp_scraper import HeroFinCorpScraper
from scrapers.heromotocorp_scraper import HeroMotoCorpScraper
from scrapers.hindalco_scraper import HindalcoScraper
from scrapers.honeywell_scraper import HoneywellScraper
from scrapers.hp_scraper import HPScraper
from scrapers.iifl_scraper import IIFLScraper
from scrapers.johnsonjohnson_scraper import JohnsonJohnsonScraper
from scrapers.jswenergy_scraper import JSWEnergyScraper
from scrapers.jubilantfoodworks_scraper import JubilantFoodWorksScraper
from scrapers.kpittechnologies_scraper import KPITTechnologiesScraper
from scrapers.lowes_scraper import LowesScraper
from scrapers.marutisuzuki_scraper import MarutiSuzukiScraper
from scrapers.maxlifeinsurance_scraper import MaxLifeInsuranceScraper
from scrapers.metlife_scraper import MetLifeScraper
from scrapers.muthootfinance_scraper import MuthootFinanceScraper
from scrapers.netflix_scraper import NetflixScraper
from scrapers.nike_scraper import NikeScraper
from scrapers.oraclecorporation_scraper import OracleCorporationScraper
from scrapers.persistentsystems_scraper import PersistentSystemsScraper
from scrapers.pfizer_scraper import PfizerScraper
from scrapers.piramalgroup_scraper import PiramalGroupScraper
from scrapers.qualcomm_scraper import QualcommScraper
from scrapers.salesforce_scraper import SalesforceScraper
from scrapers.shoppersstop_scraper import ShoppersStopScraper
from scrapers.starbucks_scraper import StarbucksScraper
from scrapers.sunpharma_scraper import SunPharmaScraper

# Batch 3 - New scrapers (25 more)
from scrapers.airindia_scraper import AirIndiaScraper
from scrapers.tataaig_scraper import TataAIGScraper
from scrapers.tatainternational_scraper import TataInternationalScraper
from scrapers.tataprojects_scraper import TataProjectsScraper
from scrapers.trent_scraper import TrentScraper
from scrapers.bajajelectricals_scraper import BajajElectricalsScraper
from scrapers.olam_scraper import OlamScraper
from scrapers.unitedbreweries_scraper import UnitedBreweriesScraper
from scrapers.tatapower_scraper import TataPowerScraper
from scrapers.natwestgroup_scraper import NatWestGroupScraper
from scrapers.hitachi_scraper import HitachiScraper
from scrapers.mckesson_scraper import McKessonScraper
from scrapers.birlasoft_scraper import BirlasoftScraper
from scrapers.coforge_scraper import CoforgeScraper
from scrapers.dhl_scraper import DHLScraper
from scrapers.ericsson_scraper import EricssonScraper
from scrapers.vois_scraper import VOISScraper
from scrapers.schneiderelectric_scraper import SchneiderElectricScraper
from scrapers.siemens_scraper import SiemensScraper
from scrapers.deutschebank_scraper import DeutscheBankScraper
from scrapers.bnpparibas_scraper import BNPParibasScraper
from scrapers.bp_scraper import BPScraper
from scrapers.continental_scraper import ContinentalScraper
from scrapers.dbsbank_scraper import DBSBankScraper
from scrapers.novartis_scraper import NovartisScraper

# Batch 4 - New scrapers (25 more)
from scrapers.adanienergy_scraper import AdaniEnergyScraper
from scrapers.adaniports_scraper import AdaniPortsScraper
from scrapers.americantower_scraper import AmericanTowerScraper
from scrapers.anz_scraper import ANZScraper
from scrapers.axa_scraper import AXAScraper
from scrapers.basf_scraper import BASFScraper
from scrapers.bayer_scraper import BayerScraper
from scrapers.disney_scraper import DisneyScraper
from scrapers.emiratesgroup_scraper import EmiratesGroupScraper
from scrapers.gsk_scraper import GSKScraper
from scrapers.hyundai_scraper import HyundaiScraper
from scrapers.ihg_scraper import IHGScraper
from scrapers.intuit_scraper import IntuitScraper
from scrapers.lenovo_scraper import LenovoScraper
from scrapers.lgelectronics_scraper import LGElectronicsScraper
from scrapers.mercedesbenz_scraper import MercedesBenzScraper
from scrapers.munichre_scraper import MunichReScraper
from scrapers.panasonic_scraper import PanasonicScraper
from scrapers.prestigegroup_scraper import PrestigeGroupScraper
from scrapers.riotinto_scraper import RioTintoScraper
from scrapers.spglobal_scraper import SPGlobalScraper
from scrapers.unitedhealthgroup_scraper import UnitedHealthGroupScraper
from scrapers.verizon_scraper import VerizonScraper
from scrapers.vodafoneidea_scraper import VodafoneIdeaScraper
from scrapers.whirlpool_scraper import WhirlpoolScraper

# Batch 5 - New scrapers (25 more)
from scrapers.britannia_scraper import BritanniaScraper
from scrapers.bmwgroup_scraper import BMWGroupScraper
from scrapers.crompton_scraper import CromptonScraper
from scrapers.diageo_scraper import DiageoScraper
from scrapers.dlf_scraper import DLFScraper
from scrapers.havells_scraper import HavellsScraper
from scrapers.hdfclife_scraper import HDFCLifeScraper
from scrapers.hal_scraper import HALScraper
from scrapers.honda_scraper import HondaScraper
from scrapers.icicilombard_scraper import ICICILombardScraper
from scrapers.indusindbank_scraper import IndusIndBankScraper
from scrapers.iocl_scraper import IOCLScraper
from scrapers.kajaria_scraper import KajariaScraper
from scrapers.kiaindia_scraper import KiaIndiaScraper
from scrapers.mankindpharma_scraper import MankindPharmaScraper
from scrapers.maxhealthcare_scraper import MaxHealthcareScraper
from scrapers.ntpc_scraper import NTPCScraper
from scrapers.nissan_scraper import NissanScraper
from scrapers.oyo_scraper import OyoScraper
from scrapers.pidilite_scraper import PidiliteScraper
from scrapers.saintgobain_scraper import SaintGobainScraper
from scrapers.siemensenergy_scraper import SiemensEnergyScraper
from scrapers.tatacommunications_scraper import TataCommunicationsScraper
from scrapers.toyotakirloskar_scraper import ToyotaKirloskarScraper
from scrapers.yesbank_scraper import YesBankScraper

# Batch 6 - New scrapers (25 more)
from scrapers.byd_scraper import BYDScraper
from scrapers.glencore_scraper import GlencoreScraper
from scrapers.hcc_scraper import HCCScraper
from scrapers.jktyre_scraper import JKTyreScraper
from scrapers.kalyanjewellers_scraper import KalyanJewellersScraper
from scrapers.kirloskar_scraper import KirloskarScraper
from scrapers.mitsubishi_scraper import MitsubishiScraper
from scrapers.motilaloswal_scraper import MotilalOswalScraper
from scrapers.navitasys_scraper import NavitasysScraper
from scrapers.poonawallafincorp_scraper import PoonawallaFincorpScraper
from scrapers.schaeffler_scraper import SchaefflerScraper
from scrapers.sis_scraper import SISScraper
from scrapers.sony_scraper import SonyScraper
from scrapers.suzlon_scraper import SuzlonScraper
from scrapers.swissre_scraper import SwissReScraper
from scrapers.tataadmin_scraper import TataAdminScraper
from scrapers.tataaia_scraper import TataAIAScraper
from scrapers.tencent_scraper import TencentScraper
from scrapers.ubsgroup_scraper import UBSGroupScraper
from scrapers.uflex_scraper import UflexScraper
from scrapers.vardhman_scraper import VardhmanScraper
from scrapers.varroc_scraper import VarrocScraper
from scrapers.visa_scraper import VisaScraper
from scrapers.voltas_scraper import VoltasScraper
from scrapers.volvo_scraper import VolvoScraper

# Config-based scrapers (Workday platform)
from scrapers.airbus_scraper import AirbusScraper
from scrapers.shell_scraper import ShellScraper
from scrapers.agilent_scraper import AgilentScraper
from scrapers.cadence_scraper import CadenceScraper
from scrapers.r1rcm_scraper import R1RcmScraper
from scrapers.suncor_scraper import SuncorScraper

# Config-based scrapers (Oracle HCM platform)
from scrapers.zensar_scraper import ZensarTechnologiesScraper
from scrapers.bergerpaints_scraper import BergerPaintsScraper
from scrapers.blackbox_scraper import BlackBoxScraper
from scrapers.croma_scraper import CromaScraper
from scrapers.quesscorp_scraper import QuessCorpScraper
from scrapers.tatacapital_scraper import TataCapitalScraper
from scrapers.tatachemicals_scraper import TataChemicalsScraper
from scrapers.tataplay_scraper import TataPlayScraper
from scrapers.hexaware_scraper import HexawareTechnologiesScraper

# Config-based scrapers (DarwinBox platform)
from scrapers.vedanta_scraper import VedantaScraper
from scrapers.brigadegroup_scraper import BrigadeGroupScraper
from scrapers.asahiglass_scraper import AsahiGlassScraper
from scrapers.nivabupa_scraper import NivaBupaScraper
from scrapers.jindalsaw_scraper import JindalSawScraper
from scrapers.skodavw_scraper import SkodaVWScraper
from scrapers.polycab_scraper import PolycabScraper
from scrapers.godigit_scraper import GoDigitScraper
from scrapers.tvsmotor_scraper import TVSMotorScraper
from scrapers.jswsteel_scraper import JSWSteelScraper
from scrapers.gmmco_scraper import GMMCOScraper
from scrapers.piramalfinance_scraper import PiramalFinanceScraper

# Config-based scrapers (PeopleStrong platform)
from scrapers.amararaja_scraper import AmaraRajaScraper
from scrapers.bajajfinserv_scraper import BajajFinservScraper
from scrapers.hdfcergo_scraper import HdfcErgoScraper
from scrapers.rblbank_scraper import RblBankScraper
from scrapers.starhealth_scraper import StarHealthScraper

# Config-based scrapers (Phenom/NAS/Radancy/Standard platforms)
from scrapers.target_scraper import TargetScraper
from scrapers.titan_scraper import TitanScraper
from scrapers.geaerospace_scraper import GEAerospaceScraper
from scrapers.abb_scraper import ABBScraper
from scrapers.allianz_scraper import AllianzScraper
from scrapers.warnerbros_scraper import WarnerBrosScraper
from scrapers.philips_scraper import PhilipsScraper
from scrapers.ntt_scraper import NTTScraper
from scrapers.tranetechnologies_scraper import TraneTechnologiesScraper
from scrapers.unitedairlines_scraper import UnitedAirlinesScraper
from scrapers.wellsfargo_scraper import WellsFargoScraper
from scrapers.astrazeneca_scraper import AstraZenecaScraper
from scrapers.sap_scraper import SapScraper
from scrapers.barclays_scraper import BarclaysScraper
from scrapers.hilton_scraper import HiltonScraper
from scrapers.marriott_scraper import MarriottScraper
from scrapers.bosch_scraper import BoschScraper
from scrapers.synchrony_scraper import SynchronyScraper


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
    # Batch 3 - New scrapers (25 more)
    'air india': AirIndiaScraper,
    'tata aig': TataAIGScraper,
    'tata international': TataInternationalScraper,
    'tata projects': TataProjectsScraper,
    'trent': TrentScraper,
    'bajaj electricals': BajajElectricalsScraper,
    'olam': OlamScraper,
    'united breweries': UnitedBreweriesScraper,
    'tata power': TataPowerScraper,
    'natwest group': NatWestGroupScraper,
    'natwest': NatWestGroupScraper,
    'hitachi': HitachiScraper,
    'mckesson': McKessonScraper,
    'birlasoft': BirlasoftScraper,
    'coforge': CoforgeScraper,
    'dhl': DHLScraper,
    'ericsson': EricssonScraper,
    'vois': VOISScraper,
    'schneider electric': SchneiderElectricScraper,
    'siemens': SiemensScraper,
    'deutsche bank': DeutscheBankScraper,
    'bnp paribas': BNPParibasScraper,
    'bp': BPScraper,
    'continental': ContinentalScraper,
    'dbs bank': DBSBankScraper,
    'dbs': DBSBankScraper,
    'novartis': NovartisScraper,
    # Batch 4 - New scrapers (25 more)
    'adani energy solutions': AdaniEnergyScraper,
    'adani energy': AdaniEnergyScraper,
    'adani ports': AdaniPortsScraper,
    'adani ports & sez': AdaniPortsScraper,
    'american tower': AmericanTowerScraper,
    'anz': ANZScraper,
    'axa': AXAScraper,
    'basf': BASFScraper,
    'bayer': BayerScraper,
    'disney': DisneyScraper,
    'walt disney': DisneyScraper,
    'emirates group': EmiratesGroupScraper,
    'emirates': EmiratesGroupScraper,
    'gsk': GSKScraper,
    'hyundai': HyundaiScraper,
    'hyundai motor': HyundaiScraper,
    'ihg': IHGScraper,
    'intuit': IntuitScraper,
    'lenovo': LenovoScraper,
    'lg electronics': LGElectronicsScraper,
    'lg': LGElectronicsScraper,
    'mercedes-benz': MercedesBenzScraper,
    'mercedes benz': MercedesBenzScraper,
    'munich re': MunichReScraper,
    'panasonic': PanasonicScraper,
    'prestige group': PrestigeGroupScraper,
    'rio tinto': RioTintoScraper,
    's&p global': SPGlobalScraper,
    'sp global': SPGlobalScraper,
    'unitedhealth group': UnitedHealthGroupScraper,
    'unitedhealth': UnitedHealthGroupScraper,
    'verizon': VerizonScraper,
    'vodafone idea': VodafoneIdeaScraper,
    'vi': VodafoneIdeaScraper,
    'whirlpool': WhirlpoolScraper,
    # Batch 5 - New scrapers (25 more)
    'britannia': BritanniaScraper,
    'britannia industries': BritanniaScraper,
    'bmw group': BMWGroupScraper,
    'bmw': BMWGroupScraper,
    'crompton': CromptonScraper,
    'crompton greaves': CromptonScraper,
    'diageo': DiageoScraper,
    'dlf': DLFScraper,
    'havells': HavellsScraper,
    'hdfc life': HDFCLifeScraper,
    'hal': HALScraper,
    'hindustan aeronautics': HALScraper,
    'honda': HondaScraper,
    'honda cars india': HondaScraper,
    'icici lombard': ICICILombardScraper,
    'indusind bank': IndusIndBankScraper,
    'iocl': IOCLScraper,
    'indian oil': IOCLScraper,
    'indian oil corporation': IOCLScraper,
    'kajaria': KajariaScraper,
    'kajaria ceramics': KajariaScraper,
    'kia india': KiaIndiaScraper,
    'kia': KiaIndiaScraper,
    'mankind pharma': MankindPharmaScraper,
    'max healthcare': MaxHealthcareScraper,
    'ntpc': NTPCScraper,
    'nissan': NissanScraper,
    'nissan motor': NissanScraper,
    'oyo': OyoScraper,
    'pidilite': PidiliteScraper,
    'pidilite industries': PidiliteScraper,
    'saint-gobain': SaintGobainScraper,
    'saint gobain': SaintGobainScraper,
    'siemens energy': SiemensEnergyScraper,
    'tata communications': TataCommunicationsScraper,
    'toyota kirloskar': ToyotaKirloskarScraper,
    'toyota': ToyotaKirloskarScraper,
    'yes bank': YesBankScraper,
    # Batch 6 - New scrapers (25 more)
    'byd': BYDScraper,
    'glencore': GlencoreScraper,
    'hcc': HCCScraper,
    'jk tyre': JKTyreScraper,
    'kalyan jewellers': KalyanJewellersScraper,
    'kirloskar': KirloskarScraper,
    'mitsubishi': MitsubishiScraper,
    'motilal oswal': MotilalOswalScraper,
    'navitasys': NavitasysScraper,
    'poonawalla fincorp': PoonawallaFincorpScraper,
    'schaeffler': SchaefflerScraper,
    'sis': SISScraper,
    'sony': SonyScraper,
    'suzlon': SuzlonScraper,
    'swiss re': SwissReScraper,
    'tata admin': TataAdminScraper,
    'tata aia': TataAIAScraper,
    'tencent': TencentScraper,
    'ubs group': UBSGroupScraper,
    'ubs': UBSGroupScraper,
    'uflex': UflexScraper,
    'vardhman': VardhmanScraper,
    'varroc': VarrocScraper,
    'visa': VisaScraper,
    'voltas': VoltasScraper,
    'volvo': VolvoScraper,
    # Config-based scrapers (Workday)
    'airbus': AirbusScraper,
    'shell': ShellScraper,
    'agilent': AgilentScraper,
    'agilent technologies': AgilentScraper,
    'cadence': CadenceScraper,
    'r1 rcm': R1RcmScraper,
    'r1rcm': R1RcmScraper,
    'suncor': SuncorScraper,
    'suncor energy': SuncorScraper,
    # Config-based scrapers (Oracle HCM)
    'zensar': ZensarTechnologiesScraper,
    'zensar technologies': ZensarTechnologiesScraper,
    'berger paints': BergerPaintsScraper,
    'black box': BlackBoxScraper,
    'croma': CromaScraper,
    'quess corp': QuessCorpScraper,
    'tata capital': TataCapitalScraper,
    'tata chemicals': TataChemicalsScraper,
    'tata play': TataPlayScraper,
    'hexaware': HexawareTechnologiesScraper,
    'hexaware technologies': HexawareTechnologiesScraper,
    # Config-based scrapers (DarwinBox)
    'vedanta': VedantaScraper,
    'brigade group': BrigadeGroupScraper,
    'asahi glass': AsahiGlassScraper,
    'niva bupa': NivaBupaScraper,
    'jindal saw': JindalSawScraper,
    'skoda vw': SkodaVWScraper,
    'polycab': PolycabScraper,
    'go digit': GoDigitScraper,
    'tvs motor': TVSMotorScraper,
    'jsw steel': JSWSteelScraper,
    'gmmco': GMMCOScraper,
    'piramal finance': PiramalFinanceScraper,
    # Config-based scrapers (PeopleStrong)
    'amara raja': AmaraRajaScraper,
    'amara raja group': AmaraRajaScraper,
    'bajaj finserv': BajajFinservScraper,
    'hdfc ergo': HdfcErgoScraper,
    'rbl bank': RblBankScraper,
    'star health': StarHealthScraper,
    'star health insurance': StarHealthScraper,
    # Config-based scrapers (Phenom/Standard)
    'target': TargetScraper,
    'titan': TitanScraper,
    'ge aerospace': GEAerospaceScraper,
    'abb': ABBScraper,
    'allianz': AllianzScraper,
    'warner bros': WarnerBrosScraper,
    'philips': PhilipsScraper,
    'ntt': NTTScraper,
    'trane technologies': TraneTechnologiesScraper,
    'united airlines': UnitedAirlinesScraper,
    'wells fargo': WellsFargoScraper,
    'astrazeneca': AstraZenecaScraper,
    'sap': SapScraper,
    'barclays': BarclaysScraper,
    'hilton': HiltonScraper,
    'marriott': MarriottScraper,
    'bosch': BoschScraper,
    'synchrony': SynchronyScraper,
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
    'Salesforce', 'Shoppers Stop', 'Starbucks', 'Sun Pharma',
    # Batch 3 - New scrapers (25 more)
    'Air India', 'Tata AIG', 'Tata International', 'Tata Projects', 'Trent',
    'Bajaj Electricals', 'Olam', 'United Breweries', 'Tata Power',
    'NatWest Group', 'Hitachi', 'McKesson', 'Birlasoft', 'Coforge', 'DHL',
    'Ericsson', 'VOIS', 'Schneider Electric', 'Siemens', 'Deutsche Bank',
    'BNP Paribas', 'BP', 'Continental', 'DBS Bank', 'Novartis',
    # Batch 4 - New scrapers (25 more)
    'Adani Energy Solutions', 'Adani Ports', 'American Tower', 'ANZ', 'AXA',
    'BASF', 'Bayer', 'Disney', 'Emirates Group', 'GSK',
    'Hyundai', 'IHG', 'Intuit', 'Lenovo', 'LG Electronics',
    'Mercedes-Benz', 'Munich Re', 'Panasonic', 'Prestige Group', 'Rio Tinto',
    'S&P Global', 'UnitedHealth Group', 'Verizon', 'Vodafone Idea', 'Whirlpool',
    # Batch 5 - New scrapers (25 more)
    'Britannia', 'BMW Group', 'Crompton', 'Diageo', 'DLF',
    'Havells', 'HDFC Life', 'HAL', 'Honda', 'ICICI Lombard',
    'IndusInd Bank', 'IOCL', 'Kajaria', 'Kia India', 'Mankind Pharma',
    'Max Healthcare', 'NTPC', 'Nissan', 'OYO', 'Pidilite',
    'Saint-Gobain', 'Siemens Energy', 'Tata Communications', 'Toyota Kirloskar', 'Yes Bank',
    # Batch 6 - New scrapers (25 more)
    'BYD', 'Glencore', 'HCC', 'JK Tyre', 'Kalyan Jewellers',
    'Kirloskar', 'Mitsubishi', 'Motilal Oswal', 'Navitasys', 'Poonawalla Fincorp',
    'Schaeffler', 'SIS', 'Sony', 'Suzlon', 'Swiss Re',
    'Tata Admin', 'Tata AIA', 'Tencent', 'UBS Group', 'Uflex',
    'Vardhman', 'Varroc', 'Visa', 'Voltas', 'Volvo',
    # Config-based scrapers (Workday)
    'Airbus', 'Shell', 'Agilent Technologies', 'Cadence', 'R1 RCM', 'Suncor Energy',
    # Config-based scrapers (Oracle HCM)
    'Zensar Technologies', 'Berger Paints', 'Black Box', 'Croma',
    'Quess Corp', 'Tata Capital', 'Tata Chemicals', 'Tata Play', 'Hexaware Technologies',
    # Config-based scrapers (DarwinBox)
    'Vedanta', 'Brigade Group', 'Asahi Glass', 'Niva Bupa', 'Jindal Saw',
    'Skoda VW', 'Polycab', 'Go Digit', 'TVS Motor', 'JSW Steel', 'GMMCO', 'Piramal Finance',
    # Config-based scrapers (PeopleStrong)
    'Amara Raja Group', 'Bajaj Finserv', 'HDFC Ergo', 'RBL Bank', 'Star Health Insurance',
    # Config-based scrapers (Phenom/Standard)
    'Target', 'Titan', 'GE Aerospace', 'ABB', 'Allianz', 'Warner Bros',
    'Philips', 'NTT', 'Trane Technologies', 'United Airlines',
    'Wells Fargo', 'AstraZeneca', 'SAP', 'Barclays', 'Hilton', 'Marriott', 'Bosch', 'Synchrony',
]

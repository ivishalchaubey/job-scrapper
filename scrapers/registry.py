"""
Scraper Registry - Generated from scrappers.csv.
"""
from datetime import datetime

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import LOGS_DIR

log_file = LOGS_DIR / f"registry_{datetime.now().strftime('%Y%m%d')}.log"
logger = setup_logger('registry', log_file)

from scrapers.abb_scraper import ABBScraper
from scrapers.abbott_scraper import AbbottScraper
from scrapers.abbvie_scraper import AbbVieScraper
from scrapers.accenture_scraper import AccentureScraper
from scrapers.accor_scraper import AccorScraper
from scrapers.acko_scraper import AckoScraper
from scrapers.adanienergy_scraper import AdaniEnergyScraper
from scrapers.adanigroup_scraper import AdaniGroupScraper
from scrapers.adaniports_scraper import AdaniPortsScraper
from scrapers.adidas_scraper import AdidasScraper
from scrapers.adityabirla_scraper import AdityaBirlaScraper
from scrapers.adobe_scraper import AdobeScraper
from scrapers.adp_scraper import ADPScraper
from scrapers.agilent_scraper import AgilentScraper
from scrapers.airbnb_scraper import AirbnbScraper
from scrapers.airbus_scraper import AirbusScraper
from scrapers.airindia_scraper import AirIndiaScraper
from scrapers.airtel_scraper import AirtelScraper
from scrapers.allianz_scraper import AllianzScraper
from scrapers.allstate_scraper import AllstateScraper
from scrapers.amadeus_scraper import AmadeusScraper
from scrapers.amararaja_scraper import AmaraRajaScraper
from scrapers.amazon_scraper import AmazonScraper
from scrapers.amdocs_scraper import AmdocsScraper
from scrapers.americanexpress_scraper import AmericanExpressScraper
from scrapers.americantower_scraper import AmericanTowerScraper
from scrapers.ametek_scraper import AmetekScraper
from scrapers.amgen_scraper import AmgenScraper
from scrapers.amnsindia_scraper import AMNSIndiaScraper
from scrapers.angelone_scraper import AngelOneScraper
from scrapers.anthropic_scraper import AnthropicScraper
from scrapers.aon_scraper import AonScraper
from scrapers.apollohospitals_scraper import ApolloHospitalsScraper
from scrapers.apple_scraper import AppleScraper
from scrapers.aptiv_scraper import AptivScraper
from scrapers.asahiglass_scraper import AsahiGlassScraper
from scrapers.ashokleyland_scraper import AshokLeylandScraper
from scrapers.asianpaints_scraper import AsianPaintsScraper
from scrapers.astrazeneca_scraper import AstraZenecaScraper
from scrapers.athenahealth_scraper import AthenaScraper
from scrapers.atlassian_scraper import AtlassianScraper
from scrapers.att_scraper import ATTScraper
from scrapers.ausmallfinance_scraper import AUSmallFinanceScraper
from scrapers.autodesk_scraper import AutodeskScraper
from scrapers.aws_scraper import AWSScraper
from scrapers.axa_scraper import AXAScraper
from scrapers.axisbank_scraper import AxisBankScraper
from scrapers.axtria_scraper import AxtriaScraper
from scrapers.ayefinance_scraper import AyeFinanceScraper
from scrapers.bain_scraper import BainScraper
from scrapers.bajajauto_scraper import BajajAutoScraper
from scrapers.bajajelectricals_scraper import BajajElectricalsScraper
from scrapers.bajajfinserv_scraper import BajajFinservScraper
from scrapers.bankofamerica_scraper import BankofAmericaScraper
from scrapers.barclays_scraper import BarclaysScraper
from scrapers.basf_scraper import BASFScraper
from scrapers.bayer_scraper import BayerScraper
from scrapers.bcg_scraper import BCGScraper
from scrapers.bectondickinson_scraper import BectonDickinsonScraper
from scrapers.bergerpaints_scraper import BergerPaintsScraper
from scrapers.bharatpe_scraper import BharatPeScraper
from scrapers.biocon_scraper import BioconScraper
from scrapers.birlasoft_scraper import BirlasoftScraper
from scrapers.blackbox_scraper import BlackBoxScraper
from scrapers.blackrock_scraper import BlackRockScraper
from scrapers.bluestar_scraper import BlueStarScraper
from scrapers.blueyonder_scraper import BlueYonderScraper
from scrapers.bms_scraper import BMSScraper
from scrapers.bnpparibas_scraper import BNPParibasScraper
from scrapers.bny_scraper import BNYScraper
from scrapers.boeing_scraper import BoeingScraper
from scrapers.bookmyshow_scraper import BookMyShowScraper
from scrapers.bosch_scraper import BoschScraper
from scrapers.bp_scraper import BPScraper
from scrapers.brigadegroup_scraper import BrigadeGroupScraper
from scrapers.britannia_scraper import BritanniaScraper
from scrapers.broadridge_scraper import BroadridgeScraper
from scrapers.cadence_scraper import CadenceScraper
from scrapers.capco_scraper import CapcoScraper
from scrapers.capgemini_scraper import CapgeminiScraper
from scrapers.capitalone_scraper import CapitalOneScraper
from scrapers.carelon_scraper import CarelonScraper
from scrapers.cargill_scraper import CargillScraper
from scrapers.cars24_scraper import CARS24Scraper
from scrapers.caterpillar_scraper import CaterpillarScraper
from scrapers.cbre_scraper import CBREScraper
from scrapers.centuryply_scraper import CenturyPlyScraper
from scrapers.chevron_scraper import ChevronScraper
from scrapers.chubb_scraper import ChubbScraper
from scrapers.cipla_scraper import CiplaScraper
from scrapers.cisco_scraper import CiscoScraper
from scrapers.citigroup_scraper import CitigroupScraper
from scrapers.cloudflare_scraper import CloudflareScraper
from scrapers.cocacola_scraper import CocaColaScraper
from scrapers.coforge_scraper import CoforgeScraper
from scrapers.cognizant_scraper import CognizantScraper
from scrapers.coinbase_scraper import CoinbaseScraper
from scrapers.colgatepalmolive_scraper import ColgatePalmoliveScraper
from scrapers.collinsaerospace_scraper import CollinsAerospaceScraper
from scrapers.continental_scraper import ContinentalScraper
from scrapers.coursera_scraper import CourseraScraper
from scrapers.cred_scraper import CREDScraper
from scrapers.croma_scraper import CromaScraper
from scrapers.crompton_scraper import CromptonScraper
from scrapers.csv_missing_scrapers import AdityaBirlaFashionAndRetailPlaceholderScraper
from scrapers.csv_missing_scrapers import AdvancedMicroDevicesPlaceholderScraper
from scrapers.csv_missing_scrapers import BhartiAxaLifeInsuranceCompanyPlaceholderScraper
from scrapers.csv_missing_scrapers import GallanttIspatPlaceholderScraper
from scrapers.csv_missing_scrapers import GlgPlaceholderScraper
from scrapers.csv_missing_scrapers import HdbFinancialServicesPlaceholderScraper
from scrapers.csv_missing_scrapers import IqviaPlaceholderScraper
from scrapers.csv_missing_scrapers import LululemonPlaceholderScraper
from scrapers.csv_missing_scrapers import PhysicsWallahPlaceholderScraper
from scrapers.csv_missing_scrapers import ServicenowPlaceholderScraper
from scrapers.csv_missing_scrapers import SevenIHoldingsPlaceholderScraper
from scrapers.csv_missing_scrapers import SmollanPlaceholderScraper
from scrapers.csv_missing_scrapers import TeamleaseServicesPlaceholderScraper
from scrapers.csv_missing_scrapers import VirtusaPlaceholderScraper
from scrapers.cummins_scraper import CumminsScraper
from scrapers.cvent_scraper import CventScraper
from scrapers.cyient_scraper import CyientScraper
from scrapers.dbsbank_scraper import DBSBankScraper
from scrapers.dcbbank_scraper import DCBBankScraper
from scrapers.delhivery_scraper import DelhiveryScraper
from scrapers.dell_scraper import DellScraper
from scrapers.deloitte_scraper import DeloitteScraper
from scrapers.deutschebahn_scraper import DeutscheBahnScraper
from scrapers.deutschebank_scraper import DeutscheBankScraper
from scrapers.deutschetelekom_scraper import DeutscheTelekomScraper
from scrapers.dhl_scraper import DHLScraper
from scrapers.diageo_scraper import DiageoScraper
from scrapers.disney_scraper import DisneyScraper
from scrapers.dow_scraper import DowScraper
from scrapers.dpworld_scraper import DPWorldScraper
from scrapers.drreddys_scraper import DrReddysScraper
from scrapers.ea_scraper import EAScraper
from scrapers.easemytrip_scraper import EaseMyTripScraper
from scrapers.ebay_scraper import EbayScraper
from scrapers.eichermotors_scraper import EicherMotorsScraper
from scrapers.elililly_scraper import EliLillyScraper
from scrapers.encora_scraper import EncoraScraper
from scrapers.epam_scraper import EPAMScraper
from scrapers.ericsson_scraper import EricssonScraper
from scrapers.esafbank_scraper import ESAFBankScraper
from scrapers.essar_scraper import EssarGroupScraper
from scrapers.expediagroup_scraper import ExpediaGroupScraper
from scrapers.experian_scraper import ExperianScraper
from scrapers.exxonmobil_scraper import ExxonMobilScraper
from scrapers.ey_scraper import EYScraper
from scrapers.fedex_scraper import FedExScraper
from scrapers.ferrero_scraper import FerreroScraper
from scrapers.finolex_scraper import FinolexScraper
from scrapers.firstamerican_scraper import FirstAmericanScraper
from scrapers.firstsource_scraper import FirstsourceScraper
from scrapers.flipkart_scraper import FlipkartScraper
from scrapers.flixbus_scraper import FlixBusScraper
from scrapers.fortishealthcare_scraper import FortisHealthcareScraper
from scrapers.fractal_scraper import FractalScraper
from scrapers.franklintempleton_scraper import FranklinTempletonScraper
from scrapers.freshworks_scraper import FreshworksScraper
from scrapers.fujitsu_scraper import FujitsuScraper
from scrapers.fynd_scraper import FyndScraper
from scrapers.gac_scraper import GACScraper
from scrapers.gainwell_scraper import GainwellScraper
from scrapers.gallagher_scraper import GallagherScraper
from scrapers.gartner_scraper import GartnerScraper
from scrapers.geaerospace_scraper import GEAerospaceScraper
from scrapers.geappliances_scraper import GEAppliancesScraper
from scrapers.gehealthcare_scraper import GEHealthCareScraper
from scrapers.generali_scraper import GeneraliScraper
from scrapers.genpact_scraper import GenpactScraper
from scrapers.gevernova_scraper import GEVernovaScraper
from scrapers.glencore_scraper import GlencoreScraper
from scrapers.godaddy_scraper import GoDaddyScraper
from scrapers.godrejgroup_scraper import GodrejGroupScraper
from scrapers.goldmansachs_scraper import GoldmanSachsScraper
from scrapers.google_scraper import GoogleScraper
from scrapers.grab_scraper import GrabScraper
from scrapers.granulesindia_scraper import GranulesScraper
from scrapers.gsk_scraper import GSKScraper
from scrapers.guardian_scraper import GuardianScraper
from scrapers.hal_scraper import HALScraper
from scrapers.haptik_scraper import HaptikScraper
from scrapers.hashedin_scraper import HashedInScraper
from scrapers.hcc_scraper import HCCScraper
from scrapers.hcltech_scraper import HCLTechScraper
from scrapers.hdfcbank_scraper import HDFCBankScraper
from scrapers.hdfcergo_scraper import HdfcErgoScraper
from scrapers.hdfclife_scraper import HDFCLifeScraper
from scrapers.herofincorp_scraper import HeroFinCorpScraper
from scrapers.heromotocorp_scraper import HeroMotoCorpScraper
from scrapers.hexaware_scraper import HexawareTechnologiesScraper
from scrapers.hilton_scraper import HiltonScraper
from scrapers.hindalco_scraper import HindalcoScraper
from scrapers.hindustanunilever_scraper import HindustanUnileverScraper
from scrapers.hitachi_scraper import HitachiScraper
from scrapers.hm_scraper import HMScraper
from scrapers.honda_scraper import HondaScraper
from scrapers.honeywell_scraper import HoneywellScraper
from scrapers.hp_scraper import HPScraper
from scrapers.hpe_scraper import HPEScraper
from scrapers.hsbc_scraper import HSBCScraper
from scrapers.htcglobal_scraper import HTCGlobalScraper
from scrapers.hyundaimobis_scraper import HyundaiMobisScraper
from scrapers.ibm_scraper import IBMScraper
from scrapers.icicibank_scraper import ICICIBankScraper
from scrapers.ifb_scraper import IFBScraper
from scrapers.ihg_scraper import IHGScraper
from scrapers.iifl_scraper import IIFLScraper
from scrapers.impetus_scraper import ImpetusScraper
from scrapers.indegene_scraper import IndegeneScraper
from scrapers.indusindbank_scraper import IndusIndBankScraper
from scrapers.infosys_scraper import InfosysScraper
from scrapers.ingersollrand_scraper import IngersollRandScraper
from scrapers.inmobi_scraper import InMobiScraper
from scrapers.innovaccer_scraper import InnovaccerScraper
from scrapers.intel_scraper import IntelScraper
from scrapers.intuit_scraper import IntuitScraper
from scrapers.invesco_scraper import InvescoScraper
from scrapers.itclimited_scraper import ITCLimitedScraper
from scrapers.jindalsaw_scraper import JindalSawScraper
from scrapers.jio_scraper import JioScraper
from scrapers.jkbank_scraper import JKBankScraper
from scrapers.jll_scraper import JLLScraper
from scrapers.johnsonjohnson_scraper import JohnsonJohnsonScraper
from scrapers.jpmorganchase_scraper import JPMorganChaseScraper
from scrapers.jswenergy_scraper import JSWEnergyScraper
from scrapers.jswsteel_scraper import JSWSteelScraper
from scrapers.jubilantfoodworks_scraper import JubilantFoodWorksScraper
from scrapers.kalyanjewellers_scraper import KalyanJewellersScraper
from scrapers.kenvue_scraper import KenvueScraper
from scrapers.kiaindia_scraper import KiaIndiaScraper
from scrapers.kirloskar_scraper import KirloskarScraper
from scrapers.kkr_scraper import KKRScraper
from scrapers.kotakmahindrabank_scraper import KotakMahindraBankScraper
from scrapers.kpittechnologies_scraper import KPITTechnologiesScraper
from scrapers.kpmg_scraper import KPMGScraper
from scrapers.larsentoubro_scraper import LarsenToubroScraper
from scrapers.lenovo_scraper import LenovoScraper
from scrapers.linkedin_lever_scraper import LinkedInLeverScraper
from scrapers.lodha_scraper import LodhaScraper
from scrapers.loreal_scraper import LorealScraper
from scrapers.lowes_scraper import LowesScraper
from scrapers.lucastvs_scraper import LucasTVSScraper
from scrapers.maersk_scraper import MaerskScraper
from scrapers.mahindra_scraper import MahindraScraper
from scrapers.makemytrip_scraper import MakeMyTripScraper
from scrapers.marico_scraper import MaricoScraper
from scrapers.marriott_scraper import MarriottScraper
from scrapers.marutisuzuki_scraper import MarutiSuzukiScraper
from scrapers.mastercard_scraper import MastercardScraper
from scrapers.maxlifeinsurance_scraper import MaxLifeInsuranceScraper
from scrapers.mcdonalds_scraper import McDonaldsScraper
from scrapers.mckinsey_scraper import McKinseyScraper
from scrapers.meesho_scraper import MeeshoScraper
from scrapers.mercedesbenz_scraper import MercedesBenzScraper
from scrapers.meta_scraper import MetaScraper
from scrapers.metlife_scraper import MetLifeScraper
from scrapers.microsoft_scraper import MicrosoftScraper
from scrapers.mitsubishi_scraper import MitsubishiScraper
from scrapers.mondelez_scraper import MondelezScraper
from scrapers.morganstanley_scraper import MorganStanleyScraper
from scrapers.motilaloswal_scraper import MotilalOswalScraper
from scrapers.motorolasolutions_scraper import MotorolaSolutionsScraper
from scrapers.msctechnology_scraper import MSCTechnologyScraper
from scrapers.munichre_scraper import MunichReScraper
from scrapers.muthootfinance_scraper import MuthootFinanceScraper
from scrapers.myntra_scraper import MyntraScraper
from scrapers.natwestgroup_scraper import NatWestGroupScraper
from scrapers.nestle_scraper import NestleScraper
from scrapers.netflix_scraper import NetflixScraper
from scrapers.nike_scraper import NikeScraper
from scrapers.nivabupa_scraper import NivaBupaScraper
from scrapers.notion_scraper import NotionScraper
from scrapers.novartis_scraper import NovartisScraper
from scrapers.npci_scraper import NPCIScraper
from scrapers.ntt_scraper import NTTScraper
from scrapers.nvidia_scraper import NvidiaScraper
from scrapers.nykaa_scraper import NykaaScraper
from scrapers.odoo_scraper import OdooScraper
from scrapers.openai_scraper import OpenAIScraper
from scrapers.oraclecorporation_scraper import OracleCorporationScraper
from scrapers.otis_scraper import OtisScraper
from scrapers.panasonic_scraper import PanasonicScraper
from scrapers.parleagro_scraper import ParleAgroScraper
from scrapers.paypal_workday_scraper import PayPalWorkdayScraper
from scrapers.paytm_scraper import PaytmScraper
from scrapers.pepsico_scraper import PepsiCoScraper
from scrapers.persistentsystems_scraper import PersistentSystemsScraper
from scrapers.pfizer_scraper import PfizerScraper
from scrapers.philips_scraper import PhilipsScraper
from scrapers.phonepe_scraper import PhonePeScraper
from scrapers.piramalfinance_scraper import PiramalFinanceScraper
from scrapers.piramalgroup_scraper import PiramalGroupScraper
from scrapers.pncinfratech_scraper import PNCInfratechScraper
from scrapers.polycab_scraper import PolycabScraper
from scrapers.poonawallafincorp_scraper import PoonawallaFincorpScraper
from scrapers.proctergamble_scraper import ProcterGambleScraper
from scrapers.prudential_scraper import PrudentialScraper
from scrapers.pwc_scraper import PwCScraper
from scrapers.qualcomm_scraper import QualcommScraper
from scrapers.quesscorp_scraper import QuessCorpScraper
from scrapers.questdiagnostics_scraper import QuestDiagnosticsScraper
from scrapers.r1rcm_scraper import R1RcmScraper
from scrapers.ralphlauren_scraper import RalphLaurenScraper
from scrapers.ramcosystems_scraper import RamcoSystemsScraper
from scrapers.rblbank_scraper import RblBankScraper
from scrapers.reckitt_scraper import ReckittScraper
from scrapers.relianceindustries_scraper import RelianceIndustriesScraper
from scrapers.rippling_scraper import RipplingScraper
from scrapers.rockwellautomation_scraper import RockwellAutomationScraper
from scrapers.royalenfield_scraper import RoyalEnfieldScraper
from scrapers.rpggroup_scraper import RPGGroupScraper
from scrapers.ryan_scraper import RyanScraper
from scrapers.saintgobain_scraper import SaintGobainScraper
from scrapers.salesforce_scraper import SalesforceScraper
from scrapers.samsung_scraper import SamsungScraper
from scrapers.sap_scraper import SapScraper
from scrapers.saudiaramco_scraper import SaudiAramcoScraper
from scrapers.schaeffler_scraper import SchaefflerScraper
from scrapers.schneiderelectric_scraper import SchneiderElectricScraper
from scrapers.sharechat_scraper import ShareChatScraper
from scrapers.shell_scraper import ShellScraper
from scrapers.shoppersstop_scraper import ShoppersStopScraper
from scrapers.shriramfinance_scraper import ShriramFinanceScraper
from scrapers.siemens_scraper import SiemensScraper
from scrapers.siemensenergy_scraper import SiemensEnergyScraper
from scrapers.sis_scraper import SISScraper
from scrapers.skodavw_scraper import SkodaVWScraper
from scrapers.snowflake_scraper import SnowflakeScraper
from scrapers.societegenerale_scraper import SocieteGeneraleScraper
from scrapers.spglobal_scraper import SPGlobalScraper
from scrapers.standardchartered_scraper import StandardCharteredScraper
from scrapers.starbucks_scraper import StarbucksScraper
from scrapers.startek_scraper import StartekScraper
from scrapers.statebankofindia_scraper import StateBankOfIndiaScraper
from scrapers.stryker_scraper import StrykerScraper
from scrapers.sunpharma_scraper import SunPharmaScraper
from scrapers.swiggy_scraper import SwiggyScraper
from scrapers.swissre_scraper import SwissReScraper
from scrapers.synchrony_scraper import SynchronyScraper
from scrapers.synopsys_scraper import SynopsysScraper
from scrapers.target_scraper import TargetScraper
from scrapers.tataadmin_scraper import TataAdminScraper
from scrapers.tataadvancedsystems_scraper import TataAdvancedSystemsScraper
from scrapers.tataaia_scraper import TataAIAScraper
from scrapers.tataaig_scraper import TataAIGScraper
from scrapers.tatacapital_scraper import TataCapitalScraper
from scrapers.tatachemicals_scraper import TataChemicalsScraper
from scrapers.tatacommunications_scraper import TataCommunicationsScraper
from scrapers.tataconsumer_scraper import TataConsumerScraper
from scrapers.tatainternational_scraper import TataInternationalScraper
from scrapers.tatamotors_scraper import TataMotorsScraper
from scrapers.tataprojects_scraper import TataProjectsScraper
from scrapers.tatasteel_scraper import TataSteelScraper
from scrapers.tatatechnologies_scraper import TataTechnologiesScraper
from scrapers.tcs_scraper import TCSScraper
from scrapers.techmahindra_scraper import TechMahindraScraper
from scrapers.tesla_scraper import TeslaScraper
from scrapers.threeem_scraper import ThreeEmScraper
from scrapers.titan_scraper import TitanScraper
from scrapers.tranetechnologies_scraper import TraneTechnologiesScraper
from scrapers.trent_scraper import TrentScraper
from scrapers.truecaller_scraper import TruecallerScraper
from scrapers.tvscredit_scraper import TVSCreditScraper
from scrapers.uber_scraper import UberScraper
from scrapers.ubsgroup_scraper import UBSGroupScraper
from scrapers.uflex_scraper import UflexScraper
from scrapers.ultratechcement_scraper import UltraTechCementScraper
from scrapers.unacademy_scraper import UnacademyScraper
from scrapers.unitedairlines_scraper import UnitedAirlinesScraper
from scrapers.unitedhealthgroup_scraper import UnitedHealthGroupScraper
from scrapers.urbancompany_scraper import UrbanCompanyScraper
from scrapers.vardhman_scraper import VardhmanScraper
from scrapers.varroc_scraper import VarrocScraper
from scrapers.varunbeverages_scraper import VarunBeveragesScraper
from scrapers.vedanta_scraper import VedantaScraper
from scrapers.visa_scraper import VisaScraper
from scrapers.vodafoneidea_scraper import VodafoneIdeaScraper
from scrapers.vois_scraper import VOISScraper
from scrapers.voltas_scraper import VoltasScraper
from scrapers.volvo_scraper import VolvoScraper
from scrapers.waaree_scraper import WaareeScraper
from scrapers.walmart_scraper import WalmartScraper
from scrapers.warnerbros_scraper import WarnerBrosScraper
from scrapers.wellsfargo_scraper import WellsFargoScraper
from scrapers.welspun_scraper import WelspunScraper
from scrapers.wework_scraper import WeWorkScraper
from scrapers.whirlpool_scraper import WhirlpoolScraper
from scrapers.wipro_scraper import WiproScraper
from scrapers.workday_inc_scraper import WorkdayIncScraper
from scrapers.wpp_scraper import WPPScraper
from scrapers.wtw_scraper import WTWScraper
from scrapers.xiaomi_scraper import XiaomiScraper
from scrapers.yash_scraper import YashScraper
from scrapers.yesbank_scraper import YesBankScraper
from scrapers.zebratechnologies_scraper import ZebraTechnologiesScraper
from scrapers.zeeentertainment_scraper import ZeeEntertainmentScraper
from scrapers.zeiss_scraper import ZeissScraper
from scrapers.zensar_scraper import ZensarTechnologiesScraper
from scrapers.zepto_scraper import ZeptoScraper
from scrapers.zoho_scraper import ZohoScraper

SCRAPER_MAP = {
    'jll': JLLScraper,
    'accenture': AccentureScraper,
    'amazon': AmazonScraper,
    'amazon web services': AWSScraper,
    'bain & company': BainScraper,
    'boston consulting group': BCGScraper,
    'deloitte': DeloitteScraper,
    'ey': EYScraper,
    'flipkart': FlipkartScraper,
    'kpmg': KPMGScraper,
    'mckinsey & company': McKinseyScraper,
    'meesho': MeeshoScraper,
    'myntra': MyntraScraper,
    'parle agro': ParleAgroScraper,
    'pricewaterhousecoopers (pwc)': PwCScraper,
    'procter & gamble': ProcterGambleScraper,
    'tata administrative services': TataAdminScraper,
    'zepto': ZeptoScraper,
    'zoho corporation': ZohoScraper,
    'aditya birla group': AdityaBirlaScraper,
    'adobe inc.': AdobeScraper,
    'apple inc.': AppleScraper,
    'citigroup': CitigroupScraper,
    'cognizant': CognizantScraper,
    'colgate-palmolive': ColgatePalmoliveScraper,
    'godrej group': GodrejGroupScraper,
    'google': GoogleScraper,
    'hcltech': HCLTechScraper,
    'itc limited': ITCLimitedScraper,
    'jpmorgan chase': JPMorganChaseScraper,
    'larsen & toubro': LarsenToubroScraper,
    'mondelez international': MondelezScraper,
    'reckitt': ReckittScraper,
    'jio': JioScraper,
    'the coca-cola company': CocaColaScraper,
    'axis bank': AxisBankScraper,
    'bank of america': BankofAmericaScraper,
    'capgemini': CapgeminiScraper,
    'goldman sachs': GoldmanSachsScraper,
    'hdfc bank': HDFCBankScraper,
    'hindustan unilever limited': HindustanUnileverScraper,
    'hsbc': HSBCScraper,
    'ibm': IBMScraper,
    'icici bank': ICICIBankScraper,
    'infosys': InfosysScraper,
    'l\'oréal': LorealScraper,
    'mahindra & mahindra': MahindraScraper,
    'marico': MaricoScraper,
    'meta': MetaScraper,
    'microsoft': MicrosoftScraper,
    'morgan stanley': MorganStanleyScraper,
    'nestlé': NestleScraper,
    'nvidia': NvidiaScraper,
    'samsung': SamsungScraper,
    'state bank of india': StateBankOfIndiaScraper,
    'swiggy': SwiggyScraper,
    'tata consultancy services': TCSScraper,
    'tata consumer products': TataConsumerScraper,
    'tech mahindra': TechMahindraScraper,
    'tesla': TeslaScraper,
    'varun beverages': VarunBeveragesScraper,
    'walmart': WalmartScraper,
    'wipro': WiproScraper,
    'pepsico': PepsiCoScraper,
    'bookmyshow': BookMyShowScraper,
    'abbott laboratories': AbbottScraper,
    'abbvie': AbbVieScraper,
    'adani group': AdaniGroupScraper,
    'american express': AmericanExpressScraper,
    'angel one': AngelOneScraper,
    'asian paints': AsianPaintsScraper,
    'at&t': ATTScraper,
    'bajaj auto': BajajAutoScraper,
    'boeing': BoeingScraper,
    'cipla': CiplaScraper,
    'cummins': CumminsScraper,
    'cyient': CyientScraper,
    'dell technologies': DellScraper,
    'dr. reddy\'s laboratories': DrReddysScraper,
    'royal enfield': RoyalEnfieldScraper,
    'eli lilly and company': EliLillyScraper,
    'exxonmobil': ExxonMobilScraper,
    'fedex': FedExScraper,
    'fortis healthcare': FortisHealthcareScraper,
    'hero fincorp': HeroFinCorpScraper,
    'hero motocorp': HeroMotoCorpScraper,
    'hindalco industries': HindalcoScraper,
    'honeywell': HoneywellScraper,
    'hp inc.': HPScraper,
    'india infoline (iifl)': IIFLScraper,
    'intel': IntelScraper,
    'johnson & johnson': JohnsonJohnsonScraper,
    'jsw energy': JSWEnergyScraper,
    'jubilant foodworks': JubilantFoodWorksScraper,
    'kotak mahindra bank': KotakMahindraBankScraper,
    'kpit technologies': KPITTechnologiesScraper,
    'lowe\'s': LowesScraper,
    'maruti suzuki': MarutiSuzukiScraper,
    'max life insurance': MaxLifeInsuranceScraper,
    'metlife': MetLifeScraper,
    'muthoot finance': MuthootFinanceScraper,
    'netflix': NetflixScraper,
    'nike': NikeScraper,
    'paytm': PaytmScraper,
    'oracle corporation': OracleCorporationScraper,
    'persistent systems': PersistentSystemsScraper,
    'pfizer': PfizerScraper,
    'piramal group': PiramalGroupScraper,
    'qualcomm': QualcommScraper,
    'salesforce': SalesforceScraper,
    'shoppers stop': ShoppersStopScraper,
    'starbucks': StarbucksScraper,
    'sun pharma': SunPharmaScraper,
    'target corporation': TargetScraper,
    'tata advanced systems': TataAdvancedSystemsScraper,
    'tata communications': TataCommunicationsScraper,
    'tata motors': TataMotorsScraper,
    'tata steel': TataSteelScraper,
    'titan company': TitanScraper,
    'uber': UberScraper,
    'united airlines': UnitedAirlinesScraper,
    'unitedhealth group': UnitedHealthGroupScraper,
    'vedanta limited': VedantaScraper,
    'visa inc.': VisaScraper,
    'vodafone idea': VodafoneIdeaScraper,
    'voltas': VoltasScraper,
    'warner bros. discovery': WarnerBrosScraper,
    'wells fargo': WellsFargoScraper,
    'xiaomi': XiaomiScraper,
    'yes bank': YesBankScraper,
    'zensar technologies': ZensarTechnologiesScraper,
    'american tower': AmericanTowerScraper,
    'brigade group': BrigadeGroupScraper,
    'ge aerospace': GEAerospaceScraper,
    'abb': ABBScraper,
    'adani energy solutions': AdaniEnergyScraper,
    'adani ports & sez': AdaniPortsScraper,
    'airbus': AirbusScraper,
    'allianz': AllianzScraper,
    'amara raja group': AmaraRajaScraper,
    'asahi india glass': AsahiGlassScraper,
    'astrazeneca': AstraZenecaScraper,
    'axa': AXAScraper,
    'bajaj finserv': BajajFinservScraper,
    'barclays': BarclaysScraper,
    'basf': BASFScraper,
    'bayer': BayerScraper,
    'berger paints': BergerPaintsScraper,
    'birlasoft': BirlasoftScraper,
    'black box': BlackBoxScraper,
    'dhl group': DHLScraper,
    'bnp paribas': BNPParibasScraper,
    'bosch': BoschScraper,
    'bp': BPScraper,
    'coforge': CoforgeScraper,
    'continental': ContinentalScraper,
    'croma': CromaScraper,
    'dbs bank': DBSBankScraper,
    'dcb bank': DCBBankScraper,
    'deutsche bank': DeutscheBankScraper,
    'esaf small finance bank': ESAFBankScraper,
    'finolex group': FinolexScraper,
    'gallantt ispat': GallanttIspatPlaceholderScraper,
    'glencore': GlencoreScraper,
    'granules india': GranulesScraper,
    'gsk': GSKScraper,
    'hdfc ergo': HdfcErgoScraper,
    'hexaware technologies': HexawareTechnologiesScraper,
    'hindustan aeronautics': HALScraper,
    'hitachi': HitachiScraper,
    'hyundai mobis': HyundaiMobisScraper,
    'ifb home appliances': IFBScraper,
    'indusind bank': IndusIndBankScraper,
    'jammu and kashmir bank': JKBankScraper,
    'jindal saw': JindalSawScraper,
    'kalyan jewellers': KalyanJewellersScraper,
    'kia': KiaIndiaScraper,
    'kirloskar oil engines': KirloskarScraper,
    'lenovo': LenovoScraper,
    'lodha group': LodhaScraper,
    'mercedes-benz': MercedesBenzScraper,
    'mitsubishi heavy industries': MitsubishiScraper,
    'motilal oswal financial services': MotilalOswalScraper,
    'natwest group': NatWestGroupScraper,
    'nippon steel': AMNSIndiaScraper,
    'niva bupa': NivaBupaScraper,
    'novartis': NovartisScraper,
    'ntt': NTTScraper,
    'panasonic': PanasonicScraper,
    'philips': PhilipsScraper,
    'pnc infratech': PNCInfratechScraper,
    'polycab india': PolycabScraper,
    'poonawalla fincorp': PoonawallaFincorpScraper,
    'quess corp': QuessCorpScraper,
    'rbl bank': RblBankScraper,
    'cisco': CiscoScraper,
    'intuit': IntuitScraper,
    'saint-gobain': SaintGobainScraper,
    'sap': SapScraper,
    'schaeffler india': SchaefflerScraper,
    'schneider electric': SchneiderElectricScraper,
    'shell': ShellScraper,
    'siemens': SiemensScraper,
    'siemens energy': SiemensEnergyScraper,
    'skoda auto volkswagen india': SkodaVWScraper,
    'standard chartered': StandardCharteredScraper,
    'swiss re': SwissReScraper,
    'agilent technologies': AgilentScraper,
    'aye finance': AyeFinanceScraper,
    'cadence': CadenceScraper,
    'ihg': IHGScraper,
    'marriott international': MarriottScraper,
    's&p global': SPGlobalScraper,
    'trane technologies': TraneTechnologiesScraper,
    'ericsson': EricssonScraper,
    'hilton': HiltonScraper,
    'vois': VOISScraper,
    'r1 rcm': R1RcmScraper,
    'sis': SISScraper,
    'hdfc life': HDFCLifeScraper,
    'synchrony': SynchronyScraper,
    'tata aia life insurance': TataAIAScraper,
    'tata aig insurance': TataAIGScraper,
    'tata capital': TataCapitalScraper,
    'tata international': TataInternationalScraper,
    'tata projects': TataProjectsScraper,
    'teamlease services': TeamleaseServicesPlaceholderScraper,
    'trent limited': TrentScraper,
    'ubs group': UBSGroupScraper,
    'uflex': UflexScraper,
    'diageo': DiageoScraper,
    'vardhman': VardhmanScraper,
    'varroc': VarrocScraper,
    'air india': AirIndiaScraper,
    'volvo': VolvoScraper,
    'waaree': WaareeScraper,
    'whirlpool corporation': WhirlpoolScraper,
    'britannia industries': BritanniaScraper,
    'delhivery': DelhiveryScraper,
    'jsw steel': JSWSteelScraper,
    'nykaa': NykaaScraper,
    'shriram group': ShriramFinanceScraper,
    'tata chemicals': TataChemicalsScraper,
    'ramco systems': RamcoSystemsScraper,
    'the walt disney company': DisneyScraper,
    'bajaj electricals': BajajElectricalsScraper,
    'bharti axa life insurance company': BhartiAxaLifeInsuranceCompanyPlaceholderScraper,
    'crompton greaves consumer electricals': CromptonScraper,
    'guangzhou automobile group': GACScraper,
    'hcc': HCCScraper,
    'honda cars india': HondaScraper,
    'munich re': MunichReScraper,
    'saudi aramco': SaudiAramcoScraper,
    'au small finance bank': AUSmallFinanceScraper,
    'broadridge financial solutions': BroadridgeScraper,
    'blue yonder': BlueYonderScraper,
    'encora': EncoraScraper,
    'firstsource': FirstsourceScraper,
    'hdb financial services': HdbFinancialServicesPlaceholderScraper,
    'hewlett packard enterprise': HPEScraper,
    'servicenow': ServicenowPlaceholderScraper,
    'experian': ExperianScraper,
    'stryker corporation': StrykerScraper,
    'yash technologies': YashScraper,
    'century plyboards': CenturyPlyScraper,
    'lucas tvs': LucasTVSScraper,
    'dow inc.': DowScraper,
    'dp world': DPWorldScraper,
    'startek': StartekScraper,
    'first american': FirstAmericanScraper,
    'fractal': FractalScraper,
    'impetus': ImpetusScraper,
    'gainwell technologies': GainwellScraper,
    'ryan': RyanScraper,
    'tvs credit': TVSCreditScraper,
    'smollan': SmollanPlaceholderScraper,
    'msc technology': MSCTechnologyScraper,
    'virtusa': VirtusaPlaceholderScraper,
    'carelon global solutions': CarelonScraper,
    'hashedin': HashedInScraper,
    'piramal finance': PiramalFinanceScraper,
    'htc global': HTCGlobalScraper,
    '3m': ThreeEmScraper,
    'acko': AckoScraper,
    'aditya birla fashion and retail': AdityaBirlaFashionAndRetailPlaceholderScraper,
    'adp': ADPScraper,
    'advanced micro devices': AdvancedMicroDevicesPlaceholderScraper,
    'airbnb': AirbnbScraper,
    'airtel': AirtelScraper,
    'amgen': AmgenScraper,
    'aon': AonScraper,
    'apollo hospitals': ApolloHospitalsScraper,
    'ashok leyland': AshokLeylandScraper,
    'atlassian': AtlassianScraper,
    'autodesk': AutodeskScraper,
    'becton dickinson': BectonDickinsonScraper,
    'biocon': BioconScraper,
    'blackrock': BlackRockScraper,
    'blue star': BlueStarScraper,
    'bny': BNYScraper,
    'bristol myers squibb': BMSScraper,
    'cadence design systems': CadenceScraper,
    'capital one': CapitalOneScraper,
    'cars24': CARS24Scraper,
    'caterpillar inc.': CaterpillarScraper,
    'cbre group': CBREScraper,
    'chubb': ChubbScraper,
    'cloudflare': CloudflareScraper,
    'coinbase': CoinbaseScraper,
    'coursera': CourseraScraper,
    'cred': CREDScraper,
    'deutsche bahn': DeutscheBahnScraper,
    'deutsche telekom': DeutscheTelekomScraper,
    'dow': DowScraper,
    'easemytrip': EaseMyTripScraper,
    'ebay inc.': EbayScraper,
    'eicher motors': EicherMotorsScraper,
    'electronic arts': EAScraper,
    'epam systems': EPAMScraper,
    'essar group': EssarGroupScraper,
    'expedia group': ExpediaGroupScraper,
    'flixbus': FlixBusScraper,
    'freshworks': FreshworksScraper,
    'gallagher': GallagherScraper,
    'gartner': GartnerScraper,
    'ge healthcare': GEHealthCareScraper,
    'godaddy': GoDaddyScraper,
    'haptik': HaptikScraper,
    'indegene': IndegeneScraper,
    'ingersoll rand': IngersollRandScraper,
    'inmobi': InMobiScraper,
    'innovaccer': InnovaccerScraper,
    'invesco': InvescoScraper,
    'iqvia': IqviaPlaceholderScraper,
    'reliance industries': RelianceIndustriesScraper,
    'kenvue': KenvueScraper,
    'kkr & co.': KKRScraper,
    'linkedin': LinkedInLeverScraper,
    'lululemon': LululemonPlaceholderScraper,
    'mahindra group': MahindraScraper,
    'makemytrip': MakeMyTripScraper,
    'mastercard': MastercardScraper,
    'max group': MaxLifeInsuranceScraper,
    'mcdonald\'s': McDonaldsScraper,
    'motorola solutions': MotorolaSolutionsScraper,
    'national payments corporation of india': NPCIScraper,
    'odoo': OdooScraper,
    'openai': OpenAIScraper,
    'otis worldwide': OtisScraper,
    'paypal': PayPalWorkdayScraper,
    'phonepe': PhonePeScraper,
    'physics wallah': PhysicsWallahPlaceholderScraper,
    'prudential financial': PrudentialScraper,
    'quest diagnostics': QuestDiagnosticsScraper,
    'ralph lauren corporation': RalphLaurenScraper,
    'rippling': RipplingScraper,
    'allstate': AllstateScraper,
    'anthropic': AnthropicScraper,
    'bharatpe': BharatPeScraper,
    'notion': NotionScraper,
    'fynd': FyndScraper,
    'seven & i holdings': SevenIHoldingsPlaceholderScraper,
    'ultratech cement': UltraTechCementScraper,
    'snowflake': SnowflakeScraper,
    'société générale': SocieteGeneraleScraper,
    'synopsys': SynopsysScraper,
    'urban company': UrbanCompanyScraper,
    'willis towers watson': WTWScraper,
    'zebra technologies': ZebraTechnologiesScraper,
    'rpg group': RPGGroupScraper,
    'rockwell automation': RockwellAutomationScraper,
    'sharechat': ShareChatScraper,
    'tata technologies': TataTechnologiesScraper,
    'unacademy': UnacademyScraper,
    'welspun': WelspunScraper,
    'wework': WeWorkScraper,
    'workday, inc.': WorkdayIncScraper,
    'truecaller': TruecallerScraper,
    'zee entertainment enterprises': ZeeEntertainmentScraper,
    'maersk': MaerskScraper,
    'accor': AccorScraper,
    'adidas': AdidasScraper,
    'amadeus': AmadeusScraper,
    'amdocs': AmdocsScraper,
    'american express global business travel': AmericanExpressScraper,
    'ametek': AmetekScraper,
    'aptiv': AptivScraper,
    'athenahealth': AthenaScraper,
    'axtria': AxtriaScraper,
    'capco': CapcoScraper,
    'cargill': CargillScraper,
    'zeiss': ZeissScraper,
    'chevron': ChevronScraper,
    'collins aerospace': CollinsAerospaceScraper,
    'cvent': CventScraper,
    'ferrero': FerreroScraper,
    'franklin templeton': FranklinTempletonScraper,
    'fujitsu': FujitsuScraper,
    'ge appliances': GEAppliancesScraper,
    'ge vernova': GEVernovaScraper,
    'generali': GeneraliScraper,
    'genpact': GenpactScraper,
    'glg': GlgPlaceholderScraper,
    'grab taxi': GrabScraper,
    'wpp': WPPScraper,
    'guardian': GuardianScraper,
    'h&m': HMScraper,
}

ALL_COMPANY_CHOICES = [
    'JLL',
    'Accenture',
    'Amazon',
    'Amazon Web Services',
    'Bain & Company',
    'Boston Consulting Group',
    'Deloitte',
    'EY',
    'Flipkart',
    'KPMG',
    'McKinsey & Company',
    'Meesho',
    'Myntra',
    'Parle Agro',
    'PricewaterhouseCoopers (PwC)',
    'Procter & Gamble',
    'Tata Administrative Services',
    'Zepto',
    'Zoho Corporation',
    'Aditya Birla Group',
    'Adobe Inc.',
    'Apple Inc.',
    'Citigroup',
    'Cognizant',
    'Colgate-Palmolive',
    'Godrej Group',
    'Google',
    'HCLTech',
    'ITC Limited',
    'JPMorgan Chase',
    'Larsen & Toubro',
    'Mondelez International',
    'Reckitt',
    'Jio',
    'The Coca-Cola Company',
    'Axis Bank',
    'Bank of America',
    'Capgemini',
    'Goldman Sachs',
    'HDFC Bank',
    'Hindustan Unilever Limited',
    'HSBC',
    'IBM',
    'ICICI Bank',
    'Infosys',
    "L'Oréal",
    'Mahindra & Mahindra',
    'Marico',
    'Meta',
    'Microsoft',
    'Morgan Stanley',
    'Nestlé',
    'Nvidia',
    'Samsung',
    'State Bank of India',
    'Swiggy',
    'Tata Consultancy Services',
    'Tata Consumer Products',
    'Tech Mahindra',
    'Tesla',
    'Varun Beverages',
    'Walmart',
    'Wipro',
    'PepsiCo',
    'BookMyShow',
    'Abbott Laboratories',
    'AbbVie',
    'Adani Group',
    'American Express',
    'Angel One',
    'Asian Paints',
    'AT&T',
    'Bajaj Auto',
    'Boeing',
    'Cipla',
    'Cummins',
    'Cyient',
    'Dell Technologies',
    "Dr. Reddy's Laboratories",
    'Royal Enfield',
    'Eli Lilly and Company',
    'ExxonMobil',
    'FedEx',
    'Fortis Healthcare',
    'Hero FinCorp',
    'Hero MotoCorp',
    'Hindalco Industries',
    'Honeywell',
    'HP Inc.',
    'India Infoline (IIFL)',
    'Intel',
    'Johnson & Johnson',
    'JSW Energy',
    'Jubilant FoodWorks',
    'Kotak Mahindra Bank',
    'KPIT Technologies',
    "Lowe's",
    'Maruti Suzuki',
    'Max Life Insurance',
    'MetLife',
    'Muthoot Finance',
    'Netflix',
    'Nike',
    'Paytm',
    'Oracle Corporation',
    'Persistent Systems',
    'Pfizer',
    'Piramal Group',
    'Qualcomm',
    'Salesforce',
    'Shoppers Stop',
    'Starbucks',
    'Sun Pharma',
    'Target Corporation',
    'Tata Advanced Systems',
    'Tata Communications',
    'Tata Motors',
    'Tata Steel',
    'Titan Company',
    'Uber',
    'United Airlines',
    'UnitedHealth Group',
    'Vedanta Limited',
    'Visa Inc.',
    'Vodafone Idea',
    'Voltas',
    'Warner Bros. Discovery',
    'Wells Fargo',
    'Xiaomi',
    'Yes Bank',
    'Zensar Technologies',
    'American Tower',
    'Brigade Group',
    'GE Aerospace',
    'ABB',
    'Adani Energy Solutions',
    'Adani Ports & SEZ',
    'Airbus',
    'Allianz',
    'Amara Raja Group',
    'Asahi India Glass',
    'AstraZeneca',
    'AXA',
    'Bajaj Finserv',
    'Barclays',
    'BASF',
    'Bayer',
    'Berger Paints',
    'Birlasoft',
    'Black Box',
    'DHL Group',
    'BNP Paribas',
    'Bosch',
    'BP',
    'Coforge',
    'Continental',
    'Croma',
    'DBS Bank',
    'DCB Bank',
    'Deutsche Bank',
    'ESAF Small Finance Bank',
    'Finolex Group',
    'Gallantt Ispat',
    'Glencore',
    'Granules India',
    'GSK',
    'HDFC Ergo',
    'Hexaware Technologies',
    'Hindustan Aeronautics',
    'Hitachi',
    'Hyundai Mobis',
    'IFB Home Appliances',
    'IndusInd Bank',
    'Jammu and Kashmir Bank',
    'Jindal Saw',
    'Kalyan Jewellers',
    'Kia',
    'Kirloskar Oil Engines',
    'Lenovo',
    'Lodha Group',
    'Mercedes-Benz',
    'Mitsubishi Heavy Industries',
    'Motilal Oswal Financial Services',
    'NatWest Group',
    'Nippon Steel',
    'Niva Bupa',
    'Novartis',
    'NTT',
    'Panasonic',
    'Philips',
    'PNC Infratech',
    'Polycab India',
    'Poonawalla Fincorp',
    'Quess Corp',
    'RBL Bank',
    'Cisco',
    'Intuit',
    'Saint-Gobain',
    'SAP',
    'Schaeffler India',
    'Schneider Electric',
    'Shell',
    'Siemens',
    'Siemens Energy',
    'Skoda Auto Volkswagen India',
    'Standard Chartered',
    'Swiss Re',
    'Agilent Technologies',
    'Aye Finance',
    'Cadence',
    'IHG',
    'Marriott International',
    'S&P Global',
    'Trane Technologies',
    'Ericsson',
    'Hilton',
    'VOIS',
    'R1 RCM',
    'SIS',
    'HDFC Life',
    'Synchrony',
    'Tata AIA Life Insurance',
    'Tata AIG Insurance',
    'Tata Capital',
    'Tata International',
    'Tata Projects',
    'TeamLease Services',
    'Trent Limited',
    'UBS Group',
    'Uflex',
    'Diageo',
    'Vardhman',
    'Varroc',
    'Air India',
    'Volvo',
    'Waaree',
    'Whirlpool Corporation',
    'Britannia Industries',
    'Delhivery',
    'JSW Steel',
    'Nykaa',
    'Shriram Group',
    'Tata Chemicals',
    'Ramco Systems',
    'The Walt Disney Company',
    'Bajaj Electricals',
    'Bharti Axa Life Insurance Company',
    'Crompton Greaves Consumer Electricals',
    'Guangzhou Automobile Group',
    'HCC',
    'Honda Cars India',
    'Munich Re',
    'Saudi Aramco',
    'AU Small Finance Bank',
    'Broadridge Financial Solutions',
    'Blue Yonder',
    'Encora',
    'Firstsource',
    'HDB Financial Services',
    'Hewlett Packard Enterprise',
    'ServiceNow',
    'Experian',
    'Stryker Corporation',
    'YASH Technologies',
    'Century Plyboards',
    'Lucas TVS',
    'Dow Inc.',
    'DP World',
    'Startek',
    'First American',
    'Fractal',
    'Impetus',
    'Gainwell Technologies',
    'Ryan',
    'TVS Credit',
    'Smollan',
    'MSC Technology',
    'Virtusa',
    'Carelon Global Solutions',
    'HashedIn',
    'Piramal Finance',
    'HTC Global',
    '3M',
    'Acko',
    'Aditya Birla Fashion and Retail',
    'ADP',
    'Advanced Micro Devices',
    'Airbnb',
    'Airtel',
    'Amgen',
    'Aon',
    'Apollo Hospitals',
    'Ashok Leyland',
    'Atlassian',
    'Autodesk',
    'Becton Dickinson',
    'Biocon',
    'BlackRock',
    'Blue Star',
    'BNY',
    'Bristol Myers Squibb',
    'Cadence Design Systems',
    'Capital One',
    'CARS24',
    'Caterpillar Inc.',
    'CBRE Group',
    'Chubb',
    'Cloudflare',
    'Coinbase',
    'Coursera',
    'CRED',
    'Deutsche Bahn',
    'Deutsche Telekom',
    'Dow',
    'EaseMyTrip',
    'eBay Inc.',
    'Eicher Motors',
    'Electronic Arts',
    'EPAM Systems',
    'Essar Group',
    'Expedia Group',
    'FlixBus',
    'Freshworks',
    'Gallagher',
    'Gartner',
    'GE HealthCare',
    'GoDaddy',
    'Haptik',
    'Indegene',
    'Ingersoll Rand',
    'InMobi',
    'Innovaccer',
    'Invesco',
    'IQVIA',
    'Reliance Industries',
    'Kenvue',
    'KKR & Co.',
    'LinkedIn',
    'Lululemon',
    'Mahindra Group',
    'MakeMyTrip',
    'Mastercard',
    'Max Group',
    "McDonald's",
    'Motorola Solutions',
    'National Payments Corporation of India',
    'Odoo',
    'OpenAI',
    'Otis Worldwide',
    'PayPal',
    'PhonePe',
    'Physics Wallah',
    'Prudential Financial',
    'Quest Diagnostics',
    'Ralph Lauren Corporation',
    'Rippling',
    'Allstate',
    'Anthropic',
    'BharatPe',
    'Notion',
    'Fynd',
    'Seven & I Holdings',
    'UltraTech Cement',
    'Snowflake',
    'Société Générale',
    'Synopsys',
    'Urban Company',
    'Willis Towers Watson',
    'Zebra Technologies',
    'RPG Group',
    'Rockwell Automation',
    'ShareChat',
    'Tata Technologies',
    'Unacademy',
    'Welspun',
    'WeWork',
    'Workday, Inc.',
    'Truecaller',
    'Zee Entertainment Enterprises',
    'Maersk',
    'Accor',
    'Adidas',
    'Amadeus',
    'Amdocs',
    'American Express Global Business Travel',
    'Ametek',
    'Aptiv',
    'Athenahealth',
    'Axtria',
    'Capco',
    'Cargill',
    'Zeiss',
    'Chevron',
    'Collins Aerospace',
    'Cvent',
    'Ferrero',
    'Franklin Templeton',
    'Fujitsu',
    'GE Appliances',
    'GE Vernova',
    'Generali',
    'Genpact',
    'GLG',
    'Grab Taxi',
    'WPP',
    'Guardian',
    'H&M',
]

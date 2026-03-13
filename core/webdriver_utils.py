"""
Chrome WebDriver utilities for cross-platform ChromeDriver management.

This module provides a standardized way to set up ChromeDriver across different
operating systems without hardcoded paths.
"""
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from core.logging import setup_logger

logger = setup_logger('webdriver_utils')


def setup_chrome_driver(headless_mode=True, additional_options=None):
    """
    Set up Chrome WebDriver with cross-platform ChromeDriver management.
    
    Args:
        headless_mode (bool): Whether to run Chrome in headless mode
        additional_options (list): Additional Chrome options to add
        
    Returns:
        webdriver.Chrome: Configured Chrome WebDriver instance
        
    Raises:
        Exception: If all ChromeDriver setup methods fail
    """
    chrome_options = Options()
    
    # Standard options for scraping
    if headless_mode:
        chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
    
    # Add any additional options
    if additional_options:
        for option in additional_options:
            chrome_options.add_argument(option)
    
    # Method 1: Try environment variable (allows custom paths)
    custom_path = os.getenv('CHROMEDRIVER_PATH')
    if custom_path and os.path.exists(custom_path):
        try:
            logger.info(f"Using custom ChromeDriver from CHROMEDRIVER_PATH: {custom_path}")
            service = Service(custom_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            # Anti-detection measures
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            })
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            logger.warning(f"Custom ChromeDriver failed: {e}")
    
    # Method 2: Use webdriver-manager (automatic download & management)
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        logger.info("Using webdriver-manager to handle ChromeDriver")
        driver_path = ChromeDriverManager().install()
        logger.info(f"ChromeDriver installed/found at: {driver_path}")
        
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        # Anti-detection measures
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        logger.warning(f"webdriver-manager failed: {e}")
    
    # Method 3: Try system PATH (if ChromeDriver is installed globally)
    try:
        logger.info("Trying system ChromeDriver from PATH")
        driver = webdriver.Chrome(options=chrome_options)
        # Anti-detection measures
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        logger.error(f"All ChromeDriver setup methods failed: {e}")
        raise Exception(
            "Could not setup ChromeDriver. Please either:\n"
            "1. Set CHROMEDRIVER_PATH environment variable to your ChromeDriver path, or\n"
            "2. Ensure ChromeDriver is in your system PATH, or\n"
            "3. Let webdriver-manager handle it automatically (recommended)\n\n"
            "To install webdriver-manager: pip install webdriver-manager"
        )


def get_chrome_options_for_scraping(headless_mode=True, additional_options=None):
    """
    Get standardized Chrome options for web scraping.
    
    Args:
        headless_mode (bool): Whether to run Chrome in headless mode
        additional_options (list): Additional Chrome options to add
        
    Returns:
        Options: Configured Chrome options
    """
    chrome_options = Options()
    
    # Standard scraping options
    if headless_mode:
        chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
    
    # Add any additional options
    if additional_options:
        for option in additional_options:
            chrome_options.add_argument(option)
    
    return chrome_options
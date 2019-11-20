from selenium.webdriver.chrome.options import Options
import time
from selenium.common.exceptions import NoSuchElementException
import bibtexparser
import zerorpc
import requests
from util.logs import get_logger


logger = get_logger('search')


def parse_bib(text):
    try:
        pp = bibtexparser.loads(text)
        pp = pp.get_entry_list()[0]
        return pp
    except Exception as e:
        print(e)
    return {}

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.expected_conditions import presence_of_element_located

#This example requires Selenium WebDriver 3.13 or newer

def get_info(driver, frame, inner, default=''):
    try:
        return driver.find_element_by_class_name(frame).find_element_by_class_name(inner).text
    except NoSuchElementException:
        return default
    except Exception as e:
        print(e)
    return default
    

    
class HelloRPC(object):
    def __init__(self):
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        self.driver = webdriver.Chrome(options=chrome_options)
        logger.info('starting searvice...')
    
    def hello(self, query):
        # wait = WebDriverWait(self.driver, 10)
        logger.info(f'query {query}')
        self.driver.get(f"http://xueshu.baidu.com/s?wd={query}")
        try:
            xx = self.driver.find_element_by_id("1")
            xx = xx.find_element_by_class_name('c_font')
            xx = xx.find_element_by_tag_name('a')
            new_url = xx.get_property('href')
            print(new_url)
            self.driver.get(new_url)
            print(self.driver.current_url)
        except NoSuchElementException as e:
            pass
        quot = self.driver.find_element_by_class_name('paper_q')
        quot.click()
        print(quot.text)
        citi = WebDriverWait(self.driver, timeout=3).until(lambda d: d.find_element_by_class_name('sc_quote_citi'))
        citi = citi.find_element_by_link_text('BibTeX')
        bib_tex_file_url = citi.get_property('href')
        bib_tex = requests.get(bib_tex_file_url).text
        bib_info = parse_bib(bib_tex)
        if 'author' in bib_info:
            bib_info['author'] = bib_info['author'].replace(' and ', '; ')
        
        bib_info['abstract'] = get_info(self.driver, 'abstract_wr', 'abstract')
        bib_info['keyword']  = get_info(self.driver, 'kw_main', 'kw_wr')
        bib_info['DOI'] = get_info(self.driver, 'doi_wr', 'kw_main')
        
        
        for k, v in bib_info.items():
            print(f'{k:15s}: {v}')
        return bib_info

s = zerorpc.Server(HelloRPC())
s.bind("tcp://0.0.0.0:4242")
s.run()


# query = 'R-CNN'
# with webdriver.Chrome(options=chrome_options) as driver:
#     wait = WebDriverWait(driver, 10)
#     driver.get(f"http://xueshu.baidu.com/s?wd={query}")
#     try:
#         xx = driver.find_element_by_id("1")
#         xx = xx.find_element_by_class_name('c_font')
#         xx = xx.find_element_by_tag_name('a')
#         new_url = xx.get_property('href')
#         print(new_url)
#         driver.get(new_url)
#         print(driver.current_url)
#     except NoSuchElementException as e:
#         pass
#     quot = driver.find_element_by_class_name('paper_q')
#     quot.click()
#     print(quot.text)
#     citi = WebDriverWait(driver, timeout=3).until(lambda d: d.find_element_by_class_name('sc_quote_citi'))
#     citi = citi.find_element_by_link_text('BibTeX')
#     bib_tex_file_url = citi.get_property('href')
#     bib_tex = requests.get(bib_tex_file_url).text
#     bib_info = parse_bib(bib_tex)
#     if 'author' in bib_info:
#         bib_info['author'] = bib_info['author'].replace(' and ', '; ')
    
#     bib_info['abstract'] = get_info(driver, 'abstract_wr', 'abstract')
#     bib_info['keyword']  = get_info(driver, 'kw_main', 'kw_wr')
#     bib_info['DOI'] = get_info(driver, 'doi_wr', 'kw_main')
    
    
#     for k, v in bib_info.items():
#         print(f'{k:15s}: {v}')

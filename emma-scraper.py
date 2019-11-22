# coding=utf-8
'''
    get issuer/ issues from emma.msrb.org 
    date: 22/10/2019
'''

from bs4 import BeautifulSoup as Soup
from collections import OrderedDict
from csv import DictWriter as CsvDictWriter
from json import loads as json_decode
from re import search as re_search
from requests import session
from selenium.webdriver import PhantomJS
from sys import exit as sys_exit, platform
from time import sleep

# disable selenium warnings
import warnings
warnings.filterwarnings('ignore')

# wait seconds
REQUEST_WAIT_TIME = 1 
CUSIPS_FILE_NAME = "cusips.txt"

# Request's session (to save the clicked "Accept" button)
s = session()

def get_cusips():
    try:
        with open(CUSIPS_FILE_NAME) as cusips_file:
            cusips = list(set([x.strip() for x in cusips_file.readlines() if x.strip()]))
    except Exception:
        print("The file %s not found. The file will be created. "
            "Please, put the list of CUSIPS there." % CUSIPS_FILE_NAME)
        sys.exit(2)

    return cusips

def due_pause():
    sleep(REQUEST_WAIT_TIME)    

def scrape_issuers(cusip, soup):
    PATTERN = r'(?P<a>pdata.issuerIssuesJson)( = )(?P<b>\[.*\])'
    iss = []

    try:
        regex = re_search(PATTERN, soup.text).groupdict()
        json = regex.get('b')
        issuerJson = json_decode(json)
    except Exception as e:
        return None

    for issue in issuerJson:

        issuer = OrderedDict()
        issuer['issuer_name'] = soup.find('div', {'class': ['card','grey-band','grey-header']}).find('h3').text
        issuer['issuer_cusip'] = cusip
        issuer['Issue_ID'] = issue['IID']
        issuer['issue_desc'] = issue['IDES']
        issuer['issue_date'] = issue['DDT']
        issuer['maturity_dates'] = issue['MDR']

        # Add dict to temporary storage
        iss.append(issuer)
    return iss

def check_agree(link, soup):
    # Agree if asked to (click on accept)

    if soup.find('input', { 'id' : 'ctl00_mainContentArea_disclaimerContent_yesButton'}):
        print("Agreeing the terms of use - please wait...")
        driver = PhantomJS('.\phantomjs.exe' if platform.startswith('win32') else './phantomjs')
        driver.get(link)
        driver.find_element_by_id('ctl00_mainContentArea_disclaimerContent_yesButton').click()
        for cookie in driver.get_cookies():
            s.cookies.set(cookie['name'], cookie['value'])
        driver.quit()
        resp_inner = s.get(link)
        soup = Soup(resp_inner.text, features="lxml")
        print("Done, now let's get back to the scraping process.")
    
    return soup

def clean_text(text):
    # remove undesired chars from text

    return (text
            .replace('*', '')
            .replace('%', '')
            .strip())

def format_as_header(text):
    # convert text into an appropiated header

    return (
        clean_text(text)
            .lower()
            .replace(':', '')
            .replace(' ', '_')
    )

def export_csv(output_name, rows):
    # export array of dicts to csv

    with open(output_name, 'w', newline='') as file:
        first_row = rows[0]
        keys = first_row.keys()
        writer = CsvDictWriter(file, keys)

        writer.writeheader()
        writer.writerows(rows)

def main():

    # Read the CUSIPS from file
    cusips = get_cusips()

    # To save the scraper result
    db1 = []
    db2 = []

    for i, cusip in enumerate(cusips):

        # Get CUSIP page and parse it
        print('Getting CUSIP no. %s out of %s ("%s")' % (i + 1, len(cusips), cusip))
        base_cusip_url = 'https://emma.msrb.org/IssuerView/IssuerDetails.aspx?cusip=%s'
        req_url = base_cusip_url % cusip
        issuers = []

        resp = s.get(req_url)
        soup_inner = Soup(resp.text, features="lxml")
        soup_inner = check_agree(req_url, soup_inner)
        
        l = scrape_issuers(cusip, soup_inner)

        if l:
            issuers.extend(l)
        else:
            print('There is no info on CUSIP no. %s - heading to the next!' % cusip)
            continue

        for j, issuer in enumerate(issuers):
            
            print("Scraping issuer no. %s (out of %s)" % (j+1, len(issuers)))
            # Get the link we've saved
            link = 'https://emma.msrb.org/IssueView/Details/' + issuer['Issue_ID']
            resp_inner = s.get(link)
            soup_inner = Soup(resp_inner.text, features="lxml")

            # check agree
            soup_inner = check_agree(link, soup_inner)

            # top area
            top_div = soup_inner.find('div', {'class': ['card','grey-band','grey-header']})
            top_h3 = top_div.find('h3')
            top_h5 = top_div.find('h5')

            # Add additional descriptions
            issuer['issue_desc2'] = clean_text(top_h3.text) if top_h3 else ''
            issuer['issue_desc3'] = clean_text(top_h5.text) if top_h5 else ''

            # Add ready item to output database
            db1.append(issuer)
            
            # Scrape additional info
            labels = {
                format_as_header(x.find('span', {'class' : 'label'}).text)
                :
                clean_text(x.find('span', {'class' : 'float-right'}).text) 
                for x in soup_inner.find('div', { 'class' : 'blue-box'})
                                .findAll( 'li')
            }

            # Scrape the second items
            link = 'https://emma.msrb.org/IssueView/GetFinalScaleData?id=' + issuer['Issue_ID']
            resp_inner = s.get(link)
            details_json = json_decode(resp_inner.text)

            for info_json in details_json:
                issue = {
                    'issue_id' : issuer['Issue_ID'],
                    'cusip' : info_json['cusip9'],
                    'principal_amount_at_issuance' : info_json['MatPrinTxt'],
                    'security_description' : info_json['SecurityDescription'],
                    'coupon' : clean_text(info_json['IntRateTxt']),
                    'maturity_date' : info_json['MatDtTxt'],
                    'price_or_yield' : clean_text(info_json['IOPTxt']),
                    'price' : clean_text(info_json['NiidsIOPTxt']),
                    'yield' : clean_text(info_json['NiidsIOYTxt']),
                    'fitch' : '', # info_json['FitchRateEnc'],
                    'kbra' : '', # info_json['KrollRateEnc'],
                    'moody' : '', # info_json['MoodyRateEnc'],
                    's&p' : '', #info_json['SnpRateEnc'],
                }

                # append issuer extra info
                for label in labels:
                    issue[label] = labels.get(label)

                # Add the ready item to output database
                db2.append(issue)

            due_pause()

        print('Done!')

    print("Successfully got everything - starting to make CSVs.")

    # exporting zone
    export_csv('db1.csv', db1)
    export_csv('db2.csv', db2)

    print("The *WHOLE* process is done!")

if __name__ == '__main__':
    main()

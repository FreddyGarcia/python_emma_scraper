# coding=utf-8
import csv
import sys
from collections import OrderedDict

import re
from lxml.html import fromstring
from requests import session
from selenium.webdriver import PhantomJS
from bs4 import BeautifulSoup as Soup
from json import loads as json_decode

PHANTOMJS_PATH = 'phantomjs-2.1.1-windows\\bin\\phantomjs.exe'
CUSIPS_FILE_NAME = "cusips.txt"
# Read the CUSIPS from file
try:
    with open(CUSIPS_FILE_NAME) as cusips_file:
        cusips = list(set([x.strip() for x in cusips_file.readlines() if x.strip()]))
except Exception:
    print("The file %s not found. The file will be created. "
          "Please, put the list of CUSIPS there." % CUSIPS_FILE_NAME)
    open(CUSIPS_FILE_NAME, "w").close()
    sys.exit(2)

# Set of keys for additional fields
keys_set = set()

# Two lists for databases
db1 = []
db2 = []
db1_headers = ['issuer_name', 'issuer_cusip', 'uuid', 'issue_desc', 'issue_date', 'issue_dates', 'issue_desc2',
               'issue_desc3']
db2_headers = ['uuid',]

# Request's session (to save the clicked "Accept" button)
s = session()


def scrape_issuers(soup):
    PATTERN = r'(?P<a>pdata.issuerIssuesJson)( = )(?P<b>\[.*\])'
    iss = []

    try:
        regex = re.search(PATTERN, soup_inner.text).groupdict()
        json = regex.get('b')
        issuerJson = json_decode(json)
    except Exception as e:
        return None

    for issue in issuerJson:

        issuer = OrderedDict()
        issuer['issuer_name'] = soup.find('div', {'class': ['card','grey-band','grey-header']}).find('h3').text
        issuer['issuer_cusip'] = cusip
        issuer['uuid'] = issue['IID']
        issuer['issue_desc'] = issue['IDES']
        issuer['issue_date'] = issue['DDT']
        issuer['issue_dates'] = issue['MDR']

        # deprecated
        # issuer['issue_state'] = issue['IDES']

        # Add dict to temporary storage
        iss.append(issuer)
    return iss


def check_agree(link, soup):
    # Agree if asked to (click on accept)

    if soup.find('input', { 'id' : 'ctl00_mainContentArea_disclaimerContent_yesButton'}):
        print("Agreeing the terms of use - please wait...")
        driver = PhantomJS('.\phantomjs.exe' if sys.platform.startswith('win32') else './phantomjs')
        driver.get(link)
        driver.find_element_by_id('ctl00_mainContentArea_disclaimerContent_yesButton').click()
        for cookie in driver.get_cookies():
            s.cookies.set(cookie['name'], cookie['value'])
        driver.quit()
        resp_inner = s.get(link)
        soup = Soup(resp_inner.text, features="lxml")
        # tree = fromstring(resp_inner.text)
        print("Done, now let's get back to the scraping process.")
    
    return soup


def clean_text(text):
    return (text
            .replace('*', '')
            .replace('%', '')
            .strip())


def export_csv(output_name, rows):

    with open(output_name, 'w', newline='') as file:
        first_row = rows[0]
        keys = first_row.keys()
        writer = csv.DictWriter(file, keys)

        writer.writeheader()
        writer.writerows(rows)



for i, cusip in enumerate(cusips):

    # Get CUSIP page and parse it
    print('Getting CUSIP no. %s out of %s ("%s")' % (i + 1, len(cusips), cusip))
    base_cusip_url = 'https://emma.msrb.org/IssuerView/IssuerDetails.aspx?cusip=%s'
    req_url = base_cusip_url % cusip
    issuers = []

    resp = s.get(req_url)
    soup_inner = Soup(resp.text, features="lxml")
    soup_inner = check_agree(req_url, soup_inner)
    
    print("Scraping page no. 1")
    l = scrape_issuers(soup_inner)

    if l:
        issuers.extend(l)
    else:
        print('There is no info on CUSIP no. %s - heading to the next!' % cusip)
        continue

    for j, issuer in enumerate(issuers):
        print("Scraping issuer no. %s (out of %s)" % (j+1, len(issuers)))
        # Get the link we've saved
        link = 'https://emma.msrb.org/IssueView/Details/' + issuer['uuid']
        resp_inner = s.get(link)
        soup_inner = Soup(resp_inner.text, features="lxml")

        # check agree
        soup_inner = check_agree(link, soup_inner)

        # top area
        top_div = soup_inner.find('div', {'class': ['card','grey-band','grey-header']})

        # Add additional descriptions
        if top_div.find('h3'):
            issuer['issue_desc2'] = clean_text(top_div.find('h3').text)
        else:
            issuer['issue_desc2'] = ''

        if top_div.find('h5'):
            issuer['issue_desc3'] = clean_text(top_div.find('h5').text)
        else:
            issuer['issue_desc3'] = ''

        
        # Scrape additional info
        labels = {
            clean_text(x.find('span', {'class' : 'label'}).text)
            :
            clean_text(x.find('span', {'class' : 'float-right'}).text) 
            for x in soup_inner.find('div', { 'class' : 'blue-box'})
                               .findAll( 'li')
        }

        # append issuer extra info
        # for label in labels:
        #     issuer[label] = labels.get(label)

        # issuer['info'] = labels
        
        # add label keys
        keys_set = set([ x for x in labels])

        # Add ready item to output database
        db1.append(issuer)

        # Scrape the second items
        link = 'https://emma.msrb.org/IssueView/GetFinalScaleData?id=' + issuer['uuid']
        resp_inner = s.get(link)
        details_json = json_decode(resp_inner.text)

        for info_json in details_json:
            issue = {
                'uuid' : issuer['uuid'],
                'CUSIP' : info_json['cusip9'],
                'Principal_Amount_At_Issuance' : info_json['MatPrinTxt'],
                'Security Description' : info_json['SecurityDescription'],
                'Coupon' : clean_text(info_json['IntRateTxt']),
                'Maturity Date' : info_json['MatDtTxt'],
                'Price or Yield' : clean_text(info_json['IOPTxt']),
                'Price' : clean_text(info_json['NiidsIOPTxt']),
                'Yield' : clean_text(info_json['NiidsIOYTxt']),
                'Fitch' : '', # info_json['FitchRateEnc'],
                'KBRA' : '', # info_json['KrollRateEnc'],
                'Moody' : '', # info_json['MoodyRateEnc'],
                'S&P' : '', #info_json['SnpRateEnc'],
            }

            # Add the ready item to output database
            db2.append(issue)

        break
    break
    print('Done!')
print("Successfully got everything - starting to make CSVs.")

export_csv('db1.csv', db1)

export_csv('db2.csv', db2)

print("The *WHOLE* process is done!")

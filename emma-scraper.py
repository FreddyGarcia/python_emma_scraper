# coding=utf-8
import csv
import sys
from collections import OrderedDict

import re
from lxml.html import fromstring
from requests import session
from selenium.webdriver import PhantomJS

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


def scrape_issuers(tree):
    iss = []
    # Scrape it into dict
    trs = tree.xpath("//tr")[1:]
    # cusip_no = tree_otter.xpath('//*[@id="ctl00_mainContentArea_issuerCusip6DataLabel"]')[0].text_content()
    for issue_element in trs:
        tds = issue_element.xpath('.//td')
        issuer = OrderedDict()
        issuer['issuer_name'] = issue_element.xpath('//*[@id="ctl00_mainContentArea_issuerNameLabel"]')[
            0].text_content().replace('*', '')
        issuer['issuer_cusip'] = cusip
        issuer['uuid'] = tds[0].xpath('.//a/@href')[0].split('=')[-1]
        issuer['issue_desc'] = tds[0].text_content().strip().replace('\n', '')
        issuer['issue_date'] = tds[1].text_content().strip().replace('\n', '')
        issuer['issue_dates'] = tds[2].text_content().strip().replace('\n', '')
        issuer['issue_state'] = tds[3].text_content().strip().replace('\n', '')

        # Save the link to it for the future use
        issuer['link'] = tds[0].xpath('.//a/@href')[0].replace('../', 'https://emma.msrb.org/')

        # Add dict to temporary storage
        iss.append(issuer)
    return iss


for i, cusip in enumerate(cusips):

    # Get CUSIP page and parse it
    print('Getting CUSIP no. %s out of %s ("%s")' % (i + 1, len(cusips), cusip))
    base_cusip_url = 'https://emma.msrb.org/IssuerView/IssuerDetails.aspx?cusip=%s'
    issuers = []

    resp = s.get(base_cusip_url % cusip)
    tree_otter = fromstring(resp.text)

    print("Scraping page no. 1")
    l = scrape_issuers(tree_otter)
    if l:
        issuers.extend(l)
    else:
        print('There is no info on CUSIP no. %s - heading to the next!' % cusip)
        continue

    data = dict()
    for x in tree_otter.xpath('//input[(@type="hidden")or(@type="text")]'):
        values = x.xpath('./@value')
        data[x.xpath('./@name')[0]] = values[0] if values else ''
    for j, target in enumerate(tree_otter.xpath('//div[@id="ctl00_mainContentArea_Paging_pageLinkDiv"]/a/@href')[1:]):
        print("Scraping page no. %s" % (j+2))
        match = re.search("doPostBack\('(.+?)',", target)
        if match:
            data['__EVENTTARGET'] = match.group(1)
            tree_o = fromstring(s.post(base_cusip_url % cusip, data).text)
            issuers.extend(scrape_issuers(tree_o))

    for j, issuer in enumerate(issuers):
        print("Scraping issuer no. %s (out of %s)" % (j+1, len(issuers)))
        # Get the link we've saved
        resp_inner = s.get(issuer['link'])
        tree_inner = fromstring(resp_inner.text)

        # Agree if asked to (click on accept)
        if tree_inner.xpath('//*[@id="ctl00_mainContentArea_disclaimerContent_yesButton"]'):
            print("Agreeing the terms of use - please wait...")
            driver = PhantomJS('.\phantomjs.exe' if sys.platform.startswith('win32') else './phantomjs')
            driver.get(issuer['link'])
            driver.find_element_by_id('ctl00_mainContentArea_disclaimerContent_yesButton').click()
            for cookie in driver.get_cookies():
                s.cookies.set(cookie['name'], cookie['value'])
            driver.quit()
            resp_inner = s.get(issuer['link'])
            tree_inner = fromstring(resp_inner.text)
            print("Done, now let's get back to the scraping process.")

        # Add additional descriptions
        issuer['issue_desc2'] = tree_inner.xpath('//*[@id="ctl00_mainContentArea_topLevelIssueDataLabel"]')[
            0].text_content().strip().replace('*', '') if tree_inner.xpath(
            '//*[@id="ctl00_mainContentArea_topLevelIssueDataLabel"]') else ''
        issuer['issue_desc3'] = tree_inner.xpath('//*[@id="ctl00_mainContentArea_secondLevelIssueDataLabel"]')[
            0].text_content().strip().replace('*', '') if tree_inner.xpath(
            '//*[@id="ctl00_mainContentArea_secondLevelIssueDataLabel"]') else ''

        # Scrape additional info
        labels = [x for x in tree_inner.xpath('//span[@class="IssueDataLabel"]') if
                  ':' in x.text_content()]
        issuer['info'] = {}
        for x in labels:
            striped_name = x.text_content().strip()
            keys_set.add(striped_name)
            try:
                issuer['info'][striped_name] = x.xpath('./following-sibling::*[1]')[0].text_content()
            except:
                issuer['info'][striped_name] = x.xpath('./../following-sibling::*[1]')[0].text_content()

        # Add ready item to output database
        db1.append(issuer)

        # Scrape the second items
        trs_inner = tree_inner.xpath('//table[@id="ctl00_mainContentArea_cusipListTableNic"]')[0]
        for issue_row in trs_inner.xpath('.//tr')[1:]:
            tds_inner = issue_row.xpath('./td')
            issue = OrderedDict()
            issue['uuid'] = issuer['uuid']
            add_headers = True
            if db2_headers != ['uuid', ]:
                add_headers = False

            # Scrape tables
            for j, col in enumerate(zip([y.text_content().strip().replace('\n', ' ') for y in trs_inner.xpath('.//th')],
                                        [y for y in issue_row])):
                issue[col[0]] = col[1].text_content().strip().replace('\n', ' ').replace(' *', '')
                if j == 0:
                    search = re.search('cusip9=([^&]+)', col[1].xpath('./input/@src')[0])
                    if search:
                        issue[col[0]] = search.group(1)
                if add_headers:
                    db2_headers.append(col[0])

            # Add the ready item to output database
            db2.append(issue)
    print('Done!')
print("Successfully got everything - starting to make CSVs.")


for x in db1:
    del x['link']
    for k in keys_set:
        x[k] = x['info'].get(k, '')
    del x['info']
if db1:
    with open('db1.csv', 'w', newline='') as file:
        writer = csv.DictWriter(file, db1[0].keys())

        writer.writeheader()
        writer.writerows(db1)
if db2:
    with open('db2.csv', 'w', newline='') as file:
        writer = csv.DictWriter(file, db2[0].keys())

        writer.writeheader()
        writer.writerows(db2)
print("The *WHOLE* process is done!")

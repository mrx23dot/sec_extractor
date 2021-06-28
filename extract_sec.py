#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# SEC.GOV RATE LIMI: 10 requests per second (strict)

from logging import basicConfig
import logging
from xbrl.cache import HttpCache
from xbrl.instance import XbrlInstance, XbrlParser
import xml
from datetime import datetime

DROP_FIELDS = 'property_plant_equipment_net_prior preferred_stock_value'.split()

# scraper config
basicConfig(level=logging.INFO)
cache = HttpCache('./cache')
# !Replace the dummy header with your information! SEC EDGAR require you to disclose information about your bot! (https://www.sec.gov/privacy.htm#security)
cache.set_headers({'From': 'test@gmail.com', 'User-Agent': 'meta extactor v1.0'})
cache.set_connection_params(delay=1000/9.9, retries=5, backoff_factor=0.8, logs=True)
xbrlParser = XbrlParser(cache)

def _get_raw_data(url, reportDate, is10K):
  inst = xbrlParser.parse_instance(url)

  # flatten values into dictionary
  flattenDict = dict()
  for fact in inst.facts:
    # only select non-dimensional data for now
    if len(fact.context.segments) > 0:
      continue # one tag reported many times, some can have dimmension
    nm = fact.concept.name

    if 1:
      try:
        # reported for different period, if exists
        if fact.context.end_date != reportDate:
          continue

        # filter non expected periods
        diff_months = (fact.context.end_date - fact.context.start_date).days / 30.5
        if is10K == True:
          # 10K 12months
          if diff_months < 11 or diff_months > 14:
            continue
        else:
          # 10Q 3months
          if diff_months < 2.5 or diff_months > 4.5:
            continue
      except AttributeError:
        pass

#    print({ 'concept': nm, 'value': fact.value})
#    if nm == 'Liabilities':
#      print(fact.context,'|',fact)

    # parse numbers if can
    val = fact.value
#    print(nm,val)

    # parse number, eg '2020'
    try:
      val = float(val)
      vali = int(val)
      if val == vali: # int if no decimal
        val = vali
    except ValueError:
      pass

    # str
    if isinstance(val, str):
      if len(val)>100:
        continue  # seen html content
      if val.lower() in ['true', 'yes']:
        val = True
      elif val.lower() in ['false', 'no']:
        val = False
      elif len(val)<=1:
        val = None # eg —

    flattenDict[nm] = flattenDict.get(nm,[]) + [val]
  return flattenDict

def _sum(dictIn, sumList):
  sumOut = 0
  for i in sumList:
    if i in dictIn:
      sumOut += dictIn[i][0]
  return sumOut

def _get_alter(dictIn, altList):
  for i in altList:
    if i in dictIn:
      return dictIn[i]
  return None


def get(flatDict, name, default=None, idx=0):
  """ gets latest or default, name str """
  val = default

  found = False
  for i in name.split(): # by white space delimetered alternatives
    if i in flatDict:
      val = flatDict[i][idx]
      found = True
      break

  if found==False:
    print(' warn missing (any)', name, 'using',default)
  return val

def _extract_my_values(flatDict):
  parseDict = dict()
  # any array item can be invalid

  # mandatory
  parseDict['total_assets'] = get(flatDict, 'Assets')
  parseDict['total_current_assets'] = get(flatDict, 'AssetsCurrent')
  parseDict['total_current_assets_pre'] = get(flatDict, 'AssetsCurrent',idx=1)

  # Liabilities
  parseDict['total_liabilities'] = get(flatDict, 'Liabilities')
  parseDict['total_current_liabilities'] = get(flatDict, 'LiabilitiesCurrent')
  parseDict['total_current_liabilities_pre'] = get(flatDict, 'LiabilitiesCurrent',idx=1)
#  parseDict['deferred_revenue'] = get(flatDict, 'ContractWithCustomerLiabilityCurrent')
  parseDict['other_non_current_liabilities'] = get(flatDict, 'OtherAccruedLiabilitiesNoncurrent OtherLiabilitiesNoncurrent')

  parseDict['other_non_current_assets'] = get(flatDict, 'OtherAssetsNoncurrent')
  parseDict['cash_and_cash_equivalents'] = get(flatDict, 'CashAndCashEquivalentsAtCarryingValue')
  parseDict['long_term_debt'] = get(flatDict, 'LongTermDebtNoncurrent LongTermDebt')
  parseDict['long_term_debt_current'] = get(flatDict, 'LongTermDebtCurrent')
  parseDict['lines_of_credit_current'] = get(flatDict, 'LinesOfCreditCurrent',default=0)
  parseDict['revenue'] = get(flatDict, 'RevenueFromContractWithCustomerExcludingAssessedTax')

  parseDict['total_stockholders_equity'] = get(flatDict, 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest StockholdersEquity PartnersCapitalIncludingPortionAttributableToNoncontrollingInterest PartnersCapital CommonStockholdersEquity MemberEquity AssetsNet EquityAttributableToParent')

  # operating only
  parseDict['net_income'] = get(flatDict, 'NetIncomeLoss NetIncome ProfitLoss NetIncomeLossAvailableToCommonStockholdersBasic IncomeLossFromContinuingOperations IncomeLossAttributableToParent IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest') # NetIncomeLoss if missing then NetIncome
  parseDict['non_operating_net_income'] = get(flatDict, 'NonoperatingIncomeExpense OtherNonoperatingIncomeExpense')

  # basic: Shares used in computing earnings per share:
  # ! see under Shares used in computing earnings per share: WeightedAverageNumberOfSharesOutstandingBasic
  parseDict['number_of_shares'] = get(flatDict, 'WeightedAverageNumberOfSharesOutstandingBasic WeightedAverageNumberOfShareOutstandingBasicAndDiluted')  # wrong in FMP

  parseDict['depreciation_and_amortization'] = get(flatDict, 'DepreciationDepletionAndAmortization DepreciationAmortizationAndLossOnDisposalOfFixedAssets') # wrong in FMP
  parseDict['interest_expense'] = get(flatDict, 'InterestExpense InterestIncomeExpenseNonoperatingNet')
  parseDict['income_tax_expense'] = get(flatDict, 'IncomeTaxExpenseBenefit')

  parseDict['eps'] = get(flatDict, 'EarningsPerShareBasic EarningsPerShareBasicAndDiluted')
  parseDict['date'] = get(flatDict, 'DocumentPeriodEndDate')

  parseDict['cik'] = str(get(flatDict, 'EntityCentralIndexKey'))
  parseDict['cik'] = '0'* (10-len(parseDict['cik'])) + parseDict['cik']
  parseDict['other_financing_activites'] = get(flatDict, 'AccumulatedOtherComprehensiveIncomeLossNetOfTax')
  parseDict['inventory'] = get(flatDict, 'InventoryNet')
  parseDict['other_current_assets'] = get(flatDict, 'OtherAssetsCurrent PrepaidExpenseAndOtherAssetsCurrent')
  parseDict['retained_earnings'] = get(flatDict, 'RetainedEarningsAccumulatedDeficit')
  parseDict['name'] = get(flatDict, 'EntityRegistrantName')

  # FMP uses  AAPL NoncurrentAssets for property_plant_equipment_net
  ppe = 'PropertyPlantAndEquipmentNet PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization NoncurrentAssets'
  parseDict['property_plant_equipment_net'] = get(flatDict, ppe)
  parseDict['property_plant_equipment_net_prior'] = get(flatDict, ppe, idx=1)

  parseDict['dividends_per_share'] = get(flatDict, 'CommonStockDividendsPerShareDeclared') # todo default 0
  parseDict['preferred_stock_value'] = get(flatDict, 'PreferredStockValue') # missing from AAPL # todo default 0

  try:
    parseDict['dividends_paid'] = abs(get(flatDict, 'PaymentsOfDividends')) #  positive if paying out # todo default 0
  except TypeError:
    parseDict['dividends_paid'] = 0

  # wrong in FMP
  parseDict['common_stock_repurchased'] = get(flatDict, 'PaymentsForRepurchaseOfCommonStock StockRepurchasedAndRetiredDuringPeriodValue') # todo default 0
  parseDict['research_and_development_expenses'] = get(flatDict, 'ResearchAndDevelopmentExpense') # FMP wrong, can be missing
  parseDict['operating_expenses'] = get(flatDict, 'OperatingExpenses') # FMP wrong
  parseDict['cost_of_goods_sold'] = get(flatDict, 'CostOfGoodsAndServicesSold CostOfRevenue')
  # aka Cash generated by operating activities
  parseDict['operating_cash_flow_net'] = get(flatDict, 'NetCashProvidedByUsedInOperatingActivities')
  parseDict['invested_capital'] = get(flatDict, 'NetCashProvidedByUsedInInvestingActivities')

  # GrossProfit not included for entire year
  # no calc here

  # vary basic sanity check
  assert 'number_of_shares' in parseDict
  assert parseDict['number_of_shares'] != None, 'number_of_shares missing'
  assert parseDict['number_of_shares'] > 0, 'number_of_shares ' + str(parseDict['number_of_shares'])
  print(' number_of_shares',parseDict['number_of_shares'])

  return parseDict

def _calc_extra(parseDict,price):
  xtra = dict()

  xtra['price'] = price
  shares = parseDict['number_of_shares']
  xtra['market_capitalization'] = int(round(price * shares, 0))
  try:
    xtra['eps2'] = parseDict['net_income'] /  shares  # basic, crosscheck with doc!
  except TypeError:
    xtra['eps2'] = None

  # from SEC: total debt = Revolving credit agreements + Current maturities of long-term debt + Long-term debt
  # sometimes lists non-gaap search Total term debt
  try:
    xtra['total_debt'] = parseDict['lines_of_credit_current'] + parseDict['long_term_debt_current'] + parseDict['long_term_debt']
  except TypeError:
    xtra['total_debt'] = None

  try:
    xtra['net_debt'] = xtra['total_debt'] - parseDict['cash_and_cash_equivalents']
  except TypeError:
    xtra['net_debt'] = None

  # https://www.investopedia.com/terms/e/enterprisevalue.asp
  try:
    xtra['enterprise_value'] = xtra['market_capitalization'] + xtra['total_debt'] - parseDict['cash_and_cash_equivalents']
  except TypeError:
    xtra['enterprise_value'] = None

  # todo doesnt match  https://www.macrotrends.net/stocks/charts/AAPL/apple/debt-equity-ratio
  try:
    xtra['debt_to_equity'] = parseDict['total_liabilities'] / parseDict['total_stockholders_equity']
#  xtra['equity_mulitplie'] = parseDict['total_assets'] / parseDict['total_stockholders_equity']
  except (TypeError, ZeroDivisionError) as e:
    xtra['debt_to_equity'] = None
    print(' warn total_stockholders_equity')

  try:
    xtra['debt_to_assets'] = parseDict['total_current_assets'] / parseDict['total_current_liabilities']
  except (TypeError, ZeroDivisionError) as e:
    xtra['debt_to_assets'] = None
    print(' warn total_current_liabilities')

  try:
    xtra['net_profit_margin'] = parseDict['net_income'] / parseDict['revenue']
  except (TypeError, ZeroDivisionError) as e:
    xtra['net_profit_margin'] = None
    print(' warn revenue 0')

  #Net income over the last full fiscal year, or trailing 12 months, is found on the income statement-a sum of financial activity over that period. Shareholders equity comes from the balance sheet-a running balance of a company's entire history of changes in assets and liabilities.
#  xtra['gross_profit_margin'] = 1.0 - (parseDict['gross_profit'] / parseDict['cost_of_goods_sold'])  # todo xcheck
  try:
    xtra['working_capital'] = parseDict['total_current_assets'] - parseDict['total_current_liabilities']
  except TypeError:
    xtra['working_capital'] = None

  try:
    xtra['working_capital_pre'] = parseDict['total_current_assets_pre'] - parseDict['total_current_liabilities_pre']
  except TypeError:
    xtra['working_capital_pre'] = None

  try:
    xtra['change_in_working_capital'] = xtra['working_capital'] - xtra['working_capital_pre']
  except TypeError:
    xtra['change_in_working_capital'] = None

#  xtra['asset_equity_ratio'] = (parseDict['total_assets'] - parseDict['total_stockholders_equity']) / parseDict['total_assets']
  # per_share
  try:
    xtra['net_current_asset_value'] = parseDict['total_current_assets'] - (parseDict['total_liabilities'] + parseDict['preferred_stock_value']) / shares
  except TypeError:
    xtra['net_current_asset_value'] = None

  try:
    xtra['non_operating_net_income_ratio'] = max(0, parseDict['non_operating_net_income']) / parseDict['net_income']
  except (TypeError, ZeroDivisionError) as e:
    xtra['non_operating_net_income_ratio'] = None
    print(' warn net_income')

  # https://corporatefinanceinstitute.com/resources/knowledge/finance/what-is-ebitda/
  # wrong in marketwatch

  try:
    xtra['ebitda'] = parseDict['depreciation_and_amortization'] + parseDict['interest_expense'] + parseDict['income_tax_expense'] + parseDict['net_income']
  except TypeError:
    xtra['ebitda'] = None
    print(' warn ebitda')

  # https://corporatefinanceinstitute.com/resources/knowledge/modeling/how-to-calculate-capex-formula/
  try:
    xtra['capital_expenditure'] = parseDict['property_plant_equipment_net'] - parseDict['property_plant_equipment_net_prior'] + parseDict['depreciation_and_amortization']
  except TypeError:
    xtra['capital_expenditure'] = None
    print(' warn capital_expenditure')
#  parseDict['capex0'] = _sum(flatDict, ['DepreciationAndAmortization','DepreciationDepletionAndAmortization','PropertyPlantAndEquipmentNet','PaymentsToAcquirePropertyPlantAndEquipment','DepreciationDepletionAndAmortizationPropertyPlantAndEquipment','CapitalExpendituresIncurredButNotYetPaid'])

  # FCF
  # from https://www.sec.gov/Archives/edgar/data/70033/000119312505163969/dex994.htm#:~:text=Free%20cash%20flow%20is%20defined,flow%20reported%20by%20other%20companies.
  #   Net Cash Provided by Operating Activities - Capital Expenditures - Dividends Paid
  # most likely better SEC!
  try:
    assert parseDict['dividends_paid'] >= 0
    xtra['free_cash_flow'] = parseDict['operating_cash_flow_net'] - abs(xtra['capital_expenditure']) - parseDict['dividends_paid']
  except TypeError:
    xtra['free_cash_flow'] = None
    print(' warn free_cash_flow')

  #Free Cash Flow = Net income + Depreciation/Amortization – Change in Working Capital – Capital Expenditure
  try:
    xtra['free_cash_flow2'] = parseDict['net_income'] + parseDict['depreciation_and_amortization'] - xtra['change_in_working_capital'] - xtra['capital_expenditure']
  except TypeError:
    xtra['free_cash_flow2'] = None
    print(' warn free_cash_flow2')
  return xtra

def parse_xbrl(url, price, reportDateStr, is10K):
  flatDict = dict()

  # parse&extract XBRL key value pairs
  try:
    flatDict = _get_raw_data(url, datetime.strptime(reportDateStr, '%Y-%m-%d').date(), is10K)
  except xml.etree.ElementTree.ParseError:
    print(' error: missing XBRL from doc, use XML', url)
    return flatDict

  if 1:
    for i in sorted(flatDict):
      print(i, flatDict[i])

  # only carrying selected values over
  parseDict = dict()
  try:
    parseDict = _extract_my_values(flatDict)
  except AssertionError as e:
    print(' error: content assert,', e, ',',url)
    return flatDict

  # calc extra values
  parseDict.update(_calc_extra(parseDict, price))

  # drop non interesting ones
  for i in DROP_FIELDS:
    parseDict.pop(i)

  return parseDict

# ================================================ #
if __name__ == "__main__":

  price = 112.28 # at the time of report
  if 1:
    urls = 'https://www.sec.gov/Archives/edgar/data/0000320193/000032019320000096/aapl-20200926.htm'.split()
    date = '2020-09-26'
    is10K = True
  else:
    urls = 'https://www.sec.gov/Archives/edgar/data/0000320193/000032019321000056/aapl-20210327.htm'.split()
    date = '2021-03-27'
    is10K = False

  for url in urls[:]:
    print('Processing')
    print(' ', url)
    print(' ', url.replace('/Archives', '/ix?doc=/Archives')) # interactive
    resultDict = parse_xbrl(url, price, reportDateStr=date, is10K=is10K)

    # print summary
    if 1:
      for i in sorted(resultDict):
        print(i, resultDict[i])

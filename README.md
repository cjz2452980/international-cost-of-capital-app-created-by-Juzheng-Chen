# international-cost-of-capital-app-created-by-Juzheng-Chen
This is for the FIN470 project

International Cost of Capital — Streamlit App
An interactive app comparing a project's cost of equity, pretax / after-tax cost of debt, and WACC in USD and a selected project's local currency. The app follows the class slides on Hamada beta relevering, CAPM, bond-yield currency conversion, credit-spread conversion, and after-tax WACC.
Run locally
```bash
python -m pip install -r requirements.txt
streamlit run app.py
```
Python 3.10 or later is recommended. The first launch retrieves data over the internet.
Deploy to Streamlit Community Cloud
Create a new public GitHub repository (e.g., `international-cost-of-capital`).
Add `app.py`, `requirements.txt`, and `README.md` to the repository root.
Go to share.streamlit.io and sign in with GitHub.
Select Create app, your repository and its branch; set the main file path to `app.py`.
Deploy. The project does not need an API key or secrets file.
If a source blocks requests from Streamlit Cloud or changes its page layout, the app alerts you and lets you enter the relevant figures manually. Refresh works by clearing the cached data and fetching again. Data are cached for 6 hours (bond yields: 30 minutes).
Data sources
Input	Publisher / method	Observation period
U.S. industry unlevered beta, cash-corrected unlevered beta, number of firms	Damodaran's `betas.xls`, `Industry Averages` sheet	The date embedded in the spreadsheet (Jan 5, 2026 when developed)
USD BBB borrowing spread	Damodaran's ratings table, Baa2/BBB for large non-financial firms	Analysis date on webpage (Jan 2026 when developed)
U.S. and foreign combined statutory corporate tax	OECD corporate income tax database, via OECD SDMX CSV API	Latest available year for each country; includes the 2026 update
U.S. and foreign 10-year yields	Trading Economics' public 10-year country table, companion to its bonds page	Market observation month/year from table and actual app fetch time
The OECD source is updated beyond the 2024 report linked in the assignment. It provides combined central + subnational statutory corporate tax rates. Its annual tax figure is not an effective tax rate.
The Trading Economics country table does not provide the exact observation day; the UI says so and never turns a month/year into a fictitious daily timestamp. Only markets listed in the drop-down have built-in currency mapping. Other country (manual) supports projects outside that list with an explicitly entered currency, yield and (if necessary) tax rate. The tool does not validate creditworthiness of sovereign bonds or guarantee that a government yield is risk-free.
Default settings
Industry: Software (System & Application).
Project country and currency: United States / USD.
Project tax jurisdiction: United States.
Annual equity risk premium: 6.50%.
Fraction financed with debt: 30%.
Beta: standard unlevered beta (not cash-corrected).
U.S. BBB spread, corporate taxes, and 10-year yields: auto-fetched unless overridden.
Foreign BBB spread: automatically converted unless overridden; when country = U.S., it equals the USD spread.
Calculation reference
All inputs are divided by 100 before calculation; formulas use decimal annual rates.
`d = debt / (debt + equity)`; `D/E = d / (1-d)`.
`beta_equity = beta_unlevered * [1 + (1 - tax_rate) * D/E]`.
`Re_USD = US_10Y_yield + beta_equity * ERP`.
`Rd_USD = US_10Y_yield + BBB_spread_USD`.
`F = (1 + foreign_10Y_yield) / (1 + US_10Y_yield)`.
`Re_local = (1 + Re_USD) * F - 1`.
`spread_local = BBB_spread_USD * F` unless the user overrides the foreign spread.
`Rd_local = foreign_10Y_yield + spread_local`.
`WACC_USD = (1-d)*Re_USD + d*Rd_USD*(1-tax_rate)`.
`WACC_local = (1-d)*Re_local + d*Rd_local*(1-tax_rate)`.
Important: The same corporate tax rate, ERP and capital structure are used in both currency scenarios. Switch tax jurisdiction in the sidebar to select either the U.S. or the project country tax rate. The model does not add a separate country-risk premium, assuming currency differences are captured by the bond yield ratio as required by the slides.
WACC is calculated separately for each currency from the converted cost of equity and the currency's after-tax debt cost. This is consistent with the classroom setup and intentionally differs from directly converting the whole USD WACC. Financial inputs are quoted in percentage points where marked `%`, not basis points (1.11 percentage points = 111 bps).
Manually verify the lecture's Colombia example
Select Colombia, then override the following inputs:
Input	Manual value
Unlevered beta	`0.80` (not 80%)
Debt share	`30%`
Colombia tax jurisdiction	`35%`
ERP	`6.5%`
U.S. 10-year yield	`4.0%`
Colombia 10-year yield	`12.0%`
USD BBB spread	`1.5%`
Colombia BBB spread	Leave automatic
Expected intermediate and final results (minor differences only from rounding):
Measure	USD	COP
D/E	0.428571	0.428571
Relevered beta	1.022857	1.022857
Currency adjustment factor	1.076923	1.076923
Cost of equity	10.6486%	19.1600%
BBB spread	1.5000%	1.6154%
Pretax debt cost	5.5000%	13.6154%
After-tax debt cost	3.5750%	8.8500%
WACC	8.5265%	16.0670%
Do not rely solely on the displayed rounded values to verify the arithmetic. The app retains full precision until output is formatted.
Features / limitations
Side-by-side USD and foreign-currency results, funding contribution breakdown and transparent formulas.
Downloadable selected-project CSV and all-industry CSV (using the same financing/tax/ERP/yields across industries).
Manual inputs for beta, corporate tax, BBB spread in USD and foreign currency, and both 10-year government bond yields.
Per-source as-of dates, fetch timestamps, source links, and refresh button.
If data are missing, manual inputs are required for the calculation; the UI flags these assumptions rather than treating stale sample numbers as real-time data.
This is an academic cost-of-capital model. It does not model FX forwards, sovereign credit-risk corrections, multiple tax regimes, different country-risk premia, or a currency-specific financing mix.
Troubleshooting
No data: Click Refresh source data, check source access, or use the manual override controls. Automated HTML scraping may be affected by website redesigns or anti-bot controls.
Missing industry comparison: Damodaran's workbook could not be retrieved or parsed. The app can still calculate a manual project beta.
Unusual result: Confirm inputs are in percent, except unlevered beta, and check whether the tax jurisdiction and the foreign BBB-spread override are set as intended.
Same country selected: USD and local-currency WACC deliberately match when United States is selected.
For course use only; independently verify live input data and calculations before submission.

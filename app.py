"""International Cost of Capital — Streamlit classroom project.

Run with: streamlit run app.py

All financial calculations use decimals internally; UI inputs use percentages.
Data is attributed to Damodaran, OECD, and Trading Economics and may be
manually overridden if a publisher changes its site or blocks scraping.
"""

from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup


BETA_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls"
SPREAD_URL = "https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html"
OECD_URL = (
    "https://sdmx.oecd.org/public/rest/data/"
    "OECD.CTP.TPS,DSD_TAX_CIT@DF_CIT,2.0/"
    ".A.CIT_C.ST.PT_INC_TAX.S13...?"
    "startPeriod=2024&dimensionAtObservation=AllDimensions&format=csvfilewithlabels"
)
OECD_INFO_URL = "https://www.oecd.org/en/data/datasets/corporate-income-tax-rates-database.html"
BONDS_URL = "https://tradingeconomics.com/country-list/government-bond-10y"

# 10-year bond markets listed by Trading Economics. The value is the local
# currency, not a country-specific FX quote. Euro-area members use EUR.
# The user may also choose a custom country/currency with a manual yield.
COUNTRY_CURRENCIES: dict[str, str] = {
    "Australia": "AUD", "Austria": "EUR", "Belgium": "EUR",
    "Brazil": "BRL", "Bulgaria": "EUR", "Canada": "CAD",
    "Chile": "CLP", "China": "CNY", "Colombia": "COP",
    "Croatia": "EUR", "Czech Republic": "CZK", "Denmark": "DKK",
    "Finland": "EUR", "France": "EUR", "Germany": "EUR",
    "Greece": "EUR", "Hong Kong": "HKD", "Hungary": "HUF",
    "Iceland": "ISK", "India": "INR", "Indonesia": "IDR",
    "Ireland": "EUR", "Israel": "ILS", "Italy": "EUR",
    "Japan": "JPY", "Kenya": "KES", "Lithuania": "EUR",
    "Malaysia": "MYR", "Mexico": "MXN", "Netherlands": "EUR",
    "New Zealand": "NZD", "Nigeria": "NGN", "Norway": "NOK",
    "Pakistan": "PKR", "Peru": "PEN", "Philippines": "PHP",
    "Poland": "PLN", "Portugal": "EUR", "Romania": "RON",
    "Russia": "RUB", "Singapore": "SGD", "Slovakia": "EUR",
    "Slovenia": "EUR", "South Africa": "ZAR", "South Korea": "KRW",
    "Spain": "EUR", "Sweden": "SEK", "Switzerland": "CHF",
    "Taiwan": "TWD", "Thailand": "THB", "Turkey": "TRY",
    "United Kingdom": "GBP", "United States": "USD",
    "Vietnam": "VND", "Zambia": "ZMW",
}

COUNTRY_ALIASES = {
    "czechia": "czech republic",
    "korea": "south korea",
    "republic of korea": "south korea",
    "turkiye": "turkey",
    "türkiye": "turkey",
    "slovak republic": "slovakia",
    "viet nam": "vietnam",
    "china (people’s republic of)": "china",
    "china (people's republic of)": "china",
    "hong kong (china)": "hong kong",
}

HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; UniversityFinanceProject/1.0)"}
TIMEOUT_SECONDS = 25


def normalized_country(name: str) -> str:
    key = re.sub(r"\s+", " ", str(name).strip().lower())
    return COUNTRY_ALIASES.get(key, key)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def get_source(url: str) -> requests.Response:
    response = requests.get(url, headers=HTTP_HEADERS, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response


@st.cache_data(ttl=21600, show_spinner=False)
def load_industry_betas() -> dict[str, Any]:
    """Read the actual unlevered-beta column, not the levered or cash-adjusted beta."""
    response = get_source(BETA_URL)
    raw = pd.read_excel(io.BytesIO(response.content), sheet_name="Industry Averages", header=None)
    header_rows = raw.index[raw.iloc[:, 0].astype(str).str.strip().eq("Industry Name")]
    if len(header_rows) != 1:
        raise ValueError("Could not identify the industry header in Damodaran's workbook.")
    h = int(header_rows[0])
    columns = raw.iloc[h].astype(str).str.strip().tolist()
    frame = raw.iloc[h + 1 :].copy()
    frame.columns = columns
    for column in ("Number of firms", "Unlevered beta", "Unlevered beta corrected for cash"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["Industry Name"] = frame["Industry Name"].astype(str).str.strip()
    frame = frame.dropna(subset=["Unlevered beta"])
    frame = frame[~frame["Industry Name"].str.contains(r"total market|all firms", case=False)]
    frame = frame[frame["Unlevered beta"].between(0, 10)]
    if len(frame) < 30:
        raise ValueError("Damodaran industry beta table is unexpectedly short.")
    date_cell = raw.iat[0, 1]
    date_str = (
        pd.Timestamp(date_cell).strftime("%Y-%m-%d")
        if pd.notna(date_cell) and not isinstance(date_cell, str)
        else str(date_cell)
    )
    data = {
        row["Industry Name"]: {
            "beta": float(row["Unlevered beta"]),
            "cash_beta": float(row["Unlevered beta corrected for cash"]),
            "firms": int(row["Number of firms"]) if pd.notna(row["Number of firms"]) else None,
        }
        for _, row in frame.iterrows()
        if pd.notna(row["Unlevered beta corrected for cash"])
    }
    return {"data": data, "asof": date_str, "retrieved": now_utc(), "url": BETA_URL}


@st.cache_data(ttl=21600, show_spinner=False)
def load_bbb_spread() -> dict[str, Any]:
    """Baa2/BBB, first (large non-financial) section — percentage points."""
    response = get_source(SPREAD_URL)
    soup = BeautifulSoup(response.text, "html.parser")
    rate: float | None = None
    for row in soup.select("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
        for i, cell in enumerate(cells[:4]):
            if re.search(r"\bBaa2\s*/\s*BBB\b", cell, flags=re.I):
                if i + 1 < len(cells):
                    match = re.search(r"([\d.]+)\s*%", cells[i + 1])
                    if match:
                        rate = float(match.group(1))
                        break
        if rate is not None:
            break
    if rate is None or not 0 <= rate <= 20:
        raise ValueError("Could not identify the large-company Baa2/BBB spread.")
    page_text = soup.get_text(" ", strip=True)
    asof_match = re.search(r"Data used is as of\s+(\w+\s+\d{4})", page_text)
    return {
        "data": rate, "asof": asof_match.group(1) if asof_match else "Not specified",
        "retrieved": now_utc(), "url": SPREAD_URL,
    }


@st.cache_data(ttl=21600, show_spinner=False)
def load_oecd_tax_rates() -> dict[str, Any]:
    """Latest combined statutory CIT by country from OECD SDMX (percentage)."""
    response = get_source(OECD_URL)
    df = pd.read_csv(io.StringIO(response.text), low_memory=False)
    needed = {"Reference area", "MEASURE", "TIME_PERIOD", "OBS_VALUE"}
    if not needed.issubset(df.columns):
        raise ValueError("OECD changed its SDMX CSV column format.")
    df = df.loc[df["MEASURE"].eq("CIT_C")].copy()
    df["year"] = pd.to_numeric(df["TIME_PERIOD"], errors="coerce")
    df["rate"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce")
    df = df.dropna(subset=["year", "rate", "Reference area"])
    df = df[df["rate"].between(0, 70)]
    df["key"] = df["Reference area"].map(normalized_country)
    df = df.sort_values("year").drop_duplicates("key", keep="last")
    if len(df) < 30:
        raise ValueError("OECD did not return enough country-level tax rates.")
    data = {
        row["key"]: {"rate": float(row["rate"]), "year": int(row["year"])}
        for _, row in df.iterrows()
    }
    return {"data": data, "asof": str(int(df["year"].max())),
            "retrieved": now_utc(), "url": OECD_URL}


@st.cache_data(ttl=1800, show_spinner=False)
def load_bond_yields() -> dict[str, Any]:
    """Scrape Trading Economics' server-rendered 10-year country list.

    The /bonds page is JavaScript-rendered; its /country-list/government-bond-10y
    companion exposes an HTML table that works without an API key.
    """
    response = get_source(BONDS_URL)
    soup = BeautifulSoup(response.text, "html.parser")
    yields: dict[str, dict[str, Any]] = {}
    for table in soup.select("table"):
        for row in table.select("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td", recursive=False)]
            if len(cells) < 4:
                continue
            country = cells[0].strip()
            if country not in COUNTRY_CURRENCIES:
                continue
            try:
                rate = float(cells[1].replace(",", ""))
            except ValueError:
                continue
            if not -10 <= rate <= 100:
                continue
            yields[country] = {"rate": rate, "date": cells[3] or "Not provided"}
    if "United States" not in yields or len(yields) < 15:
        raise ValueError("Trading Economics' 10-year bond table was not found or was blocked.")
    return {"data": yields, "asof": "Each market has a reference month/year",
            "retrieved": now_utc(), "url": BONDS_URL}


def calculate_costs(
    beta_unlevered: float,
    debt_share: float,
    tax_rate: float,
    equity_risk_premium: float,
    us_yield: float,
    foreign_yield: float,
    us_bbb_spread: float,
    foreign_bbb_spread: float | None = None,
) -> dict[str, float]:
    """Return all rates as decimals (e.g., 0.085 = 8.5%).

    `foreign_bbb_spread=None` converts the USD spread using the same F factor
    as the lecture slides. A supplied value is treated as a local-currency spread.
    """
    if not 0 <= debt_share < 1:
        raise ValueError("Debt fraction must be at least 0 and strictly less than 1.")
    if not 0 <= tax_rate <= 1:
        raise ValueError("Tax rate must be between 0 and 1.")
    if us_yield <= -1 or foreign_yield <= -1:
        raise ValueError("Bond yields must exceed -100% for rate conversion.")

    debt_to_equity = debt_share / (1 - debt_share)
    beta_levered = beta_unlevered * (1 + (1 - tax_rate) * debt_to_equity)
    cost_equity_usd = us_yield + beta_levered * equity_risk_premium
    cost_debt_usd = us_yield + us_bbb_spread

    currency_factor = (1 + foreign_yield) / (1 + us_yield)
    cost_equity_foreign = (1 + cost_equity_usd) * currency_factor - 1
    spread_foreign_auto = us_bbb_spread * currency_factor
    spread_foreign = spread_foreign_auto if foreign_bbb_spread is None else foreign_bbb_spread
    cost_debt_foreign = foreign_yield + spread_foreign

    after_tax_debt_usd = cost_debt_usd * (1 - tax_rate)
    after_tax_debt_foreign = cost_debt_foreign * (1 - tax_rate)
    equity_weight = 1 - debt_share
    wacc_usd = equity_weight * cost_equity_usd + debt_share * after_tax_debt_usd
    wacc_foreign = (
        equity_weight * cost_equity_foreign + debt_share * after_tax_debt_foreign
    )
    return {
        "debt_to_equity": debt_to_equity,
        "beta_levered": beta_levered,
        "currency_factor": currency_factor,
        "cost_equity_usd": cost_equity_usd,
        "cost_equity_foreign": cost_equity_foreign,
        "cost_debt_usd": cost_debt_usd,
        "cost_debt_foreign": cost_debt_foreign,
        "spread_foreign_auto": spread_foreign_auto,
        "spread_foreign": spread_foreign,
        "after_tax_debt_usd": after_tax_debt_usd,
        "after_tax_debt_foreign": after_tax_debt_foreign,
        "wacc_usd": wacc_usd,
        "wacc_foreign": wacc_foreign,
        "equity_contribution_usd": equity_weight * cost_equity_usd,
        "equity_contribution_foreign": equity_weight * cost_equity_foreign,
        "debt_contribution_usd": debt_share * after_tax_debt_usd,
        "debt_contribution_foreign": debt_share * after_tax_debt_foreign,
    }


def pct(rate_decimal: float, digits: int = 2) -> str:
    return f"{rate_decimal * 100:,.{digits}f}%"


def label_percent(value: float, digits: int = 2) -> str:
    return f"{value:,.{digits}f}%"


def safe_load(label: str, loader: Any) -> dict[str, Any] | None:
    """Use last successful session value if a refresh fails; tell the user."""
    key = f"previous_source_{label}"
    try:
        data = loader()
        st.session_state[key] = data
        return data
    except Exception as exc:
        previous = st.session_state.get(key)
        if previous:
            st.warning(f"{label} refresh failed: {exc}. Using the last successful session quote.")
        else:
            st.warning(f"{label} could not be fetched: {exc}. Please enter a manual value.")
        return previous


def optional_override(
    name: str,
    auto_value: float | None,
    *,
    default: float,
    key: str,
    max_value: float = 100.0,
    decimals: int = 4,
    help_text: str = "",
) -> tuple[float, bool]:
    missing = auto_value is None
    override = st.checkbox(
        f"Enter {name} manually" if not missing else f"Enter {name} manually (source unavailable)",
        value=missing, key=f"toggle_{key}", disabled=missing,
        help=help_text,
    )
    effective_override = override or missing
    if effective_override:
        value = st.number_input(
            f"{name} (%)", min_value=-10.0 if "yield" in key else 0.0,
            max_value=max_value,
            value=float(auto_value if auto_value is not None else default),
            step=0.1, format=f"%.{decimals}f", key=f"value_{key}",
        )
        return float(value), True
    st.caption(f"From source: {label_percent(float(auto_value), decimals)}")
    return float(auto_value), False


def build_industry_comparison(
    betas: dict[str, dict[str, Any]], beta_field: str, assumptions: dict[str, float],
) -> pd.DataFrame:
    rows = []
    for industry, data in betas.items():
        result = calculate_costs(
            beta_unlevered=data[beta_field],
            debt_share=assumptions["debt_share"],
            tax_rate=assumptions["tax_rate"],
            equity_risk_premium=assumptions["erp"],
            us_yield=assumptions["us_yield"],
            foreign_yield=assumptions["foreign_yield"],
            us_bbb_spread=assumptions["usd_spread"],
            foreign_bbb_spread=assumptions["foreign_spread_override"],
        )
        rows.append({
            "Industry": industry,
            "U.S. firms": data["firms"],
            "Unlevered beta": data[beta_field],
            "Relevered beta": result["beta_levered"],
            "Cost of equity · USD (%)": result["cost_equity_usd"] * 100,
            "Cost of equity · Local (%)": result["cost_equity_foreign"] * 100,
            "Pretax debt · USD (%)": result["cost_debt_usd"] * 100,
            "Pretax debt · Local (%)": result["cost_debt_foreign"] * 100,
            "WACC · USD (%)": result["wacc_usd"] * 100,
            "WACC · Local (%)": result["wacc_foreign"] * 100,
        })
    return pd.DataFrame(rows).sort_values("Industry", ignore_index=True)


def main() -> None:
    st.set_page_config(page_title="International Cost of Capital", page_icon="🌐", layout="wide")
    st.markdown("""
    <style>
      .block-container { padding-top: 2.2rem; max-width: 1370px; }
      [data-testid="stSidebar"] { background: #f8f9fb; border-right: 1px solid #e7e7ea; }
      [data-testid="stMetricValue"] { font-size: 2rem; }
      h1 { font-weight: 740; letter-spacing: -0.04em; }
      h2, h3 { letter-spacing: -0.02em; }
      .stCaption { color: #737780; }
      hr { margin: 1.4rem 0; }
      div[data-testid="stHorizontalBlock"] { align-items: flex-start; }
      .small-note { color: #6b7280; font-size: .89rem; }
    </style>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.title("Project assumptions")
        if st.button("↻ Refresh source data", width="stretch", type="primary"):
            load_industry_betas.clear()
            load_bbb_spread.clear()
            load_oecd_tax_rates.clear()
            load_bond_yields.clear()
            st.rerun()

    with st.spinner("Loading source data (first visit may take a few seconds)…"):
        betas_source = safe_load("Damodaran industry betas", load_industry_betas)
        spreads_source = safe_load("Damodaran BBB spread", load_bbb_spread)
        taxes_source = safe_load("OECD corporate tax rates", load_oecd_tax_rates)
        bonds_source = safe_load("Trading Economics bond yields", load_bond_yields)

    industries = (betas_source or {}).get("data", {})
    oecd = (taxes_source or {}).get("data", {})
    bonds = (bonds_source or {}).get("data", {})

    with st.sidebar:
        industry_choices = sorted(industries) if industries else ["Software (System & Application)"]
        default_industry = "Software (System & Application)"
        selected_industry = st.selectbox(
            "U.S. industry", industry_choices,
            index=industry_choices.index(default_industry) if default_industry in industry_choices else 0,
        )
        beta_type = st.selectbox(
            "Unlevered beta measure", ["Unlevered beta", "Cash-corrected unlevered beta"],
            help="The assignment uses standard unlevered beta. Cash-corrected beta is offered for exploration.",
        )
        beta_field = "beta" if beta_type == "Unlevered beta" else "cash_beta"
        beta_record = industries.get(selected_industry, {})
        industry_beta = beta_record.get(beta_field)
        # Beta is dimensionless, so it has its own input rather than the % helper.
        beta_manual = st.checkbox("Override industry unlevered beta", value=industry_beta is None,
                                  disabled=industry_beta is None, key="toggle_beta")
        beta_is_manual = beta_manual or industry_beta is None
        if beta_is_manual:
            beta_value = st.number_input("Unlevered beta (not %)", 0.0, 10.0,
                                         value=float(industry_beta if industry_beta is not None else 1.0),
                                         step=0.05, format="%.4f", key="manual_beta")
        else:
            beta_value = float(industry_beta)
            st.caption(f"Source beta: {beta_value:.4f} · "
                       f"{(betas_source or {}).get('asof', 'date unavailable')}")

        st.divider()
        erp_pct = st.number_input("Annual equity risk premium (%)", 0.0, 30.0,
                                  value=6.5, step=0.25, format="%.2f")
        debt_pct = st.slider("Fraction financed with debt (%)", 0, 95, 30, 1,
                             help="Uses debt / (debt + equity); debt cannot be 100% when relevering beta.")

        country_list = ["United States"] + sorted(c for c in COUNTRY_CURRENCIES if c != "United States")
        country_list.append("Other country (manual)")
        selected_country = st.selectbox("Project country / currency", country_list)
        custom_country = selected_country == "Other country (manual)"
        if custom_country:
            country = st.text_input("Country name", value="Custom country").strip() or "Custom country"
            currency = st.text_input("ISO currency code", value="XXX", max_chars=3).upper()
            st.caption("A custom country requires a manually entered 10-year yield and may require a manual tax rate.")
        else:
            country = selected_country
            currency = COUNTRY_CURRENCIES[country]
        is_us = (country == "United States" and currency == "USD")

        st.divider()
        st.subheader("Corporate tax")
        us_tax_row = oecd.get("united states", {})
        foreign_tax_row = oecd.get(normalized_country(country), {})
        us_tax_auto = us_tax_row.get("rate")
        foreign_tax_auto = foreign_tax_row.get("rate")
        tax_options = ["United States"] if is_us else ["United States", country]
        tax_jurisdiction = st.radio("Project tax jurisdiction (same rate in both currencies)",
                                     tax_options, horizontal=not is_us)
        tax_from_foreign = tax_jurisdiction != "United States"
        project_tax_auto = foreign_tax_auto if tax_from_foreign else us_tax_auto
        project_tax, tax_is_manual = optional_override(
            "project corporate tax rate", project_tax_auto, default=25.0,
            key=f"tax_{normalized_country(tax_jurisdiction)}", max_value=70.0,
        )
        if not tax_is_manual:
            tax_year = foreign_tax_row.get("year") if tax_from_foreign else us_tax_row.get("year")
            st.caption(f"OECD combined statutory rate · {tax_year}")

        st.divider()
        st.subheader("10-year bond yields")
        us_yield_row = bonds.get("United States", {})
        us_yield_auto = us_yield_row.get("rate")
        us_yield_pct, us_yield_manual = optional_override(
            "U.S. 10-year yield", us_yield_auto, default=4.0,
            key="us_yield", max_value=100.0,
        )
        if not us_yield_manual:
            st.caption(f"Trading Economics quote: {us_yield_row.get('date', 'N/A')}")

        if is_us:
            foreign_yield_pct, foreign_yield_manual = us_yield_pct, us_yield_manual
            st.caption("U.S. selected: local yield = U.S. yield.")
        else:
            local_row = bonds.get(country, {})
            local_auto = local_row.get("rate")
            foreign_yield_pct, foreign_yield_manual = optional_override(
                f"{country} 10-year yield", local_auto, default=4.0,
                key=f"foreign_yield_{country}", max_value=100.0,
            )
            if not foreign_yield_manual:
                st.caption(f"Trading Economics quote: {local_row.get('date', 'N/A')}")

        st.divider()
        st.subheader("Borrowing spreads")
        spread_auto = (spreads_source or {}).get("data")
        usd_spread_pct, usd_spread_manual = optional_override(
            "USD BBB borrowing spread", spread_auto, default=1.5,
            key="usd_spread", max_value=30.0,
        )
        if not usd_spread_manual:
            st.caption(f"Baa2/BBB · large non-financial firms · "
                       f"{(spreads_source or {}).get('asof', 'date unavailable')}")
        if is_us:
            foreign_spread_manual = False
            foreign_spread_pct = usd_spread_pct
            foreign_spread_input = None
        else:
            auto_local_spread_pct = usd_spread_pct * (1 + foreign_yield_pct / 100) / (1 + us_yield_pct / 100)
            foreign_spread_manual = st.checkbox("Override foreign-currency BBB spread",
                                                 value=False, key=f"spread_override_{country}")
            if foreign_spread_manual:
                foreign_spread_pct = st.number_input(
                    f"{currency} BBB spread (percentage points)", 0.0, 30.0,
                    value=float(auto_local_spread_pct), step=0.1, format="%.4f",
                    key=f"manual_foreign_spread_{country}",
                )
                foreign_spread_input = foreign_spread_pct / 100
            else:
                foreign_spread_pct = auto_local_spread_pct
                foreign_spread_input = None
                st.caption(f"Auto-converted spread: {foreign_spread_pct:.4f} percentage points")

    assumptions = {
        "debt_share": debt_pct / 100,
        "tax_rate": project_tax / 100,
        "erp": erp_pct / 100,
        "us_yield": us_yield_pct / 100,
        "foreign_yield": foreign_yield_pct / 100,
        "usd_spread": usd_spread_pct / 100,
        "foreign_spread_override": foreign_spread_input,
    }
    result = calculate_costs(beta_value, **{
        "debt_share": assumptions["debt_share"],
        "tax_rate": assumptions["tax_rate"],
        "equity_risk_premium": assumptions["erp"],
        "us_yield": assumptions["us_yield"],
        "foreign_yield": assumptions["foreign_yield"],
        "us_bbb_spread": assumptions["usd_spread"],
        "foreign_bbb_spread": assumptions["foreign_spread_override"],
    })

    st.title("Cost of capital")
    st.caption("U.S. industry betas, OECD corporate taxes, Damodaran BBB spreads, and Trading Economics 10-year yields")
    st.markdown(f"**Project:** {selected_industry} &nbsp;·&nbsp; **Country:** {country} ({currency}) "
                f"&nbsp;·&nbsp; **Tax jurisdiction:** {tax_jurisdiction}")
    if any([beta_is_manual, tax_is_manual, us_yield_manual, foreign_yield_manual,
            usd_spread_manual, foreign_spread_manual]):
        st.info("One or more inputs are manual. The result below uses your entered values, not necessarily current market quotes.")

    st.subheader("10-year yields used in the calculation")
    col_us, col_local = st.columns(2)
    with col_us:
        st.metric("U.S. 10-year government yield (USD)", label_percent(us_yield_pct, 4))
        st.caption("Manual" if us_yield_manual else f"Trading Economics · {us_yield_row.get('date', 'N/A')}")
    with col_local:
        st.metric(f"{country} 10-year government yield ({currency})", label_percent(foreign_yield_pct, 4))
        local_date = bonds.get(country, {}).get("date", "N/A")
        st.caption("Same as U.S. yield" if is_us else (
            "Manual" if foreign_yield_manual else f"Trading Economics · {local_date}"))

    st.subheader("Borrowing spreads")
    spread_col_us, spread_col_fx = st.columns(2)
    with spread_col_us:
        st.metric("USD BBB spread", label_percent(usd_spread_pct, 4))
        st.caption(f"{usd_spread_pct * 100:.2f} basis points over the U.S. 10-year yield")
    with spread_col_fx:
        st.metric(f"{currency} BBB spread", label_percent(foreign_spread_pct, 4))
        st.caption("Manual override" if foreign_spread_manual else
                   f"Auto-converted with factor {result['currency_factor']:.6f}")

    st.divider()
    st.subheader(selected_industry)
    firm_count = beta_record.get("firms")
    firm_desc = f"{firm_count:,} U.S. firms" if firm_count is not None else "Manual industry beta"
    st.caption(f"{firm_desc} · Damodaran beta date: "
               f"{(betas_source or {}).get('asof', 'not available')} · "
               f"same project tax rate ({project_tax:.2f}%) in both currencies")
    basics = st.columns(4)
    for column, label, value in zip(
        basics,
        ["U.S. 10Y yield", f"{country} 10Y yield", "Corporate tax rate", "Unlevered beta"],
        [label_percent(us_yield_pct, 3), label_percent(foreign_yield_pct, 3),
         label_percent(project_tax, 2), f"{beta_value:.4f}"],
    ):
        column.metric(label, value)
    st.caption(f"Relevered equity beta = **{result['beta_levered']:.4f}** · "
               f"D/E = **{result['debt_to_equity']:.4f}** · "
               f"ERP = **{erp_pct:.2f}%** · Debt financing = **{debt_pct}%**")

    st.divider()
    st.subheader("Capital costs by currency")
    usd_col, fx_col = st.columns(2, gap="large")
    with usd_col:
        st.markdown("#### United States · USD")
        x, y = st.columns(2)
        x.metric("Cost of equity", pct(result["cost_equity_usd"]))
        y.metric("WACC", pct(result["wacc_usd"]))
        st.metric("Pretax borrowing cost", pct(result["cost_debt_usd"], 4))
        st.metric("After-tax borrowing cost", pct(result["after_tax_debt_usd"], 4))
    with fx_col:
        st.markdown(f"#### {country} · {currency}")
        x, y = st.columns(2)
        x.metric("Cost of equity", pct(result["cost_equity_foreign"]))
        y.metric("WACC", pct(result["wacc_foreign"]))
        st.metric("Pretax borrowing cost", pct(result["cost_debt_foreign"], 4))
        st.metric("After-tax borrowing cost", pct(result["after_tax_debt_foreign"], 4))

    summary_rows = [
        ("Cost of equity", result["cost_equity_usd"], result["cost_equity_foreign"]),
        ("Pretax borrowing cost", result["cost_debt_usd"], result["cost_debt_foreign"]),
        ("After-tax borrowing cost", result["after_tax_debt_usd"], result["after_tax_debt_foreign"]),
        ("Equity contribution to WACC", result["equity_contribution_usd"], result["equity_contribution_foreign"]),
        ("Debt contribution to WACC", result["debt_contribution_usd"], result["debt_contribution_foreign"]),
        ("WACC", result["wacc_usd"], result["wacc_foreign"]),
    ]
    local_rate_column = f"Project · {currency} (%)"
    summary = pd.DataFrame({
        "Annual rate": [row[0] for row in summary_rows],
        "USD (%)": [row[1] * 100 for row in summary_rows],
        local_rate_column: [row[2] * 100 for row in summary_rows],
    })
    st.dataframe(summary.style.format({"USD (%)": "{:.4f}", local_rate_column: "{:.4f}"}),
                 hide_index=True, width="stretch")
    st.caption("WACC contributions are percentage points. All calculations retain full precision until display.")

    st.divider()
    st.subheader("Compare all U.S. industries")
    if industries:
        comparison = build_industry_comparison(industries, beta_field, assumptions)
        st.caption("Same country, tax, yields, equity risk premium, financing and borrowing spreads for every industry. "
                   "Only the industry unlevered beta changes. A manual beta override above applies only to the selected project.")
        st.dataframe(comparison, hide_index=True, width="stretch",
                     column_config={
                         "Unlevered beta": st.column_config.NumberColumn(format="%.4f"),
                         "Relevered beta": st.column_config.NumberColumn(format="%.4f"),
                     })
        st.download_button(
            "↓ Download all-industry comparison (CSV)",
            comparison.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"cost_of_capital_all_industries_{currency}.csv", mime="text/csv",
        )
    else:
        st.warning("All-industry comparison will appear when Damodaran's beta data can be retrieved.")

    selected_export = summary.copy()
    selected_export.insert(0, "Industry", selected_industry)
    selected_export.insert(1, "Project country", country)
    selected_export["Tax jurisdiction"] = tax_jurisdiction
    selected_export["Tax rate (%)"] = project_tax
    selected_export["Debt share (%)"] = debt_pct
    selected_export["ERP (%)"] = erp_pct
    selected_export["Unlevered beta"] = beta_value
    selected_export["Relevered beta"] = result["beta_levered"]
    selected_export["U.S. 10Y yield (%)"] = us_yield_pct
    selected_export["Local 10Y yield (%)"] = foreign_yield_pct
    selected_export["USD BBB spread (%)"] = usd_spread_pct
    selected_export["Local BBB spread (%)"] = foreign_spread_pct
    st.download_button(
        "↓ Download selected-project results (CSV)",
        selected_export.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"cost_of_capital_project_{currency}.csv", mime="text/csv",
    )

    with st.expander("Step-by-step methodology and formulas", expanded=False):
        st.markdown(r"""
        1. **Capital structure:** $D/E=d/(1-d)$.
        2. **Relever beta:** $\beta_E=\beta_U[1+(1-\tau)D/E]$.
        3. **USD cost of equity (CAPM):** $R_e=R_f+\beta_E\,ERP$.
        4. **USD pretax debt cost:** $R_d=R_f+s_{USD}$.
        5. **Currency adjustment factor:** $F=(1+R_f^*)/(1+R_f)$.
        6. **Local equity cost:** $R_e^*=(1+R_e)F-1$.
        7. **Local BBB spread (default):** $s^*=s_{USD}F$; manually overrideable.
        8. **Local pretax debt cost:** $R_d^*=R_f^*+s^*$.
        9. **Each currency's WACC:** $WACC=(1-d)R_e+dR_d(1-\tau)$.

        All yields, borrowing costs and equity risk premiums are **annual nominal rates**.
        $\tau$ is the **one selected project tax rate** in both columns.
        Risk-free rates are proxied by 10-year government bond yields, as in the assignment.
        The same global ERP is applied in USD CAPM and the resulting cost of equity
        is converted to the foreign currency. There is no additional country-risk
        premium, inflation forecast, FX spot rate, or currency hedging premium.
        USD and local WACC are each recomputed from their equity and after-tax debt
        costs; one is not assumed to be a direct Fisher conversion of the other.
        """)
        st.write(f"Current conversion factor: **{result['currency_factor']:.8f}**")
        st.write(f"USD beta calculation: **{beta_value:.4f} × "
                 f"[1 + (1 − {project_tax / 100:.4f}) × "
                 f"({debt_pct / 100:.4f} / {1 - debt_pct / 100:.4f})] "
                 f"= {result['beta_levered']:.6f}**")

    with st.expander("Data sources, as-of dates and freshness", expanded=True):
        st.caption("'As of' is the publisher's observation date, not the time the app fetched the webpage. "
                   "Trading Economics' country-list date is month/year; it is NOT an exact trading day.")
        source_rows = [
            ["U.S. industry unlevered betas", "Aswath Damodaran (NYU Stern)",
             (betas_source or {}).get("asof", "Unavailable"),
             (betas_source or {}).get("retrieved", "Unavailable"), BETA_URL],
            ["Baa2/BBB borrowing spread", "Aswath Damodaran (large non-financial)",
             (spreads_source or {}).get("asof", "Unavailable"),
             (spreads_source or {}).get("retrieved", "Unavailable"), SPREAD_URL],
            ["Combined statutory corporate tax", "OECD SDMX (country observation year)",
             str(foreign_tax_row.get("year") if tax_from_foreign else us_tax_row.get("year", "Unavailable")),
             (taxes_source or {}).get("retrieved", "Unavailable"), OECD_INFO_URL],
            ["U.S. 10-year yield", "Trading Economics", us_yield_row.get("date", "Unavailable"),
             (bonds_source or {}).get("retrieved", "Unavailable"), BONDS_URL],
            [f"{country} 10-year yield", "Trading Economics",
             bonds.get(country, {}).get("date", "Unavailable"),
             (bonds_source or {}).get("retrieved", "Unavailable"), BONDS_URL],
        ]
        st.dataframe(pd.DataFrame(source_rows, columns=["Input", "Publisher", "Source as of",
                                                         "Fetched at (UTC)", "URL"]),
                     hide_index=True, width="stretch",
                     column_config={"URL": st.column_config.LinkColumn("Source URL")})
        st.markdown(f"[Damodaran XLS]({BETA_URL}) · [Damodaran BBB table]({SPREAD_URL}) · "
                    f"[OECD tax data]({OECD_INFO_URL}) · [Trading Economics yields]({BONDS_URL})")
        st.info("Source-site HTML, worksheet formats and scraping access can change. "
                "Refresh source data to try again; use clearly labeled manual overrides if a fetch fails.")

    st.caption("Educational valuation tool · Rates are illustrative calculations, not investment recommendations.")


if __name__ == "__main__":
    main()

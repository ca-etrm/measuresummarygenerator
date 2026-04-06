__all__ = [
    # Models
    "Revision",
    "KeyTerminology",
    "KeyTerminologySection",
    "SectionDescription",
    "SunsettedMeasure",
    "SunsettedMeasureCollection",
    "SunsettedMeasuresSection",

    # Methods
    "get_api_key",
    "get_revisions",
    "get_key_terminology",
    "get_section_description",
    "get_introduction_html",
    "get_data_table_html",
    "get_use_category_intro_html",
]


import os
import pandas as pd
import re
import json
from typing import Any, Literal
from configparser import ConfigParser
import logging

from .models import (
    Revision,
    SummarySpreadsheetURL,
    KeyTerminology,
    KeyTerminologySection,
    SectionDescription,
    SunsettedMeasure,
    SunsettedMeasureCollection,
    SunsettedMeasuresSection
)

from src.etrm.models import SharedParameter

logger = logging.getLogger(__name__)
_PATH = os.path.abspath(os.path.dirname(__file__))


def get_path(file_name: str, exists: bool = True) -> str:
    file_path = os.path.join(_PATH, file_name)
    if exists and not os.path.exists(file_path):
        raise FileNotFoundError(f"No resource named {file_name} exists")

    return file_path


def get_api_key(role: Literal["user", "admin"] = "user") -> str:
    match role:
        case "user":
            source = "etrm"
        case "admin":
            source = "etrm-admin"
        case other:
            raise RuntimeError(f"Invalid eTRM role: {other}")

    config = ConfigParser()
    config.read(get_path("data/config.ini"))  #get_path() returns the file path of the config.ini file which has the API authorization token
    token_type = config[source]["type"]       #grab the type from the config.ini file based on the "Source"
    token = config[source]["token"]           #grab the token from the config.ini file based on the "Source"
    return f"{token_type} {token}"            #return the authorization string token


def get_json(file_name: str) -> dict[str, Any]:
    _, ext = os.path.splitext(file_name)
    if ext != ".json":
        raise RuntimeError(f"File {file_name} must be a JSON file")

    file_path = get_path(file_name, exists=True)
    with open(file_path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def get_revisions() -> list[Revision]:
    data = get_json("data/revisions.json")
    return [
        Revision(revision)
        for revision
        in data.get("revisions", [])
    ]

def get_summary_spreadsheet_url(use_category: str) -> SummarySpreadsheetURL:
    data = get_json("data/summary_spreadsheet_url.json")  #read in the json
    key = use_category.upper()                            #convert to upper if not already
    return SummarySpreadsheetURL(data[key])               #return the data for the usecategory


def get_key_terminology() -> KeyTerminologySection:
    data = get_json("data/key_terminology.json")
    return KeyTerminologySection(data)


def get_section_description(measure_version_id: str) -> SectionDescription | None:
    logger.info("Start src.resources.__init__.get_section_description")
    data = get_json("data/section_descriptions.json")
    desc_json = data.get(measure_version_id)
    if desc_json is None:
        return None

    return SectionDescription(desc_json)

def get_effective_dates(measure_version_id:str) -> tuple[str, str] | None:
    logger.info("Start src.resources.__init__.get_measure_effective_dates")
    
    csv_path = os.path.join(_PATH, "data", "measure_effective_dates.csv")
    data = pd.read_csv(csv_path)

    row = data.loc[data["MeasureVersionID"] == measure_version_id]

    if row.empty:
        logger.debug("\t❌src.resources.__init__.get_measure_effective_dates: can't find {measure_version_id}")
        start_date = "9999-01-01"
        end_date = "9999-01-01"
    else:
        start_date = row["StartDate"].iloc[0]
        end_date = row["EndDate"].iloc[0]

    return start_date, end_date

def get_measure_sector_flag(measure_version_id:str) -> tuple[bool, bool, bool] | None:
    logger.info("Start src.resources.__init__.get_measure_sector_flag")
    
    csv_path = os.path.join(_PATH, "data", "measure_effective_dates.csv")
    data = pd.read_csv(csv_path)

    row = data.loc[data["MeasureVersionID"] == measure_version_id]

    res = False
    mfmcmn = False
    nonres = False

    if row.empty:
        logger.debug("\t❌src.resources.__init__.get_measure_sector_flag: can't find {measure_version_id}")
        return res, mfmcmn, nonres 
    else:
        res_label = row["Res"].iloc[0]
        mfmcmn_label = row["MFmCmn"].iloc[0]
        nonres_label = row["NonRes"].iloc[0]

    if not pd.isna(res_label) and res_label != "":
        res = True
    if not pd.isna(mfmcmn_label) and mfmcmn_label != "":
        mfmcmn = True
    if not pd.isna(nonres_label) and nonres_label != "":
        nonres = True

    return res, mfmcmn, nonres


def ensure_html_file(file_name: str) -> str:
    if not file_name.endswith(".html"):
        file_name += ".html"

    return file_name


def get_html(file_name: str) -> str:
    file_path = get_path(ensure_html_file(f"data/{file_name}"))
    with open(file_path, "r") as fp:
        _html = (
            fp.read()
            .replace("\n", "")
            .replace("\t", "")
        )

    _html = re.sub(r"[ ]{2,}", " ", _html)
    return _html


def get_introduction_html() -> str:
    return get_html("introduction.html")


def get_data_table_html() -> str:
    return get_html("data_table.html")

def get_perm_data_spec_html() -> str:
    return get_html("perm_data_spec.html")

def get_use_category_intro_html() -> str:
    return get_html("uc_intro.html")


def get_sunsetted_measures() -> SunsettedMeasuresSection:
    data = get_json("data/sunsetted_measures.json")
    return SunsettedMeasuresSection(data)

def get_delivery_type_param() -> SharedParameter:
    data = get_json("data/delivery_type.json")
    return SharedParameter(data)
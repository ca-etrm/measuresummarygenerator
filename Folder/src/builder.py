import os
import re
import time
import logging
import datetime as dt

from src import lookups, resources, patterns, utils, _ROOT
from src.etrm import ETRMConnection, Measure
from src.summarygen import MeasureSummary


logger = logging.getLogger(__name__)


class MeasureFilter:
    def __init__(
        self,
        use_categories: list[str] | None = None,
        min_start_date: dt.datetime | None = None,
        max_start_date: dt.datetime | None = None,
        min_end_date: dt.datetime | None = None,
        max_end_date: dt.datetime | None = None
    ) -> None:
        if use_categories is not None:
            self.use_categories = set(use_categories)
        else:
            self.use_categories = None

        self.min_start_date = min_start_date
        self.max_start_date = max_start_date
        self.min_end_date = min_end_date
        self.max_end_date = max_end_date

    def is_allowed_measure_id(self, measure_id: str) -> bool:
        logger.info("Start src.builder.MeasureFilter.is_allowed_measure_id()")
        re_match = re.fullmatch(patterns.STWD_ID, measure_id)
        if re_match is None:
            return False

        try:
            use_category = str(re_match.group(3))
        except ValueError:
            return False

        if self.use_categories is not None and use_category not in self.use_categories:
            return False

        return True

    def is_allowed_measure(self, measure: Measure) -> bool:
        logger.info("Start src.builder.MeasureFilter.is_allowed_measure()")
        if self.use_categories is not None and measure.use_category not in self.use_categories:
            return False

        if self.min_start_date is not None and measure.start_date < self.min_start_date:
            return False

        if self.max_start_date is not None and measure.start_date >= self.max_start_date:
            return False

        if (self.min_end_date is not None
                and measure.end_date is not None
                and measure.end_date < self.min_end_date):
            return False

        if (self.max_end_date is not None
                #and measure.end_date is not None              #Need fixing: a max end date should remove measures w no end date
                and (measure.end_date >= self.max_end_date
                or measure.end_date is None)):
            return False

        return True

    def filter_measures(self, measures: list[Measure]) -> list[Measure]:
        return list(
            filter(
                lambda measure: self.is_allowed_measure(measure),
                measures
            )
        )


class Builder:
    def __init__(self, api_key: str | None = None):
        _api_key = api_key or resources.get_api_key(role="user")  #static field:
        _alt_key = resources.get_api_key(role="admin")            # --> get API key from src.resources.__init__.py
        self.connection = ETRMConnection(
            _api_key,
            alt_tokens=[_alt_key],
            use_persistent_cache=True
        )           #connection field of Builder() is an obj of ETRMConnection class -> instantiating with the API key arg

    def _get_measures(
        self,
        version_ids: list[str],
        _filter: MeasureFilter | None = None,
        limit: int | None = None        
    ) -> list[Measure]:
        logger.info("Start src.builder.Builder._get_measure()")
        measures: list[Measure] = []                         #initialize an empty list
        _filter = _filter or MeasureFilter()                 #A MeasureFilter obj to decide which measures should be included
        version_ids.sort(key=utils.version_key)               #Call src.utils.version_key, which assign an numerical # to each measure version ID. This is then used to sort the list
        for version_id in version_ids:                        #for each measure in the now sorted measures list
            measure = self.connection.get_measure(version_id)  #--> make the api/measure/<measureID>/<version> call to get the measure object
            if not _filter.is_allowed_measure(measure):        #--> above generates measure's properties (use_cat, start and end date). ...
                continue                                       #--> ... Check if these properties pass the filter criteria, if not then skip to the next iteration

            measures.append(measure)                           #--> Add the measure obj to the Measures list
            logger.info(f"\tBuilder._get_measure() added: {version_id}")
            if limit is not None and len(measures) >= limit:   #--> if exceed limit then break the loop
                break
        
        logger.info("End src.builder.Builder._get_measure()")
        return measures

    def get_measures(
        self,
        _filter: MeasureFilter,
        measure_versions: list[str] | None = None,
        limit: int | None = None
    ) -> list[Measure]:
        logger.info("Start src.builder.Builder.get_measure() ...")                           #print measures + filters to run the PDF
        logger.info(f"\tMeasure Versions: {measure_versions}")
        logger.info(f"\tUse Categories  : {_filter.use_categories}")
        logger.info(f"\tMin Start Date  : {_filter.min_start_date}")
        logger.info(f"\tMax Start Date  : {_filter.max_start_date}")
        logger.info(f"\tMin End Date    : {_filter.min_end_date}")
        logger.info(f"\tMax End Date    : {_filter.max_end_date}")
        logger.info(f"\tLimit           : {limit}")

        measures: list[Measure] = []        #initialize an empty list
        if measure_versions is not None:                                        #if CLI does pass in a list of measures
            measures.extend(self._get_measures(measure_versions, limit=limit))  #call _get_measures() fxn to add each measure (version) item to the list of Measures, meeting the limit

        if limit is not None and len(measures) >= limit:                        #if reaching limit then end here, if not cont to the rest
            return measures

        measure_ids = self.connection.get_all_measure_ids()                     #Get all the measure Ids
        for measure_id in measure_ids:                                          #Loop through the measure IDs to see if meets criteria ...
            if not _filter.is_allowed_measure_id(measure_id):                   #.... note: if the command line didn't specify a use_cat or the -a argument, this fxn will return false and measure ID is not included
                continue

            version_ids = self.connection.get_measure_versions(measure_id)      #--> if is an allowed ID, then get the measure verions for that ID
            measures.extend(                                                    #--> call _get_measures() fxn to add each measure (version) item to the list of Measures, meeting the limit
                self._get_measures(
                    version_ids,
                    _filter,
                    limit - len(measures) if limit is not None else limit
                )
            )

            if limit is not None and len(measures) >= limit:
                break

        return measures
        logger.info("End src.builder.Builder.get_measure() ...")

    def build(
        self,
        file_name: str,
        measure_versions: list[str] | None = None,
        _filter: MeasureFilter | None = None,
        limit: int | None = None
    ) -> None:
        logger.info(f"Start src.builder.Builder.build():")
        dir_path = os.path.join(_ROOT, "..", "summaries")   #folder path to store result
        measure_pdf = MeasureSummary(     #instanitize an obj of MeasureSummary class with attributes
            dir_path=dir_path,            #--> folder path to store result
            connection=self.connection,   #--> eTRMConnection class obj (contains API authorization keys)
            file_name=file_name           #--> name of the pou pdf
        )                               

        measures = self.get_measures(
            measure_versions=measure_versions,
            _filter=_filter or MeasureFilter(),
            limit=limit
        )                                #Call Builder.get_measures() to get the list of measures to add to this PDF
        for measure in measures:         #Call the add_measure fxn of measure_pdf obj to organize the above list of measures by UseCat and order
            measure_pdf.add_measure(measure)

        measure_pdf.build()              #Build the PDF
        logger.info(f"End src.builder.Builder.build(): Summary {measure_pdf.file_name} was successfully created")


def build(
    file_name: str,
    all_measures: bool = False,
    measure_versions: list[str] | None = None,
    use_categories: list[str] | None = None,
    min_start_date: dt.datetime | None = None,
    max_start_date: dt.datetime | None = None,
    min_end_date: dt.datetime | None = None,
    max_end_date: dt.datetime | None = None,
    limit: int | None = None
) -> None:
    logger.info(f"Start src.builder.build() to generate summary:")
    if all_measures:
        use_categories = list(lookups.USE_CATEGORIES.keys()) #-a = all measures for each use cat. If yes, then pull list of use_cat

    _filter = MeasureFilter(
        use_categories=use_categories,
        min_start_date=min_start_date,
        max_start_date=max_start_date,
        min_end_date=min_end_date,
        max_end_date=max_end_date
    ) #instantiating an obj of the MeasureFilter class with attributes

    builder = Builder() #instantiating an obj of the Builder() class with no attribute
    start = time.time() #start a timer
    builder.build(     #call the build() fxn for the Builder() class obj with args passed in
        file_name,
        measure_versions=measure_versions,
        _filter=_filter,
        limit=limit
    )
    elapsed = time.time() - start
    logger.info(f"End src.builder.build() - Generating summary took {elapsed}s")

import re
import os
import time
import json
import logging
import requests
import http.client as httpc
from typing import TypeVar, Callable, overload, Any
from src import (
    utils,
    resources
)
from src.etrm import sanitizers
from src.etrm.models import (
    MeasuresResponse,
    MeasureVersionsResponse,
    Measure,
    Reference,
    SharedLookupRef,
    SharedValueTable,
    PermutationsTable,
    SharedDeterminantRef,
    SharedParameter,
    SharedParameterVersion
)
from src.etrm.constants import STAGE_API, PROD_API
from src.etrm.exceptions import (
    ETRMResponseError,
    ETRMRequestError,
    ETRMConnectionError
)


logger = logging.getLogger(__name__)


_T = TypeVar('_T')

_PCACHE_FNAME = "p_cache.json"


_DEC_TYPE = Callable[..., _T | None]
def etrm_cache_request(func: _DEC_TYPE) -> _DEC_TYPE:
    """Decorator for eTRM cache request methods.

    Adds additional functionality that should be consistent with
    every eTRM cache request method.    
    """

    def wrapper(*args, **kwargs) -> _T | None:
        value = func(*args, **kwargs)
        if value is not None:
            logger.info("Cache HIT")
        else:
            logger.info("Cache MISS")

        return value

    return wrapper


def get_persistent_cache() -> dict[str, Any]:
    """
    Fxn to create a p_cache.json in src.etrm package to store cache data if file hasn't exist
    """
    dir_path = os.path.dirname(os.path.realpath(__file__)) #Getting the path for the cache file
    file_path = os.path.join(dir_path, _PCACHE_FNAME)
    if not os.path.exists(file_path):                      #if file doesn't existk, return empty dictionary (no cache data)
        return {}

    with open(file_path, "r") as fp:                       #open file and parse/load JSON file into a Python dictionary
        return json.load(fp)


def update_persistent_cache(cache: dict[str, Any]) -> None:
    dir_path = os.path.dirname(os.path.realpath(__file__))
    file_path = os.path.join(dir_path, _PCACHE_FNAME)
    with open(file_path, "w") as fp:
        json.dump(cache, fp)


class ETRMCache:
    """Cache for eTRM API response data

    Used to decrease eTRM API connection layer latency on repeat calls
    """

    def __init__(self, use_persistent_cache: bool = False) -> None:
        self._use_persistent_cache = use_persistent_cache
        if use_persistent_cache:
            self._p_cache = get_persistent_cache()
        else:
            self._p_cache = {}

        self.id_cache: list[str] = []
        self._id_count: int = -1
        self.uc_id_caches: dict[str, list[str]] = {}
        self._uc_id_counts: dict[str, int] = {}
        self.version_cache: dict[str, list[str]] = {}
        self.measure_cache: dict[str, Measure] = {}
        self.references: dict[str, Reference] = {}
        self.shared_value_tables: dict[str, SharedValueTable] = {}
        self.shared_parameters: dict[str, SharedParameter] = {}

    @etrm_cache_request
    def get_ids(
        self,
        offset: int,
        limit: int,
        use_category: str | None = None
    ) -> tuple[list[str], int] | None:
        if use_category != None:
            try:
                id_cache = self.uc_id_caches[use_category]
                count = self._uc_id_counts[use_category]
            except KeyError:
                return None
        else:
            id_cache = self.id_cache
            count = self._id_count

        try:
            cached_ids = id_cache[offset:offset + limit]
            if len(cached_ids) == limit and all(cached_ids):
                return (cached_ids, count)
        except IndexError:
            return None

        return None

    def add_ids(
        self,
        measure_ids: list[str],
        offset: int,
        limit: int,
        count: int,
        use_category: str | None = None
    ) -> None:
        if use_category != None:
            try:
                id_cache = self.uc_id_caches[use_category]
            except KeyError:
                self.uc_id_caches[use_category] = []
                id_cache = self.uc_id_caches[use_category]

            self._uc_id_counts[use_category] = count
        else:
            id_cache = self.id_cache
            self._id_count = count

        cache_len = len(id_cache)
        if offset == cache_len:
            id_cache.extend(measure_ids)
        elif offset > cache_len:
            id_cache.extend([""] * (offset - cache_len))
            id_cache.extend(measure_ids)
        elif offset + limit > cache_len:
            new_ids = measure_ids[cache_len - offset:limit]
            for i in range(offset, cache_len):
                if id_cache[i] == "":
                    id_cache[i] = measure_ids[i - offset]

            id_cache.extend(new_ids)

    @etrm_cache_request
    def get_versions(self, measure_id: str) -> list[str] | None:
        return self.version_cache.get(measure_id, None)

    def add_versions(self, measure_id: str, versions: list[str]) -> None:
        self.version_cache[measure_id] = versions

    @etrm_cache_request
    def get_measure(self, version_id: str) -> Measure | None:
        return self.measure_cache.get(version_id, None)

    def add_measure(self, measure: Measure) -> None:
        self.measure_cache[measure.full_version_id] = measure

    @etrm_cache_request
    def get_reference(self, ref_id: str) -> Reference | None:
        return self.references.get(ref_id, None)

    def add_reference(self, ref_id: str, reference: Reference) -> None:
        self.references[ref_id] = reference

    @etrm_cache_request
    def get_shared_value_table(
        self,
        table_name: str,
        version: str
    ) -> SharedValueTable | None:
        key = f"{table_name}-{version}"
        if self._use_persistent_cache:
            tables: dict[str, Any] = self._p_cache.get("shared_tables", {})
            table_dict = tables.get(key)
            if table_dict is not None:
                return SharedValueTable(table_dict)

        return self.shared_value_tables.get(key)

    def add_shared_value_table(
        self,
        table_name: str,
        version: str,
        value_table: SharedValueTable
    ) -> None:
        key = f"{table_name}-{version}"
        if self._use_persistent_cache:
            if "shared_tables" not in self._p_cache:
                self._p_cache["shared_tables"] = {}

            self._p_cache["shared_tables"][key] = value_table.as_dict()
            update_persistent_cache(self._p_cache)

        self.shared_value_tables[key] = value_table

    @etrm_cache_request
    def get_shared_parameter(
        self,
        param_type: str,
        version: str
    ) -> SharedParameter | None:
        key = f"{param_type}-{version}"
        if self._use_persistent_cache:
            params: dict[str, Any] = self._p_cache.get("shared_parameters", {})
            param_dict = params.get(key)
            if param_dict is not None:
                return SharedParameter(param_dict)

        return self.shared_parameters.get(key)

    def add_shared_parameter(self, parameter: SharedParameter) -> None:
        if self._use_persistent_cache:
            if "shared_parameters" not in self._p_cache:
                self._p_cache["shared_parameters"] = {}

            self._p_cache["shared_parameters"][parameter.version] = parameter.as_dict()
            update_persistent_cache(self._p_cache)

        self.shared_parameters[parameter.version] = parameter

class ETRMConnection:
    """eTRM API connection layer"""

    def __init__(
        self,
        auth_token: str,
        alt_tokens: list[str] | None = None,
        stage: bool = False,
        use_persistent_cache: bool = False
    ) -> None:
        self.auth_token = sanitizers.sanitize_auth_token(auth_token)  #call sanitizers to validate this is a valid API token
        self._base_token = self.auth_token
        self.alt_tokens: list[str] = []      #create alt_token to store alt tokens
        for alt_token in alt_tokens or []:
            self.alt_tokens.append(sanitizers.sanitize_auth_token(alt_token))  #validate each alt token

        self.api = STAGE_API if stage else PROD_API                #run for production; if run for stage, then set field to T in Builder Class
        self.cache = ETRMCache(use_persistent_cache=use_persistent_cache) #variable of eTRMCache class; instantiating with args

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.auth_token
        }

    def extract_id(self, url: str) -> str | None:
        URL_RE = re.compile(f"{self.api}/measures/([a-zA-Z0-9]+)/")
        re_match = re.search(URL_RE, url)
        if len(re_match.groups()) != 1:
            return None

        id_group = re_match.group(1)
        if not isinstance(id_group, str):
            return None

        return id_group

    def get(
        self,
        endpoint: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        stream: bool = True,
        **kwargs
    ) -> requests.Response:
        """Fxn takes in the API endpt + other API optional parameters
            1. Fxn ensures a valid API call URL for that endpt
            2. Fxn send the get request """
        logger.info(f'Starting etrm.connection.ETRMConnection.get():')
        _endpoint = endpoint.replace(self.api, "")   #Sanitize the endpt to ensure valid API call string
        if not _endpoint.startswith("/"):            #--> (above) If the passed-in endpt includes the base url (api), remove it
            _endpoint = "/" + _endpoint              #--> Add "/" to beginning of endpt if not already

        # if not _endpoint.endswith("/"):              #--> Add "/" to end of endpt if not already
        #     _endpoint += "/"

        _url = f"{self.api}{_endpoint}"              #put base url + endpt together (should now be valid)
        logger.info(f"ETRMConnection.get(): Making request to {_url}")
        for i in range(len(self.alt_tokens) + 1):    #go through all the alt authorization tokens
            req_headers: dict[str, str] = {**self._headers}  #-->authorization token in format of [Autorization]: [Token <API token>]
            if headers != None:
                req_headers |= headers               #--> If the caller passed additional headers, they're merged in using the |= operator (Python 3.9+ syntax for merging dicts)

            try:
                response = requests.get(             #--> make the http get request
                    _url,
                    params=params,
                    headers=req_headers,
                    stream=stream,
                    **kwargs
                )

                if response.status_code == 429:     #--> status code for being rate limited, if yes, switch token
                    try:
                        self.auth_token = self.alt_tokens[i]
                    except IndexError:
                        raise ETRMResponseError("ETRMConnection.get(): No more alt tokens to use")

                    logger.info("ETRMConnection.get(): Rate limited, switching API token...")
                    continue

                break
            except httpc.IncompleteRead:            #--> If the request fails because the response was cut off mid-read, retry 3x
                logger.info("ETRMConnection.get(): Request failed")
                if i == 3:
                    raise

                time.sleep(i)
                logger.info("ETRMConnection.get(): Trying again...") #--> Sleep for long after each retry
            except requests.exceptions.ConnectionError as err:
                raise ConnectionError() from err
            finally:
                self.auth_token = self._base_token   #--> reset the auth token to the base token after each try

        match response.status_code:               #request is successfull
            case 200:
                return response
            case status:
                msg = response.content.decode()
                raise ETRMResponseError(message=msg, status=status)
            

    def get_measure(self, measure_id: str) -> Measure:
        logger.info(f'Starting etrm.connection.ETRMConnection.get_measure: {measure_id}')

        try:
            measure_version = sanitizers.sanitize_measure_id(measure_id)  #verified the measure ID is a valid ID
        except:
            logger.debug(f'\tetrm.connection.ETRMConnection.get_measure: {measure_id} is invalid ID')
            raise

        cached_measure = self.cache.get_measure(measure_version)
        if cached_measure != None:
            logger.debug(f'\tetrm.connection.ETRMConnection.get_measure: found cache for {measure_id}')
            return cached_measure

        statewide_id, version_id = measure_version.split('-', 1)         #get the SW ID and version # from measure version ID string
        response = self.get(f'/measures/{statewide_id}/{version_id}')    #call the eTRMConnection.get() & pass in the API call endpt to get the response from the measure API call
        measure = Measure(response.json())                               #API call returns a JSON format -> instantiate a src.etrm.models.Measure obj with the json data to convert json fields to Measure attributes
        
        logger.debug(f'\tetrm.connection.ETRMConnection.get_measure: overwrite start and end dates')
        measure.start_date, measure.end_date = resources.get_effective_dates(measure_id)

        self.cache.add_measure(measure)                                  #Add this measure obj to the cache library to be used later
        logger.info(f'End etrm.connection.ETRMConnection.get_measure: {measure_id}')
        return measure                                                   #return the measure obj

    def get_measure_ids(
        self,
        offset: int = 0,
        limit: int = 25,
        use_category: str | None = None
    ) -> tuple[list[str], int]:
        logger.info(f'Start etrm.connection.ETRMConnection.get_measure_ids')

        cache_response = self.cache.get_ids(offset, limit, use_category)
        if cache_response is not None:
            logger.info(f'End etrm.connection.ETRMConnection.get_measure_ids via cache')
            return cache_response

        params = {}                                        #set up the API call parameters
        if use_category is not None:
            params['use_category'] = use_category

        params |= {
            'offset': str(offset),
            'limit': str(limit)
        }

        response = self.get('/measures', params=params)   #make the api/v1/measures API call to get list of measures
        response_body = MeasuresResponse(response.json()) #response is a json structure -> instantiatize MeasuresResponse to covert the json to obj attributes
        measure_ids = list(map(lambda result: self.extract_id(result.url),
                               response_body.results))    #response_body.results is the json results field of this api call -> call the eTRMConnection.extract_id() to get the measure ID from the url field -> compile to a list
        count = response_body.count                       #Get the # of measures; this is the "count" result of the api/v1/measures call. However, the above line only returns 25 (since limit set to 25)
        self.cache.add_ids(measure_ids=measure_ids,       #store result in cache
                           offset=offset,
                           limit=limit,
                           count=count,
                           use_category=use_category)
        return (measure_ids, count)

    def get_all_measure_ids(self, use_category: str | None=None) -> list[str]:
        logger.info('Start src.etrm.connection.ETRMConnection.get_all_measure_ids()')

        #Call ETRMConnection.get_measure__ids() - round 1. This round returns the # of measure IDs in the eTRM via the /measures API call
        _, count = self.get_measure_ids(use_category=use_category)
        #Call ETRMConnection.get_measure__ids() - round 2. Once know the total #, round 2 dynamically set the limit to the count to return all the measure IDs (this avoids doing offset/limit and using up call limit)
        measure_ids, _ = self.get_measure_ids(offset=0,
                                              limit=count,
                                              use_category=use_category)
        return measure_ids

    def get_measure_versions(self, statewide_id: str) -> list[str]:
        logger.info(f'Retrieving versions of measure {statewide_id}')

        try:
            statewide_id = sanitizers.sanitize_statewide_id(statewide_id)
        except:
            logger.info(f'Invalid statewide ID: {statewide_id}')
            raise

        cached_versions = self.cache.get_versions(statewide_id)
        if cached_versions is not None:
            return list(reversed(cached_versions))

        response = self.get(f'/measures/{statewide_id}')
        response_body = MeasureVersionsResponse(response.json())
        measure_versions: list[str] = []
        for version_info in response_body.versions:
            measure_versions.append(version_info.version)

        self.cache.add_versions(statewide_id, measure_versions)
        return list(reversed(measure_versions))

    def get_reference(self, ref_id: str) -> Reference:
        logger.info(f'Retrieving reference {ref_id}')

        try:
            ref_id = sanitizers.sanitize_reference(ref_id)
        except:
            logger.info(f'Invalid reference ID: {ref_id}')
            raise

        cached_ref = self.cache.get_reference(ref_id)
        if cached_ref is not None:
            return cached_ref

        response = self.get(f'/references/{ref_id}')
        reference = Reference(response.json())
        self.cache.add_reference(ref_id, reference)
        return reference

    @overload
    def get_shared_value_table(self,
                               lookup_ref: SharedLookupRef
                              ) -> SharedValueTable:
        ...

    @overload
    def get_shared_value_table(self,
                               table_name: str,
                               version: str | int
                              ) -> SharedValueTable:
        ...

    def get_shared_value_table(self, *args) -> SharedValueTable:
        if len(args) == 1:
            if not isinstance(args[0], SharedLookupRef):
                raise ETRMRequestError(f'unknown overload args: {args}')
            table_name = args[0].name
            version = args[0].version
            url = args[0].url
        elif len(args) == 2:
            if not (isinstance(args[0], str)
                        and isinstance(args[1], str | int)):
                raise ETRMRequestError(f'unknown overload args: {args}')
            table_name = args[0]
            version = f'{args[1]:03d}'
            url = f'/shared-value-tables/{table_name}/{version}'
        else:
            raise ETRMRequestError('missing required parameters')

        logger.info(f'Retrieving shared value table {table_name}')

        try:
            sanitizers.sanitize_table_name(table_name)
        except:
            logger.info(f'Invalid value table name: {table_name}')
            raise

        cached_table = self.cache.get_shared_value_table(table_name, version)
        if cached_table is not None:
            return cached_table

        response = self.get(url)
        value_table = SharedValueTable(response.json())
        self.cache.add_shared_value_table(table_name, version, value_table)
        return value_table

    def get_shared_parameter_versions(
        self,
        api_name: str,
        sorted: bool = True,
    ) -> list[SharedParameterVersion]:
        """Returns a list of all versions of the shared parameter associated with the
        provided API name.

        If sorted, the list of versions will be sorted from most-recent to least-recent.
        """

        results: list[dict[str, str]] = []
        url = f"/shared-parameters/{api_name}"
        while url is not None:
            res = self.get(url)
            content: dict[str, Any] = res.json()
            prev_url = utils.parse_url(url)
            url = content.get("next")
            if url is not None:
                prev_offset = prev_url.query.get("offset", "")
                parsed_url = utils.parse_url(url)
                url_offset = parsed_url.query.get("offset", "")
                if prev_offset == url_offset:
                    break

            results.extend(content.get("results", []))

        versions: list[SharedParameterVersion] = []
        for result in results:
            versions.append(SharedParameterVersion(result))

        if sorted:
            versions.sort(key=lambda version: -1 * version.version_num)

        return versions

    @overload
    def get_shared_parameter(self, reference: SharedDeterminantRef) -> SharedParameter:
        ...

    @overload
    def get_shared_parameter(self, name: str) -> SharedParameter:
        ...

    @overload
    def get_shared_parameter(self, name: str, version: str) -> SharedParameter:
        ...

    def get_shared_parameter(
        self,
        arg: str | SharedDeterminantRef,
        version: str | None = None,
    ) -> SharedParameter:
        logger.info(f'\t Start sr.etrm.connection.ETRMConnection.get_shared_parameter')
        if isinstance(arg, str):
            if version is None:
                versions = self.get_shared_parameter_versions(arg)
                if versions == []:
                    raise ETRMRequestError(f"Unknown shared parameter API name: {arg}")

                name, version = versions[0].version.split("-", 1)
            else:
                name = arg
        else:
            name = arg.name
            version = arg.version

        cached_param = self.cache.get_shared_parameter(name, version)
        if cached_param is not None:
            logger.debug(f'\tget {name}-{version} shared param via cache')
            return cached_param

        if name.lower() == "delivtype":
            logger.debug(f'\tget {name} shared param via src.resources')
            param = resources.get_delivery_type_param()
        else:
            logger.debug(f'\tget {name}-{version} shared param via API call')
            res = self.get(f"/shared-parameters/{name}/{version}")
            param = SharedParameter(res.json())
        self.cache.add_shared_parameter(param)
        return param

    def get_shared_parameter_description(self, name: str, version: str, label: str) -> str | None:
        param = self.get_shared_parameter(name, version)
        label_obj = param.get_label(label)
        if label_obj is None:
            return None

        return label_obj.description

    @overload
    def get_permutations(self, measure: Measure) -> PermutationsTable:
        ...

    @overload
    def get_permutations(self, statewide_id: str, version_id: str) -> PermutationsTable:
        ...

    def get_permutations(self, *args) -> PermutationsTable:
        match len(args):
            case 1:
                measure = args[0]
                if not isinstance(measure, Measure):
                    raise ETRMRequestError('Invalid arg type: measure must be a Measure object')

                ids = measure.full_version_id.split('-', 1)
                if len(ids) != 2:
                    raise ETRMConnectionError(f'Invalid measure id: {measure.full_version_id}')

                statewide_id = ids[0]
                version = ids[1]
            case 2:
                statewide_id = args[0]
                if not isinstance(statewide_id, str):
                    raise ETRMRequestError('Invalid arg type: statewide_id must be a string')

                version = args[1]
                if not isinstance(version, str):
                    raise ETRMRequestError('Invalid arg type: version_id must be a string')
            case _:
                raise ETRMRequestError('Unsupported arg count')

        logger.info(f'Retrieving permutations of measure {statewide_id}-{version}')
        try:
            statewide_id = sanitizers.sanitize_statewide_id(statewide_id)
        except:
            logger.info(f'Invalid statewide ID: {statewide_id}')
            raise
        
        url_offset = 0
        url = f'/measures/{statewide_id}/{version}/permutations?limit=10000'
        permutations_table: PermutationsTable | None = None
        while url is not None:
            response = self.get(url, stream=False)
            table = PermutationsTable(response.json())
            if table.links.next is not None and url_offset < 500000:
                
                url_offset += 10000
                url = f'/measures/{statewide_id}/{version}/permutations?limit=10000&offset={url_offset}'

                # prev_url = utils.parse_url(url)
                # prev_offset = prev_url.query.get('offset', '')
                # parsed_url = utils.parse_url(table.links.next)
                # url_offset = parsed_url.query.get('offset', '')
                # if prev_offset == url_offset:
                #     break
            else:
                url = None

            if permutations_table is None:
                permutations_table = table
            else:
                permutations_table.join_result(table)

        permutations_table.build_data_df()       
        return permutations_table

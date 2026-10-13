"""
HTTP client for the RadLab Semantic Search Engine REST API.

This is a port of streamlit_ui/pages/src/api.py with all Streamlit specific
code (spinners, page navigation) removed. The backend API contract is
identical:

- login:              POST {host}/api/login              form: username, password
- new_collection:     POST {host}/api/new_collection     form: collection params
- collections:        GET  {host}/api/collections
- generative_models:  GET  {host}/api/generative_models
- embedders:          GET  {host}/api/embedders
- rerankers:          GET  {host}/api/rerankers
- categories:         GET  {host}/api/categories?collection_name=...
- documents:          GET  {host}/api/documents?collection_name=...
- search_with_options:POST {host}/api/search_with_options
- generative_answer:  POST {host}/api/generative_answer
- rate_generative_answer: POST {host}/api/rate_generative_answer
- upload_and_index_files: POST {host}/api/upload_and_index_files (multipart)
- new_chat:           POST {host}/api/new_chat
- add_user_message:   POST {host}/api/add_user_message

Auth is a Django token: header ``Authorization: Token <token>``.
"""

import abc
import json

import requests


class ApiConfiguration:
    API_EP_FIELD = "ep"
    API_HOST_FIELD = "host"
    API_HOSTS_FIELD = "api_hosts"
    API_CONV_SEARCH_FIELD = "conversational_search"
    API_SEM_SEARCH_ENGINE_FIELD = "semantic_search_engine"

    def __init__(self, config_path: str | None = None) -> None:
        self._api_config_dict = {}

        self._cs_endpoints = {}
        self._sse_endpoints = {}
        self._cs_host = None
        self._sse_host = None

        self.config_path = config_path
        if config_path is not None:
            self.load()

    @property
    def conversational_search_host(self) -> str:
        return self._cs_host

    @property
    def semantic_search_engine_host(self) -> str:
        return self._sse_host

    @property
    def semantic_search_engine_endpoints(self) -> dict:
        return self._sse_endpoints

    @property
    def conversational_search_endpoints(self) -> dict:
        return self._cs_endpoints

    def load(self, config_path: str | None = None) -> None:
        if config_path is not None:
            self.config_path = config_path

        with open(self.config_path, "rt") as json_in:
            self._api_config_dict = json.load(json_in)

        self._process_config_file()

    def _process_config_file(self) -> None:
        self._cs_endpoints.clear()
        self._sse_endpoints.clear()

        api_hosts = self._api_config_dict[self.API_HOSTS_FIELD]

        api_cs = api_hosts[self.API_CONV_SEARCH_FIELD]
        api_sse = api_hosts[self.API_SEM_SEARCH_ENGINE_FIELD]

        self._cs_host = api_cs[self.API_HOST_FIELD]
        self._cs_endpoints = api_cs[self.API_EP_FIELD]
        self._sse_host = api_sse[self.API_HOST_FIELD]
        self._sse_endpoints = api_sse[self.API_EP_FIELD]


class BaseApiInterface(abc.ABC):
    def __init__(self, api_host: str, login_ep: str):
        self._api_host = api_host.rstrip("/")
        self.login_ep = login_ep.lstrip("/")

    def login(self, username: str, password: str) -> str | None:
        api_url = f"{self._api_host}/{self.login_ep}"
        context = {"username": username, "password": password}
        response = requests.post(api_url, data=context, timeout=30)
        if "token" in response.json():
            return response.json()["token"]
        return None

    @staticmethod
    def header(token: str) -> dict:
        return {"Authorization": "Token {}".format(token)} if token else {}

    @staticmethod
    def general_call_get(token, api_call_url, api_function, params=None, data=None):
        auth = BaseApiInterface.header(token=token)
        user_api_call_url = "{}/{}".format(api_call_url, api_function)
        response = requests.get(
            user_api_call_url, headers=auth, params=params, data=data, timeout=120
        )
        return response.json()

    @staticmethod
    def general_call_post(
        token: str | None,
        api_call_url: str,
        api_function: str,
        params: dict | None = None,
        data: dict | None = None,
        files=None,
        json_data: dict | None = None,
    ):
        auth = {"Content-Type": "application/json; charset=utf-8"}
        if token is not None and len(token.strip()):
            auth = BaseApiInterface.header(token=token)

        user_api_call_url = "{}/{}".format(api_call_url, api_function)
        response = requests.post(
            user_api_call_url,
            headers=auth,
            params=params,
            files=files,
            data=data,
            json=json_data,
            timeout=1800,
        )
        return response.json()


class SemanticSearchEngineAPI(BaseApiInterface):
    class EngineEP:
        def __init__(self, api_config: ApiConfiguration):
            self.login = api_config.semantic_search_engine_endpoints["login"]
            self.new_collection = api_config.semantic_search_engine_endpoints[
                "new_collection"
            ]
            self.list_collections = api_config.semantic_search_engine_endpoints[
                "collections"
            ]
            self.generative_models = api_config.semantic_search_engine_endpoints[
                "generative_models"
            ]
            self.embedders = api_config.semantic_search_engine_endpoints["embedders"]
            self.rerankers = api_config.semantic_search_engine_endpoints["rerankers"]
            self.list_categories_from_collection = (
                api_config.semantic_search_engine_endpoints["categories"]
            )
            self.list_documents_from_collection = (
                api_config.semantic_search_engine_endpoints["documents"]
            )
            self.search_with_options = api_config.semantic_search_engine_endpoints[
                "search_with_options"
            ]
            self.generative_answer = api_config.semantic_search_engine_endpoints[
                "generative_answer"
            ]
            self.rate_generative_answer = (
                api_config.semantic_search_engine_endpoints["rate_generative_answer"]
            )
            self.upload_and_index_files = (
                api_config.semantic_search_engine_endpoints["upload_and_index_files"]
            )
            self.add_new_chat = api_config.semantic_search_engine_endpoints[
                "new_chat"
            ]
            self.add_user_message_to_chat = (
                api_config.semantic_search_engine_endpoints["add_user_message"]
            )

    def __init__(self, config_path: str = "configs/ui-configuration.json"):
        self._api_config = ApiConfiguration(config_path=config_path)
        self._engine_ep = self.EngineEP(api_config=self._api_config)
        self._api_host = self._api_config.semantic_search_engine_host

        super().__init__(api_host=self._api_host, login_ep=self._engine_ep.login)

    def new_collection(self, token: str, collection_params: dict):
        response = self.general_call_post(
            token=token,
            api_call_url=self._api_host,
            api_function=self._engine_ep.new_collection,
            params=None,
            data=collection_params,
        )
        return response

    def new_chat(
        self, token: str, collection_name: str, options: dict, search_options: dict
    ):
        data = {
            "collection_name": collection_name,
            "options": json.dumps(options),
            "search_options": json.dumps(search_options),
        }

        response = self.general_call_post(
            token=token,
            api_call_url=self._api_host,
            api_function=self._engine_ep.add_new_chat,
            params=None,
            data=data,
        )
        return response["body"]["chat"]["id"]

    def add_user_message_to_chat(
        self,
        token: str,
        chat_id,
        user_message: str,
        options: dict,
        search_options: dict,
        collection_name: str,
    ):
        data = {
            "chat_id": chat_id,
            "user_message": user_message,
            "options": json.dumps(options),
            "search_options": json.dumps(search_options),
            "collection_name": collection_name,
        }

        response = self.general_call_post(
            token=token,
            api_call_url=self._api_host,
            api_function=self._engine_ep.add_user_message_to_chat,
            params=None,
            data=data,
        )
        return response["body"]

    def upload_files(
        self,
        token: str,
        files_to_upload: list,
        collection_name: str,
        indexing_options: dict,
    ) -> list | None:
        upl_files = self._prepare_files_to_upload(files_to_upload)
        if not len(upl_files):
            return None
        response = self.general_call_post(
            token=token,
            api_call_url=self._api_host,
            api_function=self._engine_ep.upload_and_index_files,
            params=None,
            data={
                "collection_name": collection_name,
                "indexing_options": json.dumps(indexing_options),
            },
            files=upl_files,
        )
        return response

    def list_user_collections(self, token: str):
        response = self.general_call_get(
            token=token,
            api_call_url=self._api_host,
            api_function=self._engine_ep.list_collections,
            params=None,
            data=None,
        )
        return response

    def list_generative_models(self, token: str):
        response = self.general_call_get(
            token=token,
            api_call_url=self._api_host,
            api_function=self._engine_ep.generative_models,
            params=None,
            data=None,
        )
        return response

    def embedders(self, token: str):
        response = self.general_call_get(
            token=token,
            api_call_url=self._api_host,
            api_function=self._engine_ep.embedders,
            params=None,
            data=None,
        )
        if "body" in response and "models" in response["body"]:
            return response["body"]["models"]
        return response

    def rerankers(self, token: str):
        response = self.general_call_get(
            token=token,
            api_call_url=self._api_host,
            api_function=self._engine_ep.rerankers,
            params=None,
            data=None,
        )
        if "body" in response and "models" in response["body"]:
            return response["body"]["models"]
        return response

    def list_categories_from_collection(self, token: str, collection_name: str):
        response = self.general_call_get(
            token=token,
            api_call_url=self._api_host,
            api_function=self._engine_ep.list_categories_from_collection,
            params={"collection_name": collection_name},
            data=None,
        )
        return response

    def list_documents_from_collection(self, token: str, collection_name: str):
        response = self.general_call_get(
            token=token,
            api_call_url=self._api_host,
            api_function=self._engine_ep.list_documents_from_collection,
            params={"collection_name": collection_name},
            data=None,
        )
        return response

    def search_answer_with_options(
        self, token: str, collection_name: str, question: str, options: dict
    ):
        options = dict(options)
        options["convert_to_display"] = True
        data = {
            "collection_name": collection_name,
            "query_str": question,
            "options": json.dumps(options),
            "ignore_question_lang_detect": True,
        }
        response = self.general_call_post(
            token=token,
            api_call_url=self._api_host,
            api_function=self._engine_ep.search_with_options,
            params=None,
            data=data,
        )
        return response

    def generative_answer_from_results(
        self, token: str, query_response_id: int, query_prompt: str, query_options
    ):
        data = {
            "query_response_id": query_response_id,
            "query_instruction": query_prompt,
            "query_options": json.dumps(query_options),
        }
        response = self.general_call_post(
            token=token,
            api_call_url=self._api_host,
            api_function=self._engine_ep.generative_answer,
            params=None,
            data=data,
        )
        return response

    def set_rating_for_generative_answer(
        self,
        token: str,
        answer_response_id: int,
        rate_value: int,
        rate_value_max: int,
        rate_comment: str | None,
    ):
        data = {
            "answer_response_id": answer_response_id,
            "rate_value": rate_value,
            "rate_value_max": rate_value_max,
        }
        if rate_comment is not None and len(rate_comment.strip()) > 0:
            data["rate_comment"] = rate_comment

        response = self.general_call_post(
            token=token,
            api_call_url=self._api_host,
            api_function=self._engine_ep.rate_generative_answer,
            params=None,
            data=data,
        )
        return response

    @staticmethod
    def _prepare_files_to_upload(files_to_upload: list) -> list:
        upl_files = []
        for f_upl in files_to_upload:
            upl_files.append(("files[]", (f_upl.filename, f_upl.file)))
        return upl_files

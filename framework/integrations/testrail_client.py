"""TestRail API client with retry logic and caching."""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .testrail_config import TestRailConfig


class TestRailAPIError(Exception):
    """TestRail API error."""
    pass


class TestRailClient:
    """TestRail API client with retry logic and caching."""
    
    def __init__(self, config: TestRailConfig):
        """Initialize TestRail client."""
        self.config = config
        self.config.validate()
        
        # Setup session with retry logic
        self.session = self._create_session()
        
        # Initialize cache
        self.cache = {} if config.enable_cache else None
        self.cache_timestamps = {}
    
    def _create_session(self) -> requests.Session:
        """Create HTTP session with retry configuration."""
        session = requests.Session()
        
        # Setup authentication
        session.auth = (self.config.username, self.config.api_key)
        session.headers.update({
            "Content-Type": "application/json"
        })
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.retry_delay,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "PUT", "OPTIONS", "DELETE"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _build_url(self, endpoint: str) -> str:
        """Build full API URL."""
        base = self.config.base_url.rstrip("/")
        if not base.endswith("/api/v2"):
            base = f"{base}/index.php?/api/v2"
        return f"{base}/{endpoint.lstrip('/')}"
    
    def _handle_response(self, response: requests.Response) -> Any:
        """Handle API response and errors."""
        if response.status_code == 429:
            # Rate limited - wait and retry
            retry_after = int(response.headers.get("Retry-After", 60))
            time.sleep(retry_after)
            raise TestRailAPIError(f"Rate limited. Retry after {retry_after} seconds")
        
        if response.status_code >= 400:
            try:
                error_data = response.json()
                error_msg = error_data.get("error", response.text)
            except:
                error_msg = response.text
            
            raise TestRailAPIError(
                f"API request failed with status {response.status_code}: {error_msg}"
            )
        
        try:
            return response.json()
        except json.JSONDecodeError:
            if response.status_code == 204:
                return None
            return response.text
    
    def _get_cached(self, cache_key: str) -> Optional[Any]:
        """Get cached data if valid."""
        if not self.cache:
            return None
        
        if cache_key in self.cache:
            timestamp = self.cache_timestamps.get(cache_key)
            if timestamp and (datetime.now() - timestamp).seconds < self.config.cache_ttl:
                return self.cache[cache_key]
        
        return None
    
    def _set_cache(self, cache_key: str, data: Any):
        """Set cache data."""
        if self.cache is not None:
            self.cache[cache_key] = data
            self.cache_timestamps[cache_key] = datetime.now()
    
    def get(self, endpoint: str, params: Optional[Dict] = None) -> Any:
        """Execute GET request."""
        cache_key = f"GET:{endpoint}:{json.dumps(params or {})}"
        
        # Check cache
        cached_data = self._get_cached(cache_key)
        if cached_data is not None:
            return cached_data
        
        url = self._build_url(endpoint)
        response = self.session.get(
            url,
            params=params,
            timeout=self.config.request_timeout
        )
        
        data = self._handle_response(response)
        self._set_cache(cache_key, data)
        return data
    
    def post(self, endpoint: str, data: Optional[Dict] = None) -> Any:
        """Execute POST request."""
        url = self._build_url(endpoint)
        response = self.session.post(
            url,
            json=data,
            timeout=self.config.request_timeout
        )
        return self._handle_response(response)
    
    def put(self, endpoint: str, data: Optional[Dict] = None) -> Any:
        """Execute PUT request."""
        url = self._build_url(endpoint)
        response = self.session.put(
            url,
            json=data,
            timeout=self.config.request_timeout
        )
        return self._handle_response(response)
    
    def delete(self, endpoint: str) -> Any:
        """Execute DELETE request."""
        url = self._build_url(endpoint)
        response = self.session.delete(
            url,
            timeout=self.config.request_timeout
        )
        return self._handle_response(response)
    
    # High-level API methods
    
    def get_project(self, project_id: Optional[int] = None) -> Dict:
        """Get project details."""
        pid = project_id or self.config.project_id
        return self.get(f"get_project/{pid}")
    
    def get_suites(self, project_id: Optional[int] = None) -> List[Dict]:
        """Get test suites for project."""
        pid = project_id or self.config.project_id
        return self.get(f"get_suites/{pid}")
    
    def get_suite(self, suite_id: int) -> Dict:
        """Get test suite details."""
        return self.get(f"get_suite/{suite_id}")
    
    def add_suite(self, name: str, description: str = "") -> Dict:
        """Create new test suite."""
        return self.post(
            f"add_suite/{self.config.project_id}",
            {"name": name, "description": description}
        )
    
    def get_sections(self, suite_id: Optional[int] = None) -> List[Dict]:
        """Get sections for suite."""
        sid = suite_id or self.config.suite_id
        return self.get(f"get_sections/{self.config.project_id}&suite_id={sid}")
    
    def add_section(
        self,
        name: str,
        parent_id: Optional[int] = None,
        suite_id: Optional[int] = None,
        description: str = ""
    ) -> Dict:
        """Create new section."""
        sid = suite_id or self.config.suite_id
        data = {
            "name": name,
            "description": description,
            "suite_id": sid
        }
        if parent_id:
            data["parent_id"] = parent_id
        
        return self.post(f"add_section/{self.config.project_id}", data)
    
    def get_cases(
        self,
        suite_id: Optional[int] = None,
        section_id: Optional[int] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Dict]:
        """Get test cases."""
        sid = suite_id or self.config.suite_id
        endpoint = f"get_cases/{self.config.project_id}&suite_id={sid}"
        
        if section_id:
            endpoint += f"&section_id={section_id}"
        if limit:
            endpoint += f"&limit={limit}&offset={offset}"
        
        return self.get(endpoint)
    
    def get_case(self, case_id: int) -> Dict:
        """Get test case details."""
        return self.get(f"get_case/{case_id}")
    
    def add_case(
        self,
        section_id: int,
        title: str,
        custom_fields: Optional[Dict] = None,
        **kwargs
    ) -> Dict:
        """Create new test case."""
        data = {
            "title": title,
            "section_id": section_id,
            **kwargs
        }
        
        # Add custom fields
        if custom_fields:
            for key, value in custom_fields.items():
                field_name = self.config.custom_fields.get(key, key)
                data[field_name] = value
        
        return self.post(f"add_case/{section_id}", data)
    
    def update_case(self, case_id: int, **kwargs) -> Dict:
        """Update test case."""
        return self.post(f"update_case/{case_id}", kwargs)
    
    def delete_case(self, case_id: int):
        """Delete test case."""
        return self.post(f"delete_case/{case_id}")
    
    def get_runs(
        self,
        project_id: Optional[int] = None,
        is_completed: Optional[bool] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Dict]:
        """Get test runs."""
        pid = project_id or self.config.project_id
        endpoint = f"get_runs/{pid}"
        
        params = {}
        if is_completed is not None:
            params["is_completed"] = 1 if is_completed else 0
        if limit:
            params["limit"] = limit
            params["offset"] = offset
        
        return self.get(endpoint, params)
    
    def get_run(self, run_id: int) -> Dict:
        """Get test run details."""
        return self.get(f"get_run/{run_id}")
    
    def add_run(
        self,
        name: str,
        suite_id: Optional[int] = None,
        milestone_id: Optional[int] = None,
        description: str = "",
        case_ids: Optional[List[int]] = None,
        include_all: bool = False
    ) -> Dict:
        """Create new test run."""
        data = {
            "name": name,
            "description": description,
            "include_all": include_all
        }
        
        if suite_id or self.config.suite_id:
            data["suite_id"] = suite_id or self.config.suite_id
        
        if milestone_id or self.config.milestone_id:
            data["milestone_id"] = milestone_id or self.config.milestone_id
        
        if case_ids and not include_all:
            data["case_ids"] = case_ids
        
        return self.post(f"add_run/{self.config.project_id}", data)
    
    def update_run(self, run_id: int, **kwargs) -> Dict:
        """Update test run."""
        return self.post(f"update_run/{run_id}", kwargs)
    
    def close_run(self, run_id: int) -> Dict:
        """Close test run."""
        return self.post(f"close_run/{run_id}")
    
    def get_results(self, test_id: int, limit: Optional[int] = None) -> List[Dict]:
        """Get test results."""
        endpoint = f"get_results/{test_id}"
        if limit:
            endpoint += f"&limit={limit}"
        return self.get(endpoint)
    
    def get_results_for_case(
        self,
        run_id: int,
        case_id: int,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """Get results for specific test case in run."""
        endpoint = f"get_results_for_case/{run_id}/{case_id}"
        if limit:
            endpoint += f"&limit={limit}"
        return self.get(endpoint)
    
    def add_result(self, test_id: int, status_id: int, **kwargs) -> Dict:
        """Add test result."""
        data = {"status_id": status_id, **kwargs}
        return self.post(f"add_result/{test_id}", data)
    
    def add_result_for_case(
        self,
        run_id: int,
        case_id: int,
        status_id: int,
        **kwargs
    ) -> Dict:
        """Add result for test case in run."""
        data = {"status_id": status_id, **kwargs}
        return self.post(f"add_result_for_case/{run_id}/{case_id}", data)
    
    def add_results(self, run_id: int, results: List[Dict]) -> List[Dict]:
        """Add multiple test results."""
        return self.post(f"add_results/{run_id}", {"results": results})
    
    def add_results_for_cases(self, run_id: int, results: List[Dict]) -> List[Dict]:
        """Add results for multiple test cases."""
        return self.post(f"add_results_for_cases/{run_id}", {"results": results})
    
    # Bulk operations with batching
    
    def bulk_add_cases(self, cases: List[Dict], section_id: int) -> List[Dict]:
        """Add multiple test cases with batching."""
        created_cases = []
        
        for i in range(0, len(cases), self.config.batch_size):
            batch = cases[i:i + self.config.batch_size]
            
            for case_data in batch:
                try:
                    case = self.add_case(section_id=section_id, **case_data)
                    created_cases.append(case)
                except TestRailAPIError as e:
                    print(f"Failed to create case: {e}")
                    continue
            
            # Small delay between batches to avoid rate limiting
            if i + self.config.batch_size < len(cases):
                time.sleep(0.5)
        
        return created_cases
    
    def bulk_update_cases(self, updates: List[Dict]) -> List[Dict]:
        """Update multiple test cases with batching."""
        updated_cases = []
        
        for i in range(0, len(updates), self.config.batch_size):
            batch = updates[i:i + self.config.batch_size]
            
            for update in batch:
                case_id = update.pop("case_id")
                try:
                    case = self.update_case(case_id, **update)
                    updated_cases.append(case)
                except TestRailAPIError as e:
                    print(f"Failed to update case {case_id}: {e}")
                    continue
            
            # Small delay between batches
            if i + self.config.batch_size < len(updates):
                time.sleep(0.5)
        
        return updated_cases
    
    def clear_cache(self):
        """Clear all cached data."""
        if self.cache is not None:
            self.cache.clear()
            self.cache_timestamps.clear()
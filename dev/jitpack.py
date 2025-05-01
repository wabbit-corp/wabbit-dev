
# https://medium.com/geekculture/publish-your-android-library-on-jitpack-for-better-reachability-1c978dde726e
# https://developerlife.com/2021/02/06/publish-kotlin-library-as-gradle-dep/

# https://github.com/settings/tokens

# https://jitpack.io/#wabbit-corp/kotlin-base58
# https://jitpack.io/com/github/wabbit-corp/kotlin-math-rational/1.0.0/kotlin-math-rational-1.0.0.pom
# https://jitpack.io/com/github/wabbit-corp/kotlin-base58/1.1.0-SNAPSHOT/kotlin-base58-1.1.0-SNAPSHOT.pom
# https://jitpack.io/com/github/wabbit-corp/kotlin-base58/1.1.0-SNAPSHOT/build.log
# https://jitpack.io/com/github/wabbit-corp/kotlin-parsing-parsers/1.0.0/build.log

#!/usr/bin/env python3
"""
jitpack_api.py

An asynchronous Python client for interacting with the JitPack.io API.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional, Union

import aiohttp
from aiohttp import ClientResponse, ClientSession

__all__ = [
    "JitPackAPI",
    "JitPackAPIError",
    "JitPackAuthError",
    "JitPackNotFoundError",
    "BuildStatus",
    "Commit",
    "Ref",
    "Build",
    "Settings",
]

logger = logging.getLogger("jitpack_api")
logger.setLevel(logging.INFO)


#
# Exceptions
#
class JitPackAPIError(Exception):
    """Base exception for JitPack API errors."""
    pass


class JitPackAuthError(JitPackAPIError):
    """Raised if authentication or permissions fail (401/403)."""
    pass


class JitPackNotFoundError(JitPackAPIError):
    """Raised if a requested resource was not found (404)."""
    pass


#
# Enums
#
class BuildStatus(Enum):
    OK = "ok"
    BUILDING = "Building"
    QUEUED = "Queued"
    ERROR = "Error"
    TAG_NOT_FOUND = "tagNotFound"
    UNKNOWN = "unknown"    # Fallback if the API returns an unknown status


#
# Data Models
#
@dataclass
class Commit:
    sha: str
    message: str


@dataclass
class Ref:
    name: str
    commit: str  # e.g. the commit SHA


@dataclass
class Version:
    status: BuildStatus
    isTag: bool | None
    commit: str | None
    deletable: bool | None
    version: str
    date: str | None

@dataclass
class Build:
    version: str
    status: BuildStatus = BuildStatus.UNKNOWN
    ci: bool = False
    build_url: Optional[str] = None
    deletable: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Settings:
    is_admin: bool = False
    need_auth: bool = False
    show_ci: bool = False
    enable_ci: bool = False
    public: bool = True
    access_tokens: List[str] = field(default_factory=list)
    collaborators: List[Dict[str, str]] = field(default_factory=list)
    environment: List[Dict[str, str]] = field(default_factory=list)
    extra_tokens: List[Dict[str, str]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


#
# Main API client
#
class JitPackAPI:
    """
    An async API client to interact with JitPack.io.

    Example usage:
        async with JitPackAPI(session_cookie="ABC123") as api:
            refs = await api.get_refs("com.github.john", "myproject")
            ...
    """

    def __init__(
        self,
        base_url: str = "https://jitpack.io",
        session_cookie: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        """
        :param base_url: Base URL for JitPack, default is https://jitpack.io
        :param session_cookie: If set, this session cookie (e.g. 'sessionId=XYZ') will be sent for
                               authorized requests (like deleting builds).
        :param timeout: Overall request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        # Just store the session ID or full cookie line. 
        # Typically for JitPack it’s "sessionId=XYZ", but you could store only "XYZ" 
        # and handle it yourself in `cookies` or `headers`.
        self.session_cookie = session_cookie  
        self.timeout = timeout

        self._session: Optional[ClientSession] = None

    async def __aenter__(self) -> "JitPackAPI":
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    #
    # Internal helpers
    #
    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
    ) -> Any:
        """
        Internal method to send an HTTP request using aiohttp.

        :param method: HTTP method: 'GET', 'POST', 'PUT', 'DELETE', etc.
        :param path: URL path relative to self.base_url
        :param params: Optional query parameters
        :param json_data: Optional JSON body for POST/PUT
        :return: The JSON-decoded response from the server
        :raises JitPackAPIError: for non-2xx responses
        """
        if not self._session:
            raise RuntimeError("ClientSession not initialized. Use `async with JitPackAPI(...) as api:`")

        url = f"{self.base_url}{path}"

        # Prepare cookies
        cookies = {}
        # If the session_cookie is "sessionId=XYZ" you can parse it or directly pass it in a dict
        if self.session_cookie:
            # If your cookie is exactly "XYZ" and you want a "sessionId" key:
            # cookies["sessionId"] = self.session_cookie
            #
            # If your cookie is already "sessionId=XYZ", you can split by '=' or just parse. 
            # For simplicity, let's assume the user provided "sessionId=XYZ":
            try:
                # e.g. "sessionId" / "XYZ"
                cookie_key, cookie_val = self.session_cookie.split("=", 1)
                cookies[cookie_key] = cookie_val
            except ValueError:
                # Fallback: if there's a parse error, treat the entire string as sessionId
                cookies["sessionId"] = self.session_cookie

        logger.debug("Request: %s %s cookies=%s params=%s json_data=%s", method, url, cookies, params, json_data)

        async with self._session.request(
            method,
            url,
            params=params,
            json=json_data,
            cookies=cookies,
        ) as resp:
            await self._raise_for_status(resp)
            # if response is JSON
            if resp.content_type == "application/json":
                return await resp.json()
            # else return text or bytes
            return await resp.text()

    async def _raise_for_status(self, response: ClientResponse) -> None:
        """
        Raise the appropriate exception if response.status is not 2xx.
        """
        if 200 <= response.status < 300:
            return

        body = await response.text()
        status = response.status

        if status in (401, 403):
            raise JitPackAuthError(
                f"Authentication/permission error (HTTP {status}). Response body: {body}"
            )
        elif status == 404:
            raise JitPackNotFoundError(f"Resource not found (HTTP 404). Response body: {body}")
        else:
            raise JitPackAPIError(f"HTTP {status} error. Body: {body}")

    #
    # Public methods
    #
    async def get_refs(self, group: str, project: str) -> List[Ref]:
        """
        GET /api/refs/{group}/{project}

        :param group: e.g. "com.github.owner"
        :param project: e.g. "myproject"
        :return: A list of Ref objects (tags, branches, etc.)
        """
        path = f"/api/refs/{group}/{project}"
        data = await self._request("GET", path)
        refs = []

        # Expecting something like:  {"tags": [...], "branches": [...]}
        # Let's combine them or parse them separately. 
        tags = data.get("tags", [])
        branches = data.get("branches", [])

        # We unify them as "Ref" objects. 
        # The JS code suggests "tag_name" and "commit" for branches as well. 
        for t in tags:
            name = t.get("tag_name") or t.get("name") or "unknown"
            commit = t.get("commit", "")[:7]
            refs.append(Ref(name=name, commit=commit))
        for b in branches:
            name = b.get("tag_name") or b.get("name") or "unknown"
            commit = b.get("commit", "")[:7]
            refs.append(Ref(name=name, commit=commit))

        return refs
    
    async def force_build(self, group: str, project: str, version: str) -> None:
        # We can force a build by sending a GET to the POM file URL.
        # This will trigger a new build for the specified version.
        # https://jitpack.io/com/github/wabbit-corp/kotlin-base58/1.1.0-SNAPSHOT/kotlin-base58-1.1.0-SNAPSHOT.pom

        assert group.startswith("com.github."), "Group must start with 'com.github.'"
        group = group[len("com.github."):]

        path = f"/com/github/{group}/{project}/{version}/{project}-{version}.pom"
        # We need it to timeout quickly, so we don't wait for the response.
        # And we don't need cookies or JSON data.
        try: 
            async with self._session.request(
                "GET",
                f"{self.base_url}{path}",
                timeout=30.0,
            ) as resp:
                # We don't need to check the status, just log it.
                await self._raise_for_status(resp)
                logger.info("Forced build for: group=%s, project=%s, version=%s", group, project, version)
                time.sleep(5)
        except asyncio.TimeoutError:
            logger.warning("Timeout while forcing build for: group=%s, project=%s, version=%s", group, project, version)
        except aiohttp.ClientError as e:
            logger.error("Client error while forcing build for: group=%s, project=%s, version=%s. Error: %s", group, project, version, e)
        except Exception as e:
            logger.error("Unexpected error while forcing build for: group=%s, project=%s, version=%s. Error: %s", group, project, version, e)
            raise

    def _get_cookies(self) -> Dict[str, str]:
        # Prepare cookies
        cookies = {}
        # If the session_cookie is "sessionId=XYZ" you can parse it or directly pass it in a dict
        if self.session_cookie:
            # If your cookie is exactly "XYZ" and you want a "sessionId" key:
            # cookies["sessionId"] = self.session_cookie
            #
            # If your cookie is already "sessionId=XYZ", you can split by '=' or just parse. 
            # For simplicity, let's assume the user provided "sessionId=XYZ":
            try:
                # e.g. "sessionId" / "XYZ"
                cookie_key, cookie_val = self.session_cookie.split("=", 1)
                cookies[cookie_key] = cookie_val
            except ValueError:
                # Fallback: if there's a parse error, treat the entire string as sessionId
                cookies["sessionId"] = self.session_cookie
        return cookies
            
    async def get_build_log(self, group: str, project: str, version: str) -> str:
        # We can get the build log by sending a GET to the build log URL.
        # https://jitpack.io/com/github/wabbit-corp/kotlin-base58/1.1.0-SNAPSHOT/build.log

        assert group.startswith("com.github."), "Group must start with 'com.github.'"
        group = group[len("com.github."):]

        path = f"/com/github/{group}/{project}/{version}/build.log"

        print(f"Getting build log for: group={group}, project={project}, version={version}")

        async with self._session.request(
            "GET",
            f"{self.base_url}{path}",
            cookies=self._get_cookies(),
            headers={"Accept": "text/plain"},
        ) as resp:
            await self._raise_for_status(resp)
            return await resp.text()

    async def get_commits(self, group: str, project: str, branch: Optional[str] = None) -> List[Commit]:
        """
        GET /api/commits/{group}/{project}?branch=<branch>

        :param group: e.g. "com.github.owner"
        :param project: e.g. "myproject"
        :param branch: optional branch name
        :return: A list of Commit objects
        """
        path = f"/api/commits/{group}/{project}"
        params = {}
        if branch:
            params["branch"] = branch

        data = await self._request("GET", path, params=params)
        commits_raw = data.get("commits", [])
        commits: List[Commit] = []

        for c in commits_raw:
            sha = c.get("sha", "")[:40]
            message = c.get("message", "")
            commits.append(Commit(sha=sha, message=message))

        return commits

    async def get_build_info(self, group: str, artifact: str, version: str) -> Build | None:
        """
        GET /api/builds/{group}/{artifact}/{version}
        Retrieve info about a single build.

        :param group: e.g. "com.github.owner"
        :param artifact: e.g. "myproject"
        :param version: e.g. "v1.0" or commit SHA
        :return: A Build object
        """
        path = f"/api/builds/{group}/{artifact}/{version}"

        try:
            data = await self._request("GET", path)
        except JitPackNotFoundError:
            return None
        # print(data)

        # The JS code suggests possible fields:
        # { "status": "ok|Building|...", "ci": bool, "buildUrl": "...", "deletable": bool, ...}
        status_str = data.get("status", "unknown")
        try:
            status = BuildStatus(status_str)
        except ValueError:
            status = BuildStatus.UNKNOWN

        build = Build(
            version=version,
            status=status,
            ci=data.get("ci", False),
            build_url=data.get("buildUrl"),
            deletable=data.get("deletable", False),
            raw=data,
        )
        return build

    async def delete_build(self, group: str, artifact: str, version: str) -> None:
        """
        DELETE /api/builds/{group}/{artifact}/{version}
        Deletes a build (requires session cookie / auth)

        :param group: e.g. "com.github.owner"
        :param artifact: e.g. "myproject"
        :param version: e.g. "1.0.0"
        :raises JitPackAuthError: if not authorized
        """
        path = f"/api/builds/{group}/{artifact}/{version}"
        await self._request("DELETE", path)
        logger.info("Deleted build: group=%s, artifact=%s, version=%s", group, artifact, version)

    async def get_versions(self, group: str, project: str, query: Optional[str] = None) -> List[Version]:
        """
        GET /api/versions/{group}/{project}?{query}

        :param group: e.g. "com.github.owner"
        :param project: e.g. "myproject"
        :param query: additional query, like 'reload' or other keys
        :return: A list of versions (string)
        """
        path = f"/api/versions/{group}/{project}"
        params = {}
        if query:
            # The JS code does: if(query) url += "?"+query
            # So let's parse that quickly.
            # If you know it's exactly `reload` you can do params={"reload": ""} or so.
            # For a general approach, parse it as k=v pairs if present:
            if "=" in query:
                # naive parse
                k, v = query.split("=", 1)
                params[k] = v
            else:
                # e.g. query="reload"
                params[query] = ""

        data = await self._request("GET", path, params=params)
        data = data.get(group, {}).get(project, {})
        versions = []
        for _, v in data.items():
            status_str = v.get("status", "unknown")
            try:
                status = BuildStatus(status_str)
            except ValueError:
                status = BuildStatus.UNKNOWN

            versions.append(Version(
                status=status,
                isTag=v.get("isTag"),
                commit=v.get("commit"),
                deletable=v.get("deletable"),
                version=v["version"],
                date=v.get("date"),
            ))
        return versions

    async def get_settings(self, group: str, project: str) -> Settings:
        """
        GET /api/settings/{group}/{project}

        :param group: e.g. "com.github.owner"
        :param project: e.g. "myproject"
        :return: Settings object
        """
        path = f"/api/settings/{group}/{project}"
        data = await self._request("GET", path)

        # Convert JSON into Settings data class
        s = Settings(
            is_admin=data.get("isAdmin", False),
            need_auth=data.get("needAuth", False),
            show_ci=data.get("showCI", False),
            enable_ci=data.get("enableCI", False),
            public=data.get("public", True),
            access_tokens=data.get("access_tokens", []),
            collaborators=data.get("collaborators", []),
            environment=data.get("environment", []),
            extra_tokens=data.get("extraTokens", []),
            raw=data
        )
        return s

    async def put_settings(self, group: str, project: str, new_settings: Dict[str, Any]) -> Settings:
        """
        PUT /api/settings/{group}/{project}

        :param group: e.g. "com.github.owner"
        :param project: e.g. "myproject"
        :param new_settings: dict with fields to update, e.g. {"enableCI": True}
        :return: Updated Settings object
        """
        path = f"/api/settings/{group}/{project}"
        data = await self._request("PUT", path, json_data=new_settings)
        return Settings(
            is_admin=data.get("isAdmin", False),
            need_auth=data.get("needAuth", False),
            show_ci=data.get("showCI", False),
            enable_ci=data.get("enableCI", False),
            public=data.get("public", True),
            access_tokens=data.get("access_tokens", []),
            collaborators=data.get("collaborators", []),
            environment=data.get("environment", []),
            extra_tokens=data.get("extraTokens", []),
            raw=data
        )

    async def post_trial(self, git_owner_url: str, login: str, plan: str) -> Dict[str, Any]:
        """
        POST /api/service/trial?gitOwnerUrl=...&login=...&plan=...

        :param git_owner_url: e.g. "https://github.com/<user-or-org>"
        :param login: your GitHub user name
        :param plan: subscription plan name
        :return: JSON response as dictionary
        """
        path = "/api/service/trial"
        params = {
            "gitOwnerUrl": git_owner_url,
            "login": login,
            "plan": plan,
        }
        data = await self._request("POST", path, params=params)
        return data


#
# Example main usage for local testing
#
async def main():
    # Replace with your actual session cookie if needed
    session_cookie = "sessionId=e2be4885-c556-4548-a06e-aa800a77a495"
    async with JitPackAPI(session_cookie=session_cookie) as api:
        # Example calls
        group = "com.github.wabbit-corp"
        project = "kotlin-base58"

        # 1. Get references (tags/branches)
        refs = await api.get_refs(group, project)
        print("Refs:", refs)

        # 2. Get commits
        commits = await api.get_commits(group, project, branch="main")
        print("Commits:", commits)

        # 3. Get versions
        versions = await api.get_versions(group, project)
        print("Versions:", versions)

        # 4. Get build info for a specific version
        if versions:
            build = await api.get_build_info(group, project, versions[0])
            print("Build info for first version:", build)

        # 5. Delete a build (needs session cookie with permission)
        # await api.delete_build(group, project, "1.0.0")

        # 6. Get settings
        settings = await api.get_settings(group, project)
        print("Settings:", settings)

        # 7. Update settings
        # updated_settings = await api.put_settings(group, project, {"enableCI": True})
        # print("Updated settings:", updated_settings)

        # 8. Start a trial
        # trial_resp = await api.post_trial(
        #     git_owner_url="https://github.com/wabbit-corp", 
        #     login="wabbit-corp", 
        #     plan="FREE"
        # )
        # print("Trial response:", trial_resp)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(main())
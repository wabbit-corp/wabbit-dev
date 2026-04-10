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
import time
from dataclasses import dataclass, field
from enum import Enum

import aiohttp
from aiohttp import ClientResponse, ClientSession

from dev.json_utils import (
    as_bool,
    as_dict,
    as_list,
    as_optional_str,
    as_str,
    as_string_dict_list,
    as_string_list,
)

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

logger = logging.getLogger(__name__)


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
    UNKNOWN = "unknown"  # Fallback if the API returns an unknown status


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
    build_url: str | None = None
    deletable: bool = False
    raw: dict[str, object] = field(default_factory=dict)


@dataclass
class Settings:
    is_admin: bool = False
    need_auth: bool = False
    show_ci: bool = False
    enable_ci: bool = False
    public: bool = True
    access_tokens: list[str] = field(default_factory=list)
    collaborators: list[dict[str, str]] = field(default_factory=list)
    environment: list[dict[str, str]] = field(default_factory=list)
    extra_tokens: list[dict[str, str]] = field(default_factory=list)
    raw: dict[str, object] = field(default_factory=dict)


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
        base_url: str = "https://jitpack.io",  # check:ignore E_HARDCODED_URL value=https://jitpack.io
        session_cookie: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """
        :param base_url: Base URL for JitPack.
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

        self._session: ClientSession | None = None

    async def __aenter__(self) -> "JitPackAPI":
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        del exc_type, exc_val, exc_tb
        if self._session and not self._session.closed:
            await self._session.close()

    #
    # Internal helpers
    #
    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        json_data: object | None = None,
    ) -> object:
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
        cookies: dict[str, str] = {}
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

        logger.debug(
            "Request: %s %s cookies=%s params=%s json_data=%s",
            method,
            url,
            cookies,
            params,
            json_data,
        )

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
            raise JitPackAuthError(f"Authentication/permission error (HTTP {status}). Response body: {body}")
        elif status == 404:
            raise JitPackNotFoundError(f"Resource not found (HTTP 404). Response body: {body}")
        else:
            raise JitPackAPIError(f"HTTP {status} error. Body: {body}")

    #
    # Public methods
    #
    async def get_refs(self, group: str, project: str) -> list[Ref]:
        """
        GET /api/refs/{group}/{project}

        :param group: e.g. "com.github.owner"
        :param project: e.g. "myproject"
        :return: A list of Ref objects (tags, branches, etc.)
        """
        path = f"/api/refs/{group}/{project}"
        data = await self._request("GET", path)
        data_dict = as_dict(data)
        if data_dict is None:
            raise JitPackAPIError(f"Unexpected refs response type: {type(data).__name__}")
        refs: list[Ref] = []

        # Expecting something like:  {"tags": [...], "branches": [...]}
        # Let's combine them or parse them separately.
        tags_raw = as_list(data_dict.get("tags")) or []
        branches_raw = as_list(data_dict.get("branches")) or []

        # We unify them as "Ref" objects.
        # The JS code suggests "tag_name" and "commit" for branches as well.
        for t in tags_raw:
            t_dict = as_dict(t)
            if t_dict is None:
                continue
            name = as_str(t_dict.get("tag_name")) or as_str(t_dict.get("name"), "unknown")
            commit = as_str(t_dict.get("commit"))[:7]
            refs.append(Ref(name=name, commit=commit))
        for b in branches_raw:
            b_dict = as_dict(b)
            if b_dict is None:
                continue
            name = as_str(b_dict.get("tag_name")) or as_str(b_dict.get("name"), "unknown")
            commit = as_str(b_dict.get("commit"))[:7]
            refs.append(Ref(name=name, commit=commit))

        return refs

    async def force_build(self, group: str, project: str, version: str) -> None:
        # We can force a build by sending a GET to the POM file URL.
        # This will trigger a new build for the specified version.
        # https://jitpack.io/com/github/wabbit-corp/kotlin-base58/1.1.0-SNAPSHOT/kotlin-base58-1.1.0-SNAPSHOT.pom

        assert group.startswith("com.github."), "Group must start with 'com.github.'"
        group = group[len("com.github.") :]

        path = f"/com/github/{group}/{project}/{version}/{project}-{version}.pom"
        # We need it to timeout quickly, so we don't wait for the response.
        # And we don't need cookies or JSON data.
        session = self._session
        if session is None:
            raise RuntimeError("ClientSession not initialized. Use `async with JitPackAPI(...) as api:`")
        try:
            async with session.request(
                "GET",
                f"{self.base_url}{path}",
                timeout=aiohttp.ClientTimeout(total=30.0),
            ) as resp:
                # We don't need to check the status, just log it.
                await self._raise_for_status(resp)
                logger.info(
                    "Forced build for: group=%s, project=%s, version=%s",
                    group,
                    project,
                    version,
                )
                time.sleep(5)
        except TimeoutError:
            logger.warning(
                "Timeout while forcing build for: group=%s, project=%s, version=%s",
                group,
                project,
                version,
            )
        except aiohttp.ClientError as e:
            logger.error(
                "Client error while forcing build for: group=%s, project=%s, version=%s. Error: %s",
                group,
                project,
                version,
                e,
            )
        except Exception as e:
            logger.error(
                "Unexpected error while forcing build for: group=%s, project=%s, version=%s. Error: %s",
                group,
                project,
                version,
                e,
            )
            raise

    def _get_cookies(self) -> dict[str, str]:
        # Prepare cookies
        cookies: dict[str, str] = {}
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

    def build_log_url(self, group: str, project: str, version: str) -> str:
        # We can get the build log by sending a GET to the build log URL.
        # https://jitpack.io/com/github/wabbit-corp/kotlin-base58/1.1.0-SNAPSHOT/build.log

        assert group.startswith("com.github."), "Group must start with 'com.github.'"
        group = group[len("com.github.") :]

        path = f"/com/github/{group}/{project}/{version}/build.log"
        return f"{self.base_url}{path}"

    async def get_build_log(self, group: str, project: str, version: str) -> str:
        # We can get the build log by sending a GET to the build log URL.
        # https://jitpack.io/com/github/wabbit-corp/kotlin-base58/1.1.0-SNAPSHOT/build.log

        assert group.startswith("com.github."), "Group must start with 'com.github.'"
        group = group[len("com.github.") :]

        path = f"/com/github/{group}/{project}/{version}/build.log"

        logger.info("Getting build log for: group=%s, project=%s, version=%s", group, project, version)

        session = self._session
        if session is None:
            raise RuntimeError("ClientSession not initialized. Use `async with JitPackAPI(...) as api:`")

        async with session.request(
            "GET",
            f"{self.base_url}{path}",
            cookies=self._get_cookies(),
            headers={"Accept": "text/plain"},
        ) as resp:
            await self._raise_for_status(resp)
            return await resp.text()

    async def get_commits(self, group: str, project: str, branch: str | None = None) -> list[Commit]:
        """
        GET /api/commits/{group}/{project}?branch=<branch>

        :param group: e.g. "com.github.owner"
        :param project: e.g. "myproject"
        :param branch: optional branch name
        :return: A list of Commit objects
        """
        path = f"/api/commits/{group}/{project}"
        params: dict[str, str] = {}
        if branch:
            params["branch"] = branch

        data = await self._request("GET", path, params=params)
        data_dict = as_dict(data)
        if data_dict is None:
            raise JitPackAPIError(f"Unexpected commits response type: {type(data).__name__}")
        commits_raw = as_list(data_dict.get("commits"))
        if commits_raw is None:
            raise JitPackAPIError("Unexpected commits payload shape")
        commits: list[Commit] = []

        for c in commits_raw:
            c_dict = as_dict(c)
            if c_dict is None:
                continue
            sha = as_str(c_dict.get("sha"))[:40]
            message = as_str(c_dict.get("message"))
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
        data_dict = as_dict(data)
        if data_dict is None:
            raise JitPackAPIError(f"Unexpected build info response type: {type(data).__name__}")

        # The JS code suggests possible fields:
        # { "status": "ok|Building|...", "ci": bool, "buildUrl": "...", "deletable": bool, ...}
        status_str = as_str(data_dict.get("status"), "unknown")
        try:
            status = BuildStatus(status_str)
        except ValueError:
            status = BuildStatus.UNKNOWN

        build = Build(
            version=version,
            status=status,
            ci=as_bool(data_dict.get("ci"), False),
            build_url=as_optional_str(data_dict.get("buildUrl")),
            deletable=as_bool(data_dict.get("deletable"), False),
            raw=data_dict,
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

    async def get_versions(self, group: str, project: str, query: str | None = None) -> list[Version]:
        """
        GET /api/versions/{group}/{project}?{query}

        :param group: e.g. "com.github.owner"
        :param project: e.g. "myproject"
        :param query: additional query, like 'reload' or other keys
        :return: A list of versions (string)
        """
        path = f"/api/versions/{group}/{project}"
        params: dict[str, str] = {}
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
        data_dict = as_dict(data)
        if data_dict is None:
            raise JitPackAPIError(f"Unexpected versions response type: {type(data).__name__}")
        grouped_data = as_dict(data_dict.get(group))
        if grouped_data is None:
            raise JitPackAPIError(f"Unexpected versions group payload type: {type(grouped_data).__name__}")
        project_data = as_dict(grouped_data.get(project))
        if project_data is None:
            raise JitPackAPIError(f"Unexpected versions project payload type: {type(project_data).__name__}")
        versions: list[Version] = []
        for version_obj in project_data.values():
            v_dict = as_dict(version_obj)
            if v_dict is None:
                continue
            status_str = as_str(v_dict.get("status"), "unknown")
            try:
                status = BuildStatus(status_str)
            except ValueError:
                status = BuildStatus.UNKNOWN

            version_name = as_str(v_dict.get("version"))
            if not version_name:
                continue
            is_tag_obj = v_dict.get("isTag")
            commit_obj = v_dict.get("commit")
            deletable_obj = v_dict.get("deletable")
            versions.append(
                Version(
                    status=status,
                    isTag=as_bool(is_tag_obj) if is_tag_obj is not None else None,
                    commit=as_optional_str(commit_obj),
                    deletable=as_bool(deletable_obj) if deletable_obj is not None else None,
                    version=version_name,
                    date=as_optional_str(v_dict.get("date")),
                )
            )
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
        data_dict = as_dict(data)
        if data_dict is None:
            raise JitPackAPIError(f"Unexpected settings response type: {type(data).__name__}")

        # Convert JSON into Settings data class
        s = Settings(
            is_admin=as_bool(data_dict.get("isAdmin"), False),
            need_auth=as_bool(data_dict.get("needAuth"), False),
            show_ci=as_bool(data_dict.get("showCI"), False),
            enable_ci=as_bool(data_dict.get("enableCI"), False),
            public=as_bool(data_dict.get("public"), True),
            access_tokens=as_string_list(data_dict.get("access_tokens")),
            collaborators=as_string_dict_list(data_dict.get("collaborators")),
            environment=as_string_dict_list(data_dict.get("environment")),
            extra_tokens=as_string_dict_list(data_dict.get("extraTokens")),
            raw=data_dict,
        )
        return s

    async def put_settings(self, group: str, project: str, new_settings: dict[str, object]) -> Settings:
        """
        PUT /api/settings/{group}/{project}

        :param group: e.g. "com.github.owner"
        :param project: e.g. "myproject"
        :param new_settings: dict with fields to update, e.g. {"enableCI": True}
        :return: Updated Settings object
        """
        path = f"/api/settings/{group}/{project}"
        data = await self._request("PUT", path, json_data=new_settings)
        data_dict = as_dict(data)
        if data_dict is None:
            raise JitPackAPIError(f"Unexpected updated settings response type: {type(data).__name__}")
        return Settings(
            is_admin=as_bool(data_dict.get("isAdmin"), False),
            need_auth=as_bool(data_dict.get("needAuth"), False),
            show_ci=as_bool(data_dict.get("showCI"), False),
            enable_ci=as_bool(data_dict.get("enableCI"), False),
            public=as_bool(data_dict.get("public"), True),
            access_tokens=as_string_list(data_dict.get("access_tokens")),
            collaborators=as_string_dict_list(data_dict.get("collaborators")),
            environment=as_string_dict_list(data_dict.get("environment")),
            extra_tokens=as_string_dict_list(data_dict.get("extraTokens")),
            raw=data_dict,
        )

    async def post_trial(self, git_owner_url: str, login: str, plan: str) -> dict[str, object]:
        """
        POST /api/service/trial?gitOwnerUrl=...&login=...&plan=...

        :param git_owner_url: e.g. "github owner URL"
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
        data_dict = as_dict(data)
        if data_dict is None:
            raise JitPackAPIError(f"Unexpected trial response type: {type(data).__name__}")
        return data_dict


#
# Example main usage for local testing
#
async def main() -> None:
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
            build = await api.get_build_info(group, project, versions[0].version)
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

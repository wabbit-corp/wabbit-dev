from typing import List, Any, Union, Dict
from dataclasses import dataclass

import asyncio, httpx
from httpx import AsyncClient

import requests
import semanticscholar.Paper
import json, yaml
import os, sys, asyncio, time
import logging
import argparse
import urllib.parse
import re
from textwrap import dedent, indent

import openai
import arxiv
import crossref.restful
import semanticscholar
from bs4 import BeautifulSoup
from enum import Enum

from sentence_transformers import SentenceTransformer, util


JSON = Any
# type JSON = Union[str, int, float, bool, None, Dict[str, JSON], List[JSON]]
# type JSONDict = Dict[str, JSON]
# type JSONArray = List[JSON]


class Source:
    # @property
    # def url(self) -> str | None: raise NotImplementedError()
    # @property
    # def title(self) -> str: raise NotImplementedError()
    # @property
    # def description(self) -> str | None: raise NotImplementedError()
    # @property
    # def snippets(self) -> List[str]: raise NotImplementedError()

    Web: type["WebSource"] = None  # type: ignore
    Arxiv: type["ArxivSource"] = None  # type: ignore
    CrossRef: type["CrossRefSource"] = None  # type: ignore
    SemanticScholar: type["SemanticScholarSource"] = None  # type: ignore


@dataclass
class WebSource(Source):
    source_id: str
    raw: Any
    title: str
    url: str
    description: str
    snippets: List[str]


@dataclass
class ArxivSource(Source):
    source_id: str
    raw: arxiv.Result

    @property
    def title(self) -> str:
        return self.raw.title

    @property
    def description(self) -> str | None:
        return self.raw.summary

    @property
    def snippets(self) -> List[str]:
        return []

    @property
    def url(self) -> str:
        return self.raw.pdf_url

    @property
    def arxiv_id(self) -> str:
        return self.raw.entry_id


@dataclass
class CrossRefSource(Source):
    source_id: str
    raw: JSON

    @property
    def title(self) -> str:
        l = self.raw.get("title", [])
        if len(l) > 0:
            return l[0]
        return "No Title"

    @property
    def description(self) -> str | None:
        return self.raw.get("abstract", None)

    @property
    def snippets(self) -> List[str]:
        return []

    @property
    def url(self) -> str | None:
        link_list = self.raw.get("link", [])
        return link_list[0]["URL"] if len(link_list) > 0 else None


@dataclass
class SemanticScholarSource(Source):
    source_id: str
    raw: semanticscholar.Paper

    @property
    def title(self) -> str:
        return self.raw.title

    @property
    def description(self) -> str | None:
        return self.raw.abstract

    @property
    def snippets(self) -> List[str]:
        return []

    @property
    def url(self) -> str:
        return self.raw.url


Source.Web = WebSource
Source.Arxiv = ArxivSource
Source.CrossRef = CrossRefSource
Source.SemanticScholar = SemanticScholarSource


@dataclass
class Query:
    query: str
    relevance: int

    @staticmethod
    def from_json(data: JSON) -> "Query":
        return Query(query=data["query"], relevance=data["relevance"])


def deduplicate_queries(queries: List[Query]) -> List[Query]:
    m: Dict[str, int] = {}
    for q in queries:
        qk = q.query.lower()
        if qk in m:
            m[qk] = min(m[qk], q.relevance)
        else:
            m[qk] = q.relevance
    return list(Query(query=k, relevance=v) for k, v in m.items())


async def get_search_queries(
    client: openai.AsyncClient, model: str, query: str, n_times: int = 3
) -> List[Query]:
    prompt = dedent(
        """
    I am researching '{query}' and I want to search for papers related to this topic.
    Please provide me queries that I can use to search for papers.
    Provide between 5-10 queries in the following JSON format:
    ```typescript
    interface Result {
        queries: Query[];
    }
    interface Query {
        query: string;
        // Estimate relevance to the Research Topic as a whole. Less specific queries should have lower relevance.
        relevance: number; // 0-100
    }
    ```
    """
    ).replace("{query}", query)

    queries: List[Query] = []

    # for _ in range(n_times):
    async def run():
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful research assistant."},
                {"role": "user", "content": prompt},
            ],
            top_p=0.95,
            response_format={"type": "json_object"},
        )

        new_queries = json.loads(response.choices[0].message.content)["queries"]

        queries.extend([Query.from_json(q) for q in new_queries])

    await asyncio.gather(*[run() for _ in range(n_times)])

    queries = deduplicate_queries(queries)
    return sorted(queries, key=lambda x: x.relevance, reverse=True)


async def get_arxiv_search_queries(
    client: openai.AsyncClient, model: str, query: str, n_times: int = 3
) -> List[Query]:
    prompt = dedent(
        """
    I am researching '{query}' (Research Topic) and I want to search for papers related to this topic.

    Please provide me SIMPLE and VERY SHORT search queries (1-3 words max) that I can use to search for papers.
    Provide between 5-10 queries in the following JSON format:
    ```typescript
    interface Result {
        queries: Query[];
    }
    interface Query {
        query: string;
        // Estimate relevance to the Research Topic as a whole. Less specific queries should have lower relevance.
        relevance: number; // 0-100
    }
    ```
    """
    ).replace("{query}", query)

    queries: List[Query] = []

    # for _ in range(n_times):
    async def run():
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful research assistant."},
                {"role": "user", "content": prompt},
            ],
            top_p=0.90,
            response_format={"type": "json_object"},
        )

        new_queries = json.loads(response.choices[0].message.content)["queries"]

        queries.extend([Query.from_json(q) for q in new_queries])

    await asyncio.gather(*[run() for _ in range(n_times)])

    queries = deduplicate_queries(queries)
    queries = [
        Query(query=q.query.strip().replace("-", " "), relevance=q.relevance)
        for q in queries
    ]
    return sorted(queries, key=lambda x: x.relevance, reverse=True)


async def brave_search(http_client: httpx.AsyncClient, q, api_key):
    # curl -s --compressed "https://api.search.brave.com/res/v1/web/search?q=brave+search" -H "Accept:
    #   application/json" -H "Accept-Encoding: gzip" -H "X-Subscription-Token: <YOUR_API_KEY>"
    url = f"https://api.search.brave.com/res/v1/web/search?q={urllib.parse.quote(q)}"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    response = await http_client.get(url, headers=headers)
    return response.json()


LAST_SCRAPERBEE_REQ = 0
CONCURRENT_SCRAPERBEE_REQ = 0


async def fetch_url(
    http_client: httpx.AsyncClient, url: str, scraperbee_key: str
) -> str | None:
    global LAST_SCRAPERBEE_REQ, CONCURRENT_SCRAPERBEE_REQ
    import random

    if url is None:
        return None
    while True:
        try:
            now = time.time()
            if now - LAST_SCRAPERBEE_REQ < 2 or CONCURRENT_SCRAPERBEE_REQ >= 5:
                delay = max(random.random() * 1.0, 2 - (now - LAST_SCRAPERBEE_REQ))
                await asyncio.sleep(delay)

            CONCURRENT_SCRAPERBEE_REQ += 1
            response = await http_client.get(
                url="https://app.scrapingbee.com/api/v1/",
                params={
                    "api_key": scraperbee_key,
                    "url": url,
                    "wait": "3000",
                },
            )
            LAST_REQ = time.time()
            break
        except Exception as e:
            logging.error(f"Failed to fetch URL: {url}, Error: {e}, {type(e)}")
            return None
        finally:
            CONCURRENT_SCRAPERBEE_REQ -= 1

    logger = logging.getLogger(__name__)

    if response.status_code != 200:
        logger.error(
            f"Failed to fetch URL: {url}, Status Code: {response.status_code}, Response: {response.text}"
        )
        return None

    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    for script in soup(["script", "style"]):
        script.extract()  # rip it out
    raw = soup.get_text()
    raw = re.sub(r"\s+", " ", raw)

    return raw


@dataclass
class ApiConfig:
    brave_key: str
    openai_key: str
    scraperbee_key: str


@dataclass
class ResultSource:
    title: str
    url: str
    relevance: int
    summary: str


@dataclass
class Result:
    sources: List[ResultSource]
    final_summary: str


class ResearcherMode:
    model: str
    long_queries: int
    short_queries: int
    arxiv_cutoff: int
    crossref_cutoff: int

    @dataclass
    class Fast:
        model: str = "gpt-4o-mini"
        long_queries: int = 1
        short_queries: int = 1
        arxiv_cutoff: int = 10
        crossref_cutoff: int = 10

    @dataclass
    class Balanced:
        model: str = "gpt-4o-mini"
        long_queries: int = 3
        short_queries: int = 3
        arxiv_cutoff: int = 25
        crossref_cutoff: int = 25

    @dataclass
    class Comprehensive:
        model: str = "gpt-4o"
        long_queries: int = 30
        short_queries: int = 30
        arxiv_cutoff: int = 50
        crossref_cutoff: int = 50


async def main():
    config = yaml.safe_load(open(".env.yml"))
    brave_key = config["BRAVE_KEY"]
    openai_key = config["OPENAI_KEY"]
    scraperbee_key = config["SCRAPERBEE_KEY"]

    mode = ResearcherMode.Balanced()

    # Set up the command line arguments
    parser = argparse.ArgumentParser()
    # <app> research <query>
    parser.add_argument("query", help="The query to search for")
    args = parser.parse_args()

    config = ApiConfig(
        brave_key=brave_key, openai_key=openai_key, scraperbee_key=scraperbee_key
    )

    await research(config, mode, args.query)


async def research(config: ApiConfig, mode: ResearcherMode, query: str) -> None:
    # await asyncio.sleep(60 * 1)
    # return Result(
    #     sources=[ResultSource(title="Title", url="URL", relevance=55, summary="Summary")],
    #     final_summary="Final Result"
    # )

    # Set up logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    async with httpx.AsyncClient(timeout=120) as http_client:
        # Set up the command line arguments
        parser = argparse.ArgumentParser()
        # <app> research <query>
        parser.add_argument("query", help="The query to search for")
        args = parser.parse_args()

        # Set up the query
        user_query = args.query
        #     user_query = '''
        # LLM agents as personal/executive assistants/secretaries that can schedule meetings, tasks, answer emails.
        # '''.strip()
        logger.info(f"Query: {user_query}")

        openai_client = openai.AsyncClient(
            api_key=config.openai_key, http_client=http_client
        )
        arxiv_client = arxiv.Client()
        # semantic_scholar_client = semanticscholar.AsyncSemanticScholar()

        logger.info("Getting search queries")

        # query = "automated winding process for fractional slot concentrated inner rotor motors, specifically for  traction motor applications"
        long_queries = await get_search_queries(
            openai_client, mode.model, user_query, n_times=3
        )
        logger.info(f"Longer Queries: {long_queries}")
        short_queries = await get_arxiv_search_queries(
            openai_client, mode.model, user_query, n_times=3
        )
        logger.info(f"Short Queries: {short_queries}")

        long_queries = long_queries[: mode.long_queries]
        short_queries = short_queries[: mode.short_queries]

        crossref_etiquette = crossref.restful.Etiquette(
            application_name="equoai-researcher",
            application_version="0.1",
            application_url="equo.ai",
            contact_email="davidhostler834@gmail.com",
        )
        crossref_works = crossref.restful.Works(etiquette=crossref_etiquette)

        ALL_SOURCES: Dict[str, Source] = {}

        def next_source_id(prefix):
            index = 1
            while True:
                source_id = f"{prefix}-{index}"
                if source_id not in ALL_SOURCES:
                    return source_id
                index += 1

        logger.info("Searching on ArXiv")
        for q in short_queries:
            search = arxiv.Search(
                query=f'"{q.query}"',
                max_results=mode.arxiv_cutoff,
                sort_by=arxiv.SortCriterion.Relevance,
            )
            time.sleep(4)

            results = arxiv_client.results(search)
            for r in results:
                source_id = next_source_id("arx")
                arxiv_source = Source.Arxiv(source_id=source_id, raw=r)
                # If there is already an arXiv source with the same id, skip
                if any(
                    x.arxiv_id == arxiv_source.arxiv_id
                    for x in ALL_SOURCES.values()
                    if isinstance(x, Source.Arxiv)
                ):
                    continue
                ALL_SOURCES[source_id] = arxiv_source
                print(f"Added {r.title}")

        logger.info("Searching using Brave Search")
        NON_AUTHORITATIVE_SOURCES = [
            "blogspot.com",
            "wordpress.com",
            "reddit.com",
            "quora.com",
            "cnn.com",
            "bbc.com",
            "foxnews.com",
            "nytimes.com",
            "huffpost.com",
            "buzzfeed.com",
            "tmz.com",
            "about.com",
            "ehow.com",
            "medium.com",
            "facebook.com",
            "twitter.com",
            "instagram.com",
            "linkedin.com",
            "forbes.com",
            "entrepreneur.com",
            "pressrelease.com",
            "prnewswire.com",
        ]
        for q in long_queries:
            results = await brave_search(http_client, q.query, config.brave_key)
            with open("brave_search.json", "wt+") as f:
                print(json.dumps(results, indent=2), file=f)
            for result in results.get("web", {}).get("results", []):
                if any(x in result["url"] for x in NON_AUTHORITATIVE_SOURCES):
                    continue
                # If there is already a source with the same URL, skip
                if any(x.url == result["url"] for x in ALL_SOURCES.values()):
                    continue

                source_id = next_source_id("web")
                ALL_SOURCES[source_id] = Source.Web(
                    source_id=source_id,
                    raw=result,
                    title=result["title"],
                    url=result["url"],
                    description=result["description"],
                    snippets=result.get("extra_snippets", []),
                )
                print(f"Added {result['title']}")

        logger.info("Searching using CrossRef")
        for q in long_queries:
            result = crossref_works.query(q.query)
            for item in result.sample(mode.crossref_cutoff):
                # If there is already a source with the same doi, skip
                if any(
                    x.raw.get("DOI", -1) == item.get("DOI", -2)
                    for x in ALL_SOURCES.values()
                    if isinstance(x, Source.CrossRef)
                ):
                    continue
                source_id = next_source_id("cr")
                source = Source.CrossRef(source_id=source_id, raw=item)
                ALL_SOURCES[source_id] = source
                logger.info(f"Added {source.title}")

        # logger.info("Searching using Semantic Scholar")
        # for query in long_queries:
        #     limit = 10 if TEST_MODE else 50
        #     result = await semantic_scholar_client.search_paper(query, limit=limit)
        #     for item in result.items:
        #         source_id = next_source_id('ss')
        #         source = Source.SemanticScholar(source_id=source_id, raw=item)
        #         ALL_SOURCES[source_id] = source
        #         logger.info(f"Added {source.title}")

        SOURCE_RELEVANCE = {}
        ALL_SOURCES_LIST = list(ALL_SOURCES.values())
        logger.info(f"Total Sources: {len(ALL_SOURCES_LIST)}")

        async def process_batch(batch: List[Source]) -> JSON:
            # logger.info(f"Estimating Relevance of Batch: {batch_start+1}-{batch_start+len(batch)}")

            def format_source(index: int, source: Source) -> str:
                result = f"{index+1}. {source.title}"
                description = source.description
                snippets = source.snippets

                if description is not None:
                    result += f"\n   Abstract/Description: {description}"
                if len(snippets) > 0:
                    result += f"\n   Snippets:\n"
                    for snippet in snippets:
                        result += f"\n      - {snippet}"
                return result

            papers_list_formatted = "\n".join(
                [format_source(i, source) for i, source in enumerate(batch)]
            )

            prompt = (
                dedent(
                    """
                I am researching <research_topic>{query}</research_topic> and I want to search for papers related to this topic.
                I found the following papers/articles:
                {papers}

                Which of these papers do you think would be most helpful for my research?
                Provide your response in the following JSON format:
                ```typescript
                interface Result {
                    papers: PaperRelevance[];
                }
                interface PaperRelevance {
                    // Paper number in the list.
                    num: number;
                    // The title of the paper.
                    title: string;
                    // The relevance of the paper to the research_topic (1-5)
                    // 1: Not relevant at all
                    // 2: Possibly relevant
                    // 3: Likely relevant
                    // 4: Very relevant
                    // 5: Extremely relevant
                    relevance: number;
                }
                ```
                """
                )
                .replace("{query}", user_query)
                .replace("{papers}", papers_list_formatted)
            )

            response = await openai_client.chat.completions.create(
                model=mode.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful research assistant.",
                    },
                    {"role": "user", "content": prompt},
                ],
                top_p=0.95,
                response_format={"type": "json_object"},
            )

            response_content = response.choices[0].message.content
            assert response_content is not None
            response_json = json.loads(response_content)
            batch_results = response_json["papers"]

            for result in batch_results:
                source = batch[result["num"] - 1]
                # Check if title is correct
                source_title = source.title.lower()
                source_title = re.sub(r"\W+", " ", source_title)
                source_title = re.sub(r"\s+", " ", source_title)
                source_title = source_title.strip()

                result_title = result.get("title", "").lower()
                result_title = re.sub(r"\W+", " ", result_title)
                result_title = re.sub(r"\s+", " ", result_title)
                result_title = result_title.strip()

                good_match = False
                if source_title == result_title:
                    good_match = True
                elif len(source_title) > 10 and source_title in result_title:
                    good_match = True
                elif len(result_title) > 10 and result_title in source_title:
                    good_match = True

                if not good_match:
                    logger.error(f"Title mismatch: {source.title} != {result['title']}")

                SOURCE_RELEVANCE[source.source_id] = int(result["relevance"])

        # for batch_start in range(0, len(ALL_SOURCES_LIST), 20):
        #     batch = ALL_SOURCES_LIST[batch_start:batch_start+20]

        await asyncio.gather(
            *[
                process_batch(ALL_SOURCES_LIST[i : i + 20])
                for i in range(0, len(ALL_SOURCES_LIST), 20)
            ]
        )

        SOURCE_SUMMARIES = {}

        with open("source_summaries.json", "wt+") as f_summaries:

            # for source_id, relevance in SOURCE_RELEVANCE.items():
            async def process_source(source_id, relevance):
                if relevance <= 3:
                    return

                source = ALL_SOURCES[source_id]
                logger.info(f"{source_id}: {relevance} - {source.title}")

                if isinstance(source, Source.Web):
                    url = source.url
                    if url is None:
                        logger.info("No URL")
                        return

                    abstract = await fetch_url(
                        http_client, source.url, config.scraperbee_key
                    )

                    if abstract is not None:
                        logger.info(f"Full Text: {abstract[:300]}")
                else:
                    abstract = source.description
                    if abstract is not None:
                        logger.info(f"Abstract: {abstract[:300]}")
                    else:
                        abstract = await fetch_url(
                            http_client, source.url, config.scraperbee_key
                        )
                        if abstract is not None:
                            logger.info(f"Full Text: {abstract[:300]}")

                if abstract is None:
                    logger.info("No Abstract")
                    return

                prompt = (
                    dedent(
                        """
                    Information Need/Query: <research_topic>{query}</research_topic>

                    I am researching the above topic and I want to understand the content of the following paper/article with respect to my research topic.

                    Here is the title of the paper/article: {title}
                    """
                    )
                    .replace("{query}", user_query)
                    .replace("{title}", source.title)
                )

                if len(abstract) > 50000:
                    abstract = abstract[:50000]

                if abstract is not None:
                    prompt += (
                        f"\n\nText of the paper/article:\n{indent(abstract, '    ')}"
                    )
                if len(source.snippets) > 0:
                    prompt += "\n\nOther Snippets:\n"
                    for snippet in source.snippets:
                        prompt += f"\n{indent(snippet, '    ')}"

                prompt += "\n\n"
                prompt += "Please extract *ALL* information DIRECTLY RELEVANT to the query from this paper/article.".replace(
                    "{query}", user_query
                )

                prompt += "\n\n"
                prompt += "Please provide your response in the following JSON format:"
                prompt += dedent(
                    """
                    ```typescript
                    interface Result {
                        // Does the paper/article contain *any* relevant information?
                        has_relevant_information: boolean;

                        // The extracted information from the paper/article.

                        // Include *ALL* information that has prime relevance to the query.
                        // If no information of primary relevance can extracted, set to null.
                        primary_relevant_information: string | null;

                        // Include *ALL* information that has secondary relevance to the query.
                        // If no information of secondary relevance can extracted, set to null.
                        secondary_relevant_information: string | null;

                        // Summarize *ALL* information that has tertiary relevance to the query.
                        // If no information of tertiary relevance can extracted, set to null.
                        tertiary_relevance_summary: string | null;

                        // Summarize *ALL* information that has peripheral relevance to the query.
                        // If no information of tertiary relevance can extracted, set to null.
                        peripheral_relevance_summary: string | null;


                        // Relevance metric.
                        // 76-100: Primary Relevance - Directly and comprehensively addresses the main focus topic with a high degree of detail and specificity.
                        // 51-75: Secondary Relevance - Discusses related technologies or broader applications that can enhance or inform the primary focus.
                        // 26-50: Tertiary Relevance - Provides foundational knowledge, contextual information, or overall advancements relevant to the primary domain.
                        // 1-25: Peripheral Relevance - Offers useful insights indirectly related to the main topic (e.g., ethical, social, historical, legal considerations).
                        // 0: No Relevance - Completely unrelated to the main topic.
                        relevance_score: number;

                        // Specificity score.
                        // 76-100: Highly Specific - Provides detailed, specific, and focused information directly related to the query.
                        // 51-75: Moderately Specific - Offers information that is relevant but may lack some specificity or detail.
                        // 26-50: Somewhat Specific - Contains information that is tangentially related to the query but lacks specificity or detail.
                        // 1-25: Not Specific - Contains information that is too general or unrelated to the query.
                        // 0: No Information - Unable to extract any relevant information.
                        specificity_score: number;
                    }
                    ```
                    """
                )

                retry_count = 0
                response = None
                while True:
                    try:
                        response = await openai_client.chat.completions.create(
                            model=mode.model,
                            messages=[
                                {
                                    "role": "system",
                                    "content": "You are a helpful research assistant.",
                                },
                                {"role": "user", "content": prompt},
                            ],
                            top_p=0.90,
                            response_format={"type": "json_object"},
                        )
                        break
                    except openai.OpenAIError as e:
                        retry_count += 1
                        if retry_count >= 3:
                            response = None
                            break
                        logger.error(f"Error: {e}")
                        time.sleep(30)

                if response is None:
                    logger.error("Failed to get response")
                    return

                summary = response.choices[0].message.content
                logger.info(f"Summary: {summary}")

                summary_json = json.loads(summary)
                if not summary_json.get("has_relevant_information", True):
                    logger.info("No relevant information")
                    return

                relevance_score = summary_json.get("relevance_score", 0)
                if relevance_score <= 25:
                    logger.info("Not relevant")
                    return

                specificity_score = summary_json.get("specificity_score", 0)
                if specificity_score <= 25:
                    logger.info("Not specific")
                    return

                relevance_flag = summary_json.get("relevance", None)

                primary_relevance_summary = summary_json.get(
                    "primary_relevant_information", None
                )
                if primary_relevance_summary is None:
                    logger.info("No relevant information")
                    return
                secondary_relevance_summary = summary_json.get(
                    "secondary_relevant_information", None
                )
                tertiary_relevance_summary = summary_json.get(
                    "tertiary_relevance_summary", None
                )
                peripheral_relevance_summary = summary_json.get(
                    "peripheral_relevance_summary", None
                )

                SOURCE_SUMMARIES[source_id] = summary

                relevance = SOURCE_RELEVANCE[source_id]
                source = ALL_SOURCES[source_id]

                print(
                    json.dumps(
                        {
                            "type": source.__class__.__name__,
                            "source_id": source_id,
                            "relevance_flag": relevance_flag,
                            "title_relevance": relevance,
                            "relevance": relevance_score,
                            "specificity": specificity_score,
                            "title": source.title,
                            "url": source.url if hasattr(source, "url") else "",
                            "summary": primary_relevance_summary,
                            "secondary_summary": secondary_relevance_summary,
                            "tertiary_summary": tertiary_relevance_summary,
                            "peripheral_summary": peripheral_relevance_summary,
                        }
                    ),
                    file=f_summaries,
                )
                f_summaries.flush()

            await asyncio.gather(
                *[
                    process_source(source_id, relevance)
                    for source_id, relevance in SOURCE_RELEVANCE.items()
                ]
            )


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

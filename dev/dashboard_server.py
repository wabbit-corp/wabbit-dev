from __future__ import annotations

import argparse
from datetime import UTC, datetime
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import signal
import threading
from types import FrameType
from urllib.parse import unquote, urlparse

from dev.dashboard_backend import DashboardCoordinator, DashboardWorkspaceState
from dev.json_types import JSONObject
from dev.service_support import DashboardPid, remove_dashboard_pid, service_paths_for_workspace, write_dashboard_pid

_SERVER_NAME = "dev-dashboard/1"
_LOCAL_HOSTS = {"127.0.0.1", "localhost"}


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _html_shell(snapshot: DashboardWorkspaceState, *, session_token: str) -> str:
    initial_state = json.dumps(snapshot.to_json(), separators=(",", ":"))
    session_token_json = json.dumps(session_token)
    workspace_title = html.escape(snapshot.workspace_name)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>dev dashboard · {workspace_title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4efe5;
      --surface: rgba(255, 252, 246, 0.92);
      --surface-strong: #fffaf0;
      --ink: #1c1b19;
      --muted: #6f685c;
      --border: rgba(92, 80, 63, 0.18);
      --accent: #0f766e;
      --warn: #b45309;
      --error: #b91c1c;
      --ok: #166534;
      --shadow: 0 18px 45px rgba(62, 45, 22, 0.12);
      --mono: "SFMono-Regular", "SF Mono", Menlo, Consolas, monospace;
      --sans: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      font-family: var(--sans);
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(15, 118, 110, 0.08), transparent 32rem),
        radial-gradient(circle at top right, rgba(180, 83, 9, 0.08), transparent 28rem),
        linear-gradient(180deg, #f8f3ea, var(--bg));
    }}
    header {{
      padding: 1.4rem 1.6rem 1rem;
      border-bottom: 1px solid var(--border);
      background: rgba(255, 250, 240, 0.84);
      backdrop-filter: blur(10px);
      position: sticky;
      top: 0;
      z-index: 20;
    }}
    h1 {{
      margin: 0;
      font-size: 1.4rem;
      letter-spacing: -0.02em;
    }}
    .subtitle {{
      color: var(--muted);
      margin-top: 0.25rem;
      font-size: 0.95rem;
    }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      margin-top: 1rem;
      align-items: center;
    }}
    .toolbar input[type="search"] {{
      min-width: 18rem;
      padding: 0.7rem 0.8rem;
      border-radius: 0.7rem;
      border: 1px solid var(--border);
      background: var(--surface-strong);
      color: var(--ink);
    }}
    .toolbar select, .toolbar button {{
      padding: 0.7rem 0.85rem;
      border-radius: 0.7rem;
      border: 1px solid var(--border);
      background: var(--surface-strong);
      color: var(--ink);
      cursor: pointer;
    }}
    .toolbar label {{
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      color: var(--muted);
      font-size: 0.95rem;
    }}
    main {{
      padding: 1.2rem 1.4rem 2rem;
    }}
    .summary-grid {{
      display: grid;
      gap: 0.9rem;
      grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
      margin-bottom: 1rem;
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 1rem;
      box-shadow: var(--shadow);
      padding: 1rem 1.05rem;
    }}
    .card-label {{
      color: var(--muted);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .card-value {{
      margin-top: 0.35rem;
      font-size: 1.5rem;
      font-weight: 700;
    }}
    .table-wrap {{
      overflow: auto;
      border: 1px solid var(--border);
      border-radius: 1rem;
      box-shadow: var(--shadow);
      background: var(--surface);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 1080px;
    }}
    thead th {{
      position: sticky;
      top: 0;
      background: rgba(255, 250, 240, 0.98);
      text-align: left;
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      padding: 0.9rem 0.85rem;
      border-bottom: 1px solid var(--border);
    }}
    tbody td {{
      vertical-align: top;
      padding: 0.85rem;
      border-top: 1px solid rgba(92, 80, 63, 0.12);
    }}
    tbody tr.clean {{
      background: rgba(255, 255, 255, 0.22);
    }}
    tbody tr.dirty {{
      background: rgba(250, 204, 21, 0.08);
    }}
    tbody tr.error {{
      background: rgba(185, 28, 28, 0.08);
    }}
    .repo-name {{
      font-weight: 700;
      font-size: 1rem;
    }}
    .secondary {{
      color: var(--muted);
      font-size: 0.86rem;
      margin-top: 0.2rem;
      line-height: 1.35;
      word-break: break-word;
    }}
    .stack {{
      display: grid;
      gap: 0.35rem;
    }}
    .badge-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      border-radius: 999px;
      border: 1px solid var(--border);
      padding: 0.22rem 0.55rem;
      font-size: 0.78rem;
      font-weight: 600;
      white-space: nowrap;
      background: rgba(255, 255, 255, 0.74);
    }}
    button.badge {{
      font: inherit;
      cursor: pointer;
    }}
    .badge.ok {{
      color: var(--ok);
      border-color: rgba(22, 101, 52, 0.24);
      background: rgba(22, 101, 52, 0.09);
    }}
    .badge.warn {{
      color: var(--warn);
      border-color: rgba(180, 83, 9, 0.25);
      background: rgba(180, 83, 9, 0.09);
    }}
    .badge.error {{
      color: var(--error);
      border-color: rgba(185, 28, 28, 0.25);
      background: rgba(185, 28, 28, 0.09);
    }}
    .badge.running {{
      color: var(--accent);
      border-color: rgba(15, 118, 110, 0.25);
      background: rgba(15, 118, 110, 0.09);
    }}
    .badge.muted {{
      color: var(--muted);
    }}
    .badge.active {{
      box-shadow: inset 0 0 0 1px rgba(15, 118, 110, 0.25);
    }}
    .mono {{
      font-family: var(--mono);
    }}
    .details-panel {{
      margin-top: 0.45rem;
      padding: 0.55rem 0.75rem;
      border-left: 3px solid rgba(15, 118, 110, 0.22);
      background: rgba(255, 255, 255, 0.36);
      border-radius: 0.6rem;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.32rem;
      align-items: center;
    }}
    .actions button {{
      padding: 0.35rem 0.56rem;
      border-radius: 0.65rem;
      border: 1px solid var(--border);
      background: var(--surface-strong);
      color: var(--ink);
      cursor: pointer;
      font-size: 0.8rem;
    }}
    .actions button:hover {{
      border-color: rgba(15, 118, 110, 0.35);
    }}
    .actions button:disabled {{
      opacity: 0.55;
      cursor: default;
    }}
    .action-menu {{
      position: relative;
      display: inline-block;
    }}
    .action-menu > summary {{
      list-style: none;
      padding: 0.35rem 0.56rem;
      border-radius: 0.65rem;
      border: 1px solid var(--border);
      background: var(--surface-strong);
      color: var(--ink);
      cursor: pointer;
      font-size: 0.8rem;
      user-select: none;
    }}
    .action-menu > summary::-webkit-details-marker {{
      display: none;
    }}
    .action-menu[open] > summary {{
      border-color: rgba(15, 118, 110, 0.35);
    }}
    .action-menu-panel {{
      position: absolute;
      top: calc(100% + 0.35rem);
      right: 0;
      z-index: 30;
      display: grid;
      gap: 0.3rem;
      min-width: 8rem;
      padding: 0.45rem;
      border: 1px solid var(--border);
      border-radius: 0.75rem;
      background: rgba(255, 250, 240, 0.98);
      box-shadow: var(--shadow);
    }}
    .action-menu-panel button {{
      width: 100%;
      text-align: left;
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    .empty {{
      padding: 2rem;
      color: var(--muted);
      text-align: center;
    }}
    .status-line {{
      color: var(--muted);
      font-size: 0.9rem;
      margin-top: 0.55rem;
    }}
    @media (max-width: 960px) {{
      header {{
        position: static;
      }}
      .toolbar {{
        align-items: stretch;
      }}
      .toolbar input[type="search"] {{
        min-width: 0;
        width: 100%;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>dev dashboard</h1>
    <div class="subtitle" id="workspace-caption"></div>
    <div class="toolbar">
      <input id="search-input" type="search" placeholder="Filter repos, projects, or paths">
      <select id="sort-select">
        <option value="dirty-age">Sort: oldest dirty first</option>
        <option value="release-risk">Sort: release attention first</option>
        <option value="name">Sort: name</option>
      </select>
      <label><input id="dirty-only" type="checkbox"> Dirty only</label>
      <label><input id="publishable-only" type="checkbox"> Publishable only</label>
      <label><input id="attention-only" type="checkbox"> Needs attention only</label>
      <button id="refresh-button" type="button">Refresh now</button>
    </div>
    <div class="status-line" id="status-line"></div>
  </header>
  <main>
    <section class="summary-grid" id="summary-grid"></section>
    <section class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Repo</th>
            <th>Dirty</th>
            <th>Tracking</th>
            <th>Release</th>
            <th>GitHub</th>
            <th>Health</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody id="repo-body"></tbody>
      </table>
      <div class="empty" id="empty-state" hidden>No repos matched the current filters.</div>
    </section>
  </main>
  <script>
    const initialState = {initial_state};
    const dashboardToken = {session_token_json};
    let currentState = initialState;
    let refreshInFlight = false;
    const expandedReleaseDetails = new Set();

    function escapeHtml(value) {{
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }}

    function formatTimestamp(value) {{
      if (!value) {{
        return "—";
      }}
      return new Intl.DateTimeFormat([], {{
        dateStyle: "medium",
        timeStyle: "medium",
      }}).format(new Date(value));
    }}

    function formatAge(value) {{
      if (!value) {{
        return "—";
      }}
      const deltaSeconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
      const days = Math.floor(deltaSeconds / 86400);
      const hours = Math.floor((deltaSeconds % 86400) / 3600);
      const minutes = Math.floor((deltaSeconds % 3600) / 60);
      if (days > 0) {{
        return `${{days}}d ${{hours}}h`;
      }}
      if (hours > 0) {{
        return `${{hours}}h ${{minutes}}m`;
      }}
      return `${{minutes}}m`;
    }}

    function badgeClass(status) {{
      switch (status) {{
        case "ok":
        case "success":
        case "published":
          return "ok";
        case "warn":
        case "warning":
        case "skipped":
        case "missing":
          return "warn";
        case "error":
          return "error";
        case "running":
          return "running";
        default:
          return "muted";
      }}
    }}

    function commandBadge(label, command) {{
      if (!command) {{
        return `<span class="badge muted">${{escapeHtml(label)}} · —</span>`;
      }}
      const titleParts = [command.summary || label];
      if (command.checkedAt) {{
        titleParts.push(`checked ${{formatTimestamp(command.checkedAt)}}`);
      }}
      if (command.detail) {{
        titleParts.push(command.detail);
      }}
      return `<span class="badge ${{badgeClass(command.status)}}" title="${{escapeHtml(titleParts.join(" · "))}}">${{escapeHtml(label)}} · ${{escapeHtml(command.status)}}</span>`;
    }}

    function backupBadge(backup) {{
      if (!backup) {{
        return `<span class="badge muted">backup · —</span>`;
      }}
      const effectiveTime = backup.successAt || backup.finishedAt || backup.attemptedAt;
      const titleParts = [];
      if (backup.status) {{
        titleParts.push(`status ${{backup.status}}`);
      }}
      if (backup.targetName) {{
        titleParts.push(`target ${{backup.targetName}}`);
      }}
      if (backup.snapshotId) {{
        titleParts.push(`snapshot ${{backup.snapshotId}}`);
      }}
      if (effectiveTime) {{
        titleParts.push(`at ${{formatTimestamp(effectiveTime)}}`);
      }}
      if (backup.message) {{
        titleParts.push(backup.message);
      }}
      let label = "recorded";
      if (backup.status === "error") {{
        label = "failed";
      }} else if (effectiveTime) {{
        label = formatAge(effectiveTime);
      }}
      return `<span class="badge ${{badgeClass(backup.status || "muted")}}" title="${{escapeHtml(titleParts.join(" · "))}}">backup · ${{escapeHtml(label)}}</span>`;
    }}

    function releaseDetailKey(repoName, projectId) {{
      return `${{repoName}}::${{projectId}}`;
    }}

    function repoNeedsAttention(repo) {{
      if (repo.monitor.error) {{
        return true;
      }}
      if (repo.monitor.dirty) {{
        return true;
      }}
      if (repo.backup && repo.backup.status === "error") {{
        return true;
      }}
      const healthCommands = [repo.spotCheck, repo.docsCheck, repo.docsSnippets, repo.checkRun, repo.releaseVerify, repo.build];
      if (healthCommands.some((command) => command && (command.status === "error" || command.status === "warning"))) {{
        return true;
      }}
      if (repo.github && repo.github.error) {{
        return true;
      }}
      return repo.releaseProjects.some((project) =>
        (project.registryStatuses || []).some((registry) => registry.status === "warn" || registry.status === "error")
        || (project.commitsAfterTag || 0) > 0
        || (project.unpushedCommits || 0) > 0
        || project.dirty
        || project.diagnostics.length > 0
      );
    }}

    function releaseRiskScore(repo) {{
      let score = 0;
      if (repo.monitor.dirty) {{
        score += 10;
      }}
      if (repo.backup && repo.backup.status === "error") {{
        score += 6;
      }}
      for (const project of repo.releaseProjects) {{
        for (const registry of (project.registryStatuses || [])) {{
          if (registry.status === "error") {{
            score += 12;
          }} else if (registry.status === "warn") {{
            score += 8;
          }}
        }}
        score += (project.commitsAfterTag || 0) * 2;
        score += (project.unpushedCommits || 0) * 2;
        score += project.dirty ? 5 : 0;
        score += project.diagnostics.length;
      }}
      for (const command of [repo.spotCheck, repo.docsCheck, repo.docsSnippets, repo.checkRun, repo.releaseVerify, repo.build]) {{
        if (!command) {{
          continue;
        }}
        if (command.status === "error") {{
          score += 6;
        }} else if (command.status === "warning") {{
          score += 3;
        }}
      }}
      if (repo.github && repo.github.ciStatus && repo.github.ciStatus !== "success") {{
        score += 4;
      }}
      return score;
    }}

    function dirtySortValue(repo) {{
      if (!repo.monitor.dirty) {{
        return Number.MAX_SAFE_INTEGER;
      }}
      if (!repo.monitor.dirtySince) {{
        return Number.MAX_SAFE_INTEGER - 1;
      }}
      return new Date(repo.monitor.dirtySince).getTime();
    }}

    function repoMatchesSearch(repo, query) {{
      if (!query) {{
        return true;
      }}
      const haystack = [
        repo.name,
        repo.path,
        repo.repoId || "",
        ...(repo.projectIds || []),
        ...(repo.publishableProjectIds || []),
        ...(repo.docsProjectIds || []),
      ].join(" ").toLowerCase();
      return haystack.includes(query);
    }}

    function visibleRepos(state) {{
      const query = document.getElementById("search-input").value.trim().toLowerCase();
      const dirtyOnly = document.getElementById("dirty-only").checked;
      const publishableOnly = document.getElementById("publishable-only").checked;
      const attentionOnly = document.getElementById("attention-only").checked;
      const sortMode = document.getElementById("sort-select").value;

      const repos = state.repos.filter((repo) => {{
        if (dirtyOnly && !repo.monitor.dirty) {{
          return false;
        }}
        if (publishableOnly && (!repo.publishableProjectIds || repo.publishableProjectIds.length === 0)) {{
          return false;
        }}
        if (attentionOnly && !repoNeedsAttention(repo)) {{
          return false;
        }}
        return repoMatchesSearch(repo, query);
      }});

      repos.sort((left, right) => {{
        if (sortMode === "name") {{
          return left.name.localeCompare(right.name);
        }}
        if (sortMode === "release-risk") {{
          const riskDelta = releaseRiskScore(right) - releaseRiskScore(left);
          if (riskDelta !== 0) {{
            return riskDelta;
          }}
          return left.name.localeCompare(right.name);
        }}
        const dirtyDelta = dirtySortValue(left) - dirtySortValue(right);
        if (dirtyDelta !== 0) {{
          return dirtyDelta;
        }}
        return left.name.localeCompare(right.name);
      }});
      return repos;
    }}

    function renderSummary(state) {{
      const cards = [
        ["Dirty repos", `${{state.dirtyRepoCount}} / ${{state.repos.length}}`],
        ["Publishable repos", String(state.publishableRepoCount)],
        ["Last update", formatTimestamp(state.updatedAt)],
        ["Polling interval", `${{state.intervalSeconds}}s`],
      ];
      document.getElementById("summary-grid").innerHTML = cards.map(([label, value]) => `
        <div class="card">
          <div class="card-label">${{escapeHtml(label)}}</div>
          <div class="card-value">${{escapeHtml(value)}}</div>
        </div>
      `).join("");
      document.getElementById("workspace-caption").textContent = `${{state.workspaceName}} · ${{state.workspaceRoot}}`;
      document.getElementById("status-line").textContent = `Showing ${{visibleRepos(state).length}} repos · last refreshed ${{formatTimestamp(state.updatedAt)}}`;
    }}

    function renderRepo(repo) {{
      const rowClass = repo.monitor.error ? "error" : (repo.monitor.dirty ? "dirty" : "clean");
      const monitor = repo.monitor;
      const counts = `${{monitor.stagedCount}} staged · ${{monitor.unstagedCount}} unstaged · ${{monitor.untrackedCount}} untracked`;
      const tracking = monitor.upstreamName
        ? `${{monitor.branchName || "HEAD"}} vs ${{monitor.upstreamName}} · ahead ${{monitor.aheadCount || 0}} · behind ${{monitor.behindCount || 0}}`
        : `${{monitor.branchName || "HEAD"}} · no upstream`;
      const backupBlock = backupBadge(repo.backup);
      const githubBlocks = [];
      if (repo.github && repo.github.ciUrl && repo.github.ciName) {{
        githubBlocks.push(`<a href="${{escapeHtml(repo.github.ciUrl)}}" target="_blank" rel="noreferrer noopener">${{escapeHtml(repo.github.ciName)}}</a>`);
      }}
      if (repo.github && repo.github.ciStatus) {{
        githubBlocks.push(`<span class="badge ${{badgeClass(repo.github.ciStatus)}}">CI · ${{escapeHtml(repo.github.ciStatus)}}</span>`);
      }}
      if (repo.github && repo.github.latestReleaseUrl && repo.github.latestReleaseTag) {{
        githubBlocks.push(`<a href="${{escapeHtml(repo.github.latestReleaseUrl)}}" target="_blank" rel="noreferrer noopener">Release · ${{escapeHtml(repo.github.latestReleaseTag)}}</a>`);
      }}
      if (repo.github && repo.github.error) {{
        githubBlocks.push(`<div class="secondary">${{escapeHtml(repo.github.error)}}</div>`);
      }}

      const releaseBlocks = repo.releaseProjects.length === 0
        ? ['<span class="secondary">No publishable projects</span>']
        : repo.releaseProjects.map((project) => {{
            const gitBits = [
              project.latestTag ? `tag ${{project.latestTag}}` : "tag —",
              `+${{project.commitsAfterTag ?? "?"}} commits`,
              `unpushed ${{project.unpushedCommits ?? "?"}}`,
              project.dirty ? "dirty" : "clean",
            ].join(" · ");
            const registryBadges = (project.registryStatuses || []).length === 0
              ? ['<span class="badge muted">no registry</span>']
              : (project.registryStatuses || []).map((registry) => {{
                  const detailKey = releaseDetailKey(repo.name, `${{project.projectId}}::${{registry.name}}`);
                  const detailExpanded = expandedReleaseDetails.has(detailKey);
                  return `
                    <button type="button" class="badge badge-button ${{badgeClass(registry.status)}} ${{detailExpanded ? "active" : ""}}" data-release-detail-toggle="${{escapeHtml(detailKey)}}" aria-expanded="${{detailExpanded ? "true" : "false"}}">
                      ${{escapeHtml(registry.name)}} · ${{escapeHtml(registry.status)}}
                    </button>
                  `;
                }});
            const detailBlocks = (project.registryStatuses || []).flatMap((registry) => {{
              const detailKey = releaseDetailKey(repo.name, `${{project.projectId}}::${{registry.name}}`);
              const detailExpanded = expandedReleaseDetails.has(detailKey);
              if (!detailExpanded) {{
                return [];
              }}
              const detailLines = [
                `package: ${{registry.package}}`,
                `current: ${{registry.currentVersion || "?"}}`,
                `latest: ${{registry.latest || "none"}}`,
                gitBits,
              ];
              for (const diagnostic of (registry.diagnostics || [])) {{
                detailLines.push(diagnostic);
              }}
              for (const diagnostic of (project.diagnostics || [])) {{
                detailLines.push(diagnostic);
              }}
              return [`
                <div class="details-panel">
                  <div class="secondary">${{detailLines.map(escapeHtml).join("<br>")}}</div>
                </div>
              `];
            }});
            return `
              <div class="stack">
                <div><strong>${{escapeHtml(project.projectId)}}</strong></div>
                <div class="badge-row">${{registryBadges.join("")}}</div>
                ${{detailBlocks.join("")}}
              </div>
            `;
          }});

      const healthBlocks = [
        commandBadge("spot", repo.spotCheck),
        commandBadge("docs", repo.docsCheck),
        commandBadge("snippets", repo.docsSnippets),
        commandBadge("check", repo.checkRun),
        commandBadge("release", repo.releaseVerify),
        commandBadge("build", repo.build),
      ];

      const releaseRunning = Boolean(repo.releaseVerify && repo.releaseVerify.status === "running");
      const checkRunning = Boolean(repo.checkRun && repo.checkRun.status === "running");
      const securityRunning = Boolean(repo.spotCheck && repo.spotCheck.status === "running");
      const docsRunning = Boolean(
        (repo.docsCheck && repo.docsCheck.status === "running")
        || (repo.docsSnippets && repo.docsSnippets.status === "running")
      );

      return `
        <tr class="${{rowClass}}">
          <td>
            <div class="repo-name">${{escapeHtml(repo.name)}}</div>
            <div class="secondary mono">${{escapeHtml(repo.path)}}</div>
            <div class="secondary">projects: ${{escapeHtml((repo.projectIds || []).join(", ") || "—")}}</div>
            <div class="secondary">last action: ${{escapeHtml(repo.lastActionMessage || "—")}}</div>
          </td>
          <td>
            <div class="stack">
              <div class="badge-row">
                <span class="badge ${{monitor.error ? "error" : (monitor.dirty ? "warn" : "ok")}}">
                  ${{monitor.error ? "repo error" : (monitor.dirty ? "dirty" : "clean")}}
                </span>
                ${{backupBlock}}
              </div>
              <div class="secondary">${{escapeHtml(counts)}}</div>
              <div class="secondary">oldest change: ${{escapeHtml(formatAge(monitor.dirtySince))}}</div>
              ${{monitor.error ? `<div class="secondary">${{escapeHtml(monitor.error)}}</div>` : ""}}
            </div>
          </td>
          <td>
            <div class="stack">
              <div>${{escapeHtml(tracking)}}</div>
              <div class="secondary">refreshed: ${{escapeHtml(formatTimestamp(monitor.trackingRefreshedAt))}}</div>
            </div>
          </td>
          <td><div class="stack">${{releaseBlocks.join("")}}</div></td>
          <td><div class="stack">${{githubBlocks.length === 0 ? '<span class="secondary">No GitHub status</span>' : githubBlocks.join("")}}</div></td>
          <td><div class="badge-row">${{healthBlocks.join("")}}</div></td>
          <td>
            <div class="actions">
              <details class="action-menu">
                <summary>Check</summary>
                <div class="action-menu-panel">
                  <button type="button" data-repo="${{escapeHtml(repo.name)}}" data-action="check" ${{checkRunning ? "disabled" : ""}}>All checks</button>
                  <button type="button" data-repo="${{escapeHtml(repo.name)}}" data-action="docs-verify" ${{docsRunning ? "disabled" : ""}}>Docs</button>
                  <button type="button" data-repo="${{escapeHtml(repo.name)}}" data-action="security-check" ${{securityRunning ? "disabled" : ""}}>Security</button>
                  <button type="button" data-repo="${{escapeHtml(repo.name)}}" data-action="release-verify" ${{releaseRunning ? "disabled" : ""}}>Release</button>
                </div>
              </details>
              <button type="button" data-repo="${{escapeHtml(repo.name)}}" data-action="difftool">Diff</button>
              <button type="button" data-repo="${{escapeHtml(repo.name)}}" data-action="commit">Commit</button>
              <button type="button" data-repo="${{escapeHtml(repo.name)}}" data-action="push">Push</button>
            </div>
          </td>
        </tr>
      `;
    }}

    function render(state) {{
      renderSummary(state);
      const repos = visibleRepos(state);
      const body = document.getElementById("repo-body");
      const empty = document.getElementById("empty-state");
      if (repos.length === 0) {{
        body.innerHTML = "";
        empty.hidden = false;
        return;
      }}
      empty.hidden = true;
      body.innerHTML = repos.map(renderRepo).join("");
    }}

    async function post(path) {{
      const response = await fetch(path, {{
        method: "POST",
        headers: {{
          "X-Dev-Dashboard-Token": dashboardToken,
        }},
      }});
      if (!response.ok) {{
        const payload = await response.text();
        throw new Error(payload || `HTTP ${{response.status}}`);
      }}
      return response.json();
    }}

    async function refreshState() {{
      if (refreshInFlight) {{
        return;
      }}
      refreshInFlight = true;
      try {{
        const response = await fetch("/api/state", {{
          cache: "no-store",
        }});
        if (!response.ok) {{
          return;
        }}
        currentState = await response.json();
        render(currentState);
      }} finally {{
        refreshInFlight = false;
      }}
    }}

    document.getElementById("search-input").addEventListener("input", () => render(currentState));
    document.getElementById("sort-select").addEventListener("change", () => render(currentState));
    document.getElementById("dirty-only").addEventListener("change", () => render(currentState));
    document.getElementById("publishable-only").addEventListener("change", () => render(currentState));
    document.getElementById("attention-only").addEventListener("change", () => render(currentState));
    document.getElementById("refresh-button").addEventListener("click", async () => {{
      try {{
        await post("/api/refresh");
      }} finally {{
        await refreshState();
      }}
    }});
    document.getElementById("repo-body").addEventListener("click", async (event) => {{
      const target = event.target;
      if (!(target instanceof HTMLButtonElement)) {{
        return;
      }}
      const detailKey = target.dataset.releaseDetailToggle;
      if (detailKey) {{
        if (expandedReleaseDetails.has(detailKey)) {{
          expandedReleaseDetails.delete(detailKey);
        }} else {{
          expandedReleaseDetails.add(detailKey);
        }}
        render(currentState);
        return;
      }}
      const repo = target.dataset.repo;
      const action = target.dataset.action;
      if (!repo || !action) {{
        return;
      }}
      target.disabled = true;
      try {{
        await post(`/api/repos/${{encodeURIComponent(repo)}}/actions/${{encodeURIComponent(action)}}`);
      }} finally {{
        window.setTimeout(refreshState, 150);
      }}
    }});

    render(currentState);
    window.setInterval(refreshState, 5000);
  </script>
</body>
</html>
"""


class DashboardHttpServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, workspace_root: Path, *, interval_seconds: int, port: int):
        self.workspace_root = workspace_root.resolve()
        self.session_token = secrets.token_urlsafe(24)
        self.coordinator = DashboardCoordinator(self.workspace_root, interval_seconds=interval_seconds)
        super().__init__(("127.0.0.1", port), DashboardRequestHandler)


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server_version = _SERVER_NAME
    sys_version = ""

    def log_message(self, format: str, *args: str) -> None:
        del format, args

    def _dashboard_server(self) -> DashboardHttpServer:
        server = self.server
        assert isinstance(server, DashboardHttpServer)
        return server

    def _host_allowed(self) -> bool:
        match self.headers.get("Host"):
            case str(host_header):
                host_value = host_header.split(":", 1)[0].strip("[]").lower()
                return host_value in _LOCAL_HOSTS
            case _:
                return False

    def _client_allowed(self) -> bool:
        return self.client_address[0] in {"127.0.0.1", "::1"}

    def _authorize_request(self) -> bool:
        if not self._client_allowed():
            self._respond_text(403, "Forbidden: dashboard only accepts local clients.\n")
            return False
        if not self._host_allowed():
            self._respond_text(403, "Forbidden: unexpected Host header.\n")
            return False
        return True

    def _authorize_mutation(self) -> bool:
        if not self._authorize_request():
            return False
        server = self._dashboard_server()
        match self.headers.get("X-Dev-Dashboard-Token"):
            case str(token) if token == server.session_token:
                return True
            case _:
                self._respond_text(403, "Forbidden: missing dashboard session token.\n")
                return False

    def _respond_json(self, status_code: int, payload: JSONObject) -> None:
        encoded = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _respond_html(self, status_code: int, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _respond_text(self, status_code: int, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _snapshot_payload(self) -> JSONObject:
        return self._dashboard_server().coordinator.snapshot().to_json()

    def _repo_exists(self, repo_name: str) -> bool:
        snapshot = self._dashboard_server().coordinator.snapshot()
        return any(repo.name == repo_name for repo in snapshot.repos)

    def _dispatch_repo_action(self, repo_name: str, action_name: str) -> bool:
        coordinator = self._dashboard_server().coordinator
        match action_name:
            case "check":
                coordinator.run_check(repo_name)
                return True
            case "docs-check":
                coordinator.run_docs_check(repo_name)
                return True
            case "docs-snippets":
                coordinator.run_docs_snippets(repo_name)
                return True
            case "docs-verify":
                coordinator.run_docs_verify(repo_name)
                return True
            case "security-check":
                coordinator.run_security_check(repo_name)
                return True
            case "release-verify":
                coordinator.run_release_verify(repo_name)
                return True
            case "difftool":
                coordinator.run_difftool(repo_name)
                return True
            case "commit":
                coordinator.run_commit(repo_name)
                return True
            case "push":
                coordinator.run_push(repo_name)
                return True
            case _:
                return False

    def do_GET(self) -> None:
        if not self._authorize_request():
            return

        path = urlparse(self.path).path
        match [part for part in path.split("/") if part]:
            case []:
                server = self._dashboard_server()
                snapshot = server.coordinator.snapshot()
                self._respond_html(200, _html_shell(snapshot, session_token=server.session_token))
            case ["api", "state"]:
                self._respond_json(200, self._snapshot_payload())
            case ["healthz"]:
                self._respond_text(200, "ok\n")
            case _:
                self._respond_text(404, "Not found.\n")

    def do_POST(self) -> None:
        if not self._authorize_mutation():
            return

        path_parts = [unquote(part) for part in urlparse(self.path).path.split("/") if part]
        match path_parts:
            case ["api", "refresh"]:
                self._dashboard_server().coordinator.request_refresh()
                self._respond_json(200, {"ok": True, "updatedAt": _now_utc().isoformat()})
            case ["api", "repos", str(repo_name), "actions", str(action_name)]:
                if not self._repo_exists(repo_name):
                    self._respond_text(404, "Unknown repo.\n")
                    return
                if not self._dispatch_repo_action(repo_name, action_name):
                    self._respond_text(404, "Unknown action.\n")
                    return
                self._respond_json(
                    202,
                    {
                        "ok": True,
                        "repo": repo_name,
                        "action": action_name,
                        "queuedAt": _now_utc().isoformat(),
                    },
                )
            case _:
                self._respond_text(404, "Not found.\n")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m dev.dashboard_server")
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--port", type=int, default=0)
    return parser.parse_args(argv)


def _install_signal_handlers(server: DashboardHttpServer) -> None:
    def _shutdown_handler(_signum: int, _frame: FrameType | None) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    workspace_root = Path(args.workspace_root).resolve()
    paths = service_paths_for_workspace(workspace_root)
    server = DashboardHttpServer(workspace_root, interval_seconds=args.interval_seconds, port=args.port)
    _install_signal_handlers(server)
    server.coordinator.start()
    write_dashboard_pid(
        paths,
        DashboardPid(
            pid=os.getpid(),
            workspace_root=workspace_root,
            started_at=_now_utc(),
            interval_seconds=args.interval_seconds,
            port=server.server_port,
        ),
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        remove_dashboard_pid(paths)
        server.coordinator.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

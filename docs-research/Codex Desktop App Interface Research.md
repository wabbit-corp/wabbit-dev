# Codex Desktop App Interface Research

## Scope

This note captures what can be learned locally from the installed Codex desktop app on this machine, with emphasis on whether it exposes a usable interface for:

- listing conversations/threads
- creating new conversations
- resuming/forking/archiving conversations
- driving turns programmatically

Tested against:

- Codex Desktop `0.119.0-alpha.28`
- macOS arm64
- app bundle at `/Applications/Codex.app`

## Short Conclusion

Yes: the shipped Codex desktop bundle contains a real app-server with an explicit JSON-RPC protocol for threads/conversations. It is not just UI strings.

Confirmed locally:

- the app registers a `codex://` URL scheme
- the bundle ships a `codex app-server` command
- that app-server can generate TypeScript bindings and JSON Schema for its protocol
- that protocol includes `thread/start`, `thread/list`, `thread/read`, `thread/resume`, `thread/fork`, `thread/archive`, `thread/unarchive`, `thread/name/set`, `turn/start`, `turn/steer`, and `turn/interrupt`
- a locally started websocket app-server accepts external JSON-RPC requests
- `thread/list` returns real existing Codex sessions
- `thread/start` can create a new ephemeral thread and returns its thread id

What is still not proven:

- whether there is a supported way to attach an external client to the already-running Electron GUI instance
- whether `codex://...` supports stable deep links for "open thread" or "create new thread"
- whether any of this is considered stable/public enough for long-term automation

So the practical conclusion is:

- there is a real interface
- the safest way to integrate with Codex today is likely to launch your own `codex app-server` process from the shipped binary rather than trying to control the running GUI

## What Was Inspected

### App bundle

- `/Applications/Codex.app/Contents/MacOS/Codex`
- `/Applications/Codex.app/Contents/Resources/codex`
- `/Applications/Codex.app/Contents/Resources/app.asar`
- `/Applications/Codex.app/Contents/Info.plist`

### User data locations

- `~/Library/Application Support/Codex`
- `~/.codex`

### Generated protocol artifacts

These were generated from the shipped binary:

```bash
/Applications/Codex.app/Contents/Resources/codex app-server generate-json-schema --out /tmp/codex-app-schema
/Applications/Codex.app/Contents/Resources/codex app-server generate-ts --out /tmp/codex-app-ts
```

## App Structure

The desktop app is an Electron application with a bundled Rust backend.

Observed processes included:

- Electron app process from `/Applications/Codex.app/Contents/MacOS/Codex`
- bundled backend from `/Applications/Codex.app/Contents/Resources/codex app-server --analytics-default-enabled`

That strongly suggests the desktop app itself talks to the bundled `app-server`, instead of all thread logic living only inside renderer code.

## Registered URL Scheme

`Info.plist` registers:

- bundle id: `com.openai.codex`
- URL scheme: `codex`

So `codex://` definitely exists.

However, I did not identify a reliable deep-link route format for:

- new conversation
- open conversation
- archive/unarchive conversation

The existence of the scheme alone is not enough to rely on it.

## Bundled App-Server Surface

The shipped binary exposes:

```text
codex app-server [OPTIONS] [COMMAND]
```

Important points from `codex app-server --help`:

- default transport is `stdio://`
- websocket transport is supported via `--listen ws://IP:PORT`
- it can generate TS bindings and JSON Schema for the protocol
- the command is explicitly marked `experimental`

This matters because it means the protocol is structured enough to self-describe.

## Confirmed Protocol Methods

From the generated TypeScript union for `ClientRequest`, the app-server supports at least these thread-related requests:

- `initialize`
- `thread/start`
- `thread/resume`
- `thread/fork`
- `thread/archive`
- `thread/unsubscribe`
- `thread/name/set`
- `thread/metadata/update`
- `thread/unarchive`
- `thread/compact/start`
- `thread/shellCommand`
- `thread/rollback`
- `thread/list`
- `thread/loaded/list`
- `thread/read`
- `turn/start`
- `turn/steer`
- `turn/interrupt`
- `review/start`

There are also thread-related notifications such as:

- `thread/started`
- `thread/status/changed`
- `thread/archived`
- `thread/unarchived`
- `thread/closed`
- `thread/name/updated`
- `thread/tokenUsage/updated`
- `turn/started`
- `turn/completed`

This is enough to treat the thread model as a real external protocol surface, not a purely internal implementation detail.

## Key Type Shapes

### `thread/start`

`ThreadStartParams` includes fields such as:

- `model`
- `modelProvider`
- `serviceTier`
- `cwd`
- `approvalPolicy`
- `approvalsReviewer`
- `sandbox`
- `config`
- `serviceName`
- `baseInstructions`
- `developerInstructions`
- `personality`
- `ephemeral`
- `experimentalRawEvents`
- `persistExtendedHistory`

The response returns:

- `thread`
- `model`
- `modelProvider`
- `serviceTier`
- `cwd`
- `approvalPolicy`
- `approvalsReviewer`
- `sandbox`
- `reasoningEffort`

### `thread/list`

`ThreadListParams` supports:

- pagination cursor
- `limit`
- `sortKey`
- `modelProviders`
- `sourceKinds`
- `archived`
- exact `cwd` filter
- `searchTerm`

`ThreadListResponse` returns:

- `data: Array<Thread>`
- `nextCursor`

### `thread/resume`

`ThreadResumeParams` supports three resume modes:

1. by `threadId`
2. by `history` (marked unstable / Codex Cloud only)
3. by rollout `path` (marked unstable)

The generated docs explicitly say: prefer `threadId` whenever possible.

### `thread/fork`

`ThreadForkParams` supports:

- `threadId`
- optional rollout `path`
- config/model/cwd overrides
- `ephemeral`
- `persistExtendedHistory`

### `thread/archive`, `thread/unarchive`, `thread/name/set`

These are simple and direct:

- `thread/archive` takes `{ threadId }`
- `thread/unarchive` takes `{ threadId }`
- `thread/name/set` takes `{ threadId, name }`

### `thread/read`

`ThreadReadParams` takes:

- `threadId`
- `includeTurns`

So a client can request a lightweight thread record or a deeper history load.

### `turn/start`

After creating or resuming a thread, user input is sent through `turn/start`.

`TurnStartParams` includes:

- `threadId`
- `input: Array<UserInput>`
- optional overrides for cwd, approval policy, sandbox, model, effort, summary, personality
- optional `outputSchema`
- optional `collaborationMode`

`UserInput` supports at least:

- text
- remote image
- local image
- skill
- mention

So conversation creation and actual prompting are separate operations:

1. `thread/start`
2. `turn/start`

## Live Websocket Probe

I started a local websocket app-server from the shipped binary:

```bash
/Applications/Codex.app/Contents/Resources/codex app-server --listen ws://127.0.0.1:8765
```

Observed startup output:

- websocket listener on `ws://127.0.0.1:8765`
- `readyz` at `http://127.0.0.1:8765/readyz`
- `healthz` at `http://127.0.0.1:8765/healthz`
- note that it binds localhost only

I then connected using Node's built-in `WebSocket` and sent JSON-RPC requests.

### Minimal initialize request

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "clientInfo": {
      "name": "probe",
      "version": "0.0.0"
    },
    "capabilities": null
  }
}
```

It returned a real result containing:

- `userAgent`
- `codexHome`
- `platformFamily`
- `platformOs`

### `thread/list` probe

I then sent:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "thread/list",
  "params": {
    "limit": 3,
    "archived": false
  }
}
```

This returned real sessions including:

- thread ids
- preview text
- `ephemeral`
- `modelProvider`
- `createdAt`
- `updatedAt`
- `status`
- rollout `path`
- `cwd`
- `cliVersion`
- `source`
- optional `gitInfo`
- optional `name`

So the server can enumerate actual Codex conversations.

### `thread/start` probe

I then sent:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "thread/start",
  "params": {
    "cwd": "/Users/wabbit/ws/datatron",
    "ephemeral": true,
    "experimentalRawEvents": false,
    "persistExtendedHistory": false
  }
}
```

That returned a new thread with:

- a new `thread.id`
- `ephemeral: true`
- `status: { "type": "idle" }`
- `cwd`
- `model: "gpt-5.4"`
- `approvalPolicy: "never"`
- `approvalsReviewer: "user"`
- `sandbox: { "type": "dangerFullAccess" }`
- `reasoningEffort: "xhigh"`

This is the strongest confirmation that external thread creation works.

## What This Means in Practice

### Things you can likely do today

By launching your own local `codex app-server`, you can likely:

- list recent threads
- create new threads
- create ephemeral threads
- resume threads by id
- fork threads
- archive and unarchive threads
- rename threads
- read thread metadata and history
- start turns by sending text input
- interrupt or steer active turns

### Things that remain uncertain

I did not prove any of the following:

- opening a new tab/window/conversation in the already-running GUI
- deep-linking the GUI to a specific thread via `codex://`
- whether the running Electron instance exposes a stable IPC surface intended for third-party automation
- whether thread ids created in an externally started server are surfaced live inside the currently open desktop app

Those are different questions from "does Codex have a conversation API at all", and they remain open.

## Likely Storage Model

Evidence from `thread/list` suggests thread rollouts are stored under:

- `~/.codex/sessions/YYYY/MM/DD/rollout-...jsonl`

The returned thread records included rollout paths in that shape.

Other observed user data locations:

- desktop app state under `~/Library/Application Support/Codex`
- automations under `~/.codex/automations`

So the desktop app and CLI/app-server appear to share at least part of the same `.codex` storage model.

## Recommended Integration Strategy

If we ever want tooling to create or inspect Codex conversations, the least risky path appears to be:

1. treat the shipped `codex app-server` as the supported-ish protocol surface
2. launch a dedicated local app-server process ourselves
3. speak JSON-RPC over stdio or localhost websocket
4. use `thread/start` plus `turn/start` rather than trying to click-drive the GUI
5. treat `codex://` deep links and renderer internals as optional future work, not the foundation

Reason:

- this path is observable and repeatable
- the protocol is self-describing
- the binary explicitly ships schema generation tools
- the websocket transport works now

## A Minimal External Client Flow

### Start a server

```bash
/Applications/Codex.app/Contents/Resources/codex app-server --listen ws://127.0.0.1:8765
```

### Initialize

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "clientInfo": { "name": "my-client", "version": "0.1.0" },
    "capabilities": null
  }
}
```

### Create a thread

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "thread/start",
  "params": {
    "cwd": "/absolute/project/path",
    "ephemeral": false,
    "experimentalRawEvents": false,
    "persistExtendedHistory": true
  }
}
```

### Send the first prompt

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "turn/start",
  "params": {
    "threadId": "THREAD_ID_FROM_STEP_2",
    "input": [
      {
        "type": "text",
        "text": "Analyze this repo and propose a plan.",
        "text_elements": []
      }
    ]
  }
}
```

### Read/list later

- use `thread/list` for discovery
- use `thread/read` for details
- use `thread/resume` for rehydration

## Caveats

- `app-server` is explicitly marked experimental
- several params are marked unstable in generated types
- we only tested localhost websocket, not a fully managed production integration
- we did not test auth modes for non-loopback listeners
- we did not validate GUI deep links
- we did not validate whether the desktop app automatically reflects threads created by a separate server process in real time

## Bottom Line

The answer to "does Codex have any interface for creating and manipulating conversations?" is yes.

The strongest, locally verified facts are:

- a real `app-server` ships with the desktop app
- it exposes explicit thread and turn JSON-RPC methods
- external clients can call those methods over websocket
- new conversations can be created programmatically via `thread/start`

The remaining unknown is not whether an interface exists, but which interface OpenAI intends third parties to rely on long term:

- external `app-server` protocol
- GUI deep links
- renderer IPC
- something else not yet documented publicly

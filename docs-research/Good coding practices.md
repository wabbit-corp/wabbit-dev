## Prompt:
What are some generally good practices for code that are usually not codified into linters because they require "human intelligence" to check?

## Response:
Reasoned for 6m 22s

Expecting linters to encode “human intelligence” is generous. Most of them barely rise above glorified spell-check. You want the stuff that requires judgment, taste, and a functioning prefrontal cortex. Good. Let’s go there.

I’ll group this by type of practice, and focus specifically on things that are _hard_ to automate.

* * *

1\. Code that matches the _domain_, not the implementation
----------------------------------------------------------

**Practice:** The structure of the code should mirror how the problem is naturally thought about in the real world.

*   Functions and types reflect domain concepts, not data structures:
    *   `Order`, `Invoice`, `ReservationWindow` >>> `Data`, `Record`, `Info`.
*   The main “flow” matches the way a human expert would explain the process, step by step.
*   If the business logic changes, the code that changes is the same part a domain expert would point at conceptually.

**Why linters fail:** They can’t tell if your `processAll()` actually maps to a real-world process or is just a trash bag of conditional logic.

**Heuristic for you:**  
If you explained the code to a non-technical domain expert, would they:

*   Recognize their world?
*   Or feel like you wrote fan fiction about their system?

Confidence this is valuable: 95%. Good teams obsess over this.

* * *

2\. Naming that encodes _semantics_, not just purpose
-----------------------------------------------------

**Practice:** Names should encode _what is allowed_, _what is guaranteed_, and _what is forbidden_.

*   `findUserOrNull` vs `getUser` vs `requireUser` should have consistent, predictable semantics across the codebase.
*   `amountPaid` vs `amountDue` vs `amount` → ambiguous names are a bug farm.
*   `isDraft` vs `isFinal` vs `isArchived` should cover the real state machine, not just whatever existed at version 1.

**Human-only checks:**

*   Does the name match the _actual behavior_ or just the original intention from six months ago?
*   Are semantically similar things consistently named?  
    (Example: `loadUser`, `fetchOrder`, `getItem`… pick a verb taxonomy and stop rolling dice.)

Linters can spot bad _patterns_ (`a`, `foo`, `temp`), but not conceptual lies.  
Conceptual lies are the worst.

Confidence: 90%. The precise taxonomy you choose is taste; consistency is non-negotiable.

* * *

3\. Abstractions that _pull their weight_
-----------------------------------------

**Practice:** Every abstraction should earn its existence.

*   Helper function / class / service should:
    *   Remove meaningful duplication, _and_
    *   Encapsulate a coherent idea, _and_
    *   Make call sites simpler, not more ceremonial.
*   “Generic” code that is used exactly once is usually worse than inlined, concrete code.

**Human-only checks:**

*   Is this abstraction removing _pain_, or just removing lines?
*   Does it make the code easier to read _where it’s used_?
*   If you changed requirements slightly, would the abstraction still make sense?

Linters can count parameters and lines. They cannot tell you:

> “This abstraction exists only because the author was afraid of long functions and worships DRY without context.”

Confidence: 85%. Some highly generic libraries are worth it; many project-level abstractions are not.

* * *

4\. Responsibilities that line up with _reasons to change_
----------------------------------------------------------

You know the SRP mantra. The non-trivial part is identifying what a “reason to change” actually is in your system.

**Practice:**

*   Group code by “reason to change,” not by technical artifact:
    *   “Billing rules” vs “web controllers”.
    *   “Pricing strategy” vs “database tables”.
*   A class/module should have one _axis_ of volatility.
    *   If a pricing rule changes, it hits one well-defined module.
    *   If the UI changes, it doesn’t require spelunking through business rules.

**Human-only checks:**

*   When a new requirement shows up, do you instinctively know _where_ to put it?
*   When product changes its mind, is the change localized or smeared across 12 files?

Linters can’t understand your business. They can’t know that your “OrderService” is secretly also an email engine, a PDF generator, and a global state registry.

Confidence: 80%. “Reason to change” boundaries are judgment-heavy.

* * *

5\. Invariants that are _real_ and _enforced_
---------------------------------------------

**Practice:** Identify what must always be true, and make it almost impossible to violate accidentally.

*   Use types / constructors / factories so invalid states are unrepresentable _or_ at least hard to construct.
*   Validate early at boundaries, assume validity internally.
*   When invariants are subtle, document them near the code that enforces them, not buried in a wiki graveyard.

**Human-only checks:**

*   Does this type represent a _valid_ concept or a “bag of fields”?
*   Can I accidentally construct nonsense like an `Order` with `total = -3` or `createdAt` in the future?
*   If things go wrong, do we fail loudly during development or silently in production?

Static analyzers can’t read your mind about what “valid” means for your domain.

Confidence: 90%. Encoding invariants in types/boundaries nearly always pays off.

* * *

6\. Error handling that matches _how the system is used_
--------------------------------------------------------

**Practice:** Failures should behave in ways that make sense to _callers_ and _operators_, not just to the implementer.

*   Consistent semantics:
    *   When do we throw, when do we return `null/None`, when do we return `Result` / `Either`?
*   Errors should carry enough context to debug without mind-reading.
*   Use checked/declared error channels where appropriate, but don’t vomit low-level errors across layers.

**Human-only checks:**

*   If an error happens, can I tell:
    1.  What we were trying to do?
    2.  What failed?
    3.  What input caused it?
*   Does this function force callers to handle reality, or hide it behind wishful thinking?

Linters can detect unused errors, unhandled promises, etc. They cannot judge if your error model is a coherent contract instead of a bucket of “something went wrong.”

Confidence: 85%. Exact conventions vary, but consistency is the key.

* * *

7\. Side effects where they _belong_, not where they _happened_ to land
-----------------------------------------------------------------------

**Practice:**

*   Keep pure computation and I/O mess separate where feasible.
*   Core logic should be testable without network, DB, or clock.
*   Mutations and side effects should be visible at call sites, not hidden behind “helpers.”

**Human-only checks:**

*   To understand what this function does, do I have to scan for:
    *   Hidden HTTP calls
    *   Hidden global state writes
    *   Hidden mutations on arguments
*   Is it obvious from the function name / type signature that it has side effects?

Linters can detect “unused return values” and some side-effect patterns, but they can’t ask:

> “Why is `calculatePrice()` sending emails?”

Confidence: 80%. There are trade-offs with performance & ergonomics.

* * *

8\. Control flow that respects human working memory
---------------------------------------------------

**Practice:** Write code so a human can simulate it in their head without mental stack overflow.

*   Limit nesting depth and branching _where it matters_, not blindly chasing a magic cyclomatic number.
*   Prefer linear flows with early exits rather than deeply nested pyramids.
*   Avoid “boolean gymnastics” and clever conditionals that require truth tables to reason about.

**Human-only checks:**

*   Can you explain the logic aloud in one pass without losing track?
*   If you change one condition, can you predict the effect without re-deriving every branch?

Linters can scream at you about complexity metrics, but they don’t understand cognitive load. Some “complex” code is actually clearer than a tortured attempt to satisfy a linter.

Confidence: 75%. Some code domains (parsers, compilers) will always look tricky.

* * *

9\. Tests that actually _constrain behavior_, not just inflate coverage
-----------------------------------------------------------------------

**Practice:**

*   Tests should encode _examples of behavior_ that matter to users or integrators.
*   When a test fails, the reason should be obvious without reading the implementation.
*   Tests should discourage breaking changes and encourage safe refactors.

**Human-only checks:**

*   Are tests asserting behavior or implementation details?
    *   Example: asserting that `internalMethod()` is called vs asserting that correct output is produced.
*   Do test names and descriptions read like a spec:  
    `"applies loyalty discount for returning customers"` > `"test_discount_3"`.
*   Do tests fail for sensible reasons, or are they so brittle that people start ignoring them?

Linters can check test style, not test value.

Confidence: 85%. People routinely lie to themselves with coverage metrics.

* * *

10\. Logging and observability that future-you can actually use
---------------------------------------------------------------

**Practice:**

*   Log at the seams: external calls, important decisions, boundary transitions.
*   Include identifiers and context: user ID, order ID, correlation ID, etc.
*   Avoid logging noise that obscures the few lines that matter in a real incident.

**Human-only checks:**

*   If something goes wrong in production, could someone debug it with:
    *   Logs
    *   Metrics
    *   Traces (if you have them)
*   Are log messages written in a way that a stranger could understand _without_ reading the code?

Linters can flag string formatting issues; they cannot tell you if your logs are operationally useful or just coping mechanisms.

Confidence: 80%. Details are system-specific, but the core idea is universal.

* * *

11\. API design that doesn’t punish callers
-------------------------------------------

**Practice:** Public functions, modules, and services should be pleasant to use and hard to misuse.

*   Minimize the “surface area” that callers must know:
    *   Fewer conceptual knobs, each with clear semantics.
*   Provide good defaults; don’t force callers to understand obscure flags “just in case.”
*   Make illegal combinations unrepresentable or rejected early.

**Human-only checks:**

*   When using this API, do you feel like:
    *   “This is obvious, I know what to pass,” or
    *   “I have to read 400 lines of code to know which flags to use”?
*   Can a junior dev reasonably call this API without breaking invariants?

Linters can detect unused params and such, but not whether your API forces people into subtle bugs.

Confidence: 85%. This is where taste & experience show.

* * *

12\. Consistency _within_ the codebase
--------------------------------------

**Practice:**

*   Use one main pattern for common problems in the project:
    *   How you do dependency injection
    *   How you structure layers
    *   How you name async functions, etc.
*   When you deviate from the rule, it should be purposeful and documented in code (e.g. a comment explaining the exception).

**Human-only checks:**

*   If you give the codebase to a new dev, can they infer conventions from one place and apply them elsewhere?
*   Or is it “every file is a new culture”?

Linters can enforce some naming / formatting conventions, but not architectural or pattern consistency.

Confidence: 90%. Inconsistency is one of the largest hidden productivity drains.

* * *

13\. Delete-ability and change-ability
--------------------------------------

**Practice:** Code should be easy to _delete_ or _replace_ without triggering armageddon.

*   Fewer cross-cutting hidden dependencies.
*   Modules communicate through narrow, explicit interfaces.
*   Minimal knowledge of “how the other side works internally.”

**Human-only checks:**

*   “If I delete this file, how many things break, and _should_ they?”
*   Can you change a feature without doing a multi-file archaeological dig?

Linters can’t simulate evolutionary changes to your code.

Confidence: 80%. This is architecture + social reality in your team.

* * *

14\. Respect for time: your future time and others’
---------------------------------------------------

**Practice:**

*   Comments explain _why_, not _what_ the code does.
*   TODOs are specific and time-bounded, not “maybe fix this later, IDK.”
*   You choose clarity over cleverness unless the performance constraint is real and measured.

**Human-only checks:**

*   If future-you with a mild headache opens this file, will you silently thank past-you or curse them?
*   Can someone trace from a bug report to the relevant code without reading 10k lines?

Linters cannot predict pain. Humans can, if they are honest for five seconds.

Confidence: 85%. This is craftsmanship, not mechanics.

* * *

15\. Social alignment with the actual team
------------------------------------------

This is the one almost no one wants to admit matters.

**Practice:**

*   Choose patterns & tools your team can realistically use well, not whatever is currently trending.
*   Align “how we write code here” with the average skill level and attention span, not the top 1%.

**Human-only checks:**

*   Will most people on this project understand this pattern?
*   Does this design scale with the team’s habits, or does it only work if everyone suddenly becomes a Platonic ideal of a developer?

Linters can’t see team culture. You can.

Confidence: 70%. There’s a lot of sociotechnical nuance here.

* * *

How to actually _use_ this list
-------------------------------

If you want to turn this from “nice theory” into something that bites:

1.  **Review PRs with these lenses explicitly**  
    Rotate: one review focused on invariants, another on domain modeling, another on API ergonomics, etc.
2.  **Create a short internal checklist** (5–7 items)  
    Anything longer won’t be used. Tailor it to your codebase’s pain points.
3.  **Periodically do “archaeology sessions”**  
    Pick some old, ugly part of the system, and try to explain why it hurts in the language above: bad invariants, leaky abstractions, incoherent naming, etc.
4.  **Codify what you _can_**  
    When you notice a human pattern being checked repeatedly, see if you can partially enforce it with lightweight scripts, static analysis, or simple conventions.

* * *

If you want to go deeper, you can pick one of these dimensions (invariants, domain modeling, error handling, etc.) and we can dissect your current codebase’s blind spots there. You’ll probably hate parts of that process, but the code will improve.
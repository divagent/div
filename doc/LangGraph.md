Why This Is the Right Problem to Start With

The core issue you’ve identified is that analyze_dividend for a Prediction row is doing a fixed fan-out — it calls a predetermined set of signals, runs one LLM read, and exits. That’s a pipeline, not an agent. It has no concept of “did I find enough?” or “where should I look next?”

LangGraph’s value is precisely in problems where the next step depends on what you found in the last step. A fixed pipeline can’t express “if I found a declared amount, stop; if I found conflicting signals, try one more source; if I found nothing, mark as unresolved.”

The Mental Model You Need First

Before writing any code, understand the difference between these three patterns:

Chain (what you have now): A → B → C → D, always. No conditionals.

Agent loop (LangChain AgentExecutor style): LLM decides the next tool, loops until done. Flexible but unpredictable — hard to reason about when it stops, easy to loop forever.

Graph with conditional edges (LangGraph): You define the nodes (steps) and the routing logic explicitly. The LLM can influence routing, but you define what the valid transitions are. This gives you the adaptivity of an agent with the predictability of a pipeline.

Your resolver needs the third pattern because:

The stop condition is deterministic (“verified declaration found”)
The search strategy is adaptive (“try next source if current source is inconclusive”)
The failure path is explicit (“exhausted sources → keep as Prediction”)
How to Think About the Graph Structure

Don’t think about code yet. Think about states and decisions:

What is the state? At any point in the resolution, you know: the ticker, the target ex-date range, sources already tried, candidate amounts/dates found so far, and whether any candidate has been verified.

What are the decisions? After each source lookup: “Is this a verified declaration?” → yes → stop and promote. No → “Have I tried all structured sources?” → no → try next. Yes → “Is there a candidate worth verifying?” → try search/fetch. “Have I exhausted everything?” → mark unresolved.

Draw this as a flowchart before thinking about nodes. The flowchart is the graph.

Why Keep age_pattern.py Separate

This is an important architectural principle: don’t put deterministic computation inside a graph node if it doesn’t need to branch. The pattern calculation always runs and always produces the same output given the same input. Making it a graph node adds overhead with no benefit. The graph’s job is resolution of uncertainty, not mechanical extrapolation.

The graph starts after the pattern has produced its prediction. The graph’s job is to answer: “has this prediction been superseded by a real declaration?”

The Learning Progression This Project Gives You

Rebuilding just this one resolver teaches you:

State schema — TypedDict or Pydantic state that flows through nodes
Conditional edges — add_conditional_edges with a routing function
Node design — each node does one thing and returns a state update, not a side effect
Stop conditions — END node and how to reach it from multiple paths
LangSmith tracing — you’ll see each node’s input/output, which immediately shows you why the old code was stopping too early
Bounded iteration — how to prevent infinite loops with a attempts counter in state

This is the right scope for a first LangGraph project: not trivial, not overwhelming, and directly fixes a real bug.

One Thing to Validate Before Starting

The 10% → 99% claim deserves a quick audit. Before designing the graph, manually check 10 Prediction rows that are within the 30-day window and see why the current code failed to resolve them.

Is it:

(a) the declared amount was available in the structured source but the lookup didn’t find it (a signal/query bug)?
(b) the declared amount was available but the verification step wrongly rejected it?
(c) the LLM correctly found it but reconcile_declared had a bug that prevented the write?

The graph design changes depending on the answer. If it’s mostly (a), the graph needs better source coverage. If it’s (b) or (c), the graph needs a better verification/write step. Knowing this before designing saves a lot of rework.

Does this framing make sense as a starting point?
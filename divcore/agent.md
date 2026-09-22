## What the “agent” must decide

Before doing vector search, the system must decide:

> **Does this question REQUIRE dividend data search, or is it a general question?**

Examples:

* “What is a dividend?” → ❌ no search
* “Which dividends are next week?” → ✅ search
* “Explain dividend yield” → ❌ no search
* “What dividend does TD Bank pay next week?” → ✅ search

This is **exactly** what interviewers mean by *agentic framework* .

## 2.1 Agent decision contract

### Input

User question

### Output

<pre class="overflow-visible! px-0!" data-start="953" data-end="1036"><div class="contain-inline-size rounded-2xl corner-superellipse/1.1 relative bg-token-sidebar-surface-primary"><div class="sticky top-[calc(var(--sticky-padding-top)+9*var(--spacing))]"><div class="absolute end-0 bottom-0 flex h-9 items-center pe-2"><div class="bg-token-bg-elevated-secondary text-token-text-secondary flex items-center gap-4 rounded-sm px-2 font-sans text-xs"></div></div></div><div class="overflow-y-auto p-4" dir="ltr"><code class="whitespace-pre! language-json"><span><span><span class="hljs-punctuation">{</span></span><span>
  </span><span><span class="hljs-attr">"action"</span></span><span><span class="hljs-punctuation">:</span></span><span> </span><span><span class="hljs-string">"search"</span></span><span> | </span><span><span class="hljs-string">"no_search"</span></span><span><span class="hljs-punctuation">,</span></span><span>
  </span><span><span class="hljs-attr">"reason"</span></span><span><span class="hljs-punctuation">:</span></span><span> </span><span><span class="hljs-string">"short explanation"</span></span><span>
</span><span><span class="hljs-punctuation">}</span></span><span>
</span></span></code></div></div></pre>

# STEP 3 — Observability & tracing (enterprise-grade)

**Goal**

You must be able to answer, in prod:

> “Why did this answer happen, how long did it take, and where did it fail?”

We’ll add:

* request correlation
* step-level timing
* agent + RAG visibility
* zero behavior change

No refactors. No guessing.

## 3.1 What we will instrument (explicit)

For **every request** :

* request_id
* agent decision
* search latency
* LLM latency
* total latency
* error (if any)

We’ll log **JSON** , not strings.

{
"question": "Should I buy TD Bank stock next week?",
"top_k": 5
}



STEP 4.1 — Agent Decision (REAL agent begins here)


We implement human-in-the-loop as a blocking agent action. The agent emits an ask_human action, the executor returns control to the user, and the user’s reply is injected as an observation in the next turn, preserving the ReAct loop
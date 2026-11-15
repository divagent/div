Predict: predict_and_publish runs a deterministic pattern calculation in age_pattern.py, this part is ok. following Yahoo API, the result is certain. 

then a signals lookup and one LLM research call in age_predictor.py, then publishes to Google Calendar.The pattern is a mechanical extrapolation of history—not a deterministic prediction of what the company will do.
 -- this also ok. it's just a prediction, could be wrong, the major task is understand the pattern and populate to calender.



Click a calendar row: analyze_dividend branches on status. Declared rows get a breaking-news/rumor pass; Prediction rows get signal gathering, an LLM read, and possible reconciliation. So “analyze this row” does not always mean the same analysis. -- 90% failed here. the key thing is that Agent should try many different resources, and understand where to stop. The thumb of the rule is: if find declared or if can confirm it's a fact, stop... but the logic is mixed up here,and only 10% of can update Prediction to Declared,but the truth should be 99% (it's 30 days dividend time-period), almsot 100% has confirmed the amount and date.


You are hired to do and answer what to do. no worry unrelevant like below
The Strands/MCP agent is not the engine for those two main endpoints. The live predict/analyze services are in divcore; the Strands agent in divagent/app/agent/analyze.py is used for the separate MCP-backed path, including the trace workflow. This is a split architecture, not one end-to-end agent framework.





Your note changes my recommendation: yes, use a graph for the Prediction-row click path. The missing piece is not generic structure; it’s an adaptive resolver that keeps searching when evidence is missing, knows what counts as confirmation, and stops once it has enough. Today, analyze_dividend calls a fixed signal-gathering fan-out and then one LLM read. That is not the “try resources, then stop on verified fact” workflow you want.

What I recommend building
Create a dedicated declared-dividend resolution graph and make it the first step when a user clicks a Prediction row:


The graph should track the target ex-date, sources tried, candidate amounts/dates, evidence URLs or excerpts, and why it stopped. A verified source should end resolution immediately; a separate risk-analysis step can run afterward if desired.

Use structured feeds first, then relevant company announcements and regulator filings, then search/fetch sources for gaps or disagreements. Search results and LLM-extracted values should be candidates, not facts: only promote the calendar row when the candidate is verified against the ticker and the target payment. If the graph exhausts its sources or finds conflicting evidence, keep the row as Prediction and show what remains unverified.

Share this resolver between predict and click workflows so there is one definition of “declared.” The current lookup in age_signals.py can return a latest historical payment when it doesn’t find a close target-date match; that is exactly the kind of result the new graph must not mistake for the next declaration. Only a verified result should reach reconcile_declared.

Framework choice
Use LangGraph for this resolver, not a free-form LangChain agent loop. Its value here is explicit conditional routing, bounded retries/searches, and a clear stop condition—not better dividend facts on its own. Keep the existing deterministic pattern calculation in age_pattern.py as-is; this change is about resolving declarations on click, not replacing prediction wholesale.
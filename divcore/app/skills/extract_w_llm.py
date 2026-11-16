EXTRACT_PROMPT = """You are a dividend data extractor.
Given raw HTML from dividendhistory.org, extract the most recent 
declared dividend for the ticker.

Return ONLY valid JSON, no markdown, no explanation:
{
  "amount": 1.63,
  "ex_date": "2024-11-20",
  "confidence": "declared"
}

If you cannot find a declared amount, return:
{
  "amount": null,
  "ex_date": null, 
  "confidence": "not_found"
}"""

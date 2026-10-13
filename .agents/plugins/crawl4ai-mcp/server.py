from mcp.server.fastmcp import FastMCP
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
import asyncio

mcp = FastMCP("Crawl4AI")

@mcp.tool()
async def crawl_url(url: str, js_code: str = None, wait_for: str = None) -> str:
    """
    Crawls a given URL and returns the Markdown content.
    Optionally executes JS code (js_code) and waits for a specific CSS selector (wait_for).
    """
    try:
        async with AsyncWebCrawler() as crawler:
            config = CrawlerRunConfig()
            if js_code:
                config.js_code = js_code
            if wait_for:
                config.wait_for = wait_for
                
            result = await crawler.arun(url=url, config=config)
            if result.success:
                return result.markdown
            else:
                return f"Failed to crawl: {result.error_message}"
    except Exception as e:
        return f"Error running Crawl4AI: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport="stdio")

from playwright.async_api import async_playwright
import asyncio
import re

async def get_soundcloud_stats(track_url: str):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(track_url)
            
            # Wait for main track container
            main_track_selector = '.l-about-main'
            await page.wait_for_selector(main_track_selector, timeout=5000)
            main_track_container = await page.query_selector(main_track_selector)
            
            if not main_track_container:
                print(f"Main track container not found for {track_url}")
                return None
            
            # Get plays
            plays_element = await main_track_container.query_selector('.sc-ministats-plays')
            plays_text = await plays_element.text_content() if plays_element else None
            plays = int(re.search(r'\d+', plays_text)[0]) if plays_text else 0
            
            # Get likes
            likes_element = await main_track_container.query_selector('.sc-ministats-likes span[aria-hidden="true"]')
            likes_text = await likes_element.text_content() if likes_element else None
            likes = int(likes_text) if likes_text else 0
            
            # Get reposts
            reposts_element = await main_track_container.query_selector('.sc-ministats-reposts span[aria-hidden="true"]')
            reposts_text = await reposts_element.text_content() if reposts_element else None
            reposts = int(reposts_text) if reposts_text else 0
            
            # Get days since release
            time_element = await page.query_selector('time.relativeTime span[aria-hidden="true"]')
            days_released_text = await time_element.text_content() if time_element else None
            days_released = int(re.search(r'\d+', days_released_text)[0]) if days_released_text else None
            
            # Calculate per-day metrics
            plays_per_day = plays / days_released if days_released else None
            likes_per_day = likes / days_released if days_released else None
            reposts_per_day = reposts / days_released if days_released else None
            
            await browser.close()
            
            return {
                'plays': plays,
                'likes': likes,
                'reposts': reposts,
                'days_released': days_released,
                'plays_per_day': plays_per_day,
                'likes_per_day': likes_per_day,
                'reposts_per_day': reposts_per_day,
                'url': track_url
            }
            
    except Exception as error:
        print(f"Error fetching stats for {track_url}:", error)
        return None

tracks = [
    "https://soundcloud.com/dolla-llama/hallucinations",
    "https://soundcloud.com/dolla-llama/cabal",
]

async def get_all_track_stats():
    stats = await asyncio.gather(*[get_soundcloud_stats(track) for track in tracks])
    print("All track stats:", stats)
    return stats

async def test():
    try:
        await get_all_track_stats()
    except Exception as error:
        print("Error getting stats:", error)

# Run the async function
if __name__ == "__main__":
    asyncio.run(test())
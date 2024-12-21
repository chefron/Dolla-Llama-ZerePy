import { chromium } from 'playwright';

async function getSoundCloudStats(trackUrl: string) {
    try {
        const browser = await chromium.launch({ headless: true });
        const page = await browser.newPage();
        await page.goto(trackUrl);

        // Wait for the main track container to load
        const mainTrackSelector = '.l-about-main';
        await page.waitForSelector(mainTrackSelector, { timeout: 5000 });

        const mainTrackContainer = await page.$(mainTrackSelector);

        if (!mainTrackContainer) {
            console.error(`Main track container not found for ${trackUrl}`);
            return null;
        }

        // Get plays (scoped to main track)
        const playsElement = await mainTrackContainer.$('.sc-ministats-plays');
        const playsText = playsElement ? await playsElement.textContent() : null;
        const plays = playsText ? parseInt(playsText.match(/\d+/)?.[0] || '0') : 0;

        // Get likes (scoped to main track)
        const likesElement = await mainTrackContainer.$('.sc-ministats-likes span[aria-hidden="true"]');
        const likesText = likesElement ? await likesElement.textContent() : null;
        const likes = likesText ? parseInt(likesText || '0') : 0;

        // Get reposts (scoped to main track)
        const repostsElement = await mainTrackContainer.$('.sc-ministats-reposts span[aria-hidden="true"]');
        const repostsText = repostsElement ? await repostsElement.textContent() : null;
        const reposts = repostsText ? parseInt(repostsText || '0') : 0;

        // Get days since release (not scoped to main track)
        const timeElement = await page.$('time.relativeTime span[aria-hidden="true"]');
        const daysReleasedText = timeElement ? await timeElement.textContent() : null;
        const daysReleased = daysReleasedText
            ? parseInt(daysReleasedText.match(/\d+/)?.[0] || '0')
            : null;

        // Calculate per-day metrics
        const playsPerDay = daysReleased ? plays / daysReleased : null;
        const likesPerDay = daysReleased ? likes / daysReleased : null;
        const repostsPerDay = daysReleased ? reposts / daysReleased : null;

        await browser.close();

        return {
            plays,
            likes,
            reposts,
            daysReleased,
            playsPerDay,
            likesPerDay,
            repostsPerDay,
            url: trackUrl,
        };
    } catch (error) {
        console.error(`Error fetching stats for ${trackUrl}:`, error);
        return null;
    }
}

const tracks = [
    "https://soundcloud.com/dolla-llama/hallucinations",
    "https://soundcloud.com/dolla-llama/cabal",
];

async function getAllTrackStats() {
    const stats = await Promise.all(
        tracks.map((track) => getSoundCloudStats(track))
    );
    console.log("All track stats:", stats);
    return stats;
}

// Run and handle any errors
async function test() {
    try {
        await getAllTrackStats();
    } catch (error) {
        console.error("Error getting stats:", error);
    }
}

test();
import os
import time
import uuid
import hashlib
from datetime import datetime, timedelta
from supabase import create_client, Client
from apify_client import ApifyClient

# Configuration loaded securely from environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
APIFY_TOKEN = os.getenv("APIFY_TOKEN")
# Abstracted to a generic scraper task variable
COMMENTS_SCRAPER_TASK_ID = os.getenv("APIFY_COMMENTS_TASK_ID", "generic-comments-scraper")

# Client initialization
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
apify = ApifyClient(APIFY_TOKEN)


def sync_posts_with_their_comments():
    """
    Synchronizes parent posts stored in the database with their respective 
    comments fetched via external scraper APIs. Utilizes deterministic UUIDs 
    to handle upserts and prevent duplicate records.
    """
    print("\n🔄 Starting comment synchronization pipeline...")

    try:
        # Fetching posts from the last 7 days to maintain hot-data updates
        cutoff_date = (datetime.utcnow() - timedelta(days=7)).isoformat()

        posts_res = supabase.table("source_posts") \
            .select("id, post_url, status") \
            .not_.is_("post_url", "null") \
            .gte("posted_at", cutoff_date) \
            .execute()

        all_posts = posts_res.data or []

        if not all_posts:
            print("ℹ️ No active posts found for comment validation.")
            return

        urls_to_scrape = []
        posts_map = {}  # Map URL back to internal DB ID for relational storage

        for post in all_posts:
            url = post.get("post_url")
            status = (post.get("status") or "").lower()

            if "disapproved" in status:
                continue

            if url:
                urls_to_scrape.append(url)
                posts_map[url] = post["id"]

        unique_urls = list(set(urls_to_scrape))

        if not unique_urls:
            print("ℹ️ No eligible posts to verify.")
            return

        print(f"📌 Verifying {len(unique_urls)} parent posts...")
        start_urls = [{"url": url} for url in unique_urls]

        # Triggering the external scraping task
        task_client = apify.task(COMMENTS_SCRAPER_TASK_ID)
        run_info = task_client.start(task_input={"startUrls": start_urls})
        run_id = run_info.id
        print(f"🚀 External task initiated: {run_id}")

        # Polling execution status with defensive waiting
        while True:
            current_run = apify.run(run_id).get()
            status = current_run.status

            if status == 'SUCCEEDED':
                print("✅ Scraper task finished successfully.")
                break
            elif status in ['FAILED', 'ABORTED', 'TIMED-OUT']:
                print(f"❌ Scraper task failed with status: {status}")
                return

            print(f"⏳ Task state: {status}... (waiting 10s)")
            time.sleep(10)

        # Retrieving and parsing the dataset
        dataset_id = current_run.default_dataset_id
        scraped_comments = apify.dataset(dataset_id).list_items().items

        saved_count = 0

        for item in scraped_comments:
            if item.get("error") == "no_items":
                continue

            input_url = item.get("inputUrl")
            comment_id = item.get("id")
            author_name = item.get("profileName") or "Unknown"
            comment_text = item.get("text")

            if not comment_text or not comment_id or not input_url:
                continue

            db_post_id = posts_map.get(input_url)
            if not db_post_id:
                continue

            try:
                # Deterministic UUID generation based on comment signature to allow safe upserts
                hash_object = hashlib.md5(comment_id.encode())
                comment_uuid = str(uuid.UUID(hash_object.hexdigest()[:32]))

                db_payload = {
                    "id": comment_uuid,
                    "author_name": author_name,
                    "comment_text": comment_text.strip(),
                    "scraped_at": datetime.utcnow().isoformat(),
                    "post_id": db_post_id
                }

                # Executing database upsert
                supabase.table("source_comments").upsert(db_payload, on_conflict="id").execute()
                saved_count += 1

            except Exception as e:
                print(f"⚠️ Error processing comment ID {comment_id}: {e}")

        print(f"✅ Successfully synchronized {saved_count} comments.")

    except Exception as e:
        print(f"❌ Synchronization pipeline critical failure: {e}")


if __name__ == "__main__":
    sync_posts_with_their_comments()
